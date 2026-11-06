"""Minutage de l'épisode (timeline.json) : tout ce que le rendu doit afficher, et quand.

Règles (CLAUDE.md) : répliques bout à bout + pause_after + 0,4 s entre deux répliques ;
clignements toutes les 2,5 à 5 s ; cartes-mots 2,5 s à l'écran, apparition en 0,3 s ;
zoom lent du décor (2 à 4 % par scène) ; fondu de 0,5 s entre les scènes ; aucun plan de moins de 3 s.
Tout l'aléatoire utilise une graine dérivée du numéro d'épisode.
"""

from __future__ import annotations

import json
import random
import re
from pathlib import Path

from bongo.config import Config
from bongo.curriculum import Episode
from bongo.schema import BONGO, Script

LEAD_IN_S = 0.6        # avant la première réplique (fondu depuis le noir)
TAIL_S = 1.5           # après la dernière réplique (fondu vers le noir)
EDGE_FADE_S = 0.5
CHANT_GAP_S = 0.5      # silence entre une comptine et les répliques
CARD_S = 2.5
CARD_FADE_S = 0.3
BLINK_S = 0.25
BLINK_EVERY_S = (2.5, 5.0)
ZOOM_RANGE = (0.02, 0.04)
POSE_BLEND_S = 0.2     # fondu entre deux poses (pas de changement brusque)
DRUM_PERIOD_S = 0.4    # alternance tambour A / B
# Ce que fait Bongo pendant la pause d'une invitation à mimer
GESTURE_MOTION = {"jump": "bounce", "hop": "bounce", "drum": "drum", "clap": "drum", "tap": "drum", "stomp": "bounce"}
SURPRISE_RE = re.compile(r"^\s*(oh|wow)\b|\bwow\b", re.IGNORECASE)


def episode_seed(episode_id: int, salt: int = 0) -> int:
    return 7919 * episode_id + salt


