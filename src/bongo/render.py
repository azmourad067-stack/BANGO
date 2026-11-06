"""Rendu de l'image : assemblage des calques (Pillow) et encodage H.264 (FFmpeg par un tube).

1920x1080, 24 images/s. Calques mis en cache. Respiration au repos (+1 % sur 3 s),
fondus doux, aucun clignotement ni mouvement brusque.
"""

from __future__ import annotations

import math
import multiprocessing
import os
import shutil
import subprocess
import time
from bisect import bisect_right
from collections import OrderedDict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Callable

from PIL import Image, ImageDraw

from bongo.assets import FONT_FILE, card_path, character_layers, find_background
from bongo.config import Config
from bongo.errors import BongoError
from bongo.schema import BONGO

BREATH_PERIOD_S = 3.0
BREATH_AMPLITUDE = 0.01
BREATH_STEPS = 10           # respiration quantifiée (cache) : 0,1 % par pas
BOUNCE_PERIOD_S = 0.6
BOUNCE_HEIGHT = 0.05        # fraction de la taille du personnage
SPRITE_CACHE = 240
X264 = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p"]


def find_ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise BongoError("FFmpeg introuvable : installe-le (winget install Gyan.FFmpeg) puis relance `check-setup`.")
    return path


def _smooth(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


class _LRU(OrderedDict):
    def __init__(self, size: int):
        super().__init__()
        self.size = size

    def get_or(self, key, make):
        if key in self:
            self.move_to_end(key)
            return self[key]
        value = make()
        self[key] = value
        if len(self) > self.size:
            self.popitem(last=False)
        return value


# --- Personnages -----------------------------------------------------------------------------


class CharacterArt:
    """Calques d'un personnage et leur assemblage (avec cache)."""

    def __init__(self, root: Path, name: str, display_height: float):
        import json

        self.name = name
        self.is_bongo = name == BONGO
        self.base = root / "assets" / "characters" / name
        missing = [str(p) for p in character_layers(name) if not (root / p).is_file()]
        if missing:
            raise BongoError(
                f"Dessins manquants pour {name} ({len(missing)} fichier(s), par ex. {missing[0]}). "
                "Lance `python -m bongo placeholders` pour des dessins provisoires."
            )
        try:
            rig = json.loads((self.base / "rig.json").read_text(encoding="utf-8"))
            self.canvas = tuple(rig["canvas"])
            self.feet = tuple(rig["feet"])
            self.face = rig["face"]
            self.eyes_closed_in = set(rig.get("eyes_closed_in", []))
        except (KeyError, ValueError, TypeError) as exc:
            raise BongoError(f"{self.base / 'rig.json'} est incomplet (canvas, feet, face attendus) : {exc}") from None
        self.scale = display_height / self.canvas[1]
        self._layers: dict[str, Image.Image] = {}
        self._composed = _LRU(SPRITE_CACHE)
        self._scaled = _LRU(SPRITE_CACHE)

    def layer(self, rel: str) -> Image.Image:
        if rel not in self._layers:
            img = Image.open(self.base / f"{rel}.png").convert("RGBA")
            self._layers[rel] = img
        return self._layers[rel]

    def _paste_centered(self, canvas: Image.Image, rel: str, anchor) -> None:
        part = self.layer(rel)
        x, y = int(anchor[0] - part.width / 2), int(anchor[1] - part.height / 2)
        canvas.alpha_composite(part, dest=(max(0, x), max(0, y)),
                               source=(max(0, -x), max(0, -y)))

    def compose(self, pose: str, eyes: str, brows: str, mouth: str) -> Image.Image:
        def make() -> Image.Image:
            if self.is_bongo:
                body = self.layer(f"body/{pose}").copy()
                face = self.face.get(pose) or self.face.get("stand")
                eyes_name = "closed" if pose in self.eyes_closed_in else eyes
                self._paste_centered(body, f"eyes/{eyes_name}", face["eyes"])
                self._paste_centered(body, f"brows/{brows}", face["brows"])
                self._paste_centered(body, f"mouth/{mouth}", face["mouth"])
            else:
                body = self.layer(pose).copy()
                face = self.face.get(pose) or self.face.get("pose_1")
                self._paste_centered(body, eyes, face["eyes"])
                self._paste_centered(body, mouth, face["mouth"])
            return body

        return self._composed.get_or((pose, eyes, brows, mouth), make)

    def sprite(self, pose, eyes, brows, mouth, breath_step: int, blend_from=None, blend: float = 1.0):
        """Image mise à l'échelle et position des pieds dans cette image."""
        factor = self.scale * (1 + BREATH_AMPLITUDE * breath_step / BREATH_STEPS)
        size = (max(1, round(self.canvas[0] * factor)), max(1, round(self.canvas[1] * factor)))
        if blend_from is not None and blend < 1.0:
            mixed = Image.blend(self.compose(*blend_from), self.compose(pose, eyes, brows, mouth), blend)
            img = mixed.resize(size, Image.LANCZOS)
        else:
            img = self._scaled.get_or(
                (pose, eyes, brows, mouth, breath_step),
                lambda: self.compose(pose, eyes, brows, mouth).resize(size, Image.LANCZOS),
            )
        return img, (self.feet[0] * factor, self.feet[1] * factor)

    def rest_mouth(self) -> str:
        return "X" if self.is_bongo else "mouth_closed"

    def eyes_names(self) -> tuple[str, str, str]:
        return ("open", "half", "closed") if self.is_bongo else ("eyes_open", "eyes_closed", "eyes_closed")


# --- Rendu d'une image ------------------------------------------------------------------------------


class FrameRenderer:
    def __init__(self, root: Path, timeline: dict, config: Config):
        self.root = root
        self.tl = timeline
        self.config = config
        self.W, self.H = timeline["width"], timeline["height"]
        self.stage = config.stage
        names = sorted({c["name"] for s in timeline["scenes"] for c in s["characters"]})
        self.chars = {
            n: CharacterArt(root, n, self.H * (self.stage.bongo_height if n == BONGO else self.stage.friend_height))
            for n in names
        }
        self.backgrounds: dict[str, Image.Image] = {}
        for scene in timeline["scenes"]:
            bg = scene["background"]
            if bg in self.backgrounds:
                continue
            path = find_background(root, timeline["biome"], bg)
            if path is None:
                raise BongoError(
                    f"Décor manquant : {bg} (milieu {timeline['biome']}). "
                    "Lance `python -m bongo placeholders` ou ajoute le dessin dans assets/backgrounds/."
                )
            self.backgrounds[bg] = self._cover(Image.open(path).convert("RGB"))
        self._cards: dict[str, Image.Image] = {}
        self._black = Image.new("RGB", (self.W, self.H), (0, 0, 0))
        # Index par personnage
        self.pose_changes: dict[str, list[dict]] = {}
        for p in timeline["poses"]:
            self.pose_changes.setdefault(p["character"], []).append(p)
        self.lines_by_speaker: dict[str, list[dict]] = {}
        for line in timeline["lines"]:
            self.lines_by_speaker.setdefault(line["speaker"], []).append(line)
        self.blinks: dict[tuple[str, str], list[float]] = {}
        for b in timeline["blinks"]:
            self.blinks.setdefault((b["scene"], b["character"]), []).append(b["start"])

    # --- Décor ---
    def _cover(self, img: Image.Image) -> Image.Image:
        """Recadre au format 16:9 (sans déformer)."""
        target = self.W / self.H
        w, h = img.size
        if abs(w / h - target) < 1e-3:
            return img
        if w / h > target:
            nw = int(h * target)
            return img.crop(((w - nw) // 2, 0, (w - nw) // 2 + nw, h))
        nh = int(w / target)
        return img.crop((0, (h - nh) // 2, w, (h - nh) // 2 + nh))

    def _background(self, scene: dict, t: float) -> Image.Image:
        bg = self.backgrounds[scene["background"]]
        span = scene["end"] + self.tl["scene_fade_s"] - scene["start"]
        z = 1 + scene["zoom"] * _smooth((t - scene["start"]) / span if span > 0 else 0)
        w, h = bg.size
        cw, ch = w / z, h / z
        box = ((w - cw) / 2, (h - ch) / 2, (w + cw) / 2, (h + ch) / 2)
        return bg.resize((self.W, self.H), Image.BILINEAR, box=box, reducing_gap=2.0)

    # --- État des personnages ---
    @staticmethod
    def _active(items: list[dict], t: float) -> dict | None:
        for item in items:
            if item["start"] <= t < item.get("end", item.get("pause_end", item["start"])):
                return item
        return None

    def _pose_at(self, name: str, base: str, t: float) -> tuple[str, float | None]:
        """Pose à l'instant t, et instant du dernier changement de pose."""
        pose, changed = base, None
        for p in self.pose_changes.get(name, []):
            if p["start"] <= t < p["end"]:
                pose, changed = p["pose"], p["start"]
            elif p["end"] <= t and (changed is None or p["end"] > changed):
                changed = p["end"]
        for m in self.tl["motions"]:
            if m["character"] == name and m["start"] <= t < m["end"]:
                if m["motion"] == "drum":
                    pose, changed = "drum_a", m["start"]
                elif m["motion"] == "arms_up":
                    pose, changed = "arms_up", m["start"]
            elif m["character"] == name and m["end"] <= t and (changed is None or m["end"] > changed):
                changed = m["end"]
        return pose, changed

    def _drum(self, pose: str, since: float | None, t: float) -> str:
        if pose in ("drum_a", "drum_b") and since is not None:
            k = int((t - since) / self.tl["drum_period_s"])
            return "drum_a" if k % 2 == 0 else "drum_b"
        return pose

    def _state(self, scene: dict, name: str, base_pose: str, t: float):
        art = self.chars[name]
        pose, since = self._pose_at(name, base_pose, t)
        pose = self._drum(pose, since, t)
        blend_from, blend = None, 1.0
        if since is not None and 0 <= t - since < self.tl["pose_blend_s"]:
            prev, _ = self._pose_at(name, base_pose, since - 1e-3)
            prev = self._drum(prev, since - self.tl["drum_period_s"], since - 1e-3)
            if prev != pose and not ({prev, pose} <= {"drum_a", "drum_b"}):
                blend_from, blend = prev, _smooth((t - since) / self.tl["pose_blend_s"])
        open_, half, closed = art.eyes_names()
        eyes = open_
        if art.is_bongo:
            look = self._active(self.tl["looks"], t)
            if look:
                eyes = look["direction"]
        starts = self.blinks.get((scene["id"], name), [])
        i = bisect_right(starts, t) - 1
        if i >= 0 and t - starts[i] < self.tl["blink_s"]:
            phase = (t - starts[i]) / self.tl["blink_s"]
            eyes = closed if 0.3 <= phase < 0.7 else half
        brows = "surprised" if art.is_bongo and self._active(self.tl["brows"], t) else "neutral"
        mouth = art.rest_mouth()
        line = self._active(self.lines_by_speaker.get(name, []), t)
        if line and line["scene"] == scene["id"]:
            for cue in line.get("mouth", []):
                if cue["start"] <= t < cue["end"]:
                    mouth = cue["shape"]
                    break
        state = (pose, eyes, brows, mouth)
        prev_state = (blend_from, eyes, brows, mouth) if blend_from else None
        return state, prev_state, blend

    def _bounce(self, name: str, t: float) -> float:
        for m in self.tl["motions"]:
            if m["character"] == name and m["motion"] == "bounce" and m["start"] <= t < m["end"]:
                k = ((t - m["start"]) % BOUNCE_PERIOD_S) / BOUNCE_PERIOD_S
                return math.sin(math.pi * k)
        return 0.0

    def _draw_scene(self, scene: dict, t: float) -> Image.Image:
        frame = self._background(scene, t)
        ground = self.H * self.stage.ground
        for char in sorted(scene["characters"], key=lambda c: c["name"] == BONGO):  # Bongo devant
            name = char["name"]
            art = self.chars[name]
            state, prev_state, blend = self._state(scene, name, char["pose"], t)
            phase = (t + self.tl["breath_phase"].get(name, 0)) / BREATH_PERIOD_S
            breath = round(BREATH_STEPS * (0.5 - 0.5 * math.cos(2 * math.pi * phase)))
            img, (fx, fy) = art.sprite(*state, breath, blend_from=prev_state, blend=blend)
            x = self.W * getattr(self.config.positions, char["position"])
            lift = self._bounce(name, t) * BOUNCE_HEIGHT * img.height
            frame.paste(img, (round(x - fx), round(ground - fy - lift)), img)
        self._draw_cards(frame, t, scene)
        return frame

    # --- Cartes-mots ---
    def _card_panel(self, word: str) -> Image.Image:
        if word in self._cards:
            return self._cards[word]
        from bongo.placeholders import load_font

        ph = int(self.H * self.stage.card_height)
        pw = int(ph * 0.82)
        panel = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
        d = ImageDraw.Draw(panel)
        d.rounded_rectangle((4, 4, pw - 5, ph - 5), radius=ph // 12, fill=(255, 253, 246, 255),
                            outline=(70, 70, 80, 255), width=5)
        pic_size = int(pw * 0.80)
        path = self.root / card_path(word)
        if not path.is_file():
            raise BongoError(f"Carte-mot manquante : {card_path(word)}. Lance `python -m bongo placeholders`.")
        pic = Image.open(path).convert("RGBA")
        pic.thumbnail((pic_size, pic_size), Image.LANCZOS)
        panel.alpha_composite(pic, ((pw - pic.width) // 2, int(ph * 0.06)))
        font = load_font(self.root, int(ph * 0.15))
        d.text((pw // 2, int(ph * 0.86)), word.lower(), font=font, fill=(50, 50, 60, 255), anchor="mm")
        self._cards[word] = panel
        return panel

    def _card_x(self, scene: dict) -> float:
        """Place libre de la scène pour la carte (droite, sinon gauche, sinon centre)."""
        used = {c["position"] for c in scene["characters"]}
        for pos in ("right", "left", "center"):
            if pos not in used:
                return self.W * getattr(self.config.positions, pos)
        return self.W / 2

    def _draw_cards(self, frame: Image.Image, t: float, scene: dict) -> None:
        for card in self.tl["cards"]:
            if not card["start"] <= t < card["end"]:
                continue
            fade = self.tl["card_fade_s"]
            a = min(_smooth((t - card["start"]) / fade), _smooth((card["end"] - t) / fade))
            panel = self._card_panel(card["word"])
            scale = 0.92 + 0.08 * a
            if a < 1.0:
                size = (round(panel.width * scale), round(panel.height * scale))
                panel = panel.resize(size, Image.BILINEAR)
                alpha = panel.getchannel("A").point(lambda v: int(v * a))
                panel.putalpha(alpha)
            x = int(self._card_x(scene) - panel.width / 2)
            y = int(self.H * self.stage.card_top + (1 - scale) * panel.height / 2)
            frame.paste(panel, (x, y), panel)

    # --- Image finale ---
    def frame(self, t: float) -> Image.Image:
        scenes = self.tl["scenes"]
        fade = self.tl["scene_fade_s"]
        img = None
        for i, scene in enumerate(scenes):
            nxt = scenes[i + 1] if i + 1 < len(scenes) else None
            if scene["start"] <= t < scene["end"] or nxt is None:
                img = self._draw_scene(scene, t)
                break
            if nxt and scene["end"] <= t < nxt["start"]:
                a = _smooth((t - scene["end"]) / fade)
                img = Image.blend(self._draw_scene(scene, t), self._draw_scene(nxt, t), a)
                break
        edge = self.tl["edge_fade_s"]
        if t < edge:
            img = Image.blend(self._black, img, _smooth(t / edge))
        elif t > self.tl["duration_s"] - edge:
            img = Image.blend(self._black, img, _smooth((self.tl["duration_s"] - t) / edge))
        return img


# --- Encodage ----------------------------------------------------------------------------------------


def frame_count(timeline: dict) -> int:
    return max(1, math.ceil(timeline["duration_s"] * timeline["fps"]))


def _encode_range(args) -> str:
    root, timeline, config, first, last, out, ffmpeg = args
    renderer = FrameRenderer(root, timeline, config)
    cmd = [ffmpeg, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{timeline['width']}x{timeline['height']}", "-r", str(timeline["fps"]), "-i", "-",
           *X264, "-an", str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for k in range(first, last):
            proc.stdin.write(renderer.frame(k / timeline["fps"]).tobytes())
        proc.stdin.close()
    except BrokenPipeError:
        pass
    err = proc.stderr.read().decode("utf-8", "replace")
    if proc.wait() != 0:
        raise BongoError(f"FFmpeg a échoué pendant l'encodage : {err.strip()[-400:]}")
    return str(out)


def default_workers() -> int:
    return max(1, min(4, (os.cpu_count() or 2) - 1))


def render_video(
    root: Path,
    timeline: dict,
    config: Config,
    out: Path,
    workers: int | None = None,
    max_seconds: float | None = None,
    log: Callable[[str], None] = print,
) -> Path:
    """Rend la vidéo (sans le son). En parallèle par morceaux, puis assemblage sans réencodage."""
    ffmpeg = find_ffmpeg()
    FrameRenderer(root, timeline, config)  # vérifie les assets avant de lancer les processus
    total = frame_count(timeline)
    if max_seconds:
        total = min(total, int(max_seconds * timeline["fps"]))
    workers = max(1, min(workers or default_workers(), total // (timeline["fps"] * 10) or 1))
    out.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    log(f"  {total} images ({total / timeline['fps']:.0f} s de vidéo), {workers} processus…")
    if workers == 1:
        _encode_range((root, timeline, config, 0, total, out, ffmpeg))
    else:
        bounds = [round(total * i / workers) for i in range(workers + 1)]
        parts = [out.with_name(f"{out.stem}.part{i}.mp4") for i in range(workers)]
        jobs = [(root, timeline, config, bounds[i], bounds[i + 1], parts[i], ffmpeg) for i in range(workers)]
        # « spawn » partout : même comportement que sous Windows
        with ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("spawn")) as pool:
            list(pool.map(_encode_range, jobs))
        listing = out.with_name(f"{out.stem}.parts.txt")
        listing.write_text("".join(f"file '{p.name}'\n" for p in parts), encoding="utf-8")
        proc = subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                               "-i", str(listing), "-c", "copy", str(out)], capture_output=True, text=True)
        for p in [*parts, listing]:
            p.unlink(missing_ok=True)
        if proc.returncode != 0:
            raise BongoError(f"FFmpeg n'a pas pu assembler les morceaux : {proc.stderr.strip()[-400:]}")
    log(f"  Rendu terminé en {time.monotonic() - started:.0f} s.")
    return out


def mux_preview(video: Path, audio: Path, out: Path) -> Path:
    """Vidéo + voix seules (aperçu de l'étape 3 ; le vrai mixage arrive à l'étape 4)."""
    ffmpeg = find_ffmpeg()
    proc = subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", str(video), "-i", str(audio),
                           "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", str(out)],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise BongoError(f"FFmpeg n'a pas pu ajouter le son : {proc.stderr.strip()[-400:]}")
    return out


def render_still(root: Path, timeline: dict, config: Config, t: float, out: Path) -> Path:
    """Une image fixe (pour vérifier la mise en scène sans tout rendre)."""
    FrameRenderer(root, timeline, config).frame(t).save(out)
    return out
