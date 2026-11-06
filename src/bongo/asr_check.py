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
        segments, _info = whisper.transcribe(
            str(path), language="en", beam_size=5, condition_on_previous_text=False, vad_filter=False
        )
        return " ".join(seg.text.strip() for seg in segments).strip()

    return transcribe


def _same(a: str, b: str) -> bool:
    return a == b or bool(word_forms(a) & word_forms(b))


def mismatch_rate(expected: list[str], heard: list[str]) -> float:
    """Taux d'erreur sur les mots (distance d'édition / nombre de mots attendus)."""
    if not expected:
        return 0.0 if not heard else 1.0
    prev = list(range(len(heard) + 1))
    for i, e in enumerate(expected, 1):
        cur = [i] + [0] * len(heard)
        for j, h in enumerate(heard, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (0 if _same(e, h) else 1))
        prev = cur
    return prev[-1] / len(expected)


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
