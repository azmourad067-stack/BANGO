"""Les décors (2560 x 1440) : plans successifs en aplats, sol dégagé où se tiennent les personnages
(pieds à 96 % de la hauteur ; places à 25 %, 50 % et 75 % de la largeur)."""

from __future__ import annotations

import math
import random

from bongo.art.pen import INK, Pen, shade

W, H = 2560, 1440
GROUND = 1380  # niveau des pieds
OUT = 4        # contour plus fin pour le décor (les personnages ressortent)


def _rng(name: str) -> random.Random:
    return random.Random(sum(ord(c) * (i + 1) for i, c in enumerate(name)))


def sky(p, color, bands=()):
    p.rect((0, 0, W, H), color, width=0)
    for y, c in bands:  # bandes de couleur unie (pas de dégradé)
        p.rect((0, y, W, H), c, width=0)


def sun(p, x, y, r=110):
    p.circle(x, y, r * 1.35, (255, 236, 150, 255), width=0)
    p.circle(x, y, r, (255, 214, 92, 255), outline=INK, width=OUT)


def cloud(p, x, y, s=1.0, color=(255, 255, 255, 255)):
    for dx, dy, r in ((-90, 10, 60), (-30, -25, 80), (50, -10, 70), (110, 15, 50), (0, 25, 70)):
        p.circle(x + dx * s, y + dy * s, r * s, color, width=0)


def hills(p, base, amp, color, rng, step=320, outline=True):
    pts = [(0, H)]
    x = -100
    while x < W + 400:
        pts.append((x, base - rng.uniform(0.4, 1.0) * amp))
        x += step
    pts.append((W + 100, H))
    smooth = []
    for (x0, y0), (x1, y1) in zip(pts[1:-2], pts[2:-1]):
        for i in range(12):
            t = i / 12
            smooth.append((x0 + (x1 - x0) * t, y0 + (y1 - y0) * (1 - math.cos(math.pi * t)) / 2))
    p.poly([(0, H)] + smooth + [(W, H)], color, outline=INK if outline else None, width=OUT if outline else 0)


def round_tree(p, x, base, h, canopy, trunk=(130, 92, 66, 255)):
    p.rect((x - h * 0.06, base - h * 0.55, x + h * 0.06, base), trunk, 10, width=OUT)
    for dx, dy, r in ((0, -0.72, 0.26), (-0.17, -0.6, 0.2), (0.17, -0.6, 0.2), (0, -0.52, 0.18)):
        p.circle(x + dx * h, base + dy * h, r * h, canopy, width=OUT)


GREENS = ((98, 170, 96, 255), (118, 186, 98, 255), (84, 156, 100, 255), (132, 196, 112, 255))


def forest_rows(p, rng, base, back_color=(168, 214, 160, 255)):
    """Deux rangées d'arbres variés : une au fond (claire, petite), une devant (plus grande)."""
    x = -40
    while x < W + 100:
        round_tree(p, x, base - 60, rng.uniform(220, 330), back_color, trunk=(160, 124, 96, 255))
        x += rng.uniform(140, 220)
    x = rng.uniform(0, 120)
    while x < W + 100:
        round_tree(p, x, base, rng.uniform(330, 560), rng.choice(GREENS))
        x += rng.uniform(220, 380)


def pine(p, x, base, h, color, snow=False):
    p.rect((x - h * 0.04, base - h * 0.15, x + h * 0.04, base), (120, 84, 60, 255), 6, width=OUT)
    for i, (w, top) in enumerate(((0.36, 0.55), (0.29, 0.78), (0.2, 1.0))):
        y0 = base - h * (0.12 + i * 0.25)
        pts = [(x - h * w, y0), (x, base - h * top), (x + h * w, y0)]
        p.poly(pts, color, width=OUT)
        if snow:
            p.poly([(x - h * w * 0.45, base - h * top + h * 0.13), (x, base - h * top),
                    (x + h * w * 0.45, base - h * top + h * 0.13)], (250, 252, 255, 255), width=0)


def palm_plant(p, x, base, size, color, rng, flip=1):
    for k in range(7):
        ang = -160 + k * 23 + rng.uniform(-6, 6)
        a = math.radians(ang)
        cx, cy = x + math.cos(a) * size * 0.45 * flip, base + math.sin(a) * size * 0.45
        p.leaf(cx, cy, size, size * 0.34, ang if flip > 0 else 180 - ang, shade(color, 0.85 + 0.1 * (k % 2)), width=OUT)


