"""Bongo : gorille doux, grosse tête (≈ un tiers de la hauteur), longs bras, écharpe de feuilles.
Fourrure gris-bleu foncé ; visage, torse et paumes gris clair chaud ; grands yeux avec reflet blanc."""

from __future__ import annotations

from bongo.art.pen import INK, WHITE, Pen, shade

FUR = (70, 82, 104, 255)
FUR_DARK = shade(FUR, 0.78)
SKIN = (222, 210, 196, 255)
SKIN_DARK = shade(SKIN, 0.85)
LEAF_A = (96, 178, 86, 255)
LEAF_B = (146, 204, 92, 255)
NOSE = (86, 74, 82, 255)
MOUTH_IN = (110, 38, 56, 255)
TONGUE = (236, 120, 138, 255)
BROW = (46, 54, 70, 255)

CANVAS = (700, 900)
FEET = (350, 885)
HEAD_Y = {"crouch": 120, "sleep": 170}  # la tête descend dans ces poses
FACE = {"eyes": (352, 240), "brows": (352, 168), "mouth": (352, 352)}
EYES_SIZE, BROWS_SIZE, MOUTH_SIZE = (300, 130), (300, 80), (180, 120)

# Bras : (épaule, coude, main) gauche puis droite, en coordonnées de toile (avant décalage dy)
ARMS = {
    "stand":   ([(212, 470), (168, 630), (178, 770)], [(488, 470), (532, 630), (522, 770)]),
    "arms_up": ([(212, 470), (128, 350), (112, 210)], [(488, 470), (572, 350), (588, 210)]),
    "drum_a":  ([(212, 470), (180, 600), (300, 575)], [(488, 470), (520, 600), (400, 575)]),
    "drum_b":  ([(212, 470), (150, 590), (232, 520)], [(488, 470), (550, 590), (468, 520)]),
    "point":   ([(212, 470), (168, 630), (178, 770)], [(488, 470), (585, 440), (655, 405)]),
    "crouch":  ([(212, 470), (185, 610), (262, 700)], [(488, 470), (515, 610), (438, 700)]),
    "sleep":   ([(212, 470), (240, 620), (330, 640)], [(488, 470), (460, 620), (370, 640)]),
}


def _scarf(p: Pen, y: float) -> None:
    import math

    n = 9
    for i in range(n):
        t = i / (n - 1)
        x = 215 + 270 * t
        yy = y + 30 * math.sin(math.pi * t)
        ang = -60 + 120 * t + (12 if i % 2 else -12)
        p.leaf(x, yy, 74, 40, ang + 90, LEAF_A if i % 2 else LEAF_B)


def _head(p: Pen, dy: float) -> None:
    cx, cy = 350, 240 + dy
    # oreilles
    for ex in (cx - 168, cx + 168):
        p.circle(ex, cy + 15, 42, FUR)
        p.circle(ex, cy + 15, 22, SKIN, width=0)
    # crâne avec petite houppe
    p.blob(cx, cy, 172, 162, FUR, squash=0.05)
    for bx, by, br in ((cx - 26, cy - 160, 22), (cx + 2, cy - 170, 26), (cx + 28, cy - 158, 20)):
        p.circle(bx, by, br, FUR)
    p.blob(cx, cy, 168, 158, FUR, width=0, squash=0.05)
    # visage (léger trois-quarts : décalé à droite)
    fx = cx + 8
    p.blob(fx, cy + 10, 128, 120, SKIN, squash=0.12)
    # front doux, au-dessus des sourcils
    p.ellipse((fx - 110, cy - 128, fx + 110, cy - 78), FUR, width=0)
    # museau
    p.blob(fx, cy + 98, 96, 62, SKIN_DARK, width=4)
    p.ellipse((fx - 30, cy + 58, fx + 30, cy + 90), NOSE, width=3)
    p.circle(fx - 12, cy + 76, 6, shade(NOSE, 0.6), width=0)
    p.circle(fx + 12, cy + 76, 6, shade(NOSE, 0.6), width=0)


def draw_body(pose: str):
    p = Pen(CANVAS)
    dy = HEAD_Y.get(pose, 0)
    left, right = ARMS.get(pose, ARMS["stand"])
    shift = lambda pts: [(x, y + dy) for x, y in pts]
    # jambes et pieds
    if pose in ("crouch", "sleep"):
        p.blob(255, 815, 95, 62, FUR)
        p.blob(445, 815, 95, 62, FUR)
        p.ellipse((185, 840, 305, 885), SKIN)
        p.ellipse((395, 840, 515, 885), SKIN)
    else:
        p.capsule((280, 760), (270, 850), 48, FUR)
        p.capsule((420, 760), (430, 850), 48, FUR)
        p.ellipse((205, 842, 320, 886), SKIN)
        p.ellipse((380, 842, 495, 886), SKIN)
    # corps (poire) et torse clair
    top = 380 + dy
    p.blob(350, (top + 860) / 2, 178, (860 - top) / 2, FUR, squash=0.18)
    chest_cy = top + (860 - top) * 0.52
    p.circle(305, top + 120, 62, SKIN, width=4)
    p.circle(395, top + 120, 62, SKIN, width=4)
    p.blob(350, chest_cy, 112, (860 - top) * 0.36, SKIN, width=4)
    # bras (les mains passent devant le torse quand il tambourine)
    for arm in (shift(left), shift(right)):
        p.limb(arm, 44, FUR)
        hx, hy = arm[-1]
        p.circle(hx, hy, 36, SKIN)
    if pose == "point":
        hx, hy = shift(right)[-1]
        p.capsule((hx + 18, hy - 10), (hx + 52, hy - 26), 11, SKIN)
    _scarf(p, top + 6)
    _head(p, dy)
    return p.done()


