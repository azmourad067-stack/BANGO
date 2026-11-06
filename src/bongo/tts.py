"""Synthèse vocale avec Kokoro (anglais américain).

Étape 1 : écoute comparée des voix (`python -m bongo voices`).
Étape 2 : fabrication des répliques d'un épisode.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
from dataclasses import dataclass
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


class KokoroEngine:
    """Kokoro chargé une seule fois. S'appelle comme une fonction : engine(texte, voix, vitesse).
    Après chaque appel, `last_phonemes` contient les phonèmes utilisés (pour `pronounce`)."""

    last_phonemes: str = ""

    def __init__(self) -> None:
        try:
            from kokoro import KPipeline  # import tardif : lourd (torch)
        except ImportError:
            raise BongoError(_INSTALL_HINT) from None
        try:
            self.pipeline = KPipeline(lang_code=AMERICAN_LANG_CODE, repo_id=KOKORO_REPO)
        except Exception as exc:  # téléchargement du modèle, espeak-ng…
            raise BongoError(
                "Impossible de démarrer Kokoro. Vérifie ta connexion Internet (le modèle se télécharge "
                f"la première fois), puis relance `python -m bongo check-setup`.\nDétail : {exc}"
            ) from None

    def __call__(self, text: str, voice: str, speed: float) -> np.ndarray:
        chunks = []
        phonemes = []
        for result in self.pipeline(text, voice=voice, speed=speed):
            phonemes.append(str(getattr(result, "phonemes", "") or ""))
            audio = result.audio if hasattr(result, "audio") else result[2]
            if audio is not None:
                if hasattr(audio, "detach"):  # tenseur torch
                    audio = audio.detach().cpu().numpy()
                chunks.append(np.asarray(audio, dtype=np.float32).reshape(-1))
        self.last_phonemes = " ".join(p for p in phonemes if p)
        if not chunks:
            raise BongoError(f"Kokoro n'a produit aucun son pour « {text} » avec la voix {voice}.")
        return np.concatenate(chunks)


def load_kokoro() -> KokoroEngine:
    return KokoroEngine()


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


def read_wav(path: Path) -> tuple[np.ndarray, int]:
    import wave

    with wave.open(str(path), "rb") as wav:
        rate = wav.getframerate()
        frames = wav.readframes(wav.getnframes())
        width, channels = wav.getsampwidth(), wav.getnchannels()
    if width != 2:
        raise BongoError(f"{path.name} : format WAV inattendu (16 bits attendu).")
    audio = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    return audio, rate


def wav_duration(path: Path) -> float:
    import wave

    with wave.open(str(path), "rb") as wav:
        return wav.getnframes() / wav.getframerate()


def silence(seconds: float, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    return np.zeros(int(round(seconds * sample_rate)), dtype=np.float32)


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


# --- Prononciations ---------------------------------------------------------------------


def load_pronunciations(root: Path) -> dict[str, str]:
    """content/pronunciations.yaml : mot -> phonèmes Kokoro (alphabet de misaki)."""
    import yaml

    path = root / "content" / "pronunciations.yaml"
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise BongoError(f"pronunciations.yaml est mal formé : {exc}") from None
    if not isinstance(data, dict):
        raise BongoError("pronunciations.yaml doit contenir des lignes « mot: phonèmes ».")
    return {str(k).lower(): str(v).strip().strip("/") for k, v in data.items() if v}


def apply_pronunciations(text: str, pronunciations: dict[str, str]) -> str:
    """Remplace chaque mot corrigé par la syntaxe de Kokoro : [mot](/phonèmes/)."""
    if not pronunciations:
        return text
    words = sorted(pronunciations, key=len, reverse=True)
    pattern = re.compile(r"(?<![\w\[])(" + "|".join(re.escape(w) for w in words) + r")(?![\w\]])", re.IGNORECASE)
    return pattern.sub(lambda m: f"[{m.group(0)}](/{pronunciations[m.group(0).lower()]}/)", text)


# --- Répliques d'un épisode ------------------------------------------------------------------

SENTENCE_GAP_S = 0.25  # silence entre les phrases, pour la variante de régénération


@dataclass
class LineAudio:
    id: str
    scene_id: str
    index: int  # rang dans la scène
    speaker: str
    text: str
    wav: Path
    txt: Path
    duration_s: float
    variant: int = 0


def line_id(n: int) -> str:
    return f"l{n:03d}"


def synthesize_line(text: str, voice: str, speed: float, synth: Synth, variant: int = 0) -> np.ndarray:
    """Variante 0 : la réplique d'un bloc. Variante 1 : phrase par phrase, avec un court silence
    (Kokoro donne toujours le même son pour le même texte : c'est la seule façon de « régénérer »)."""
    if variant == 0:
        return synth(text, voice, speed)
    sentences = [s.strip() for s in re.findall(r"[^.!?]+[.!?]*", text) if s.strip()]
    if len(sentences) <= 1:
        words = text.split()
        if len(words) > 2:
            half = len(words) // 2
            sentences = [" ".join(words[:half]) + ",", " ".join(words[half:])]
        else:
            sentences = [text]
    parts = []
    for i, sentence in enumerate(sentences):
        if i:
            parts.append(silence(SENTENCE_GAP_S))
        parts.append(synth(sentence, voice, speed))
    return np.concatenate(parts)


def _fingerprint(*parts: object) -> str:
    return hashlib.sha1("\x1f".join(map(str, parts)).encode("utf-8")).hexdigest()


def synthesize_script(
    script,
    config,
    out_dir: Path,
    synth: Synth | None,
    pronunciations: dict[str, str],
    variants: dict[str, int] | None = None,
    log: Callable[[str], None] = print,
) -> list[LineAudio]:
    """Une réplique = un WAV 24 kHz (+ son texte pour Rhubarb). Réutilise les fichiers déjà faits."""
    from bongo.config import voice_for

    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        manifest = {}
    variants = variants or {}
    results: list[LineAudio] = []
    n = 0
    total = len(script.all_lines())
    for scene in script.scenes:
        for i, line in enumerate(scene.lines):
            n += 1
            lid = line_id(n)
            vc = voice_for(config, line.speaker)
            variant = variants.get(lid, 0)
            spoken = apply_pronunciations(line.text, pronunciations)
            key = _fingerprint(spoken, vc.voice, vc.speed, variant, SAMPLE_RATE)
            wav = out_dir / f"{lid}.wav"
            txt = out_dir / f"{lid}.txt"
            if not (wav.is_file() and manifest.get(lid) == key):
                if synth is None:
                    synth = load_kokoro()
                log(f"  [{n}/{total}] {line.speaker} : {line.text}")
                write_wav(wav, synthesize_line(spoken, vc.voice, vc.speed, synth, variant))
                manifest[lid] = key
                manifest_path.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
            txt.write_text(line.text + "\n", encoding="utf-8")
            results.append(LineAudio(lid, scene.id, i, line.speaker, line.text, wav, txt, wav_duration(wav), variant))
    return results
