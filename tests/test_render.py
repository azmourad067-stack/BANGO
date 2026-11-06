import subprocess

import pytest
from PIL import Image

from bongo.curriculum import load_curriculum
from bongo.errors import BongoError
from bongo.placeholders import generate_placeholders
from bongo.render import FrameRenderer, frame_count, render_video
from bongo.schema import parse_script
from bongo.timeline import build_timeline


@pytest.fixture
def staged(project, example, config):
    curriculum = load_curriculum(project)
    generate_placeholders(project, curriculum)
    script = parse_script(example)
    durations = [1.2] * len(script.all_lines())
    cues = {"l001": [{"start": 0.0, "end": 0.6, "shape": "D"}, {"start": 0.6, "end": 1.2, "shape": "X"}]}
    tl = build_timeline(script, curriculum.get(3), config, durations, cues)
    return project, tl


def _small(tl, w=384, h=216):
    return {**tl, "width": w, "height": h}


def test_frame_size_and_fade_from_black(staged, config):
    root, tl = staged
    r = FrameRenderer(root, _small(tl), config)
    first = r.frame(0.0)
    assert first.size == (384, 216) and first.mode == "RGB"
    assert max(first.getextrema(), key=lambda e: e[1])[1] < 10  # noir au tout début
    mid = r.frame(5.0)
    assert max(c[1] for c in mid.getextrema()) > 100


def test_mouth_moves(staged, config):
    root, tl = staged
    r = FrameRenderer(root, tl, config)
    scene = tl["scenes"][0]
    t0 = tl["lines"][0]["start"]
    open_state = r._state(scene, "bongo", "stand", t0 + 0.3)[0]
    rest_state = r._state(scene, "bongo", "stand", t0 + 0.9)[0]
    assert open_state[3] == "D" and rest_state[3] == "X"


def test_breathing(staged, config):
    root, tl = staged
    r = FrameRenderer(root, tl, config)
    art = r.chars["bongo"]
    small, _ = art.sprite("stand", "open", "neutral", "X", 0)
    big, _ = art.sprite("stand", "open", "neutral", "X", 10)
    assert big.height / small.height == pytest.approx(1.01, abs=0.003)


def test_card_on_free_side(staged, config):
    root, tl = staged
    r = FrameRenderer(root, tl, config)
    scene_center_bongo = {"characters": [{"name": "bongo", "position": "center"}]}
    scene_left_right = {"characters": [{"name": "bongo", "position": "left"}, {"name": "frog", "position": "right"}]}
    assert r._card_x(scene_center_bongo) == pytest.approx(1920 * 0.75)
    assert r._card_x(scene_left_right) == pytest.approx(1920 * 0.5)


def test_missing_drawing(staged, config):
    root, tl = staged
    (root / "assets/characters/frog/pose_1.png").unlink()
    with pytest.raises(BongoError, match="placeholders"):
        FrameRenderer(root, tl, config)


def test_render_video_in_parts(staged, config, tmp_path):
    root, tl = staged
    tl = _small(tl)
    out = render_video(root, tl, config, tmp_path / "v.mp4", workers=2, max_seconds=22, log=lambda m: None)
    frames = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
                             "-show_entries", "stream=nb_read_frames,width,pix_fmt,codec_name", "-of", "csv=p=0", str(out)],
                            capture_output=True, text=True).stdout.strip()
    codec, width, pix, n = frames.split(",")
    assert (codec, width, pix) == ("h264", "384", "yuv420p")
    assert int(n) == 22 * 24
    assert frame_count(tl) == pytest.approx(tl["duration_s"] * 24, abs=1)


def test_validate_rig(staged):
    import json

    from bongo.assets import validate_rig

    root, _ = staged
    assert validate_rig(root, "bongo") == [] and validate_rig(root, "frog") == []
    rig_path = root / "assets/characters/bongo/rig.json"
    rig = json.loads(rig_path.read_text())
    del rig["face"]["crouch"]
    rig_path.write_text(json.dumps(rig))
    Image.new("RGB", (10, 10)).save(root / "assets/characters/bongo/body/point.png")
    problems = " ".join(validate_rig(root, "bongo"))
    assert "crouch" in problems and "10x10" in problems and "transparence" in problems


def test_cli_render_still_mockup(staged, monkeypatch, capsys):
    from bongo.cli import main
    from conftest import EXAMPLE

    root, _ = staged
    monkeypatch.chdir(root)
    monkeypatch.delenv("BONGO_ROOT", raising=False)
    assert main(["render", "3", "--script-file", str(EXAMPLE), "--image", "40"]) == 0
    out = root / "episodes/ep003/image_40s.png"
    assert Image.open(out).size == (1920, 1080)
    assert "maquette muette" in capsys.readouterr().out
