import datetime as dt
import json
import shutil
import subprocess

import pytest

from bongo.errors import BongoError
from bongo.pipeline import EpisodeReport, episode_dir
from bongo.week import build_week, check_disk, is_done, week_starts

START = dt.date(2026, 12, 1)


def test_week_starts(curriculum):
    assert week_starts(curriculum) == [dt.date(2026, 12, d) for d in (1, 8, 15, 22)]


def test_disk_check(tmp_path):
    with pytest.raises(BongoError, match="Go sur le disque"):
        check_disk(tmp_path, needed_gb=10**9)


def _fake_build(statuses, calls):
    def build(root, ep_id, log=print):
        calls.append(ep_id)
        outcome = statuses.get(ep_id, "ok")
        if outcome == "quota":
            raise BongoError("Quota gratuit de Gemini dépassé. Réessaie plus tard.")
        if outcome == "crash":
            raise ZeroDivisionError("boum")
        folder = episode_dir(root, ep_id)
        folder.mkdir(parents=True, exist_ok=True)
        report = EpisodeReport(ep_id)
        if outcome == "error":
            from bongo.script_check import Issue

            report.issues.append(Issue("error", "x", "bloqué"))
        (folder / "qa.json").write_text(json.dumps(report.to_dict()))
        if outcome != "error":
            (folder / f"ep{ep_id:03d}.mp4").write_bytes(b"video")
        return report

    return build


def test_build_week_isolates_failures(project):
    calls = []
    results = build_week(project, START, build=_fake_build({2: "crash", 3: "error"}, calls), log=lambda m: None)
    assert calls == [1, 2, 3, 4, 5, 6, 7]
    assert results[2] == "error" and results[3] == "error" and results[1] == "ok"
    week = project / "out" / "week_2026-12-01"
    journal = (week / "journal.txt").read_text(encoding="utf-8")
    assert "ZeroDivisionError" in journal and "ERREUR INATTENDUE" in journal
    qa2 = json.loads((episode_dir(project, 2) / "qa.json").read_text())
    assert qa2["status"] == "error" and qa2["issues"][0]["code"] == "crash"
    assert (week / "report.html").is_file()


def test_build_week_stops_on_quota_and_resumes(project):
    calls = []
    results = build_week(project, START, build=_fake_build({3: "quota"}, calls), log=lambda m: None)
    assert calls == [1, 2, 3]
    assert results[4] == "non fabriqué" and results[7] == "non fabriqué"
    qa5 = json.loads((episode_dir(project, 5) / "qa.json").read_text())
    assert "quota" in qa5["issues"][0]["message"].lower()
    # Le lendemain : seuls les épisodes manquants sont refaits
    calls2 = []
    results2 = build_week(project, START, build=_fake_build({}, calls2), log=lambda m: None)
    assert calls2 == [3, 4, 5, 6, 7]
    assert set(results2.values()) == {"ok"}
    assert is_done(project, 1)
    calls3 = []
    build_week(project, START, force=True, build=_fake_build({}, calls3), log=lambda m: None)
    assert calls3 == [1, 2, 3, 4, 5, 6, 7]


def test_compile(project):
    from bongo.compile import compile_range, probe_duration
    from bongo.curriculum import load_curriculum
    from bongo.pipeline import build_episode_audio
    from bongo.placeholders import generate_placeholders
    from conftest import EXAMPLE
    from fakes import FakeSynth, FakeWhisper, fake_rhubarb

    cfg = project / "config.yaml"
    cfg.write_text(cfg.read_text().replace("width: 1920, height: 1080", "width: 192, height: 108"))
    generate_placeholders(project, load_curriculum(project))
    build_episode_audio(project, 3, script_file=EXAMPLE, synth=FakeSynth(), transcriber=FakeWhisper(),
                        rhubarb_runner=fake_rhubarb, workers=1, log=lambda m: None)
    with pytest.raises(BongoError, match="pas prêt"):
        compile_range(project, 3, 4, "Test", log=lambda m: None)
    # L'épisode 4 : copie de l'épisode 3 (même encodage)
    src, dst = episode_dir(project, 3), episode_dir(project, 4)
    dst.mkdir(parents=True)
    shutil.copy(src / "ep003.mp4", dst / "ep004.mp4")
    shutil.copy(src / "ep003.srt", dst / "ep004.srt")
    for name in ("qa.json", "script.json"):
        shutil.copy(src / name, dst / name)
    out = compile_range(project, 3, 4, "Bongo's Days with Frog", log=lambda m: None)
    one = probe_duration(src / "ep003.mp4")
    total = probe_duration(out)
    assert total == pytest.approx(6 + 2 * one, abs=0.5)
    streams = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_name", "-of", "csv=p=0", str(out)],
                             capture_output=True, text=True).stdout.split()
    assert streams == ["h264", "aac"]
    folder = out.parent
    meta = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
    assert meta["title"] == "Bongo's Days with Frog — Learn English with Bongo the Gorilla"
    assert meta["publish_at_local"].startswith("2026-12-05T13:00")
    assert "0:00 Intro\n0:06 Frog and Leaf\n" in meta["description"]
    srt = (folder / "ep003-004.srt").read_text(encoding="utf-8")
    assert srt.startswith("1\n00:00:06,")
    assert srt.count("I am Bongo the gorilla.") == 2
    assert (folder / "thumb.png").is_file() and not (folder / "intro.mp4").exists()


def test_duration_advice(project):
    from bongo.week import duration_advice

    for ep_id, est, real in [(1, 200, 250), (2, 210, 255)]:
        folder = episode_dir(project, ep_id)
        folder.mkdir(parents=True)
        (folder / "qa.json").write_text(json.dumps({"duration_s": real, "steps": {"script": {"estimated_duration_s": est}}}))
    advice = duration_advice(project, [1, 2])
    assert "1.40" in advice and "123%" in advice
    (episode_dir(project, 2) / "qa.json").write_text(json.dumps({"duration_s": 210, "steps": {"script": {"estimated_duration_s": 205}}}))
    (episode_dir(project, 1) / "qa.json").write_text(json.dumps({"duration_s": 200, "steps": {"script": {"estimated_duration_s": 205}}}))
    assert duration_advice(project, [1, 2]) is None


def test_quota_keeps_episodes_that_have_a_script(project):
    # semaine déjà fabriquée une fois (les scénarios existent avant les vidéos)
    for ep_id in (6, 7):
        episode_dir(project, ep_id).mkdir(parents=True)
        (episode_dir(project, ep_id) / "script.json").write_text("{}")
    build_week(project, START, build=_fake_build({}, []), log=lambda m: None)
    # on refait tout (--force) mais le quota tombe à l'épisode 5
    calls = []
    results = build_week(project, START, force=True, build=_fake_build({5: "quota"}, calls), log=lambda m: None)
    assert calls == [1, 2, 3, 4, 5]          # 6 et 7 déjà faits : gardés, pas reconstruits
    assert results[6] == "ok" and results[7] == "ok"
    # un épisode avec scénario mais pas encore fini est fabriqué malgré le quota
    (episode_dir(project, 7) / "ep007.mp4").unlink()
    calls = []
    build_week(project, START, build=_fake_build({5: "quota"}, calls), log=lambda m: None)
    assert calls == [5, 7]