def flower(p, x, y, r, color):
    for k in range(5):
        a = 2 * math.pi * k / 5
        p.circle(x + math.cos(a) * r, y + math.sin(a) * r, r * 0.75, color, width=3)
    p.circle(x, y, r * 0.6, (255, 220, 90, 255), width=3)


def grass_tufts(p, rng, y0, y1, color, n=40, avoid=()):
    for _ in range(n):
        x = rng.uniform(40, W - 40)
        if any(abs(x - a) < 150 for a in avoid):
            continue
        y = rng.uniform(y0, y1)
        for dx in (-14, 0, 14):
            p.line([(x + dx, y), (x + dx * 2.2, y - 34 - abs(dx))], color, 6)


def rock(p, x, y, rx, ry, color):
    p.blob(x, y, rx, ry, color, width=OUT, squash=0.15)
    p.arc((x - rx * 0.6, y - ry * 0.7, x + rx * 0.2, y + ry * 0.1), 200, 260, shade(color, 1.3), 8)


def mushroom(p, x, y, s, cap=(222, 82, 74, 255)):
    p.rect((x - 14 * s, y - 50 * s, x + 14 * s, y), (250, 240, 222, 255), 8, width=OUT)
    p.ellipse((x - 46 * s, y - 86 * s, x + 46 * s, y - 36 * s), cap, width=OUT)
    for dx, dy in ((-20, -66), (12, -72), (26, -56)):
        p.circle(x + dx * s, y + dy * s, 7 * s, (255, 250, 240, 255), width=0)


def vine(p, x, length, color, rng):
    pts = [(x + 20 * math.sin(i / 2), i * length / 10) for i in range(11)]
    p.line(pts, shade(color, 0.7), 10)
    for i in range(2, 11, 2):
        p.leaf(pts[i][0] + 26, pts[i][1], 70, 34, 30, color, width=3)
        p.leaf(pts[i][0] - 26, pts[i][1] + 20, 70, 34, 150, color, width=3)


# --- Décors ------------------------------------------------------------------------------------


SPOTS = (W * 0.25, W * 0.5, W * 0.75)


def nest(p, rng):
    sky(p, (178, 222, 240, 255))
    cloud(p, 520, 210, 1.1)
    cloud(p, 1900, 160, 0.9)
    hills(p, 900, 160, (150, 204, 140, 255), rng)
    forest_rows(p, rng, 990)
    # grands troncs sur les côtés et branche sous le nid
    for x in (110, W - 110):
        p.rect((x - 120, 0, x + 120, H), (128, 90, 64, 255), 30, width=OUT)
        p.line([(x - 40, 200), (x - 30, 900)], (108, 74, 52, 255), 10)
    p.rect((0, 1240, W, 1320), (128, 90, 64, 255), 30, width=OUT)
    # feuillage en haut
    for x in range(0, W + 1, 180):
        for k in range(3):
            p.leaf(x + rng.uniform(-60, 60), 40 + k * 55 + rng.uniform(-20, 20), 170, 70, rng.uniform(0, 180),
                   (96, 178, 86, 255) if k % 2 else (130, 196, 96, 255), width=OUT)
    # le nid : grande corbeille tressée (les personnages sont dedans)
    p.ellipse((150, 1180, W - 150, 1440 + 120), (176, 132, 84, 255), width=OUT)
    for k in range(9):
        y = 1210 + k * 26
        p.arc((180 + k * 10, y - 60, W - 180 - k * 10, y + 120), 200, 340, (146, 104, 64, 255), 7)
    p.ellipse((240, 1250, W - 240, 1440 + 60), (204, 162, 108, 255), width=OUT)
    for _ in range(26):
        x = rng.uniform(260, W - 260)
        p.line([(x, rng.uniform(1300, 1330)), (x + rng.uniform(-90, 90), rng.uniform(1340, 1440))], (170, 126, 78, 255), 6)
    for x in (220, W - 220):
        for k in range(4):
            p.leaf(x + rng.uniform(-50, 50), 1200 + rng.uniform(-40, 40), 160, 64, rng.uniform(-40, 40) + 180 * k,
                   (110, 186, 92, 255), width=OUT)


