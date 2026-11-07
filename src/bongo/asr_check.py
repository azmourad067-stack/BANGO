"""Contrôle de prononciation : faster-whisper transcrit chaque réplique.

- erreur si un mot cible (mot nouveau, prompt_word, carte-mot) n'est pas reconnu à l'identique ;
- avertissement si l'écart sur le reste de la phrase dépasse le seuil de config.yaml (20 %).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from bongo.errors import BongoError
from bongo.script_check import tokenize, word_forms

Transcriber = Callable[[Path], str]


def load_whisper(model: str = "small.en", device: str = "cpu", compute_type: str = "int8") -> Transcriber:
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise BongoError(
            'faster-whisper n\'est pas installé : lance pip install -e ".[controle]" puis relance la commande.'
        ) from None
    try:
        whisper = WhisperModel(model, device=device, compute_type=compute_type)
    except Exception as exc:
        raise BongoError(
            f"Impossible de charger le modèle Whisper « {model} ». Il se télécharge la première fois : "
            f"vérifie la connexion Internet puis relance.\nDétail : {exc}"
        ) from None

    def transcribe(path: Path) -> str:
        # On décode nous-mêmes (WAV -> 16 kHz) : évite le lecteur audio de faster-whisper (PyAV),
        # dont certaines versions sont incompatibles.
        segments, _info = whisper.transcribe(
            load_for_whisper(path), language="en", beam_size=5, condition_on_previous_text=False, vad_filter=False
        )
        return " ".join(seg.text.strip() for seg in segments).strip()

    return transcribe


WHISPER_RATE = 16_000


def resample(audio, rate: int, target: int = WHISPER_RATE):
    """Rééchantillonne un signal mono float32."""
    import numpy as np

    if rate == target or len(audio) == 0:
        return audio.astype(np.float32)
    try:
        from math import gcd

        from scipy.signal import resample_poly

        g = gcd(rate, target)
        return resample_poly(audio, target // g, rate // g).astype(np.float32)
    except ImportError:
        n = int(round(len(audio) * target / rate))
        x_new = np.linspace(0, len(audio) - 1, n)
        return np.interp(x_new, np.arange(len(audio)), audio).astype(np.float32)


def load_for_whisper(path: Path):
    """WAV 16 bits -> signal mono float32 à 16 kHz, comme l'attend Whisper."""
    from bongo.tts import read_wav

    audio, rate = read_wav(path)
    return resample(audio, rate)


def _same(a: str, b: str) -> bool:
    return a == b or bool(word_forms(a) & word_forms(b))


# Interjections sans orthographe fixe : Whisper les écrit au hasard (« Hmm » -> « Um », « And »…)
FILLERS = {"hmm", "hm", "mm", "mmm", "um", "uh", "ah", "er", "erm", "uhm", "huh"}


def mismatch_rate(expected: list[str], heard: list[str]) -> float:
    """Taux d'erreur sur les mots (distance d'édition / nombre de mots attendus).
    Une interjection attendue peut être entendue comme n'importe quel mot, ou pas du tout ;
    une interjection entendue en plus ne compte pas."""
    real = [e for e in expected if e not in FILLERS]
    if not real:
        return 0.0
    prev = [0]
    for h in heard:
        prev.append(prev[-1] + (0 if h in FILLERS else 1))
    for e in expected:
        filler = e in FILLERS
        cur = [prev[0] + (0 if filler else 1)]
        for j, h in enumerate(heard, 1):
            sub = 0 if (filler or _same(e, h)) else 1
            cur.append(min(prev[j] + (0 if filler else 1),
                           cur[j - 1] + (0 if h in FILLERS else 1),
                           prev[j - 1] + sub))
        prev = cur
    return prev[-1] / len(real)


@dataclass
class LineCheck:
    line_id: str
    text: str
    heard: str
    missing_targets: list[str] = field(default_factory=list)
    mismatch: float = 0.0

    @property
    def ok(self) -> bool:
        return not self.missing_targets

    def to_dict(self) -> dict:
        return {
            "line_id": self.line_id,
            "text": self.text,
            "heard": self.heard,
            "missing_targets": self.missing_targets,
            "mismatch": round(self.mismatch, 3),
        }


def target_words(text: str, candidates: set[str]) -> list[str]:
    """Mots cibles présents dans la réplique (dans l'ordre, sans doublon)."""
    found: dict[str, None] = {}
    for token in tokenize(text):
        for word in word_forms(token) & candidates:
            found.setdefault(word, None)
    return list(found)


def check_line(line_id: str, text: str, heard: str, targets: list[str]) -> LineCheck:
    heard_tokens = tokenize(heard)
    heard_forms: set[str] = set()
    for t in heard_tokens:
        heard_forms |= word_forms(t)
    # « good night » entendu pour « goodnight »
    for a, b in zip(heard_tokens, heard_tokens[1:]):
        heard_forms |= word_forms(a + b)
    missing = [w for w in targets if w not in heard_forms]
    return LineCheck(line_id, text, heard, missing, mismatch_rate(tokenize(text), heard_tokens))
