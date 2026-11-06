"""Assets provisoires (formes simples) pour développer sans attendre les dessins.

Ne remplace jamais un vrai dessin : un fichier existant n'est réécrit que s'il est
listé dans assets/placeholders.txt (donc créé par cette commande) et que --force est donné.
Quand un vrai dessin remplace un fichier provisoire, il suffit d'écraser le PNG :
check-setup compare les fichiers et ne le compte plus comme provisoire.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Callable

from PIL import Image, ImageDraw, ImageFont

from bongo.assets import (
    BONGO_BROWS,
    BONGO_EYES,
    BONGO_MOUTHS,
    COMMON_BIOME,
    FONT_FILE,
    PLACEHOLDER_MANIFEST,
    card_path,
)
from bongo.curriculum import Curriculum
from bongo.schema import BONGO_POSES

# Couleurs de la bible : fourrure gris-bleu foncé, visage gris clair chaud, écharpe de feuilles vertes
FUR = (61, 74, 92, 255)
SKIN = (205, 196, 184, 255)
SCARF = (88, 170, 80, 255)
INK = (40, 40, 48, 255)
WHITE = (255, 255, 255, 255)
CLEAR = (0, 0, 0, 0)

BONGO_CANVAS = (700, 900)
BONGO_FEET = (350, 885)
BONGO_FACE = {"eyes": (350, 250), "brows": (350, 185), "mouth": (350, 345)}
LOW_POSES = {"crouch": 140, "sleep": 200}  # décalage vertical de la tête
EYES_SIZE, BROWS_SIZE, MOUTH_SIZE = (300, 120), (300, 70), (160, 100)

FRIEND_CANVAS = (500, 500)
FRIEND_FEET = (250, 490)
FRIEND_EYES_SIZE, FRIEND_MOUTH_SIZE = (200, 80), (120, 80)
FRIEND_COLORS = {
    "parrot": (226, 85, 63),
    "frog": (92, 184, 92),
    "elephant": (154, 165, 177),
    "owl": (160, 120, 90),
    "squirrel": (217, 130, 43),
    "bear": (123, 81, 52),
    "duck": (242, 201, 76),
    "fish": (86, 168, 224),
    "turtle": (107, 142, 35),
    "goat": (216, 203, 176),
    "eagle": (90, 70, 50),
    "rabbit": (217, 212, 206),
}
BACKGROUND_SIZE = (2560, 1440)
DECOR_COLORS = {
    "nest": ((190, 225, 240), (150, 115, 80)),
    "clearing": ((185, 230, 235), (120, 190, 100)),
    "big_tree": ((180, 225, 225), (95, 165, 85)),
    "undergrowth": ((200, 225, 210), (90, 140, 90)),
    "forest_night": ((45, 55, 95), (40, 70, 60)),
    "riverbank": ((190, 225, 245), (110, 180, 215)),
    "river_rocks": ((195, 225, 240), (140, 150, 160)),
    "rocky_slope": ((200, 220, 240), (160, 145, 130)),
    "snowy_peak": ((210, 230, 250), (240, 245, 250)),
}


# --- Outils -----------------------------------------------------------------------


def load_font(root: Path, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    path = root / FONT_FILE
    if path.is_file():
        font = ImageFont.truetype(str(path), size)
        try:
            font.set_variation_by_name("SemiBold")
        except (OSError, ValueError, AttributeError):
            pass
        return font
    return ImageFont.load_default(size=size)


def _canvas(size: tuple[int, int]) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGBA", size, CLEAR)
    return img, ImageDraw.Draw(img)


def _label(draw: ImageDraw.ImageDraw, root: Path, text: str, xy: tuple[int, int], size: int, fill=INK) -> None:
    draw.text(xy, text, font=load_font(root, size), fill=fill, anchor="mm")


def _rgba(rgb: tuple[int, int, int], a: int = 255) -> tuple[int, int, int, int]:
    return (*rgb, a)


# --- Bongo ------------------------------------------------------------------------------


def draw_bongo_body(root: Path, pose: str) -> Image.Image:
    img, d = _canvas(BONGO_CANVAS)
    dy = LOW_POSES.get(pose, 0)
    cx = BONGO_CANVAS[0] // 2
    # Corps et ventre
    d.ellipse((170, 380 + dy, 530, 880), fill=FUR)
    d.ellipse((250, 470 + dy, 450, 800), fill=SKIN)
    # Bras
    arm = {"width": 70, "fill": FUR}
    if pose == "arms_up":
        d.line((210, 470 + dy, 90, 250 + dy), **arm)
        d.line((490, 470 + dy, 610, 250 + dy), **arm)
    elif pose in ("drum_a", "drum_b"):
        spread = 0 if pose == "drum_a" else 50
        d.line((200, 470 + dy, 290 - spread, 560 + dy), **arm)
        d.line((500, 470 + dy, 410 + spread, 560 + dy), **arm)
        for x in (290 - spread, 410 + spread):
            d.ellipse((x - 40, 520 + dy, x + 40, 600 + dy), fill=SKIN)
    elif pose == "point":
        d.line((200, 470 + dy, 140, 760), **arm)
        d.line((500, 470 + dy, 660, 430 + dy), **arm)
        d.ellipse((630, 400 + dy, 690, 460 + dy), fill=SKIN)
    elif pose == "sleep":
        d.line((200, 500 + dy, 330, 640 + dy), **arm)
        d.line((500, 500 + dy, 370, 640 + dy), **arm)
    else:  # stand, crouch
        d.line((200, 470 + dy, 140, 780), **arm)
        d.line((500, 470 + dy, 560, 780), **arm)
    # Tête (environ un tiers de la hauteur) et visage
    d.ellipse((180, 80 + dy, 520, 420 + dy), fill=FUR)
    d.ellipse((235, 170 + dy, 465, 400 + dy), fill=SKIN)
    # Écharpe de feuilles
    for i, x in enumerate(range(215, 500, 45)):
        d.ellipse((x, 405 + dy + (i % 2) * 10, x + 60, 455 + dy + (i % 2) * 10), fill=SCARF)
    _label(d, root, f"BONGO · {pose}", (cx, 860), 28, WHITE)
    return img


def draw_bongo_eyes(variant: str) -> Image.Image:
    img, d = _canvas(EYES_SIZE)
    for cx in (90, 210):
        box = (cx - 45, 15, cx + 45, 105)
        if variant == "closed":
            d.arc(box, 20, 160, fill=INK, width=8)
            continue
        d.ellipse(box, fill=WHITE, outline=INK, width=4)
        px = {"left": -20, "right": 20}.get(variant, 0)
        d.ellipse((cx + px - 22, 38, cx + px + 22, 82), fill=INK)
        d.ellipse((cx + px - 2, 44, cx + px + 10, 56), fill=WHITE)
        if variant == "half":
            d.pieslice(box, 180, 360, fill=FUR)
            d.line((cx - 45, 60, cx + 45, 60), fill=INK, width=4)
    return img


def draw_bongo_brows(variant: str) -> Image.Image:
    img, d = _canvas(BROWS_SIZE)
    y = 10 if variant == "surprised" else 30
    for cx in (90, 210):
        d.arc((cx - 50, y, cx + 50, y + 50), 200, 340, fill=INK, width=10)
    return img


def draw_bongo_mouth(root: Path, shape: str) -> Image.Image:
    """Formes de Rhubarb : A (M/B/P), B (dents), C (E), D (A ouvert), E (O), F (OU), G (F/V), H (L), X (repos)."""
    img, d = _canvas(MOUTH_SIZE)
    mouth = (120, 50, 60, 255)
    if shape in ("A", "X"):
        d.line((40, 50, 120, 50), fill=INK, width=8)
    elif shape == "B":
        d.rounded_rectangle((35, 35, 125, 65), 12, fill=mouth)
        d.rectangle((45, 38, 115, 48), fill=WHITE)
    elif shape == "C":
        d.ellipse((35, 25, 125, 75), fill=mouth)
    elif shape == "D":
        d.ellipse((30, 10, 130, 92), fill=mouth)
        d.ellipse((55, 60, 105, 88), fill=(220, 110, 120, 255))
    elif shape == "E":
        d.ellipse((50, 20, 110, 80), fill=mouth)
    elif shape == "F":
        d.ellipse((62, 32, 98, 68), fill=mouth, outline=INK, width=4)
    elif shape == "G":
        d.rounded_rectangle((40, 40, 120, 70), 10, fill=mouth)
        d.rectangle((50, 40, 110, 50), fill=WHITE)
    elif shape == "H":
        d.ellipse((35, 25, 125, 75), fill=mouth)
        d.ellipse((60, 25, 100, 50), fill=(220, 110, 120, 255))
    _label(d, root, shape, (150, 12), 14)
    return img


def bongo_rig() -> dict:
    faces = {}
    for pose in BONGO_POSES:
        dy = LOW_POSES.get(pose, 0)
        faces[pose] = {k: [x, y + dy] for k, (x, y) in BONGO_FACE.items()}
    return {
        "canvas": list(BONGO_CANVAS),
        "feet": list(BONGO_FEET),
        "neck": [BONGO_CANVAS[0] // 2, 420],
        "layers_centered_on_anchor": True,
        "face": faces,
        "eyes_closed_in": ["sleep"],
    }


# --- Amis ---------------------------------------------------------------------------------


def draw_friend_pose(root: Path, name: str, pose: str) -> Image.Image:
    img, d = _canvas(FRIEND_CANVAS)
    color = _rgba(FRIEND_COLORS.get(name, (180, 180, 180)))
    dy = -40 if pose == "pose_2" else 0
    d.ellipse((90, 170 + dy, 410, 490 + dy), fill=color, outline=INK, width=5)
    d.ellipse((150, 60 + dy, 350, 260 + dy), fill=color, outline=INK, width=5)
    _label(d, root, name, (250, 380 + dy), 44, INK)
    if pose == "pose_2":
        d.line((100, 300 + dy, 30, 200 + dy), fill=color, width=30)
        d.line((400, 300 + dy, 470, 200 + dy), fill=color, width=30)
    return img


def draw_friend_eyes(variant: str) -> Image.Image:
    img, d = _canvas(FRIEND_EYES_SIZE)
    for cx in (60, 140):
        box = (cx - 30, 10, cx + 30, 70)
        if variant == "eyes_closed":
            d.arc(box, 20, 160, fill=INK, width=6)
        else:
            d.ellipse(box, fill=WHITE, outline=INK, width=3)
            d.ellipse((cx - 14, 26, cx + 14, 54), fill=INK)
    return img


def draw_friend_mouth(variant: str) -> Image.Image:
    img, d = _canvas(FRIEND_MOUTH_SIZE)
    mouth = (120, 50, 60, 255)
    if variant == "mouth_closed":
        d.line((25, 40, 95, 40), fill=INK, width=6)
    elif variant == "mouth_half":
        d.ellipse((30, 25, 90, 55), fill=mouth)
    else:
        d.ellipse((25, 8, 95, 72), fill=mouth)
    return img


def friend_rig() -> dict:
    face = {"eyes": [250, 140], "mouth": [250, 220]}
    return {
        "canvas": list(FRIEND_CANVAS),
        "feet": list(FRIEND_FEET),
        "layers_centered_on_anchor": True,
        "face": {"pose_1": face, "pose_2": {k: [x, y - 40] for k, (x, y) in face.items()}},
    }


# --- Décors et cartes ---------------------------------------------------------------------------


def draw_background(root: Path, decor: str) -> Image.Image:
    sky, ground = DECOR_COLORS.get(decor, ((200, 225, 240), (130, 180, 110)))
    w, h = BACKGROUND_SIZE
    img = Image.new("RGB", BACKGROUND_SIZE, sky)
    d = ImageDraw.Draw(img)
    d.rectangle((0, int(h * 0.68), w, h), fill=ground)
    # Quelques formes douces pour voir le zoom et les panoramiques
    for i, x in enumerate(range(150, w, 420)):
        r = 120 + (i % 3) * 40
        d.ellipse((x - r, int(h * 0.68) - r, x + r, int(h * 0.68) + r // 2), fill=tuple(max(0, c - 25) for c in ground))
    if decor == "forest_night":
        d.ellipse((w - 500, 120, w - 300, 320), fill=(245, 240, 200))
    _label(d, root, f"{decor} (provisoire)", (w // 2, 140), 90, (60, 60, 70))
    return img


def draw_card(root: Path, word: str) -> Image.Image:
    img, d = _canvas((800, 800))
    hue = int(hashlib.sha1(word.encode()).hexdigest()[:6], 16)
    color = (150 + hue % 90, 150 + (hue >> 8) % 90, 150 + (hue >> 16) % 90, 255)
    d.rounded_rectangle((20, 20, 780, 780), 80, fill=color, outline=INK, width=8)
    size = 300 if len(word) <= 4 else max(110, int(1250 / len(word)))
    _label(d, root, word, (400, 380), size, WHITE)
    _label(d, root, "image provisoire", (400, 700), 40, INK)
    return img


# --- Génération --------------------------------------------------------------------------------


def _jobs(root: Path, curriculum: Curriculum) -> list[tuple[Path, Callable[[], object]]]:
    jobs: list[tuple[Path, Callable[[], object]]] = []
    bongo = Path("assets/characters/bongo")
    for pose in BONGO_POSES:
        jobs.append((bongo / "body" / f"{pose}.png", lambda p=pose: draw_bongo_body(root, p)))
    for eye in BONGO_EYES:
        jobs.append((bongo / "eyes" / f"{eye}.png", lambda e=eye: draw_bongo_eyes(e)))
    for brow in BONGO_BROWS:
        jobs.append((bongo / "brows" / f"{brow}.png", lambda b=brow: draw_bongo_brows(b)))
    for shape in BONGO_MOUTHS:
        jobs.append((bongo / "mouth" / f"{shape}.png", lambda s=shape: draw_bongo_mouth(root, s)))
    jobs.append((bongo / "rig.json", bongo_rig))
    for name in curriculum.all_friends():
        base = Path("assets/characters") / name
        for pose in ("pose_1", "pose_2"):
            jobs.append((base / f"{pose}.png", lambda n=name, p=pose: draw_friend_pose(root, n, p)))
        for eye in ("eyes_open", "eyes_closed"):
            jobs.append((base / f"{eye}.png", lambda e=eye: draw_friend_eyes(e)))
        for mouth in ("mouth_closed", "mouth_half", "mouth_open"):
            jobs.append((base / f"{mouth}.png", lambda m=mouth: draw_friend_mouth(m)))
        jobs.append((base / "rig.json", friend_rig))
    for biome, decors in curriculum.backgrounds_by_biome().items():
        for decor in decors:
            folder = COMMON_BIOME if decor == "nest" else biome
            jobs.append((Path("assets/backgrounds") / folder / f"{decor}.png", lambda dc=decor: draw_background(root, dc)))
    for word in dict.fromkeys(curriculum.all_words()):
        jobs.append((card_path(word), lambda w=word: draw_card(root, w)))
    # Dédoublonnage (le nid est commun à tous les milieux)
    return list({str(rel): (rel, fn) for rel, fn in jobs}.values())


def _fingerprint(path: Path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()


def generate_placeholders(root: Path, curriculum: Curriculum, force: bool = False) -> dict[str, int]:
    """Crée les assets provisoires manquants. Renvoie les compteurs created / kept / replaced."""
    manifest_path = root / PLACEHOLDER_MANIFEST
    manifest: dict[str, str] = {}
    if manifest_path.is_file():
        for line in manifest_path.read_text(encoding="utf-8").splitlines():
            rel, _, digest = line.strip().partition(" ")
            if rel:
                manifest[rel] = digest
    stats = {"created": 0, "kept": 0, "replaced": 0}
    for rel, make in _jobs(root, curriculum):
        key = rel.as_posix()
        target = root / rel
        if target.exists():
            ours = key in manifest and _fingerprint(target) == manifest[key]
            if not (force and ours):
                stats["kept"] += 1
                if not ours:
                    manifest.pop(key, None)  # vrai dessin : ce n'est plus un provisoire
                continue
            stats["replaced"] += 1
        else:
            stats["created"] += 1
        target.parent.mkdir(parents=True, exist_ok=True)
        result = make()
        if isinstance(result, dict):
            target.write_text(json.dumps(result, indent=2), encoding="utf-8")
        else:
            result.save(target)
        manifest[key] = _fingerprint(target)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        "".join(f"{rel} {digest}\n" for rel, digest in sorted(manifest.items())), encoding="utf-8"
    )
    return stats


def count_placeholders_in_use(root: Path) -> int:
    """Nombre d'assets encore provisoires (fichier identique à celui généré)."""
    path = root / PLACEHOLDER_MANIFEST
    if not path.is_file():
        return 0
    n = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        rel, _, digest = line.strip().partition(" ")
        target = root / rel
        if rel and target.is_file() and _fingerprint(target) == digest:
            n += 1
    return n