def clearing(p, rng):
    sky(p, (176, 224, 238, 255))
    sun(p, 2180, 220)
    cloud(p, 600, 230, 1.2)
    cloud(p, 1400, 140, 0.8)
    hills(p, 820, 140, (156, 210, 146, 255), rng)
    forest_rows(p, rng, 970)
    hills(p, 1000, 70, (126, 194, 98, 255), rng, step=400)
    p.rect((0, 1080, W, H), (150, 208, 104, 255), width=0)
    p.line([(0, 1080), (W, 1080)], INK, OUT)
    grass_tufts(p, rng, 1110, 1420, (112, 176, 80, 255), 60, avoid=SPOTS)
    for _ in range(26):
        x = rng.uniform(80, W - 80)
        if all(abs(x - s) > 170 for s in SPOTS):
            flower(p, x, rng.uniform(1120, 1400), rng.uniform(14, 22),
                   rng.choice([(246, 120, 140, 255), (255, 190, 80, 255), (170, 140, 240, 255), (255, 255, 255, 255)]))
    palm_plant(p, 60, 1440, 420, (84, 168, 92, 255), rng)
    palm_plant(p, W - 60, 1440, 420, (84, 168, 92, 255), rng, flip=-1)
    for x in (380, 1050, 1750, 2350):
        vine(p, x, rng.uniform(260, 420), (106, 182, 90, 255), rng)


def big_tree(p, rng):
    sky(p, (186, 226, 236, 255))
    cloud(p, 2100, 200, 1.0)
    hills(p, 860, 120, (160, 212, 150, 255), rng)
    p.rect((0, 1060, W, H), (146, 204, 102, 255), width=0)
    p.line([(0, 1060), (W, 1060)], INK, OUT)
    # l'arbre géant, un peu à gauche
    tx = 980
    p.poly([(tx - 190, 1100), (tx - 120, 300), (tx + 120, 300), (tx + 190, 1100)], (140, 98, 66, 255), width=OUT)
    for dx in (-260, 260):
        p.limb([(tx + dx * 0.3, 1060), (tx + dx, 1110)], 40, (140, 98, 66, 255))
    for x in (tx - 60, tx + 40):
        p.line([(x, 420), (x + 10, 1000)], (116, 80, 54, 255), 10)
    p.ellipse((tx - 50, 640, tx + 50, 760), (90, 62, 46, 255), width=OUT)  # creux
    for dx, dy, r in ((0, 200, 330), (-380, 300, 260), (380, 300, 260), (-660, 360, 200), (640, 380, 200), (0, 40, 240)):
        p.circle(tx + dx, dy, r, (96, 172, 88, 255), width=OUT)
    for _ in range(18):
        p.circle(tx + rng.uniform(-700, 700), rng.uniform(80, 520), 26, (238, 108, 92, 255), width=3)  # fruits
    round_tree(p, 2200, 1080, 520, (112, 186, 98, 255))
    grass_tufts(p, rng, 1100, 1420, (110, 172, 78, 255), 50, avoid=SPOTS)
    for _ in range(18):
        x = rng.uniform(80, W - 80)
        if all(abs(x - s) > 170 for s in SPOTS):
            flower(p, x, rng.uniform(1110, 1400), 18, rng.choice([(250, 236, 120, 255), (246, 140, 170, 255)]))
    palm_plant(p, W - 40, 1440, 380, (80, 160, 90, 255), rng, flip=-1)


def undergrowth(p, rng):
    sky(p, (196, 228, 214, 255))
    hills(p, 760, 90, (150, 196, 150, 255), rng, outline=False)
    x = -40
    while x < W + 60:
        w = rng.uniform(36, 90)
        p.rect((x - w, 0, x + w, 1120), rng.choice([(120, 92, 70, 255), (134, 102, 76, 255), (146, 112, 84, 255)]), 20,
               width=OUT)
        x += rng.uniform(170, 330)
    for x in range(0, W + 1, 230):
        p.circle(x + rng.uniform(-60, 60), rng.uniform(40, 160), rng.uniform(170, 240), (82, 150, 92, 255), width=OUT)
    p.rect((0, 1060, W, H), (118, 170, 92, 255), width=0)
    p.line([(0, 1060), (W, 1060)], INK, OUT)
    for x in range(60, W, 280):
        if all(abs(x - s) > 200 for s in SPOTS):
            palm_plant(p, x, 1150, 200, (90, 160, 96, 255), rng)
    for x in (220, 1100, 1530, 2380):
        mushroom(p, x + rng.uniform(-30, 30), rng.uniform(1260, 1400), rng.uniform(0.9, 1.3))
    for _ in range(14):
        x = rng.uniform(60, W - 60)
        if all(abs(x - s) > 170 for s in SPOTS):
            p.circle(x, rng.uniform(1120, 1400), 16, (176, 96, 196, 255), width=3)  # baies
    grass_tufts(p, rng, 1090, 1420, (92, 150, 74, 255), 50, avoid=SPOTS)


