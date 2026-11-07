"""Les 12 amis de la saison 1 : silhouettes rondes et douces, une pose calme (pose_1), une pose d'action (pose_2)."""

from __future__ import annotations

import math

from bongo.art.pen import INK, WHITE, Pen, shade

CANVAS = (500, 500)
FEET = (250, 490)
MOUTH_IN = (110, 38, 56, 255)
TONGUE = (236, 120, 138, 255)
BEAK = (250, 176, 60, 255)
PINK = (244, 170, 182, 255)
CREAM = (250, 238, 214, 255)


def _feet(p, xs, y, color, r=26):
    for x in xs:
        p.ellipse((x - r, y - r * 0.55, x + r, y + r * 0.45), color)


def parrot(p, act):
    body, wing, tail = (226, 72, 64, 255), (64, 170, 120, 255), (60, 120, 210, 255)
    for i, (dx, c) in enumerate(((-28, tail), (0, (250, 204, 70, 255)), (28, tail))):
        p.capsule((250 + dx * 0.4, 380), (250 + dx, 478), 18, c)
    _feet(p, (215, 285), 476, (140, 140, 150, 255), 18)
    p.blob(250, 330, 95, 125, body, squash=0.15)
    p.ellipse((195, 300, 305, 440), shade(body, 1.35))
    if act:
        p.leaf(150, 230, 170, 70, -55, wing, vein=False)
        p.leaf(350, 230, 170, 70, 55, wing, vein=False)
    else:
        p.leaf(162, 340, 160, 62, 75, wing, vein=False)
        p.leaf(338, 340, 160, 62, 105, wing, vein=False)
    p.circle(250, 175, 92, body)
    p.circle(250, 138, 30, (255, 214, 90, 255), width=0)  # plume du front
    return {"eyes": (250, 160), "mouth": (250, 215)}


def frog(p, act):
    green, belly = (108, 190, 84, 255), (206, 236, 160, 255)
    lift = 70 if act else 0
    if act:
        p.limb([(190, 400 - lift), (150, 450), (130, 488)], 22, green)
        p.limb([(310, 400 - lift), (350, 450), (370, 488)], 22, green)
    else:
        p.blob(160, 440, 70, 48, green)
        p.blob(340, 440, 70, 48, green)
        _feet(p, (130, 370), 478, shade(green, 0.85), 30)
    p.blob(250, 360 - lift, 160, 108, green, squash=0.12)
    p.blob(250, 395 - lift, 100, 66, belly, width=4)
    for x in (182, 318):
        p.circle(x, 262 - lift, 54, green)
    if not act:
        _feet(p, (200, 300), 470, shade(green, 0.85), 24)
    for x in (150, 350):
        p.circle(x, 318 - lift, 9, shade(green, 1.35), width=0)  # joues
    return {"eyes": (250, 258 - lift), "mouth": (250, 350 - lift)}


def elephant(p, act):
    grey, ear = (152, 170, 196, 255), (238, 168, 182, 255)
    for x in (175, 220, 280, 325):
        p.rect((x - 26, 380, x + 26, 488), grey, 18)
        p.ellipse((x - 22, 474, x + 22, 490), shade(grey, 1.4), width=3)
    p.blob(250, 360, 150, 100, grey)
    for sx in (-1, 1):
        cx = 250 + sx * 128
        p.blob(cx, 200, 82, 100, grey)
        p.blob(cx + sx * 6, 205, 56, 72, ear, width=0)
    p.circle(250, 200, 110, grey)
    if act:  # trompe levée
        p.limb([(250, 250), (300, 230), (330, 170), (318, 120)], 24, grey)
    else:
        p.limb([(250, 250), (246, 320), (268, 370)], 26, grey)
    return {"eyes": (250, 178), "mouth": (300, 268)}


