"""Outils de tracé : on dessine en double résolution puis on réduit, pour des bords lisses."""

from __future__ import annotations

import math

from PIL import Image, ImageDraw

SS = 2  # suréchantillonnage
INK = (43, 45, 58, 255)
WHITE = (255, 255, 255, 255)
CLEAR = (0, 0, 0, 0)
LINE = 5  # épaisseur du contour, en pixels de l'image finale


def rgba(c, a: int = 255):
    return c if len(c) == 4 else (*c, a)


def shade(c, k: float):
    """Variante plus foncée (k < 1) ou plus claire (k > 1) d'une couleur, sans dégradé."""
    r, g, b = c[:3]
    if k < 1:
        return (int(r * k), int(g * k), int(b * k), 255)
    return (int(r + (255 - r) * (k - 1)), int(g + (255 - g) * (k - 1)), int(b + (255 - b) * (k - 1)), 255)


class Pen:
    """Toile RGBA en coordonnées finales ; tout est multiplié par SS en interne."""

    def __init__(self, size, background=CLEAR):
        self.size = size
        self.img = Image.new("RGBA", (size[0] * SS, size[1] * SS), background)
        self.d = ImageDraw.Draw(self.img)

    # conversions
    def _p(self, pts):
        return [(x * SS, y * SS) for x, y in pts]

    def _w(self, w):
        return max(1, int(round(w * SS)))

    def done(self) -> Image.Image:
        return self.img.resize(self.size, Image.LANCZOS)

    # formes
    def ellipse(self, box, fill, outline=INK, width=LINE):
        x0, y0, x1, y1 = box
        self.d.ellipse([x0 * SS, y0 * SS, x1 * SS, y1 * SS], fill=rgba(fill) if fill else None,
                       outline=outline if width else None, width=self._w(width) if width else 0)

    def circle(self, cx, cy, r, fill, outline=INK, width=LINE):
        self.ellipse((cx - r, cy - r, cx + r, cy + r), fill, outline, width)

    def poly(self, pts, fill, outline=INK, width=LINE):
        pts = self._p(pts)
        self.d.polygon(pts, fill=rgba(fill) if fill else None)
        if width and outline:
            self.d.line(pts + [pts[0]], fill=outline, width=self._w(width), joint="curve")

    def line(self, pts, color=INK, width=LINE, round_caps=True):
        p = self._p(pts)
        self.d.line(p, fill=rgba(color), width=self._w(width), joint="curve")
        if round_caps:
            r = self._w(width) / 2
            for x, y in (p[0], p[-1]):
                self.d.ellipse([x - r, y - r, x + r, y + r], fill=rgba(color))

    def rect(self, box, fill, radius=0, outline=INK, width=LINE):
        x0, y0, x1, y1 = box
        self.d.rounded_rectangle([x0 * SS, y0 * SS, x1 * SS, y1 * SS], radius=radius * SS,
                                 fill=rgba(fill) if fill else None, outline=outline if width else None,
                                 width=self._w(width) if width else 0)

    def arc(self, box, start, end, color=INK, width=LINE):
        x0, y0, x1, y1 = box
        self.d.arc([x0 * SS, y0 * SS, x1 * SS, y1 * SS], start, end, fill=rgba(color), width=self._w(width))

    def capsule(self, a, b, r, fill, outline=INK, width=LINE):
        """Membre arrondi (bras, jambe) de a vers b."""
        (x0, y0), (x1, y1) = a, b
        ang = math.atan2(y1 - y0, x1 - x0)
        pts = []
        for i in range(13):  # demi-cercle côté b
            t = ang - math.pi / 2 + math.pi * i / 12
            pts.append((x1 + math.cos(t) * r, y1 + math.sin(t) * r))
        for i in range(13):  # demi-cercle côté a
            t = ang + math.pi / 2 + math.pi * i / 12
            pts.append((x0 + math.cos(t) * r, y0 + math.sin(t) * r))
        self.poly(pts, fill, outline, width)

    def limb(self, pts, r, fill, outline=INK, width=LINE):
        """Membre coudé : suite de capsules, contour d'abord, remplissage ensuite (joint propre)."""
        for a, b in zip(pts, pts[1:]):
            self.capsule(a, b, r + width / 2, outline, None, 0)
        for a, b in zip(pts, pts[1:]):
            self.capsule(a, b, r - width / 2, fill, None, 0)

    def blob(self, cx, cy, rx, ry, fill, outline=INK, width=LINE, squash=0.0, n=48):
        """Ellipse légèrement en poire (squash > 0 : plus large en bas)."""
        pts = []
        for i in range(n):
            t = 2 * math.pi * i / n
            s = math.sin(t)
            k = 1 + squash * s
            pts.append((cx + math.cos(t) * rx * k, cy + s * ry))
        self.poly(pts, fill, outline, width)

    def leaf(self, cx, cy, length, wide, angle, fill, vein=True, outline=INK, width=LINE * 0.7):
        """Feuille pointue orientée selon `angle` (degrés)."""
        a = math.radians(angle)
        pts = []
        for i in range(25):
            t = i / 24
            x = (t - 0.5) * length
            y = math.sin(math.pi * t) * wide / 2
            pts.append((x, y))
        for i in range(24, -1, -1):
            t = i / 24
            pts.append(((t - 0.5) * length, -math.sin(math.pi * t) * wide / 2))
        rot = [(cx + x * math.cos(a) - y * math.sin(a), cy + x * math.sin(a) + y * math.cos(a)) for x, y in pts]
        self.poly(rot, fill, outline, width)
        if vein:
            p0 = (cx - math.cos(a) * length * 0.42, cy - math.sin(a) * length * 0.42)
            p1 = (cx + math.cos(a) * length * 0.42, cy + math.sin(a) * length * 0.42)
            self.line([p0, p1], shade(fill, 0.7), width * 0.6)

    def star(self, cx, cy, r, fill, points=5, inner=0.45, outline=INK, width=LINE * 0.6):
        pts = []
        for i in range(points * 2):
            rr = r if i % 2 == 0 else r * inner
            t = -math.pi / 2 + math.pi * i / points
            pts.append((cx + math.cos(t) * rr, cy + math.sin(t) * rr))
        self.poly(pts, fill, outline, width)


def rotate_points(pts, cx, cy, deg):
    a = math.radians(deg)
    ca, sa = math.cos(a), math.sin(a)
    return [(cx + (x - cx) * ca - (y - cy) * sa, cy + (x - cx) * sa + (y - cy) * ca) for x, y in pts]