def forest_night(p, rng):
    sky(p, (40, 54, 104, 255))
    for _ in range(70):
        p.star(rng.uniform(0, W), rng.uniform(0, 700), rng.uniform(6, 13), (255, 244, 190, 255), width=0)
    p.circle(2050, 260, 140, (252, 244, 206, 255), width=OUT)
    p.circle(2010, 240, 22, (232, 222, 182, 255), width=0)
    p.circle(2100, 300, 16, (232, 222, 182, 255), width=0)
    hills(p, 820, 120, (52, 74, 110, 255), rng)
    for x in range(-40, W, 240):
        if abs(x - 2050) < 200:
            continue
        pine(p, x + rng.uniform(-40, 40), 1080, rng.uniform(520, 760), (44, 84, 92, 255))
    p.rect((0, 1060, W, H), (58, 96, 92, 255), width=0)
    p.line([(0, 1060), (W, 1060)], INK, OUT)
    for x in (300, 1100, 2300):
        mushroom(p, x, rng.uniform(1280, 1400), 1.1, cap=(150, 120, 210, 255))
    grass_tufts(p, rng, 1090, 1420, (70, 120, 104, 255), 50, avoid=SPOTS)


def riverbank(p, rng):
    sky(p, (180, 224, 244, 255))
    sun(p, 400, 200, 95)
    cloud(p, 1500, 190, 1.1)
    hills(p, 760, 140, (150, 206, 150, 255), rng)
    forest_rows(p, rng, 860)
    p.rect((0, 840, W, 1120), (98, 170, 222, 255), width=0)  # rivière
    p.line([(0, 840), (W, 840)], INK, OUT)
    for _ in range(30):
        x, y = rng.uniform(0, W), rng.uniform(870, 1090)
        p.line([(x, y), (x + rng.uniform(60, 140), y)], (186, 226, 248, 255), 8)
    for _ in range(8):
        x, y = rng.uniform(100, W - 100), rng.uniform(900, 1060)
        p.ellipse((x - 70, y - 22, x + 70, y + 22), (110, 186, 96, 255), width=OUT)
        if rng.random() < 0.5:
            flower(p, x + 20, y - 18, 12, (250, 190, 210, 255))
    p.poly([(0, 1120), (W, 1100), (W, H), (0, H)], (146, 206, 106, 255), width=OUT)
    for x in range(20, W, 90):
        if all(abs(x - s) > 220 for s in SPOTS) and rng.random() < 0.6:
            h = rng.uniform(140, 240)
            p.line([(x, 1160), (x + rng.uniform(-10, 10), 1160 - h)], (96, 150, 70, 255), 7)
            p.rect((x - 9, 1160 - h, x + 9, 1160 - h + 60), (150, 104, 70, 255), 9, width=3)  # massettes
    for _ in range(20):
        x = rng.uniform(60, W - 60)
        if all(abs(x - s) > 180 for s in SPOTS):
            rock(p, x, rng.uniform(1200, 1410), rng.uniform(20, 36), rng.uniform(14, 24), (196, 196, 204, 255))
    grass_tufts(p, rng, 1150, 1420, (112, 176, 80, 255), 40, avoid=SPOTS)


def river_rocks(p, rng):
    sky(p, (186, 226, 244, 255))
    cloud(p, 700, 180, 1.0)
    hills(p, 640, 160, (138, 196, 150, 255), rng)
    # petite cascade au fond
    p.rect((1180, 520, 1420, 900), (150, 206, 240, 255), 20, width=OUT)
    for x in range(1210, 1400, 40):
        p.line([(x, 540), (x, 880)], (224, 242, 252, 255), 8)
    rock(p, 1080, 760, 170, 130, (170, 170, 182, 255))
    rock(p, 1520, 770, 180, 125, (160, 162, 176, 255))
    p.rect((0, 860, W, H), (92, 162, 218, 255), width=0)
    p.line([(0, 860), (W, 860)], INK, OUT)
    for _ in range(36):
        x, y = rng.uniform(0, W), rng.uniform(890, 1400)
        p.line([(x, y), (x + rng.uniform(60, 150), y)], (180, 222, 246, 255), 8)
    for x in (260, 900, 1640, 2320):
        rock(p, x, rng.uniform(980, 1060), rng.uniform(80, 130), rng.uniform(50, 70), (176, 178, 190, 255))
    # rochers plats où se tiennent les personnages
    for x in SPOTS:
        rock(p, x, 1400, 250, 70, (198, 190, 176, 255))
    rock(p, 80, 1380, 160, 120, (170, 172, 184, 255))
    rock(p, W - 60, 1390, 170, 120, (166, 168, 180, 255))


