"""Images des cartes-mots (800 x 800, fond transparent) : une image simple et claire par mot.
Le mot écrit en minuscules est ajouté par le rendu, sous l'image."""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image

from bongo.art import friends, gorilla
from bongo.art.pen import INK, WHITE, Pen, shade

SIZE = (800, 800)
C = 400
RED, YELLOW, GREEN, BLUE = (230, 70, 66, 255), (252, 206, 64, 255), (96, 182, 86, 255), (70, 140, 226, 255)
ORANGE, PURPLE, BROWN = (246, 150, 58, 255), (150, 110, 214, 255), (140, 98, 66, 255)
SKY_NIGHT, MOON = (44, 58, 110, 255), (252, 232, 150, 255)


def _fit(img: Image.Image, box: int = 700) -> Image.Image:
    bbox = img.getbbox()
    if bbox:
        img = img.crop(bbox)
    img.thumbnail((box, box), Image.LANCZOS)
    out = Image.new("RGBA", SIZE, (0, 0, 0, 0))
    out.alpha_composite(img, ((SIZE[0] - img.width) // 2, (SIZE[1] - img.height) // 2))
    return out


def friend_portrait(name: str, pose: str = "pose_1", mouth: str = "mouth_closed") -> Image.Image:
    body = friends.draw_pose(name, pose)
    face = friends.rig(name)["face"][pose]
    for img, key in ((friends.draw_eyes(name, "eyes_open"), "eyes"), (friends.draw_mouth(name, mouth), "mouth")):
        x, y = face[key]
        body.alpha_composite(img, (int(x - img.width / 2), int(y - img.height / 2)))
    return body


def bongo_portrait(pose: str = "stand", eyes: str = "open", mouth: str = "X") -> Image.Image:
    body = gorilla.draw_body(pose)
    face = gorilla.rig()["face"][pose]
    for img, key in ((gorilla.draw_eyes("closed" if pose == "sleep" else eyes), "eyes"),
                     (gorilla.draw_brows("neutral"), "brows"), (gorilla.draw_mouth(mouth), "mouth")):
        x, y = face[key]
        body.alpha_composite(img, (int(x - img.width / 2), int(y - img.height / 2)))
    return body


def _font(root: Path, size: int):
    from bongo.thumbnail import _font as f

    return f(root, size)


def _text(p: Pen, root: Path, text: str, x, y, size, fill, stroke=INK):
    from PIL import ImageDraw

    d = ImageDraw.Draw(p.img)
    font = _font(root, size * 2)
    d.text((x * 2, y * 2), text, font=font, fill=fill, anchor="mm", stroke_width=max(4, size // 9), stroke_fill=stroke)


# --- Petits dessins ---------------------------------------------------------------------------


def splat(p: Pen, color, r=250):
    pts = []
    for i in range(36):
        t = 2 * math.pi * i / 36
        rr = r * (1 + 0.12 * math.sin(5 * t) + 0.06 * math.sin(11 * t))
        pts.append((C + math.cos(t) * rr, C + math.sin(t) * rr))
    p.poly(pts, color)
    for a, d, rr in ((0.4, 1.35, 34), (2.2, 1.3, 26), (3.9, 1.38, 30), (5.2, 1.28, 20)):
        p.circle(C + math.cos(a) * r * d, C + math.sin(a) * r * d, rr, color)
    p.circle(C - r * 0.35, C - r * 0.35, r * 0.16, shade(color, 1.45), width=0)


def apple(p: Pen, cx=C, cy=C + 30, r=240, color=RED):
    p.circle(cx - r * 0.42, cy, r * 0.82, color)
    p.circle(cx + r * 0.42, cy, r * 0.82, color)
    p.circle(cx - r * 0.42, cy, r * 0.82 - 6, color, width=0)
    p.capsule((cx, cy - r * 0.7), (cx + r * 0.12, cy - r * 1.05), r * 0.06, BROWN)
    p.leaf(cx + r * 0.42, cy - r * 0.95, r * 0.6, r * 0.28, -25, GREEN)
    p.ellipse((cx - r * 0.75, cy - r * 0.45, cx - r * 0.45, cy - r * 0.1), shade(color, 1.4), width=0)


def snowflake(p: Pen, cx=C, cy=C, r=300, color=(150, 200, 246, 255)):
    for k in range(6):
        a = math.pi / 3 * k
        x1, y1 = cx + math.cos(a) * r, cy + math.sin(a) * r
        p.line([(cx, cy), (x1, y1)], color, 30)
        for t in (0.45, 0.72):
            bx, by = cx + math.cos(a) * r * t, cy + math.sin(a) * r * t
            for s in (-1, 1):
                b = a + s * math.pi / 4
                p.line([(bx, by), (bx + math.cos(b) * r * 0.25, by + math.sin(b) * r * 0.25)], color, 22)
    p.circle(cx, cy, 40, color, width=0)


def crescent(p: Pen, cx, cy, r, color=MOON, back=None):
    p.circle(cx, cy, r, color)
    p.circle(cx + r * 0.45, cy - r * 0.3, r * 0.85, back or (0, 0, 0, 0), outline=None, width=0)


def _moon_face(p: Pen, cx, cy, r):
    """Croissant de lune souriant, par une découpe (sans transparence parasite)."""
    pts = []
    for i in range(40):
        t = math.pi * 0.5 + math.pi * i / 39
        pts.append((cx + math.cos(t) * r, cy + math.sin(t) * r))
    for i in range(40):
        t = math.pi * 1.5 - math.pi * i / 39
        pts.append((cx + r * 0.25 + math.cos(t) * r * 0.62, cy + math.sin(t) * r * 0.95))
    p.poly(pts, MOON)
    p.arc((cx - r * 0.62, cy - r * 0.2, cx - r * 0.3, cy + r * 0.05), 20, 160, INK, 8)
    p.arc((cx - r * 0.6, cy + r * 0.15, cx - r * 0.25, cy + r * 0.45), 20, 160, INK, 8)


def number(p: Pen, root: Path, n: int, color):
    _text(p, root, str(n), C, 300, 360, color)
    r = 44
    total = n * r * 2 + (n - 1) * 26
    for i in range(n):
        x = C - total / 2 + r + i * (2 * r + 26)
        p.circle(x, 650, r, color)


def arrow_up(p: Pen, color=GREEN):
    p.poly([(C, 70), (C + 250, 360), (C + 110, 360), (C + 110, 720), (C - 110, 720), (C - 110, 360), (C - 250, 360)], color)


def speed_lines(p: Pen, x, ys, length=160):
    for y in ys:
        p.line([(x, y), (x - length, y)], (170, 186, 210, 255), 16)


# --- Une fonction par mot ------------------------------------------------------------------------


def draw_card(root: Path, word: str) -> Image.Image:
    animals = set(friends.SPECIES)
    if word in animals:
        return _fit(friend_portrait(word))
    if word == "gorilla":
        return _fit(bongo_portrait("stand").crop((120, 40, 580, 520)))
    if word == "jump":
        img = _fit(friend_portrait("frog", "pose_2"), 520)
        p = Pen(SIZE)
        p.arc((100, 120, 700, 760), 200, 340, (170, 186, 210, 255), 18)
        bg = p.done()
        bg.alpha_composite(img)
        return bg
    if word == "fly":
        img = _fit(friend_portrait("eagle", "pose_2"), 620)
        p = Pen(SIZE)
        for y in (220, 400, 580):
            p.line([(30, y), (140, y - 30)], (170, 186, 210, 255), 14)
        out = p.done()
        out.alpha_composite(img)
        return out
    if word == "run":
        img = _fit(friend_portrait("rabbit", "pose_2"), 560)
        p = Pen(SIZE)
        speed_lines(p, 200, (300, 420, 540))
        out = p.done()
        out.alpha_composite(img, (60, 0))
        return out
    if word == "sleep":
        img = _fit(bongo_portrait("sleep"), 560)
        p = Pen(SIZE)
        out = p.done()
        out.alpha_composite(img, (-60, 60))
        p2 = Pen(SIZE)
        for i, (x, y, s) in enumerate(((560, 260, 120), (650, 160, 90), (720, 80, 64))):
            _text(p2, root, "z", x, y, s, (150, 170, 240, 255))
        out.alpha_composite(p2.done())
        return out

    p = Pen(SIZE)
    if word == "hello":  # main qui fait coucou
        skin = gorilla.SKIN
        p.blob(C, 470, 170, 190, skin)
        for i, (dx, ln) in enumerate(((-130, 170), (-60, 230), (10, 245), (80, 220))):
            p.capsule((C + dx, 380), (C + dx - 20, 380 - ln), 38, skin)
        p.capsule((C + 150, 520), (C + 250, 400), 40, skin)
        p.blob(C, 470, 160, 180, skin, width=0)
        for k, r in enumerate((300, 360)):
            p.arc((C - r, 380 - r, C + r, 380 + r), 200, 245, (170, 186, 210, 255), 16)
            p.arc((C - r, 380 - r, C + r, 380 + r), 295, 340, (170, 186, 210, 255), 16)
    elif word == "tree":
        p.rect((C - 60, 420, C + 60, 760), BROWN, 20)
        for dx, dy, r in ((0, 260, 200), (-160, 360, 150), (160, 360, 150), (0, 400, 160)):
            p.circle(C + dx, dy, r, GREEN)
        for dx, dy, r in ((0, 260, 196), (-160, 360, 146), (160, 360, 146)):
            p.circle(C + dx, dy, r, GREEN, width=0)
    elif word == "leaf":
        p.capsule((C + 150, C + 150), (C + 260, C + 300), 14, shade(GREEN, 0.75))
        p.leaf(C, C, 600, 330, -45, GREEN)
    elif word == "big":
        p.circle(C - 60, C + 20, 300, ORANGE)
        p.circle(C + 290, C + 260, 60, shade(ORANGE, 1.4))
        p.circle(C - 160, C - 90, 50, shade(ORANGE, 1.45), width=0)
    elif word == "small":
        p.circle(C - 120, C + 20, 260, None, outline=(200, 200, 210, 255), width=8)
        p.circle(C + 250, C + 220, 90, ORANGE)
        p.circle(C + 225, C + 195, 18, shade(ORANGE, 1.45), width=0)
    elif word == "banana":  # croissant épais, pointes brunes
        outer, inner = [], []
        for i in range(31):
            t = math.radians(25 + 130 * i / 30)
            outer.append((C + math.cos(t) * 330, 140 + math.sin(t) * 440))
            inner.append((C + math.cos(t) * 300, 120 + math.sin(t) * 330))
        p.poly(outer + inner[::-1], YELLOW)
        p.poly([(C + math.cos(math.radians(t)) * 315, 130 + math.sin(math.radians(t)) * 385) for t in range(40, 141, 5)]
               + [(C + math.cos(math.radians(t)) * 300, 120 + math.sin(math.radians(t)) * 330) for t in range(140, 39, -5)],
               shade(YELLOW, 1.3), width=0)
        for t in (25, 155):
            a = math.radians(t)
            p.circle(C + math.cos(a) * 316, 132 + math.sin(a) * 385, 26, BROWN)
    elif word == "flower":
        p.capsule((C, 430), (C, 760), 18, GREEN)
        p.leaf(C + 110, 620, 220, 100, -30, GREEN)
        p.leaf(C - 110, 660, 220, 100, 210, GREEN)
        for k in range(6):
            a = 2 * math.pi * k / 6
            p.circle(C + math.cos(a) * 140, 300 + math.sin(a) * 140, 105, (246, 120, 150, 255))
        p.circle(C, 300, 100, YELLOW)
    elif word == "friend":
        for cx, col in ((C - 160, gorilla.FUR), (C + 160, friends.SPECIES and (108, 190, 84, 255))):
            p.circle(cx, 470, 170, col)
            p.circle(cx - 55, 440, 26, WHITE)
            p.circle(cx + 55, 440, 26, WHITE)
            p.circle(cx - 55, 446, 13, INK, width=0)
            p.circle(cx + 55, 446, 13, INK, width=0)
            p.arc((cx - 70, 450, cx + 70, 560), 20, 160, INK, 9)
        x, y = C, 200
        p.circle(x - 55, y, 62, RED)
        p.circle(x + 55, y, 62, RED)
        p.poly([(x - 115, y + 15), (x, y + 150), (x + 115, y + 15)], RED)
        p.circle(x - 55, y, 58, RED, width=0)
        p.circle(x + 55, y, 58, RED, width=0)
    elif word in ("green", "red", "yellow", "blue"):
        splat(p, {"green": GREEN, "red": RED, "yellow": YELLOW, "blue": BLUE}[word])
    elif word == "apple":
        apple(p)
    elif word == "rainbow":
        cols = [RED, ORANGE, YELLOW, GREEN, BLUE, PURPLE]
        for i, col in enumerate(cols):
            r = 340 - i * 40
            p.arc((C - r, 560 - r, C + r, 560 + r), 180, 360, col, 42)
        for x in (C - 300, C + 300):
            for dx, dy, r in ((-60, 0, 60), (0, -30, 70), (60, 0, 60), (0, 20, 60)):
                p.circle(x + dx, 580 + dy, r, WHITE)
            for dx, dy, r in ((-60, 0, 56), (0, -30, 66), (60, 0, 56), (0, 20, 56)):
                p.circle(x + dx, 580 + dy, r, WHITE, width=0)
    elif word == "color":
        p.blob(C, C, 330, 250, (236, 206, 160, 255))
        p.circle(C + 170, C + 110, 55, None, outline=INK, width=6)
        for (dx, dy), col in zip(((-190, -40), (-90, -150), (40, -160), (160, -80), (-160, 110)),
                                 (RED, YELLOW, GREEN, BLUE, PURPLE)):
            p.circle(C + dx, C + dy, 58, col)
    elif word == "moon":
        _moon_face(p, C, C, 300)
    elif word == "night":
        p.rect((40, 40, 760, 760), SKY_NIGHT, 90)
        _moon_face(p, C + 60, C, 220)
        for x, y, r in ((170, 170, 40), (620, 150, 30), (180, 560, 34), (600, 640, 26), (300, 330, 22)):
            p.star(x, y, r, MOON)
    elif word == "goodnight":
        p.rect((40, 40, 760, 760), SKY_NIGHT, 90)
        p.rect((150, 520, 650, 700), (150, 190, 236, 255), 40)  # petit lit
        p.ellipse((170, 450, 360, 560), WHITE)
        p.circle(380, 470, 95, gorilla.FUR)
        p.arc((330, 440, 380, 490), 20, 160, INK, 7)
        p.arc((390, 440, 440, 490), 20, 160, INK, 7)
        p.rect((300, 520, 680, 700), (246, 150, 170, 255), 40)
        _moon_face(p, 560, 220, 120)
        for x, y in ((180, 160), (330, 110), (700, 400)):
            p.star(x, y, 30, MOON)
    elif word in ("one", "two", "three", "four", "five"):
        n = ["one", "two", "three", "four", "five"].index(word) + 1
        number(p, root, n, [RED, ORANGE, GREEN, BLUE, PURPLE][n - 1])
    elif word == "count":
        for i, col in enumerate((RED, ORANGE, GREEN)):
            x = 170 + i * 230
            _text(p, root, str(i + 1), x, 270, 230, col)
            for k in range(i + 1):
                p.circle(x, 470 + k * 95, 38, col)
    elif word == "rock":
        p.blob(C, C + 60, 320, 230, (170, 170, 182, 255), squash=0.2)
        p.blob(C - 60, C + 10, 120, 70, shade((170, 170, 182, 255), 1.25), width=0)
        p.circle(C + 120, C + 120, 22, shade((170, 170, 182, 255), 0.8), width=0)
    elif word == "water":
        pts = [(C, 60)]
        for i in range(41):
            t = math.pi * i / 40
            pts.append((C + math.cos(t + math.pi) * -230, 470 + math.sin(t) * 230))
        p.poly([(C, 70), (C + 230, 470)] + pts[1:] + [(C - 230, 470)], BLUE)
        p.ellipse((C - 140, 420, C - 70, 560), shade(BLUE, 1.5), width=0)
        for y in (720, 770):
            p.line([(150, y), (250, y - 20), (350, y), (450, y - 20), (550, y), (650, y - 20)], BLUE, 14)
    elif word == "splash":
        p.ellipse((130, 560, 670, 720), BLUE)
        for k in range(7):
            a = math.pi * (1.1 + 0.8 * k / 6)
            p.leaf(C + math.cos(a) * 220, 560 + math.sin(a) * 240, 200, 70, math.degrees(a), BLUE, vein=False)
        for x, y, r in ((170, 200, 34), (630, 180, 30), (400, 120, 40), (280, 330, 24), (540, 320, 22)):
            p.circle(x, y, r, shade(BLUE, 1.2))
    elif word == "climb":
        p.poly([(60, 740), (420, 120), (760, 740)], (170, 160, 150, 255))
        p.poly([(330, 270), (420, 120), (510, 270), (460, 300), (420, 270), (380, 300)], WHITE)
        p.capsule((420, 120), (420, 20), 8, BROWN)
        p.poly([(420, 25), (520, 55), (420, 85)], RED)
        for i in range(6):
            x0 = 180 + i * 45
            y0 = 680 - i * 85
            p.rect((x0, y0, x0 + 70, y0 + 24), (110, 88, 70, 255), 8)
    elif word == "up":
        arrow_up(p)
    elif word == "snow":
        snowflake(p)
    elif word == "cold":
        snowflake(p, C - 170, 300, 160, (170, 214, 250, 255))
        p.rect((C + 70, 120, C + 190, 620), WHITE, 60)
        p.circle(C + 130, 640, 100, BLUE)
        p.rect((C + 105, 400, C + 155, 640), BLUE, 24, width=0)
        for y in (220, 300, 380):
            p.line([(C + 70, y), (C + 110, y)], INK, 6)
        for x in (90, 170):
            p.line([(x, 560), (x + 30, 600), (x, 640), (x + 30, 680)], (150, 190, 236, 255), 12)
    else:  # mot sans dessin prévu : une étoile (le mot écrit reste sous l'image)
        p.star(C, C, 300, YELLOW)
    return _fit(p.done())
