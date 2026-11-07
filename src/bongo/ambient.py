"""Petite vie des décors, lente et douce : nuages, feuilles qui tombent, papillons, lucioles, neige.
Tout est calculé à partir du temps (pas d'état) : reproductible et compatible avec le rendu en parallèle.
Aucun clignotement : les lucioles brillent de façon continue."""

from __future__ import annotations

import math
import random

from PIL import Image

from bongo.art.pen import INK, Pen, shade

EFFECTS = {
    "nest": ("clouds", "leaves"),
    "clearing": ("clouds", "butterflies"),
    "big_tree": ("clouds", "leaves"),
    "undergrowth": ("leaves", "butterflies"),
    "forest_night": ("fireflies",),
    "riverbank": ("clouds", "butterflies"),
    "river_rocks": ("clouds",),
    "rocky_slope": ("clouds", "butterflies"),
    "snowy_peak": ("clouds", "snow"),
}


def _cloud_sprite(scale: float) -> Image.Image:
    p = Pen((int(300 * scale), int(140 * scale)))
    for dx, dy, r in ((80, 85, 48), (135, 60, 62), (195, 78, 52), (240, 95, 36), (150, 100, 50)):
        p.circle(dx * scale, dy * scale, r * scale, (255, 255, 255, 235), width=0)
    return p.done()


def _leaf_sprites(scale: float) -> list[Image.Image]:
    out = []
    for color in ((120, 190, 90, 255), (232, 176, 72, 255)):
        p = Pen((int(70 * scale), int(70 * scale)))
        p.leaf(35 * scale, 35 * scale, 56 * scale, 26 * scale, 0, color, width=2.5 * scale)
        base = p.done()
        out += [base.rotate(a, resample=Image.BICUBIC) for a in range(0, 360, 30)]
    return out


def _butterfly(scale: float, open_: float, color) -> Image.Image:
    p = Pen((int(80 * scale), int(60 * scale)))
    w = 26 * scale * (0.35 + 0.65 * open_)
    cx, cy = 40 * scale, 30 * scale
    for sx in (-1, 1):
        p.ellipse((cx + sx * 2 * scale - (w if sx < 0 else 0), cy - 22 * scale,
                   cx + sx * 2 * scale + (w if sx > 0 else 0), cy + 4 * scale), color, width=2.5 * scale)
        p.ellipse((cx - (w * 0.7 if sx < 0 else 0), cy, cx + (w * 0.7 if sx > 0 else 0), cy + 18 * scale),
                  shade(color, 0.85), width=2.5 * scale)
    p.capsule((cx, cy - 16 * scale), (cx, cy + 16 * scale), 3.5 * scale, INK, width=0)
    return p.done()


class Ambient:
    def __init__(self, decor: str, seed: int, W: int, H: int):
        self.W, self.H = W, H
        self.effects = EFFECTS.get(decor, ())
        self.s = H / 1080
        rng = random.Random(seed)
        self.clouds = [(rng.uniform(0, 1), rng.uniform(0.04, 0.2), rng.uniform(10, 18), rng.uniform(0.7, 1.1))
                       for _ in range(3)]
        self.leaves = [(rng.uniform(0, 1), rng.uniform(0, 30), rng.uniform(28, 45), rng.uniform(0.5, 1.2), rng.randrange(24))
                       for _ in range(5)]
        self.flies = [(rng.uniform(0, 6.28), rng.uniform(0.1, 0.9), rng.uniform(0.15, 0.6)) for _ in range(16)]
        self.flakes = [(rng.uniform(0, 1), rng.uniform(0, 30), rng.uniform(30, 60), rng.uniform(2.5, 5.5)) for _ in range(70)]
        colors = ((246, 150, 180, 255), (250, 210, 80, 255), (150, 190, 250, 255))
        self.butterflies = [(rng.uniform(0, 6.28), rng.uniform(0.15, 0.85), rng.uniform(0.35, 0.6), colors[i % 3])
                            for i in range(2)]
        self._cloud = {}
        self._leaves = None
        self._bfly = {}
        self._glow = None

    def draw(self, frame: Image.Image, t: float) -> None:
        W, H, s = self.W, self.H, self.s
        if "clouds" in self.effects:
            for x0, y, speed, k in self.clouds:
                if k not in self._cloud:
                    self._cloud[k] = _cloud_sprite(k * s * 1.6)
                spr = self._cloud[k]
                span = W + spr.width
                x = (x0 * span + speed * s * t) % span - spr.width
                frame.paste(spr, (int(x), int(y * H)), spr)
        if "leaves" in self.effects:
            self._leaves = self._leaves or _leaf_sprites(s)
            for x0, off, fall, sway, idx in self.leaves:
                cycle = (H + 100 * s) / (fall * s)
                tt = (t + off) % cycle
                y = -60 * s + tt * fall * s
                x = x0 * W + math.sin(tt * sway) * 60 * s
                spr = self._leaves[(idx + int(tt * 1.5)) % len(self._leaves)]
                frame.paste(spr, (int(x), int(y)), spr)
        if "snow" in self.effects:
            from PIL import ImageDraw

            d = ImageDraw.Draw(frame)
            for x0, off, fall, r in self.flakes:
                cycle = (H + 20) / (fall * s)
                tt = (t + off) % cycle
                y = -10 + tt * fall * s
                x = (x0 * W + math.sin(tt * 0.8 + x0 * 9) * 30 * s) % W
                rr = r * s
                d.ellipse((x - rr, y - rr, x + rr, y + rr), fill=(255, 255, 255))
        if "fireflies" in self.effects:
            if self._glow is None:
                p = Pen((int(36 * s), int(36 * s)))
                p.circle(18 * s, 18 * s, 16 * s, (255, 240, 150, 90), width=0)
                p.circle(18 * s, 18 * s, 6 * s, (255, 250, 200, 255), width=0)
                self._glow = p.done()
            for ph, x0, y0 in self.flies:
                x = (x0 + 0.04 * math.sin(t * 0.3 + ph)) * W
                y = (0.45 + y0 * 0.45 + 0.03 * math.sin(t * 0.45 + ph * 2)) * H
                frame.paste(self._glow, (int(x), int(y)), self._glow)
        if "butterflies" in self.effects:
            for ph, x0, y0, color in self.butterflies:
                x = (x0 + 0.1 * math.sin(t * 0.25 + ph)) * W
                y = (y0 + 0.06 * math.sin(t * 0.5 + ph * 1.7)) * H
                open_ = round(0.5 + 0.5 * math.sin(t * 2 * math.pi * 1.2 + ph), 1)
                key = (color, open_)
                if key not in self._bfly:
                    self._bfly[key] = _butterfly(s * 1.2, open_, color)
                spr = self._bfly[key]
                frame.paste(spr, (int(x), int(y)), spr)