def build_timeline(
    script: Script,
    episode: Episode,
    config: Config,
    line_durations: list[float],
    mouth_cues: dict[str, list[dict]] | None = None,
    chants: dict[str, float] | None = None,
) -> dict:
    """Calcule le minutage complet. `line_durations` : durée de chaque réplique (dans l'ordre).
    `chants` : durée des comptines d'accueil (« hello ») et d'au revoir (« goodbye »), si elles existent."""
    qa = config.qa
    lines_flat = [(scene, line) for scene in script.scenes for line in scene.lines]
    if len(line_durations) != len(lines_flat):
        raise ValueError("une durée par réplique est attendue")
    mouth_cues = mouth_cues or {}
    rng = random.Random(episode_seed(episode.id))
    chants = chants or {}
    chant_marks = []
    if chants.get("hello"):
        chant_marks.append({"name": "hello", "start": LEAD_IN_S, "end": round(LEAD_IN_S + chants["hello"], 3)})

    scenes, lines, poses, cards, looks, brows, motions = [], [], [], [], [], [], []
    t = LEAD_IN_S + (chants.get("hello", 0) + CHANT_GAP_S if chants.get("hello") else 0)
    n = 0
    for s_idx, scene in enumerate(script.scenes):
        scene_start = 0.0 if s_idx == 0 else t
        positions = {c.name: c.position for c in scene.characters}
        base_pose = {c.name: c.pose for c in scene.characters}
        for i, line in enumerate(scene.lines):
            n += 1
            lid = f"l{n:03d}"
            start = t
            end = start + line_durations[n - 1]
            pause_end = end + line.pause_after
            entry = {"id": lid, "scene": scene.id, "speaker": line.speaker, "text": line.text,
                     "start": round(start, 3), "end": round(end, 3), "pause_end": round(pause_end, 3)}
            if line.prompt_word:
                entry["prompt_word"] = line.prompt_word
            lines.append(entry)
            for cue in mouth_cues.get(lid, []):
                entry.setdefault("mouth", []).append(
                    {"start": round(start + cue["start"], 3), "end": round(start + cue["end"], 3), "shape": cue["shape"]}
                )
            if line.pose and line.pose != base_pose.get(line.speaker):
                poses.append({"character": line.speaker, "pose": line.pose, "start": entry["start"], "end": entry["pause_end"]})
            if line.card:
                cards.append({"word": line.card, "start": entry["start"], "end": round(start + CARD_S, 3)})
            if line.speaker != BONGO and BONGO in positions:
                friend_x = getattr(config.positions, positions[line.speaker])
                bongo_x = getattr(config.positions, positions[BONGO])
                if friend_x != bongo_x:
                    looks.append({"direction": "left" if friend_x < bongo_x else "right",
                                  "start": entry["start"], "end": entry["pause_end"]})
            if line.speaker == BONGO and SURPRISE_RE.search(line.text):
                brows.append({"start": entry["start"], "end": entry["end"]})
            if line.gesture and BONGO in positions and line.pause_after > 0:
                motion = GESTURE_MOTION.get(line.gesture, "arms_up")
                motions.append({"character": BONGO, "motion": motion, "start": entry["end"], "end": entry["pause_end"]})
            t = pause_end
            last_overall = s_idx == len(script.scenes) - 1 and i == len(scene.lines) - 1
            if not last_overall:
                t += qa.gap_between_lines_s
        if s_idx == len(script.scenes) - 1:
            if chants.get("goodbye"):
                start_chant = t + CHANT_GAP_S
                chant_marks.append({"name": "goodbye", "start": round(start_chant, 3),
                                    "end": round(start_chant + chants["goodbye"], 3)})
                t = start_chant + chants["goodbye"]
            t += TAIL_S
        if t - scene_start < qa.min_shot_s:  # aucun plan de moins de 3 s
            t = scene_start + qa.min_shot_s
        scene_end = t
        zoom = round(rng.uniform(*ZOOM_RANGE), 4)
        scenes.append({
            "id": scene.id, "segment": scene.segment, "background": scene.background,
            "start": round(scene_start, 3), "end": round(scene_end, 3), "zoom": zoom,
            "characters": [{"name": c.name, "pose": c.pose, "position": c.position} for c in scene.characters],
        })
        if s_idx < len(script.scenes) - 1:
            t += qa.scene_fade_s  # fondu enchaîné vers la scène suivante
    duration = round(t, 3)

    # Une carte s'efface quand la suivante arrive
    cards.sort(key=lambda c: c["start"])
    for a, b in zip(cards, cards[1:]):
        a["end"] = min(a["end"], b["start"])

    # Clignements : par personnage et par scène, intervalles de 2,5 à 5 s (graine fixe)
    blinks = []
    for scene in scenes:
        for char in scene["characters"]:
            bt = scene["start"] + rng.uniform(0.8, 2.5)
            stop = scene["end"] + (qa.scene_fade_s if scene is not scenes[-1] else 0)
            while bt + BLINK_S < stop:
                blinks.append({"scene": scene["id"], "character": char["name"], "start": round(bt, 3)})
                bt += rng.uniform(*BLINK_EVERY_S)

    breath_phase = {name: round(rng.uniform(0, 3), 3) for name in sorted({c["name"] for s in scenes for c in s["characters"]})}
    return {
        "episode_id": episode.id,
        "biome": episode.biome,
        "fps": config.video.fps,
        "width": config.video.width,
        "height": config.video.height,
        "duration_s": duration,
        "edge_fade_s": EDGE_FADE_S,
        "scene_fade_s": qa.scene_fade_s,
        "card_s": CARD_S,
        "card_fade_s": CARD_FADE_S,
        "blink_s": BLINK_S,
        "pose_blend_s": POSE_BLEND_S,
        "drum_period_s": DRUM_PERIOD_S,
        "breath_phase": breath_phase,
        "scenes": scenes,
        "lines": lines,
        "poses": poses,
        "motions": motions,
        "cards": cards,
        "looks": looks,
        "brows": brows,
        "blinks": blinks,
        "chants": chant_marks,
    }


def check_timeline(timeline: dict, min_shot_s: float) -> list[str]:
    """Contrôles de cohérence (renvoie des messages d'erreur en français)."""
    problems = []
    for s in timeline["scenes"]:
        if s["end"] - s["start"] < min_shot_s - 1e-6:
            problems.append(f"scène {s['id']} : plan de {s['end'] - s['start']:.1f} s (minimum {min_shot_s:g} s)")
    prev = 0.0
    for line in timeline["lines"]:
        if line["start"] < prev - 1e-6:
            problems.append(f"réplique {line['id']} : chevauche la précédente")
        prev = line["pause_end"]
    return problems


def save_timeline(timeline: dict, path: Path) -> None:
    path.write_text(json.dumps(timeline, indent=1, ensure_ascii=False), encoding="utf-8")


def load_timeline(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