def draw_eyes(variant: str):
    p = Pen(EYES_SIZE)
    for cx in (98, 204):
        cy = 66
        if variant == "closed":
            p.arc((cx - 38, cy - 30, cx + 38, cy + 26), 20, 160, INK, 7)
            continue
        p.ellipse((cx - 42, cy - 50, cx + 42, cy + 50), WHITE)
        px = {"left": -16, "right": 16}.get(variant, 0)
        p.ellipse((cx + px - 25, cy - 22, cx + px + 25, cy + 30), INK, width=0)
        p.circle(cx + px - 9, cy - 8, 9, WHITE, width=0)
        p.circle(cx + px + 9, cy + 14, 4, WHITE, width=0)
        if variant == "half":
            p.poly([(cx - 44, cy - 52), (cx + 44, cy - 52), (cx + 44, cy + 2), (cx - 44, cy + 2)], FUR, width=0)
            p.line([(cx - 42, cy + 2), (cx + 42, cy + 2)], INK, 5)
    return p.done()


def draw_brows(variant: str):
    """Petits arcs doux et arrondis (jamais froncés) ; plus hauts et plus courbés quand il est surpris."""
    p = Pen(BROWS_SIZE)
    surprised = variant == "surprised"
    for cx in (98, 204):
        y = 22 if surprised else 32
        h = 46 if surprised else 36
        p.arc((cx - 30, y, cx + 30, y + h), 200, 340, BROW, 8)
    return p.done()


def draw_mouth(shape: str):
    """Les 9 formes de Rhubarb : A (M/B/P), B (dents), C (E), D (A ouvert), E (O), F (OU), G (F/V), H (L), X (repos)."""
    p = Pen(MOUTH_SIZE)
    cx, cy = 90, 54
    if shape == "X":  # repos : petit sourire
        p.arc((cx - 46, cy - 40, cx + 46, cy + 18), 25, 155, INK, 6)
    elif shape == "A":  # lèvres serrées
        p.line([(cx - 34, cy + 2), (cx, cy + 6), (cx + 34, cy + 2)], INK, 7)
    elif shape == "B":
        p.ellipse((cx - 40, cy - 16, cx + 40, cy + 20), MOUTH_IN)
        p.rect((cx - 28, cy - 13, cx + 28, cy - 2), WHITE, 4, width=0)
    elif shape == "C":
        p.ellipse((cx - 44, cy - 24, cx + 44, cy + 30), MOUTH_IN)
        p.rect((cx - 30, cy - 21, cx + 30, cy - 9), WHITE, 5, width=0)
        p.ellipse((cx - 22, cy + 6, cx + 22, cy + 26), TONGUE, width=0)
    elif shape == "D":  # grand A
        p.ellipse((cx - 50, cy - 36, cx + 50, cy + 46), MOUTH_IN)
        p.rect((cx - 34, cy - 32, cx + 34, cy - 18), WHITE, 6, width=0)
        p.ellipse((cx - 28, cy + 10, cx + 28, cy + 40), TONGUE, width=0)
    elif shape == "E":  # O
        p.ellipse((cx - 30, cy - 30, cx + 30, cy + 34), MOUTH_IN)
        p.ellipse((cx - 16, cy + 8, cx + 16, cy + 28), TONGUE, width=0)
    elif shape == "F":  # OU
        p.ellipse((cx - 18, cy - 16, cx + 18, cy + 20), MOUTH_IN, width=7)
    elif shape == "G":  # F/V : dents sur la lèvre
        p.ellipse((cx - 40, cy - 14, cx + 40, cy + 22), MOUTH_IN)
        p.rect((cx - 28, cy - 12, cx + 28, cy + 4), WHITE, 4, width=0)
        p.line([(cx - 36, cy + 8), (cx + 36, cy + 8)], shade(SKIN, 0.75), 6)
    elif shape == "H":  # L : langue levée
        p.ellipse((cx - 44, cy - 26, cx + 44, cy + 32), MOUTH_IN)
        p.ellipse((cx - 24, cy - 14, cx + 24, cy + 14), TONGUE, width=0)
    return p.done()


def rig() -> dict:
    faces = {}
    from bongo.schema import BONGO_POSES

    for pose in BONGO_POSES:
        dy = HEAD_Y.get(pose, 0)
        faces[pose] = {k: [x, y + dy] for k, (x, y) in FACE.items()}
    return {"canvas": list(CANVAS), "feet": list(FEET), "neck": [350, 410], "layers_centered_on_anchor": True,
            "face": faces, "eyes_closed_in": ["sleep"]}