def owl(p, act):
    brown, disc, feet = (150, 108, 74, 255), (238, 214, 168, 255), (246, 168, 60, 255)
    _feet(p, (215, 285), 478, feet, 20)
    p.blob(250, 330, 125, 150, brown, squash=0.12)
    p.blob(250, 360, 82, 100, disc, width=4)
    for y in (330, 370, 410):
        for x in (225, 250, 275):
            p.arc((x - 10, y - 8, x + 10, y + 8), 20, 160, shade(brown, 0.8), 4)
    if act:
        p.leaf(120, 260, 190, 80, -40, shade(brown, 0.85), vein=False)
        p.leaf(380, 260, 190, 80, 40, shade(brown, 0.85), vein=False)
    else:
        p.leaf(140, 340, 170, 60, 80, shade(brown, 0.85), vein=False)
        p.leaf(360, 340, 170, 60, 100, shade(brown, 0.85), vein=False)
    p.poly([(160, 150), (180, 70), (215, 135)], brown)
    p.poly([(340, 150), (320, 70), (285, 135)], brown)
    p.blob(250, 190, 120, 100, brown)
    for x in (205, 295):
        p.circle(x, 188, 52, disc, width=4)
    return {"eyes": (250, 188), "mouth": (250, 240)}


def squirrel(p, act):
    orange, cream = (214, 128, 54, 255), CREAM
    # queue touffue : une suite de boules qui s'enroule
    pts = [(310, 440), (375, 410), (412, 345), (418, 268), (396, 200), (352, 162), (318, 170)]
    if act:
        pts = [(310, 430), (378, 382), (414, 305), (406, 220), (370, 152), (318, 118), (282, 136)]
    tail_c = shade(orange, 1.12)
    for (x, y), r in zip(pts, (48, 58, 64, 66, 62, 54, 44)):
        p.circle(x, y, r, tail_c)
    for (x, y), r in zip(pts, (48, 58, 64, 66, 62, 54, 44)):
        p.circle(x, y, r - 6, tail_c, width=0)
    p.circle(pts[-1][0], pts[-1][1], 30, shade(orange, 1.45), width=0)
    _feet(p, (210, 290), 478, shade(orange, 0.85), 26)
    p.blob(250, 380, 85, 100, orange, squash=0.15)
    p.blob(250, 400, 52, 70, cream, width=4)
    if act:
        p.limb([(205, 340), (170, 280), (175, 230)], 18, orange)
        p.limb([(295, 340), (330, 280), (325, 230)], 18, orange)
    else:
        p.limb([(210, 340), (230, 375)], 18, orange)
        p.limb([(290, 340), (270, 375)], 18, orange)
    for x in (190, 310):
        p.poly([(x - 28, 195), (x, 130), (x + 28, 195)], orange)
    p.circle(250, 230, 78, orange)
    p.blob(250, 258, 50, 36, cream, width=0)
    return {"eyes": (250, 218), "mouth": (250, 266)}


def bear(p, act):
    brown, muzzle = (156, 104, 68, 255), (226, 192, 150, 255)
    _feet(p, (200, 300), 478, shade(brown, 0.85), 34)
    p.blob(250, 370, 135, 120, brown, squash=0.1)
    p.blob(250, 390, 80, 80, muzzle, width=4)
    if act:
        p.limb([(150, 330), (110, 250), (120, 190)], 30, brown)
        p.limb([(350, 330), (390, 250), (380, 190)], 30, brown)
    else:
        p.limb([(140, 320), (130, 400), (160, 430)], 30, brown)
        p.limb([(360, 320), (370, 400), (340, 430)], 30, brown)
    for x in (165, 335):
        p.circle(x, 125, 40, brown)
        p.circle(x, 125, 20, muzzle, width=0)
    p.circle(250, 200, 105, brown)
    p.blob(250, 245, 52, 40, muzzle, width=4)
    p.ellipse((232, 222, 268, 244), (70, 50, 46, 255), width=3)
    return {"eyes": (250, 180), "mouth": (250, 262)}


