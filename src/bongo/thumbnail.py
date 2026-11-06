"""Miniature 1280x720 : décor, Bongo bras levés, l'ami du jour, les mots du jour en gros."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from bongo.assets import find_background
from bongo.curriculum import Episode
from bongo.errors import BongoError
from bongo.render import CharacterArt

SIZE = (1280, 720)
TEXT_FILL = (255, 255, 255)
TEXT_STROKE = (45, 50, 70)


def _font(root: Path, size: int):
    from bongo.placeholders import load_font

    font = load_font(root, size)
    try:
        font.set_variation_by_name("Bold")
    except (OSError, ValueError, AttributeError):
        pass
    return font


def thumbnail_words(episode: Episode, title: str) -> str:
    if episode.is_review:
        return title
    return "  ".join(episode.new_words)


def _backdrop(root: Path, episode: Episode) -> Image.Image:
    W, H = SIZE
    decor = next((b for b in episode.backgrounds if b != "nest"), episode.backgrounds[0])
    bg_path = find_background(root, episode.biome, decor)
    if bg_path is None:
        raise BongoError(f"Décor manquant pour la miniature : {decor}. Lance `python -m bongo placeholders`.")
    bg = Image.open(bg_path).convert("RGB")
    scale = max(W / bg.width, H / bg.height)
    bg = bg.resize((round(bg.width * scale), round(bg.height * scale)), Image.LANCZOS)
    left, top = (bg.width - W) // 2, (bg.height - H) // 2
    return bg.crop((left, top, left + W, top + H))


def _big_text(root: Path, img: Image.Image, text: str) -> None:
    W, H = SIZE
    draw = ImageDraw.Draw(img)
    size = 150
    while size > 50:
        font = _font(root, size)
        box = draw.textbbox((0, 0), text, font=font, stroke_width=size // 12)
        if box[2] - box[0] <= W * 0.92:
            break
        size -= 8
    draw.text((W / 2, H * 0.14), text, font=font, fill=TEXT_FILL, anchor="mm",
              stroke_width=max(4, size // 12), stroke_fill=TEXT_STROKE)


def make_compilation_thumbnail(root: Path, episodes: list[Episode], title: str, out: Path) -> Path:
    """Bongo au centre, jusqu'à 4 amis de la période autour de lui, le titre en gros."""
    W, H = SIZE
    img = _backdrop(root, episodes[-1])
    ground = H * 0.99
    friends = list(dict.fromkeys(f for ep in episodes for f in ep.friends))[:4]
    for name, x in zip(friends, (0.12, 0.88, 0.27, 0.73)):
        art = CharacterArt(root, name, H * 0.34)
        sprite, (fx, fy) = art.sprite("pose_2", "eyes_open", "neutral", "mouth_open", 0)
        img.paste(sprite, (round(W * x - fx), round(ground - fy)), sprite)
    bongo = CharacterArt(root, "bongo", H * 0.74)
    sprite, (fx, fy) = bongo.sprite("arms_up", "open", "surprised", "B", 0)
    img.paste(sprite, (round(W * 0.5 - fx), round(ground - fy)), sprite)
    _big_text(root, img, title)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, optimize=True)
    return out


def make_thumbnail(root: Path, episode: Episode, title: str, out: Path) -> Path:
    W, H = SIZE
    img = _backdrop(root, episode)

    ground = H * 0.99
    bongo = CharacterArt(root, "bongo", H * 0.80)
    sprite, (fx, fy) = bongo.sprite("arms_up", "open", "surprised", "B", 0)
    img.paste(sprite, (round(W * 0.30 - fx), round(ground - fy)), sprite)
    if episode.friends:
        friend = CharacterArt(root, episode.friends[0], H * 0.45)
        sprite, (fx, fy) = friend.sprite("pose_2", "eyes_open", "neutral", "mouth_open", 0)
        img.paste(sprite, (round(W * 0.74 - fx), round(ground - fy)), sprite)

    _big_text(root, img, thumbnail_words(episode, title))
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, optimize=True)
    return out
