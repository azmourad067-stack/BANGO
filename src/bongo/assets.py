"""Emplacement des assets attendus (dessins, décors, cartes-mots, police)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from bongo.curriculum import Curriculum
from bongo.schema import BONGO, BONGO_POSES

BONGO_EYES = ("open", "half", "closed", "left", "right")
BONGO_BROWS = ("neutral", "surprised")
BONGO_MOUTHS = ("A", "B", "C", "D", "E", "F", "G", "H", "X")
FRIEND_LAYERS = ("pose_1", "pose_2", "eyes_open", "eyes_closed", "mouth_closed", "mouth_half", "mouth_open")
COMMON_BIOME = "common"  # décors partagés par tous les milieux (le nid de Bongo)
FONT_FILE = Path("assets/fonts/Fredoka.ttf")
PLACEHOLDER_MANIFEST = Path("assets/placeholders.txt")


def bongo_layers() -> list[Path]:
    base = Path("assets/characters/bongo")
    paths = [base / "body" / f"{p}.png" for p in BONGO_POSES]
    paths += [base / "eyes" / f"{e}.png" for e in BONGO_EYES]
    paths += [base / "brows" / f"{b}.png" for b in BONGO_BROWS]
    paths += [base / "mouth" / f"{m}.png" for m in BONGO_MOUTHS]
    paths.append(base / "rig.json")
    return paths


def friend_layers(name: str) -> list[Path]:
    base = Path("assets/characters") / name
    return [base / f"{layer}.png" for layer in FRIEND_LAYERS] + [base / "rig.json"]


def character_layers(name: str) -> list[Path]:
    return bongo_layers() if name == BONGO else friend_layers(name)


def background_candidates(biome: str, decor: str) -> list[Path]:
    """Le décor propre au milieu, sinon le décor commun (ex. le nid)."""
    return [
        Path("assets/backgrounds") / biome / f"{decor}.png",
        Path("assets/backgrounds") / COMMON_BIOME / f"{decor}.png",
    ]


def find_background(root: Path, biome: str, decor: str) -> Path | None:
    for rel in background_candidates(biome, decor):
        if (root / rel).is_file():
            return root / rel
    return None


def card_path(word: str) -> Path:
    return Path("assets/cards") / f"{word}.png"


@dataclass
class MissingAsset:
    category: str
    path: Path


def missing_assets_for_biome(root: Path, curriculum: Curriculum, biome: str) -> list[MissingAsset]:
    """Assets manquants pour fabriquer tous les épisodes d'un milieu."""
    episodes = [e for e in curriculum.episodes if e.biome == biome]
    missing: list[MissingAsset] = []
    characters = {BONGO} | {f for e in episodes for f in e.friends}
    for name in sorted(characters):
        for rel in character_layers(name):
            if not (root / rel).is_file():
                missing.append(MissingAsset(f"personnage {name}", rel))
    for decor in dict.fromkeys(bg for e in episodes for bg in e.backgrounds):
        if find_background(root, biome, decor) is None:
            missing.append(MissingAsset("décor", background_candidates(biome, decor)[0]))
    for word in dict.fromkeys(w for e in episodes for w in e.new_words):
        if not (root / card_path(word)).is_file():
            missing.append(MissingAsset("carte-mot", card_path(word)))
    return missing