def duck(p, act):
    yellow, orange = (248, 210, 76, 255), (246, 150, 58, 255)
    _feet(p, (205, 295), 480, orange, 30)
    p.blob(250, 380, 130, 95, yellow, squash=0.1)
    if act:
        p.leaf(130, 300, 140, 60, -35, shade(yellow, 0.88), vein=False)
        p.leaf(370, 300, 140, 60, 35, shade(yellow, 0.88), vein=False)
    else:
        p.leaf(150, 380, 130, 56, 20, shade(yellow, 0.88), vein=False)
        p.leaf(350, 380, 130, 56, 160, shade(yellow, 0.88), vein=False)
    p.circle(250, 220, 90, yellow)
    p.poly([(240, 128), (250, 100), (262, 128)], yellow)
    return {"eyes": (250, 205), "mouth": (250, 258)}


def fish(p, act):
    teal, fin = (78, 172, 222, 255), (250, 176, 80, 255)
    p.ellipse((110, 455, 390, 495), (150, 206, 240, 255), width=3)  # flaque d'eau
    for bx, by, br in ((150, 180, 14), (128, 140, 9), (145, 110, 6)):
        p.circle(bx, by, br, (210, 236, 252, 255), width=3)
    tilt = -12 if act else 0
    p.poly([(360, 310 + tilt), (450, 240 + tilt * 2), (440, 390)], fin)
    p.poly([(230, 220), (290, 170), (320, 235)], fin)
    p.blob(250, 320, 150, 110, teal)
    for x in (270, 320):
        p.arc((x - 30, 230, x + 30, 410), 280, 80, shade(teal, 1.3), 10)
    p.leaf(240, 380, 70, 36, 30 if act else 60, fin, vein=False)
    return {"eyes": (175, 300), "mouth": (122, 345)}


def turtle(p, act):
    shell, skin = (104, 146, 70, 255), (156, 204, 116, 255)
    for x in (165, 335):
        p.rect((x - 30, 410, x + 30, 488), skin, 20)
    head_y = 230 if act else 300
    p.limb([(360, 400), (400, head_y + 60)], 40, skin)
    p.circle(410, head_y, 62, skin)
    p.blob(250, 380, 175, 120, shell, squash=-0.2)
    p.rect((80, 400, 420, 440), shade(shell, 1.3), 18)
    for cx, cy in ((250, 330), (175, 370), (325, 370), (250, 400)):
        pts = [(cx + 34 * math.cos(math.pi / 3 * i), cy + 30 * math.sin(math.pi / 3 * i)) for i in range(6)]
        p.poly(pts, shade(shell, 1.25), width=4)
    return {"eyes": (412, head_y - 12), "mouth": (420, head_y + 30)}


def goat(p, act):
    white, horn, hoof = (244, 240, 230, 255), (176, 150, 120, 255), (90, 80, 76, 255)
    lift = 40 if act else 0
    legs = [(180, 0), (220, 0), (290, lift), (330, lift)]
    for x, l in legs:
        p.rect((x - 16, 380 - l, x + 16, 478 - l), white, 12)
        p.rect((x - 16, 462 - l, x + 16, 488 - l), hoof, 6, width=3)
    p.blob(255, 360 - lift / 2, 125, 70, white)
    p.capsule((330, 330 - lift), (350, 240 - lift), 34, white)
    for dx in (-24, 24):
        p.limb([(350 + dx, 150 - lift), (350 + dx * 1.8, 100 - lift), (350 + dx * 2.6, 112 - lift)], 12, horn)
    for dx in (-60, 60):
        p.leaf(350 + dx, 190 - lift, 70, 30, 10 if dx > 0 else 170, white, vein=False)
    p.blob(350, 205 - lift, 62, 70, white)
    p.poly([(335, 268 - lift), (350, 312 - lift), (365, 268 - lift)], (210, 200, 186, 255))
    return {"eyes": (350, 190 - lift), "mouth": (350, 250 - lift)}


