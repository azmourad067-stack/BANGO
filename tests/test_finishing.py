import datetime as dt
import json

import numpy as np
import pytest

from bongo.audio_mix import (
    MIX_RATE,
    _ramp_envelope,
    child_pauses,
    decode,
    loop_to,
    master,
    mix_tracks,
    sfx_events,
    speech_rms,
)
from bongo.curriculum import load_curriculum
from bongo.metadata import build_metadata, clean_title
from bongo.placeholders import generate_placeholders
from bongo.report import publish_to_week, week_start_for, write_week_report
from bongo.schema import parse_script
from bongo.subtitles import build_srt
from bongo.thumbnail import make_thumbnail
from bongo.timeline import build_timeline
from bongo.tts import SAMPLE_RATE, write_wav


@pytest.fixture
def tl(example, config, curriculum):
    script = parse_script(example)
    return build_timeline(script, curriculum.get(3), config, [1.0] * len(script.all_lines()))


# --- Sous-titres ------------------------------------------------------------------------------


def test_srt(tl):
    srt = build_srt(tl)
    blocks = srt.strip().split("\n\n")
    assert len(blocks) == len(tl["lines"])
    assert blocks[0] == "1\n00:00:00,600 --> 00:00:01,800\nHello, little explorer!"
    # pas de chevauchement
    import re

    times = [re.findall(r"(\d\d):(\d\d):(\d\d),(\d\d\d)", b.split("\n")[1]) for b in blocks]
    secs = [[int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000 for h, m, s, ms in t] for t in times]
    assert all(a[1] <= b[0] for a, b in zip(secs, secs[1:]))


# --- Métadonnées ---------------------------------------------------------------------------------


def test_metadata(curriculum, config):
    meta = build_metadata(curriculum.get(3), "Frog and Leaf", "Frog lost his leaf.", config, "ep003.srt")
    assert meta["title"] == "Frog and Leaf — Learn English with Bongo the Gorilla"
    assert meta["publish_at_local"] == "2026-12-03T13:00:00+01:00"
    assert meta["publish_at_utc"] == "2026-12-03T12:00:00Z"
    assert meta["made_for_kids"] is True and meta["altered_or_synthetic_content"] is False
    assert meta["playlists"] == ["Bongo in the Jungle", "All episodes"]
    assert "Today's words: frog, leaf." in meta["description"] and "jump together" in meta["description"]
    assert len(meta["tags"]) <= 10 and len(set(meta["tags"])) == len(meta["tags"])
    review = build_metadata(curriculum.get(28), "Big Review", "Bongo visits all his friends.", config, "x.srt")
    assert len(review["tags"]) == 10 and "Today we review" in review["description"]


def test_clean_title():
    assert clean_title('  "Frog <and> Leaf"  ') == "Frog and Leaf"
    assert len(clean_title("x" * 200) + " — Learn English with Bongo the Gorilla") <= 100


# --- Mixage -----------------------------------------------------------------------------------------


def test_loop_and_envelope():
    track = np.ones((MIX_RATE, 2), dtype=np.float32)
    assert loop_to(track, 3 * MIX_RATE).shape == (3 * MIX_RATE, 2)
    env = _ramp_envelope(10 * MIX_RATE, [(4.0, 6.0)])
    assert env[5 * MIX_RATE] == 0 and env[int(3 * MIX_RATE)] == 1
    assert 0 < env[int(3.85 * MIX_RATE)] < 1  # rampe douce
    assert env[0] == 0  # fondu d'entrée


def test_child_pauses_and_sfx(tl):
    pauses = child_pauses(tl)
    prompt = next(l for l in tl["lines"] if l.get("prompt_word"))
    assert (prompt["end"], prompt["pause_end"]) in pauses
    names = {n for n, _ in sfx_events(tl)}
    assert names == {"card", "jump", "drum"}


def test_mix_levels_and_master(project, tl, config, tmp_path):
    generate_placeholders(project, load_curriculum(project))
    # Voix : 1 s de son, 1 s de silence, en boucle
    t = np.arange(int(tl["duration_s"] * SAMPLE_RATE)) / SAMPLE_RATE
    voice = 0.3 * np.sin(2 * np.pi * 200 * t) * ((t % 2) < 1)
    write_wav(tmp_path / "voice.wav", voice.astype(np.float32))
    mix, warnings = mix_tracks(project, tl, tmp_path / "voice.wav", -20.0, log=lambda m: None)
    assert warnings == []
    music_only = mix - decode(tmp_path / "voice.wav")[: len(mix)]
    # pendant une pause de l'enfant (hors bruitage) : silence
    prompt = next(l for l in tl["lines"] if l.get("prompt_word") and l["pause_end"] - l["end"] > 2)
    mid = int((prompt["end"] + prompt["pause_end"]) / 2 * MIX_RATE)
    assert np.abs(music_only[mid - 100 : mid + 100]).max() < 1e-3
    # ailleurs : la musique est environ 20 dB sous la voix
    level = speech_rms(music_only[int(10 * MIX_RATE) : int(20 * MIX_RATE)])
    ratio_db = 20 * np.log10(level / speech_rms(decode(tmp_path / "voice.wav")))
    assert -26 < ratio_db < -14
    # Assemblage et volume final
    import subprocess

    video = tmp_path / "v.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", f"color=c=blue:s=64x36:r=24:d={tl['duration_s']}",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video)], check=True)
    loud = master(mix, video, tmp_path / "final.mp4", -14.0, tmp_path)
    assert abs(loud["integrated_lufs"] + 14) <= 1.0 and loud["true_peak_db"] <= -1.0


