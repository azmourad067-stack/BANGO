import json

import pytest
import yaml

from bongo.cli import main
from bongo.errors import BongoError
from bongo.pipeline import build_episode_audio, episode_dir, pronounce_words
from bongo.tts import wav_duration
from conftest import EXAMPLE
from fakes import FakeLLM, FakeSynth, FakeWhisper, fake_rhubarb

QUIET = dict(log=lambda m: None)


def _build(project, **kw):
    kw.setdefault("synth", FakeSynth())
    kw.setdefault("transcriber", FakeWhisper())
    kw.setdefault("rhubarb_runner", fake_rhubarb)
    return build_episode_audio(project, 3, **kw, **QUIET)


def test_build_with_handwritten_script(project):
    report = _build(project, script_file=EXAMPLE)
    folder = episode_dir(project, 3)
    assert report.status in ("ok", "warning"), report.summary_fr()
    assert not [i for i in report.issues if i.level == "error"]
    assert (folder / "script.json").is_file()
    n_lines = len(json.loads((folder / "script.json").read_text())["scenes"][0]["lines"])
    assert n_lines == 9
    assert (folder / "audio" / "l001.wav").is_file()
    assert (folder / "lipsync" / "l001.json").is_file()
    qa = json.loads((folder / "qa.json").read_text())
    assert qa["status"] == report.status and qa["steps"]["asr"]
    preview = folder / "ep003_audio.wav"
    assert wav_duration(preview) == pytest.approx(report.duration_s, abs=0.01)
    history = yaml.safe_load((project / "content" / "quest_history.yaml").read_text())
    assert history["quests"][0]["episode_id"] == 3


def test_rebuild_reuses_everything(project):
    _build(project, script_file=EXAMPLE)
    synth, whisper = FakeSynth(), FakeWhisper()
    _build(project, synth=synth, transcriber=whisper)  # réutilise script.json
    assert synth.calls == [] and whisper.calls == 0


def test_mispronounced_word_regenerated_then_blocked(project):
    # Whisper n'entend jamais « leaf » : régénération une fois, puis erreur
    synth = FakeSynth()
    report = _build(project, script_file=EXAMPLE, synth=synth,
                    transcriber=FakeWhisper(replace={"leaf": "beef", "Leaf": "Beef"}))
    assert report.status == "error"
    errors = [i for i in report.issues if i.code == "asr_target"]
    assert errors and "pronunciations.yaml" in errors[0].message
    variants = json.loads((episode_dir(project, 3) / "audio" / "variants.json").read_text())
    assert variants and set(variants.values()) == {1}
    history = yaml.safe_load((project / "content" / "quest_history.yaml").read_text())
    assert not history["quests"]  # épisode bloqué : quête non enregistrée


def test_blocked_script_stops_before_voices(project, tmp_path):
    data = json.loads(EXAMPLE.read_text())
    data["scenes"][0]["lines"][0]["text"] = "Hello, scary explorer!"
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(data))
    synth = FakeSynth()
    report = _build(project, script_file=bad, synth=synth)
    assert report.status == "error" and synth.calls == []
    assert not (episode_dir(project, 3) / "script.json").exists()


def test_build_with_gemini(project):
    llm = FakeLLM(["{}", EXAMPLE.read_text()])
    report = _build(project, llm_factory=lambda: llm)
    folder = episode_dir(project, 3)
    assert report.steps["script"]["source"] == "gemini" and report.steps["script"]["attempts"] == 2
    assert (folder / "rejected" / "essai_1.json").is_file()
    assert (folder / "script.json").is_file()


def test_missing_gemini_key(project, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(BongoError, match="Clé Gemini absente"):
        _build(project)


def test_pronounce(project):
    synth = FakeSynth()
    page = pronounce_words(project, synth=synth, transcriber=FakeWhisper(replace={"frog": "fog"}),
                           words=["frog", "leaf"], **QUIET)
    html = page.read_text(encoding="utf-8")
    assert "frog.wav" in html and "/frog!/" in html
    assert html.count("à écouter") == 1
    assert synth.calls[0][1:] == ("am_michael", 0.85)
    with pytest.raises(BongoError, match="absent"):
        pronounce_words(project, synth=synth, transcriber=None, words=["dragon"], **QUIET)


def test_cli_build_episode_without_rhubarb(project, monkeypatch, capsys):
    monkeypatch.chdir(project)
    monkeypatch.delenv("BONGO_ROOT", raising=False)
    assert main(["build-episode", "3", "--script-file", str(EXAMPLE)]) == 1
    assert "Rhubarb" in capsys.readouterr().err