def eagle(p, act):
    brown, head, yellow = (112, 78, 54, 255), (248, 246, 240, 255), (246, 196, 70, 255)
    _feet(p, (215, 285), 480, yellow, 22)
    if act:
        p.leaf(110, 230, 240, 90, -25, shade(brown, 0.85), vein=False)
        p.leaf(390, 230, 240, 90, 25, shade(brown, 0.85), vein=False)
    p.poly([(215, 440), (250, 480), (285, 440)], shade(brown, 0.8))
    p.blob(250, 345, 105, 125, brown, squash=0.12)
    if not act:
        p.leaf(160, 350, 170, 64, 80, shade(brown, 0.85), vein=False)
        p.leaf(340, 350, 170, 64, 100, shade(brown, 0.85), vein=False)
    p.circle(250, 185, 86, head)
    return {"eyes": (250, 172), "mouth": (250, 222)}


def rabbit(p, act):
    grey, white = (226, 222, 216, 255), (252, 250, 246, 255)
    lift = 40 if act else 0
    for dx, ang in ((-38, -8 if act else -18), (38, 8 if act else 18)):
        x = 250 + dx
        p.leaf(x + ang * 2, 105 - lift, 170, 62, 90 + ang, grey, vein=False)
        p.leaf(x + ang * 2, 108 - lift, 120, 30, 90 + ang, PINK, vein=False, width=0)
    _feet(p, (200, 300), 478 - lift, white, 34)
    p.circle(360, 420 - lift, 26, white)
    p.blob(250, 390 - lift, 100, 92, grey, squash=0.15)
    p.blob(250, 405 - lift, 60, 64, white, width=4)
    p.circle(250, 235 - lift, 88, grey)
    for x in (205, 295):
        p.circle(x, 262 - lift, 12, shade(PINK, 1.15), width=0)
    p.poly([(240, 252 - lift), (260, 252 - lift), (250, 264 - lift)], PINK, width=3)
    return {"eyes": (250, 222 - lift), "mouth": (250, 282 - lift)}


SPECIES = {
    "parrot": (parrot, {"eyes": ((-38, 38), 24), "mouth": "beak"}),
    "frog": (frog, {"eyes": ((-68, 68), 32), "mouth": "wide"}),
    "elephant": (elephant, {"eyes": ((-44, 44), 22), "mouth": "smile"}),
    "owl": (owl, {"eyes": ((-45, 45), 38, (246, 168, 60, 255)), "mouth": "beak_small"}),
    "squirrel": (squirrel, {"eyes": ((-32, 32), 20), "mouth": "smile"}),
    "bear": (bear, {"eyes": ((-42, 42), 20), "mouth": "smile"}),
    "duck": (duck, {"eyes": ((-34, 34), 22), "mouth": "beak_flat"}),
    "fish": (fish, {"eyes": ((0,), 26), "mouth": "fish"}),
    "turtle": (turtle, {"eyes": ((-22, 22), 15), "mouth": "smile_small"}),
    "goat": (goat, {"eyes": ((-28, 28), 18), "mouth": "smile_small"}),
    "eagle": (eagle, {"eyes": ((-36, 36), 20), "mouth": "beak"}),
    "rabbit": (rabbit, {"eyes": ((-36, 36), 22), "mouth": "smile_small"}),
}
DEFAULT = (bear, {"eyes": ((-42, 42), 20), "mouth": "smile"})


def draw_pose(name: str, pose: str):
    fn, _ = SPECIES.get(name, DEFAULT)
    p = Pen(CANVAS)
    fn(p, pose == "pose_2")
    return p.done()


def rig(name: str) -> dict:
    fn, _ = SPECIES.get(name, DEFAULT)
    faces = {}
    for pose in ("pose_1", "pose_2"):
        scratch = Pen((10, 10))  # dessin jetable : seules les ancres comptent
        try:
            faces[pose] = {k: list(v) for k, v in fn(_Probe(), pose == "pose_2").items()}
        finally:
            del scratch
    return {"canvas": list(CANVAS), "feet": list(FEET), "layers_centered_on_anchor": True, "face": faces}


