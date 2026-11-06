"""Chargement et contrôle du programme de la saison (content/curriculum.yaml)."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from bongo.errors import BongoError

MIN_NEW_WORDS = 2
MAX_NEW_WORDS = 3


def _lower_list(values: list[str]) -> list[str]:
    return [str(v).strip().lower() for v in values]


class Episode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int = Field(ge=1)
    date: dt.date
    type: Literal["lesson", "review"]
    biome: str
    backgrounds: list[str] = Field(min_length=1)
    new_words: list[str] = Field(default_factory=list)
    review_words: list[str] = Field(default_factory=list)
    friends: list[str] = Field(default_factory=list)
    action: str | None = None
    note: str | None = None

    _norm = field_validator("backgrounds", "new_words", "review_words", "friends", mode="before")(
        lambda cls, v: _lower_list(v or [])
    )

    @model_validator(mode="after")
    def _check_type(self) -> "Episode":
        if self.type == "lesson" and not MIN_NEW_WORDS <= len(self.new_words) <= MAX_NEW_WORDS:
            raise ValueError(
                f"un épisode « lesson » doit avoir {MIN_NEW_WORDS} ou {MAX_NEW_WORDS} mots nouveaux "
                f"(trouvé : {len(self.new_words)})"
            )
        if self.type == "review" and self.new_words:
            raise ValueError("un épisode de révision n'enseigne pas de mot nouveau")
        if self.action:
            self.action = self.action.strip().lower()
        return self

    @property
    def is_review(self) -> bool:
        return self.type == "review"


class Curriculum(BaseModel):
    model_config = ConfigDict(extra="forbid")

    season: int
    episodes: list[Episode] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_consistency(self) -> "Curriculum":
        ids = [e.id for e in self.episodes]
        if len(ids) != len(set(ids)):
            raise ValueError("deux épisodes ont le même numéro")
        if ids != sorted(ids):
            raise ValueError("les épisodes doivent être rangés par numéro croissant")
        taught: set[str] = set()
        for ep in self.episodes:
            again = [w for w in ep.new_words if w in taught]
            if again:
                raise ValueError(f"épisode {ep.id} : {', '.join(again)} déjà enseigné(s) avant")
            missing = [w for w in ep.review_words if w not in taught]
            if missing:
                raise ValueError(
                    f"épisode {ep.id} : mot(s) rappelé(s) jamais enseigné(s) avant : {', '.join(missing)}"
                )
            taught.update(ep.new_words)
        return self

    # --- Accès -------------------------------------------------------------

    def get(self, episode_id: int) -> Episode:
        for ep in self.episodes:
            if ep.id == episode_id:
                return ep
        raise BongoError(
            f"L'épisode {episode_id} n'existe pas dans content/curriculum.yaml "
            f"(épisodes disponibles : {self.episodes[0].id} à {self.episodes[-1].id})."
        )

    def _until(self, episode_id: int) -> list[Episode]:
        self.get(episode_id)
        return [e for e in self.episodes if e.id <= episode_id]

    def words_taught_until(self, episode_id: int) -> set[str]:
        """Mots nouveaux des épisodes 1 à `episode_id` inclus."""
        return {w for e in self._until(episode_id) for w in e.new_words}

    def friends_until(self, episode_id: int) -> set[str]:
        return {f for e in self._until(episode_id) for f in e.friends}

    def vocabulary_until(self, episode_id: int) -> set[str]:
        """Mots du programme utilisables dans l'épisode : mots enseignés jusqu'ici,
        gestes à mimer déjà proposés et noms des amis déjà rencontrés."""
        eps = self._until(episode_id)
        words = {w for e in eps for w in e.new_words + e.review_words + e.friends}
        words |= {e.action for e in eps if e.action}
        return words

    def all_words(self) -> list[str]:
        return [w for e in self.episodes for w in e.new_words]

    def all_friends(self) -> list[str]:
        seen: dict[str, None] = {}
        for e in self.episodes:
            for f in e.friends:
                seen.setdefault(f, None)
        return list(seen)

    def backgrounds_by_biome(self) -> dict[str, list[str]]:
        result: dict[str, dict[str, None]] = {}
        for e in self.episodes:
            for bg in e.backgrounds:
                result.setdefault(e.biome, {}).setdefault(bg, None)
        return {biome: list(bgs) for biome, bgs in result.items()}

    def week(self, start: dt.date) -> list[Episode]:
        end = start + dt.timedelta(days=6)
        eps = [e for e in self.episodes if start <= e.date <= end]
        if not eps:
            raise BongoError(f"Aucun épisode programmé entre le {start} et le {end}.")
        return eps


def load_curriculum(root: Path) -> Curriculum:
    path = root / "content" / "curriculum.yaml"
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise BongoError(f"{path} introuvable : le programme de la saison est indispensable.") from None
    except yaml.YAMLError as exc:
        raise BongoError(f"content/curriculum.yaml est mal formé (vérifie l'indentation) : {exc}") from None
    try:
        return Curriculum.model_validate(data)
    except ValidationError as exc:
        raise BongoError(f"content/curriculum.yaml contient une erreur :\n{exc}") from None


def load_word_list(path: Path) -> set[str]:
    """Lit un fichier texte : un mot par ligne, # pour les commentaires."""
    if not path.is_file():
        raise BongoError(f"{path} introuvable.")
    words = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip().lower()
        if line:
            words.add(line)
    return words
