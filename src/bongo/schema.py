"""Schéma du scénario d'un épisode (episodes/epNNN/script.json)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from bongo.errors import BongoError

SEGMENTS: tuple[str, ...] = (
    "hello",
    "quest",
    "encounter_1",
    "encounter_2",
    "review_word",
    "success",
    "recap",
    "goodbye",
)
REVIEW_SEGMENTS: tuple[str, ...] = ("hello", "recap", "goodbye")

BONGO = "bongo"
BONGO_POSES: tuple[str, ...] = ("stand", "arms_up", "drum_a", "drum_b", "point", "crouch", "sleep")
FRIEND_POSES: tuple[str, ...] = ("pose_1", "pose_2")

Segment = Literal["hello", "quest", "encounter_1", "encounter_2", "review_word", "success", "recap", "goodbye"]
Position = Literal["left", "center", "right"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def _lower(v: str | None) -> str | None:
    return v.lower() if isinstance(v, str) else v


class CharacterOnStage(_Strict):
    name: str = Field(min_length=1)
    pose: str = Field(min_length=1)
    position: Position

    _n = field_validator("name", "pose", mode="before")(lambda cls, v: _lower(v))


class Line(_Strict):
    speaker: str = Field(min_length=1)
    text: str = Field(min_length=1)
    pose: str | None = None
    prompt_word: str | None = None
    pause_after: float = Field(default=0.0, ge=0, le=10)
    card: str | None = None
    gesture: str | None = None  # geste que l'enfant est invité à mimer (ex. "jump")

    _n = field_validator("speaker", "pose", "prompt_word", "card", "gesture", mode="before")(
        lambda cls, v: _lower(v)
    )


class Scene(_Strict):
    id: str = Field(min_length=1)
    segment: Segment
    background: str = Field(min_length=1)
    characters: list[CharacterOnStage] = Field(min_length=1)
    lines: list[Line] = Field(min_length=1)

    _n = field_validator("background", mode="before")(lambda cls, v: _lower(v))


class Script(_Strict):
    episode_id: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=60)
    quest_summary: str = Field(min_length=1)
    scenes: list[Scene] = Field(min_length=1)

    def all_lines(self) -> list[Line]:
        return [line for scene in self.scenes for line in scene.lines]


def format_validation_error(exc: ValidationError) -> list[str]:
    """Transforme les erreurs pydantic en lignes lisibles (« scenes[0].lines[2].text : ... »)."""
    messages = []
    for err in exc.errors():
        where = "".join(f"[{p}]" if isinstance(p, int) else f".{p}" for p in err["loc"]).lstrip(".")
        messages.append(f"{where or 'script'} : {err['msg']}")
    return messages


def parse_script(data: dict | str) -> Script:
    """Valide un scénario (dictionnaire ou texte JSON). Lève ValidationError ou ValueError."""
    if isinstance(data, str):
        data = json.loads(data)
    return Script.model_validate(data)


def load_script(path: Path) -> Script:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise BongoError(f"Scénario introuvable : {path}") from None
    try:
        return parse_script(text)
    except json.JSONDecodeError as exc:
        raise BongoError(f"{path.name} n'est pas un JSON valide (ligne {exc.lineno}) : {exc.msg}") from None
    except ValidationError as exc:
        details = "\n  - ".join(format_validation_error(exc))
        raise BongoError(f"{path.name} ne respecte pas le format du scénario :\n  - {details}") from None