def test_missing_music_is_warning(project, tl, tmp_path):
    write_wav(tmp_path / "voice.wav", np.zeros(SAMPLE_RATE, dtype=np.float32) + 0.1)
    _, warnings = mix_tracks(project, tl, tmp_path / "voice.wav", -20.0, log=lambda m: None)
    assert any("musique" in w for w in warnings) and any("bruitage" in w for w in warnings)


# --- Miniature et rapport -----------------------------------------------------------------------------


def test_thumbnail(project, tmp_path):
    from PIL import Image

    curriculum = load_curriculum(project)
    generate_placeholders(project, curriculum)
    out = make_thumbnail(project, curriculum.get(3), "Frog and Leaf", tmp_path / "t.png")
    assert Image.open(out).size == (1280, 720)
    out7 = make_thumbnail(project, curriculum.get(7), "Jungle Review", tmp_path / "t7.png")
    assert out7.is_file()


def _fake_episode(project, ep_id, status, config, curriculum):
    from bongo.pipeline import episode_dir

    folder = episode_dir(project, ep_id)
    folder.mkdir(parents=True)
    (folder / "qa.json").write_text(json.dumps({"episode_id": ep_id, "status": status, "duration_s": 230,
        "issues": [{"level": "warning", "code": "x", "message": "petit souci <b>", "where": None}] if status != "ok" else [],
        "steps": {"mix": {"integrated_lufs": -14.0}}}))
    meta = build_metadata(curriculum.get(ep_id), f"Title {ep_id}", "A quest.", config, f"ep{ep_id:03d}.srt")
    (folder / "metadata.json").write_text(json.dumps(meta))
    for name in (f"ep{ep_id:03d}.mp4", f"ep{ep_id:03d}.srt", "thumb.png"):
        (folder / name).write_bytes(b"x")


def test_week_report(project, config):
    curriculum = load_curriculum(project)
    start = week_start_for(curriculum, curriculum.get(10))
    assert start == dt.date(2026, 12, 8)
    week = project / "out" / "week_2026-12-08"
    for ep_id, status in [(8, "ok"), (9, "warning"), (10, "error"), (11, "ok"), (12, "ok")]:
        _fake_episode(project, ep_id, status, config, curriculum)
        publish_to_week(project, ep_id, status, week)
    assert (week / "ep008.mp4").is_file() and not (week / "ep010.mp4").exists()
    html = write_week_report(project, curriculum, start).read_text(encoding="utf-8")
    assert "Title 9 — Learn English" in html and "petit souci &lt;b&gt;" in html  # échappé
    assert "1 bloqué(s)" in html and "Semaines 1 à 3" in html
    assert "../../episodes/ep010/thumb.png" in html


def test_random_picks_are_reproducible(project, config):
    curriculum = load_curriculum(project)
    start = dt.date(2026, 12, 22)  # 4e semaine : 2 épisodes tirés au hasard
    week = project / "out" / "week_2026-12-22"
    for ep_id in range(22, 29):
        _fake_episode(project, ep_id, "ok", config, curriculum)
        publish_to_week(project, ep_id, "ok", week)
    a = write_week_report(project, curriculum, start).read_text(encoding="utf-8")
    b = write_week_report(project, curriculum, start).read_text(encoding="utf-8")
    strip = lambda h: h.split("Rapport du")[0] + h.split("</p>", 1)[1]
    assert strip(a) == strip(b)
    assert a.count("tiré au hasard") == 2


def test_real_music_preferred_over_placeholder(project):
    import shutil

    from bongo.audio_mix import find_music

    generate_placeholders(project, load_curriculum(project))
    assert find_music(project, "jungle").name == "jungle.wav"
    shutil.copy(project / "assets/audio/music/jungle.wav", project / "assets/audio/music/jungle.flac")
    assert find_music(project, "jungle").name == "jungle.flac"
