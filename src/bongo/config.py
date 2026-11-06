"""Lecture de config.yaml et du fichier .env."""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from bongo.errors import BongoError

PLACEHOLDER = "A_CHOISIR"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VideoConfig(_Strict):
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    fps: int = Field(gt=0)


class PositionsConfig(_Strict):
    left: float
    center: float
    right: float


class VoiceConfig(_Strict):
    voice: str
    speed: float = Field(gt=0)


class LLMConfig(_Strict):
    model: str
    temperature: float = Field(ge=0)
    max_retries: int = Field(ge=1)


class QAConfig(_Strict):
    min_word_repeats: int
    min_cards_per_word: int
    max_words_per_sentence: int
    prompt_pause_s: float
    lesson_duration_s: tuple[float, float]
    review_duration_s: tuple[float, float]
    min_shot_s: float
    estimate_words_per_s: float = Field(gt=0)
    estimate_min_line_s: float = Field(ge=0)
    gap_between_lines_s: float = Field(ge=0)
    scene_fade_s: float = Field(ge=0)
    quest_similarity_max: float = Field(gt=0, le=1)


class ASRConfig(_Strict):
    model: str = "small.en"
    device: str = "cpu"
    compute_type: str = "int8"
    max_mismatch: float = Field(default=0.20, ge=0, le=1)


class AudioConfig(_Strict):
    music_db_under_voice: float
    loudness_lufs: float


class PublishConfig(_Strict):
    time: str
    timezone: str


class UploadConfig(_Strict):
    enabled: bool


class Config(_Strict):
    video: VideoConfig
    positions: PositionsConfig
    voices: dict[str, VoiceConfig]
    llm: LLMConfig
    qa: QAConfig
    asr: ASRConfig = ASRConfig()
    audio: AudioConfig
    publish: PublishConfig
    upload: UploadConfig


def voice_for(config: "Config", speaker: str) -> VoiceConfig:
    try:
        return config.voices[speaker]
    except KeyError:
        raise BongoError(
            f"Aucune voix pour « {speaker} » dans config.yaml (rubrique voices) : ajoute-la, "
            "par exemple après écoute avec `python -m bongo voices`."
        ) from None


def find_root(start: Path | None = None) -> Path:
    """Dossier du projet : celui qui contient config.yaml (dossier courant ou un parent).

    La variable d'environnement BONGO_ROOT, si elle existe, est prioritaire.
    """
    env = os.environ.get("BONGO_ROOT")
    if env:
        root = Path(env)
        if (root / "config.yaml").is_file():
            return root.resolve()
        raise BongoError(f"BONGO_ROOT pointe vers {root}, mais config.yaml n'y est pas.")
    here = (start or Path.cwd()).resolve()
    for folder in [here, *here.parents]:
        if (folder / "config.yaml").is_file():
            return folder
    raise BongoError(
        "config.yaml introuvable : ouvre le terminal dans le dossier du projet Bongo, puis relance la commande."
    )


def load_config(root: Path | None = None) -> Config:
    root = root or find_root()
    path = root / "config.yaml"
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise BongoError(f"{path} introuvable.") from None
    except yaml.YAMLError as exc:
        raise BongoError(f"config.yaml est mal formé (vérifie l'indentation) : {exc}") from None
    try:
        return Config.model_validate(data)
    except ValidationError as exc:
        raise BongoError(f"config.yaml contient une valeur invalide :\n{exc}") from None


def load_env(root: Path) -> dict[str, str]:
    """Lit le fichier .env (lignes CLE=valeur). Ne modifie pas os.environ."""
    path = root / ".env"
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def get_secret(root: Path, name: str) -> str | None:
    value = os.environ.get(name) or load_env(root).get(name)
    return value or None