class _Probe:
    """Faux crayon : permet de lire les ancres sans dessiner."""

    def __getattr__(self, _name):
        return lambda *a, **k: None


def draw_eyes(name: str, variant: str):
    _, spec = SPECIES.get(name, DEFAULT)
    offsets, r = spec["eyes"][0], spec["eyes"][1]
    iris = spec["eyes"][2] if len(spec["eyes"]) > 2 else None
    w = int(2 * (max(abs(o) for o in offsets) + r) + 24)
    h = int(2 * r + 24)
    p = Pen((w, h))
    cy = h / 2
    for o in offsets:
        cx = w / 2 + o
        if variant == "eyes_closed":
            p.arc((cx - r * 0.8, cy - r * 0.7, cx + r * 0.8, cy + r * 0.5), 20, 160, INK, max(4, r * 0.22))
            continue
        p.circle(cx, cy, r, WHITE, width=max(3, r * 0.14))
        if iris:
            p.circle(cx, cy + r * 0.05, r * 0.72, iris, width=0)
        p.circle(cx, cy + r * 0.12, r * 0.5, INK, width=0)
        p.circle(cx - r * 0.18, cy - r * 0.1, r * 0.2, WHITE, width=0)
    return p.done()


def draw_mouth(name: str, variant: str):
    """Trois bouches : mouth_closed, mouth_half, mouth_open (bec pour les oiseaux)."""
    _, spec = SPECIES.get(name, DEFAULT)
    kind = spec["mouth"]
    opening = {"mouth_closed": 0.0, "mouth_half": 0.5, "mouth_open": 1.0}.get(variant, 0.0)
    if kind.startswith("beak"):
        flat = kind == "beak_flat"
        small = kind == "beak_small"
        w = 70 if small else (110 if flat else 90)
        p = Pen((w + 30, 110))
        cx, cy = (w + 30) / 2, 40
        gap = 22 * opening
        half = w / 2
        if flat:  # bec de canard, large et arrondi
            p.ellipse((cx - half, cy + gap, cx + half, cy + 34 + gap), shade(BEAK, 0.9))
            if gap:
                p.ellipse((cx - half * 0.7, cy + 8, cx + half * 0.7, cy + 18 + gap), MOUTH_IN, width=0)
            p.ellipse((cx - half, cy - 12, cx + half, cy + 22), BEAK)
        else:
            p.poly([(cx - half * 0.7, cy + 4 + gap), (cx, cy + 34 + gap * 1.2), (cx + half * 0.7, cy + 4 + gap)], shade(BEAK, 0.85))
            if gap:
                p.poly([(cx - half * 0.5, cy + 6), (cx, cy + 6 + gap), (cx + half * 0.5, cy + 6)], MOUTH_IN, width=0)
            p.poly([(cx - half * 0.8, cy - 10), (cx + half * 0.8, cy - 10), (cx, cy + 26)], BEAK)
        return p.done()
    size = {"wide": (170, 90), "smile": (110, 80), "smile_small": (80, 60), "fish": (70, 60)}[kind]
    p = Pen(size)
    cx, cy = size[0] / 2, size[1] / 2
    rx = {"wide": 62, "smile": 34, "smile_small": 22, "fish": 14}[kind]
    if opening == 0:
        if kind == "fish":
            p.circle(cx, cy, 8, None, width=5)
        else:
            p.arc((cx - rx, cy - rx * 0.7, cx + rx, cy + rx * 0.45), 25, 155, INK, 5 if rx > 30 else 4)
    else:
        ry = rx * (0.35 + 0.45 * opening)
        p.ellipse((cx - rx * (0.75 + 0.25 * opening), cy - ry * 0.6, cx + rx * (0.75 + 0.25 * opening), cy + ry), MOUTH_IN,
                  width=4)
        if opening == 1 and kind != "fish":
            p.ellipse((cx - rx * 0.45, cy + ry * 0.2, cx + rx * 0.45, cy + ry * 0.9), TONGUE, width=0)
    return p.done()