def rocky_slope(p, rng):
    sky(p, (190, 222, 246, 255))
    sun(p, 2200, 210, 95)
    cloud(p, 900, 220, 1.0)
    for base, color in ((760, (170, 184, 214, 255)),):
        for x0, peak, w in ((-100, 260, 900), (600, 160, 1000), (1500, 300, 900), (2200, 200, 800)):
            p.poly([(x0, base + 200), (x0 + w / 2, peak), (x0 + w, base + 200)], color, width=OUT)
            p.poly([(x0 + w / 2 - 110, peak + 110), (x0 + w / 2, peak), (x0 + w / 2 + 110, peak + 110),
                    (x0 + w / 2 + 40, peak + 140), (x0 + w / 2 - 40, peak + 130)], (250, 252, 255, 255), width=OUT)
    hills(p, 980, 160, (172, 196, 140, 255), rng)
    p.poly([(0, 1080), (W, 1000), (W, H), (0, H)], (206, 186, 150, 255), width=OUT)
    for _ in range(14):
        x = rng.uniform(60, W - 60)
        if all(abs(x - s) > 220 for s in SPOTS):
            rock(p, x, rng.uniform(1120, 1400), rng.uniform(40, 110), rng.uniform(30, 70), (176, 170, 164, 255))
    for x in (160, 2400):
        pine(p, x, 1300, 520, (82, 140, 96, 255))
    for _ in range(22):
        x = rng.uniform(60, W - 60)
        if all(abs(x - s) > 170 for s in SPOTS):
            flower(p, x, rng.uniform(1140, 1410), 14, rng.choice([(170, 150, 240, 255), (250, 250, 250, 255), (255, 200, 80, 255)]))


def snowy_peak(p, rng):
    sky(p, (196, 222, 246, 255))
    cloud(p, 500, 260, 1.1)
    cloud(p, 1800, 180, 0.9)
    p.poly([(300, 1000), (1300, 120), (2300, 1000)], (180, 196, 226, 255), width=OUT)
    p.poly([(1000, 380), (1300, 120), (1600, 380), (1450, 430), (1300, 380), (1150, 440)], (252, 253, 255, 255), width=OUT)
    for x0, peak, w in ((-200, 420, 900), (1900, 380, 1000)):
        p.poly([(x0, 1050), (x0 + w / 2, peak), (x0 + w, 1050)], (196, 210, 234, 255), width=OUT)
        p.poly([(x0 + w / 2 - 140, peak + 150), (x0 + w / 2, peak), (x0 + w / 2 + 140, peak + 150)],
               (252, 253, 255, 255), width=OUT)
    hills(p, 1060, 90, (236, 242, 252, 255), rng)
    for x in range(40, W, 230):
        if all(abs(x - s) > 230 for s in SPOTS):
            pine(p, x + rng.uniform(-40, 40), 1120, rng.uniform(300, 460), (70, 128, 104, 255), snow=True)
    p.poly([(0, 1150), (W, 1120), (W, H), (0, H)], (246, 249, 255, 255), width=OUT)
    for _ in range(26):
        x, y = rng.uniform(60, W - 60), rng.uniform(1180, 1420)
        p.arc((x - 60, y - 20, x + 60, y + 20), 200, 340, (210, 224, 244, 255), 6)


DECORS = {
    "nest": nest, "clearing": clearing, "big_tree": big_tree, "undergrowth": undergrowth,
    "forest_night": forest_night, "riverbank": riverbank, "river_rocks": river_rocks,
    "rocky_slope": rocky_slope, "snowy_peak": snowy_peak,
}


def draw_background(decor: str):
    p = Pen((W, H))
    fn = DECORS.get(decor, clearing)
    fn(p, _rng(decor))
    return p.done().convert("RGB")
