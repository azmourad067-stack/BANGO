"""Synthèse vocale avec Kokoro (anglais américain).

Étape 1 : écoute comparée des voix (`python -m bongo voices`).
Étape 2 : fabrication des répliques d'un épisode.
"""

from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Callable, Iterable

import numpy as np

from bongo.errors import BongoError

SAMPLE_RATE = 24_000
KOKORO_REPO = "hexgrad/Kokoro-82M"
AMERICAN_LANG_CODE = "a"

# Voix américaines de Kokoro-82M (af_ = féminines, am_ = masculines)
AMERICAN_VOICES: tuple[str, ...] = (
    "af_heart", "af_alloy", "af_aoede", "af_bella", "af_jessica", "af_kore", "af_nicole",
    "af_nova", "af_river", "af_sarah", "af_sky",
    "am_adam", "am_echo", "am_eric", "am_fenrir", "am_liam", "am_michael", "am_onyx",
    "am_puck", "am_santa",
)

# Une « synthèse » prend (texte, voix, vitesse) et renvoie un signal mono 24 kHz
Synth = Callable[[str, str, float], np.ndarray]

_INSTALL_HINT = (
    "Kokoro n'est pas installé : dans le terminal du projet, lance\n"
    '    pip install -e ".[voix]"\n'
    "puis relance la commande (voir README, section Installation)."
)


def load_kokoro() -> Synth:
    """Charge Kokoro une seule fois et renvoie une fonction de synthèse."""
    try:
        from kokoro import KPipeline  # import tardif : lourd (torch)
    except ImportError:
        raise BongoError(_INSTALL_HINT) from None
    try:
        pipeline = KPipeline(lang_code=AMERICAN_LANG_CODE, repo_id=KOKORO_REPO)
    except Exception as exc:  # téléchargement du modèle, espeak-ng…
        raise BongoError(
            "Impossible de démarrer Kokoro. Vérifie ta connexion Internet (le modèle se télécharge "
            f"la première fois), puis relance `python -m bongo check-setup`.\nDétail : {exc}"
        ) from None

    def synth(text: str, voice: str, speed: float) -> np.ndarray:
        chunks = []
        for result in pipeline(text, voice=voice, speed=speed):
            audio = result.audio if hasattr(result, "audio") else result[2]
            if audio is not None:
                if hasattr(audio, "detach"):  # tenseur torch
                    audio = audio.detach().cpu().numpy()
                chunks.append(np.asarray(audio, dtype=np.float32).reshape(-1))
        if not chunks:
            raise BongoError(f"Kokoro n'a produit aucun son pour « {text} » avec la voix {voice}.")
        return np.concatenate(chunks)

    return synth


def write_wav(path: Path, audio: np.ndarray, sample_rate: int = SAMPLE_RATE) -> None:
    """WAV 16 bits mono, sans dépendance externe."""
    import wave

    pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype("<i2")
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm.tobytes())


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:40] or "phrase"


def preview_voices(
    text: str,
    out_dir: Path,
    speed: float,
    voices: Iterable[str] = AMERICAN_VOICES,
    synth: Synth | None = None,
    log: Callable[[str], None] = print,
) -> Path:
    """Fait dire `text` par chaque voix et écrit une page d'écoute. Renvoie le chemin de la page."""
    voices = list(voices)
    unknown = [v for v in voices if v not in AMERICAN_VOICES]
    if unknown:
        raise BongoError(
            f"Voix inconnue(s) : {', '.join(unknown)}. Voix américaines disponibles : {', '.join(AMERICAN_VOICES)}"
        )
    synth = synth or load_kokoro()
    folder = out_dir / f"{_slug(text)}_x{speed:g}"
    rows = []
    for i, voice in enumerate(voices, 1):
        log(f"  [{i}/{len(voices)}] {voice}")
        audio = synth(text, voice, speed)
        write_wav(folder / f"{voice}.wav", audio)
        kind = "féminine" if voice.startswith("af_") else "masculine"
        rows.append(
            f'<tr><td><b>{voice}</b></td><td>{kind}</td><td>{len(audio) / SAMPLE_RATE:.1f} s</td>'
            f'<td><audio controls preload="none" src="{voice}.wav"></audio></td></tr>'
        )
    page = folder / "ecoute.html"
    page.write_text(
        "<!doctype html><meta charset='utf-8'><title>Voix Kokoro</title>"
        "<style>body{font-family:sans-serif;margin:2em}td{padding:.4em 1em}</style>"
        f"<h1>« {html.escape(text)} » — vitesse {speed:g}</h1>"
        "<p>Choisis une voix par personnage, puis reporte son nom dans <code>config.yaml</code> "
        "(rubrique <code>voices</code>).</p>"
        f"<table>{''.join(rows)}</table>",
        encoding="utf-8",
    )
    return page
