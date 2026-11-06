"""Remplaçants de Kokoro, Whisper, Rhubarb et Gemini pour les tests."""

from pathlib import Path

import numpy as np

from bongo.tts import SAMPLE_RATE


class FakeSynth:
    """0,35 s par mot, un son simple (pour que Rhubarb ait quelque chose à analyser)."""

    def __init__(self):
        self.calls = []
        self.last_phonemes = ""

    def __call__(self, text, voice, speed):
        self.calls.append((text, voice, speed))
        self.last_phonemes = f"/{text.lower()}/"
        n = max(1, len(text.split()))
        t = np.arange(int(SAMPLE_RATE * 0.35 * n)) / SAMPLE_RATE
        return (0.3 * np.sin(2 * np.pi * 220 * t) * (0.5 + 0.5 * np.sin(2 * np.pi * 4 * t))).astype(np.float32)


class FakeWhisper:
    """Entend exactement le texte de la réplique (fichier .txt voisin), sauf les remplacements demandés."""

    def __init__(self, replace=None, only_variant0=False):
        self.replace = replace or {}
        self.calls = 0

    def __call__(self, wav: Path) -> str:
        self.calls += 1
        txt = wav.with_suffix(".txt")
        text = txt.read_text(encoding="utf-8").strip() if txt.is_file() else wav.stem
        for old, new in self.replace.items():
            text = text.replace(old, new)
        return text


def fake_rhubarb(rhubarb, wav, txt, out_json):
    return [{"start": 0.0, "end": 0.1, "value": "X"}, {"start": 0.1, "end": 0.3, "value": "D"},
            {"start": 0.3, "end": 0.5, "value": "B"}]


class FakeLLM:
    model_name = "gemini-test-flash"

    def __init__(self, answers):
        self.answers = list(answers)
        self.histories = []

    def complete(self, system, history):
        self.system = system
        self.histories.append(list(history))
        return self.answers.pop(0)
