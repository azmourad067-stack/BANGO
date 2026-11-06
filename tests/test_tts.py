import importlib.util
import wave

import numpy as np
import pytest

from bongo.errors import BongoError
from bongo.tts import AMERICAN_VOICES, SAMPLE_RATE, load_kokoro, preview_voices


def fake_synth(text, voice, speed):
    return np.zeros(int(SAMPLE_RATE * 0.5), dtype=np.float32)


def test_preview_voices(tmp_path):
    page = preview_voices("Hello, little explorer!", tmp_path, 0.85, ["am_adam", "af_heart"], synth=fake_synth, log=lambda m: None)
    assert page.name == "ecoute.html"
    html = page.read_text(encoding="utf-8")
    assert "am_adam.wav" in html and "af_heart.wav" in html
    with wave.open(str(page.parent / "am_adam.wav")) as wav:
        assert wav.getframerate() == 24_000
        assert wav.getnchannels() == 1


def test_unknown_voice(tmp_path):
    with pytest.raises(BongoError, match="Voix inconnue"):
        preview_voices("Hi", tmp_path, 1.0, ["bf_emma"], synth=fake_synth)


def test_voices_are_american():
    assert len(AMERICAN_VOICES) == 20
    assert all(v[:3] in ("af_", "am_") for v in AMERICAN_VOICES)


@pytest.mark.skipif(importlib.util.find_spec("kokoro") is not None, reason="Kokoro est installé")
def test_kokoro_missing_message():
    with pytest.raises(BongoError, match="pip install"):
        load_kokoro()
