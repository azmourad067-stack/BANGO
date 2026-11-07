"""Dessins et sons générés par le programme (personnages, décors, cartes-mots, musique provisoire).

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

INK = (40, 40, 48, 255)
WHITE = (255, 255, 255, 255)
CLEAR = (0, 0, 0, 0)

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


# --- Sons provisoires (synthèse simple, aucune IA) ---------------------------------------------------

AUDIO_RATE = 48_000
MUSIC_KEYS = {"jungle": 0, "forest": -3, "river": 2, "mountain": -5}


def _note(freq: float, dur: float, decay: float, rate: int = AUDIO_RATE) -> "np.ndarray":
    import numpy as np

    t = np.arange(int(dur * rate)) / rate
    env = np.exp(-t / decay) * np.minimum(1, t / 0.01)
    return (np.sin(2 * np.pi * freq * t) + 0.25 * np.sin(4 * np.pi * freq * t)) * env


def synth_music(biome: str, rate: int = AUDIO_RATE):
    """Boucle douce de 24 s : nappe lente et arpège pentatonique (calme, sans percussion)."""
    import numpy as np

    shift = MUSIC_KEYS.get(biome, 0)
    bpm, bars = 80, 8
    beat = 60 / bpm
    total = int(bars * 4 * beat * rate)
    out = np.zeros(total)
    root_freq = 261.63 * 2 ** (shift / 12)
    chords = [(0, 4, 7), (-3, 0, 4), (-7, -3, 0), (-5, -1, 2)]  # I vi IV V
    penta = [0, 2, 4, 7, 9, 12]
    for bar in range(bars):
        chord = chords[bar % 4]
        start = int(bar * 4 * beat * rate)
        length = int(4 * beat * rate)
        t = np.arange(length) / rate
        pad_env = np.minimum(1, t / 0.8) * np.minimum(1, (length / rate - t) / 0.8)
        for semi in chord:
            f = root_freq / 2 * 2 ** (semi / 12)
            out[start : start + length] += 0.12 * np.sin(2 * np.pi * f * t) * pad_env
        for step in range(8):
            semi = chord[0] + penta[(bar * 3 + step * 2) % len(penta)]
            note = _note(root_freq * 2 ** (semi / 12), beat, 0.35, rate) * 0.18
            a = start + int(step * beat / 2 * rate)
            out[a : a + len(note)] += note[: total - a]
    out /= max(1e-9, np.abs(out).max()) / 0.5
    return np.stack([out, out], axis=1)


def synth_sfx(name: str, rate: int = AUDIO_RATE):
    import numpy as np

    if name == "card":  # petit carillon
        a = _note(880, 0.35, 0.12, rate)
        b = _note(1318.5, 0.45, 0.15, rate)
        out = np.zeros(int(0.5 * rate))
        out[: len(a)] += a
        out[int(0.07 * rate) : int(0.07 * rate) + len(b)] += b[: len(out) - int(0.07 * rate)]
    elif name == "jump":  # « boing » doux
        t = np.arange(int(0.35 * rate)) / rate
        freq = 260 + 280 * t / t[-1]
        out = np.sin(2 * np.pi * np.cumsum(freq) / rate) * np.exp(-t / 0.12) * np.minimum(1, t / 0.01)
    else:  # tambour sur la poitrine
        t = np.arange(int(0.3 * rate)) / rate
        out = np.sin(2 * np.pi * (70 + 40 * np.exp(-t / 0.03)) * t) * np.exp(-t / 0.08)
    out = out / np.abs(out).max() * 0.6
    return np.stack([out, out], axis=1)


def write_wav_stereo(path: Path, audio, rate: int = AUDIO_RATE) -> None:
    import wave

    import numpy as np

    pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(pcm.tobytes())


# --- Génération --------------------------------------------------------------------------------


def _jobs(root: Path, curriculum: Curriculum) -> list[tuple[Path, Callable[[], object]]]:
    from bongo.art import cards, friends, gorilla, scenes

    jobs: list[tuple[Path, Callable[[], object]]] = []
    bongo = Path("assets/characters/bongo")
    for pose in BONGO_POSES:
        jobs.append((bongo / "body" / f"{pose}.png", lambda p=pose: gorilla.draw_body(p)))
    for eye in BONGO_EYES:
        jobs.append((bongo / "eyes" / f"{eye}.png", lambda e=eye: gorilla.draw_eyes(e)))
    for brow in BONGO_BROWS:
        jobs.append((bongo / "brows" / f"{brow}.png", lambda b=brow: gorilla.draw_brows(b)))
    for shape in BONGO_MOUTHS:
        jobs.append((bongo / "mouth" / f"{shape}.png", lambda m=shape: gorilla.draw_mouth(m)))
    jobs.append((bongo / "rig.json", gorilla.rig))
    for name in curriculum.all_friends():
        base = Path("assets/characters") / name
        for pose in ("pose_1", "pose_2"):
            jobs.append((base / f"{pose}.png", lambda n=name, p=pose: friends.draw_pose(n, p)))
        for eye in ("eyes_open", "eyes_closed"):
            jobs.append((base / f"{eye}.png", lambda n=name, e=eye: friends.draw_eyes(n, e)))
        for mouth in ("mouth_closed", "mouth_half", "mouth_open"):
            jobs.append((base / f"{mouth}.png", lambda n=name, m=mouth: friends.draw_mouth(n, m)))
        jobs.append((base / "rig.json", lambda n=name: friends.rig(n)))
    for biome, decors in curriculum.backgrounds_by_biome().items():
        for decor in decors:
            folder = COMMON_BIOME if decor == "nest" else biome
            jobs.append((Path("assets/backgrounds") / folder / f"{decor}.png", lambda dc=decor: scenes.draw_background(dc)))
    for word in dict.fromkeys(curriculum.all_words()):
        jobs.append((card_path(word), lambda w=word: cards.draw_card(root, w)))
    for biome in curriculum.backgrounds_by_biome():
        jobs.append((Path("assets/audio/music") / f"{biome}.wav", lambda b=biome: ("wav", synth_music(b))))
    for name in ("card", "jump", "drum"):
        jobs.append((Path("assets/audio/sfx") / f"{name}.wav", lambda n=name: ("wav", synth_sfx(n))))
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
        elif isinstance(result, tuple) and result[0] == "wav":
            write_wav_stereo(target, result[1])
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


def placeholder_paths(root: Path) -> set[str]:
    """Chemins (relatifs) des fichiers encore provisoires."""
    path = root / PLACEHOLDER_MANIFEST
    if not path.is_file():
        return set()
    result = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        rel, _, digest = line.strip().partition(" ")
        target = root / rel
        if rel and target.is_file() and _fingerprint(target) == digest:
            result.add(rel)
    return result
