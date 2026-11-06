import json
import shutil
import subprocess

import numpy as np
import pytest

from bongo.asr_check import check_line, mismatch_rate, target_words
from bongo.lipsync import convert_cues, lipsync_lines, run_rhubarb
from bongo.setup_check import rhubarb_path
from bongo.tts import LineAudio, write_wav
from conftest import ROOT
from fakes import FakeSynth, fake_rhubarb


def test_mismatch_rate():
    assert mismatch_rate(["look", "a", "frog"], ["look", "a", "frog"]) == 0
    assert mismatch_rate(["look", "a", "frog"], ["look", "a", "dog"]) == pytest.approx(1 / 3)
    assert mismatch_rate(["frog"], ["frogs"]) == 0


def test_check_line_targets():
    ok = check_line("l1", "Can you say frog?", "Can you say frog?", ["frog"])
    assert ok.ok and ok.mismatch == 0
    bad = check_line("l2", "Can you say frog?", "Can you say fog?", ["frog"])
    assert bad.missing_targets == ["frog"]
    joined = check_line("l3", "Goodnight, Owl!", "Good night, Owl.", ["goodnight"])
    assert joined.ok


def test_target_words():
    assert target_words("Frogs! Look, a leaf and a tree.", {"frog", "leaf", "parrot"}) == ["frog", "leaf"]


def test_convert_cues():
    cues = [{"start": 0, "end": 0.1, "value": "X"}, {"start": 0.1, "end": 0.2, "value": "A"},
            {"start": 0.2, "end": 0.4, "value": "D"}, {"start": 0.4, "end": 0.5, "value": "G"}]
    assert [c["shape"] for c in convert_cues(cues, "bongo")] == ["X", "A", "D", "G"]
    animal = convert_cues(cues, "frog")
    assert [c["shape"] for c in animal] == ["mouth_closed", "mouth_open", "mouth_half"]
    assert animal[0] == {"start": 0.0, "end": 0.2, "shape": "mouth_closed"}  # X et A fusionnés


def _line(tmp_path, lid="l001", speaker="frog"):
    wav, txt = tmp_path / f"{lid}.wav", tmp_path / f"{lid}.txt"
    write_wav(wav, FakeSynth()("Hello Bongo", "x", 1))
    txt.write_text("Hello, Bongo!\n", encoding="utf-8")
    return LineAudio(lid, "s1", 0, speaker, "Hello, Bongo!", wav, txt, 0.7)


def test_lipsync_lines_with_fake(tmp_path):
    line = _line(tmp_path)
    out = lipsync_lines([line], tmp_path / "lipsync", rhubarb=None, log=lambda m: None, runner=fake_rhubarb)
    data = json.loads(out["l001"].read_text())
    assert data["speaker"] == "frog"
    assert [c["shape"] for c in data["cues"]] == ["mouth_closed", "mouth_open", "mouth_half"]
    calls = []
    lipsync_lines([line], tmp_path / "lipsync", rhubarb=None, log=lambda m: None,
                  runner=lambda *a: calls.append(a) or [])
    assert calls == []  # déjà à jour


@pytest.mark.skipif(rhubarb_path(ROOT) is None, reason="Rhubarb absent de tools/rhubarb")
def test_real_rhubarb(tmp_path):
    line = _line(tmp_path, speaker="bongo")
    cues = run_rhubarb(rhubarb_path(ROOT), line.wav, line.txt, tmp_path / "raw.json")
    assert cues and cues[0]["start"] == 0
    assert {c["value"] for c in cues} <= set("ABCDEFGHX")
