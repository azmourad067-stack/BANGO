"""Compilations : carton d'introduction (même moteur de rendu) puis épisodes bout à bout
(démultiplexeur concat de FFmpeg, sans réencodage), avec miniature, sous-titres et métadonnées."""

from __future__ import annotations

import datetime as dt
import json
import random
import re
import subprocess
from pathlib import Path
from typing import Callable

import numpy as np

from bongo.config import load_config
from bongo.curriculum import load_curriculum
from bongo.errors import BongoError
from bongo.render import find_ffmpeg

INTRO_S = 6.0
INTRO_LUFS = -18.0  # carton musical un peu plus doux que les épisodes


WEEK_TITLES = {
    "jungle": "Bongo's Week in the Jungle",
    "forest": "Bongo's Week in the Forest",
    "river": "Bongo's Week at the River",
    "mountain": "Bongo's Week in the Mountains",
}


def default_title(curriculum, first: int, last: int) -> str:
    biomes = list(dict.fromkeys(curriculum.get(i).biome for i in range(first, last + 1)))
    if len(biomes) == 1:
        return WEEK_TITLES.get(biomes[0], "Bongo's Week")
    return f"Bongo's Adventures, Episodes {first} to {last}"


def probe_duration(path: Path) -> float:
    proc = subprocess.run([find_ffmpeg(), "-hide_banner", "-i", str(path)], capture_output=True, text=True)
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", proc.stderr)
    if not m:
        raise BongoError(f"Durée illisible pour {path.name} : le fichier est peut-être abîmé.")
    h, mi, s = m.groups()
    return int(h) * 3600 + int(mi) * 60 + float(s)


def title_timeline(config, biome: str, title: str, friends: list[str], seed: int) -> dict:
    rng = random.Random(seed)
    chars = [{"name": "bongo", "pose": "arms_up", "position": "center"}]
    for name, pos in zip(friends[:2], ("left", "right")):
        chars.append({"name": name, "pose": "pose_2", "position": pos})
    blinks = [{"scene": "intro", "character": c["name"], "start": round(rng.uniform(1, 4), 2)} for c in chars]
    return {
        "episode_id": 0, "biome": biome, "fps": config.video.fps, "width": config.video.width,
        "height": config.video.height, "duration_s": INTRO_S, "edge_fade_s": 0.5, "scene_fade_s": 0.5,
        "card_s": 2.5, "card_fade_s": 0.3, "blink_s": 0.25, "pose_blend_s": 0.2, "drum_period_s": 0.4,
        "breath_phase": {c["name"]: rng.uniform(0, 3) for c in chars},
        "scenes": [{"id": "intro", "segment": "hello", "background": "nest", "start": 0.0, "end": INTRO_S,
                    "zoom": 0.03, "characters": chars}],
        "lines": [], "poses": [], "motions": [], "cards": [], "looks": [], "brows": [], "blinks": blinks,
        "chants": [], "title": title,
    }


def _parse_srt(text: str) -> list[tuple[float, float, str]]:
    def secs(ts: str) -> float:
        h, m, rest = ts.split(":")
        s, ms = rest.split(",")
        return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000

    items = []
    for block in text.strip().split("\n\n"):
        rows = block.strip().split("\n")
        if len(rows) >= 3 and "-->" in rows[1]:
            a, b = (x.strip() for x in rows[1].split("-->"))
            items.append((secs(a), secs(b), "\n".join(rows[2:])))
    return items


def _fmt(t: float) -> str:
    from bongo.subtitles import _ts

    return _ts(t)


def _chapter(t: float) -> str:
    m, s = divmod(int(t), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def compile_range(root: Path, first: int, last: int, title: str, log: Callable[[str], None] = print) -> Path:
    from bongo.audio_mix import MIX_RATE, _ramp_envelope, decode, find_music, loop_to, master
    from bongo.metadata import ALL_EPISODES, PLAYLISTS, SHOW, TITLE_SUFFIX, clean_title, write_metadata
    from bongo.pipeline import episode_dir
    from bongo.render import render_video
    from bongo.thumbnail import make_compilation_thumbnail

    config = load_config(root)
    curriculum = load_curriculum(root)
    if first > last:
        raise BongoError("--from doit être inférieur ou égal à --to.")
    episodes = [curriculum.get(i) for i in range(first, last + 1)]
    problems = []
    for ep in episodes:
        folder = episode_dir(root, ep.id)
        qa = folder / "qa.json"
        status = json.loads(qa.read_text(encoding="utf-8"))["status"] if qa.is_file() else None
        if not (folder / f"ep{ep.id:03d}.mp4").is_file() or status in (None, "error"):
            problems.append(str(ep.id))
    if problems:
        raise BongoError(
            f"Épisode(s) pas prêt(s) pour la compilation : {', '.join(problems)}. "
            "Fabrique-les d'abord sans erreur (build-episode ou build-week)."
        )
    name = f"ep{first:03d}-{last:03d}"
    out_dir = root / "out" / "compilations" / name
    out_dir.mkdir(parents=True, exist_ok=True)
    biome = episodes[-1].biome
    friends = list(dict.fromkeys(f for ep in episodes for f in ep.friends))

    log("1/4 Carton d'introduction")
    tl = title_timeline(config, biome, title, friends, seed=first * 100 + last)
    intro_video = render_video(root, tl, config, out_dir / "intro_video.mp4", workers=1, log=log)
    length = int(INTRO_S * MIX_RATE)
    music_path = find_music(root, biome)
    mix = np.zeros((length, 2), dtype=np.float32)
    if music_path:
        mix += loop_to(decode(music_path), length) * _ramp_envelope(length, [])[:, None]
    else:
        mix += 1e-4  # silence (loudnorm a besoin d'un signal)
    master(mix, intro_video, out_dir / "intro.mp4", INTRO_LUFS, out_dir)
    intro_video.unlink(missing_ok=True)

    log("2/4 Assemblage des épisodes")
    parts = [out_dir / "intro.mp4"] + [episode_dir(root, ep.id) / f"ep{ep.id:03d}.mp4" for ep in episodes]
    listing = out_dir / "concat.txt"
    listing.write_text("".join(f"file '{p.resolve().as_posix().replace(chr(39), chr(39) + chr(92) + chr(39) + chr(39))}'\n"
                               for p in parts), encoding="utf-8")
    final = out_dir / f"{name}.mp4"
    proc = subprocess.run([find_ffmpeg(), "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(listing),
                           "-c", "copy", "-movflags", "+faststart", str(final)], capture_output=True, text=True)
    listing.unlink(missing_ok=True)
    if proc.returncode != 0:
        raise BongoError(f"FFmpeg n'a pas pu assembler la compilation : {proc.stderr.strip()[-400:]}")

    log("3/4 Sous-titres et chapitres")
    offset = probe_duration(parts[0])
    subs, chapters, n = [], [("0:00", "Intro")], 0
    for ep, part in zip(episodes, parts[1:]):
        script = json.loads((episode_dir(root, ep.id) / "script.json").read_text(encoding="utf-8"))
        chapters.append((_chapter(offset), clean_title(script["title"])))
        srt = episode_dir(root, ep.id) / f"ep{ep.id:03d}.srt"
        if srt.is_file():
            for a, b, text in _parse_srt(srt.read_text(encoding="utf-8")):
                n += 1
                subs.append(f"{n}\n{_fmt(a + offset)} --> {_fmt(b + offset)}\n{text}\n")
        offset += probe_duration(part)
    (out_dir / f"{name}.srt").write_text("\n".join(subs), encoding="utf-8")

    log("4/4 Miniature et métadonnées")
    make_compilation_thumbnail(root, episodes, title, out_dir / "thumb.png")
    words = [w for ep in episodes for w in ep.new_words]
    publish_day = episodes[-1].date + dt.timedelta(days=1)
    from zoneinfo import ZoneInfo

    hour, minute = (int(x) for x in config.publish.time.split(":"))
    local = dt.datetime.combine(publish_day, dt.time(hour, minute), tzinfo=ZoneInfo(config.publish.timezone))
    description = "\n\n".join([
        (f"{len(episodes)} episodes of {SHOW} in a row" if len(episodes) > 1 else f"An episode of {SHOW}")
        + f" (about {offset / 60:.0f} minutes).",
        f"Words: {', '.join(words)}." if words else "",
        "\n".join(f"{t} {label}" for t, label in chapters),
        f"{SHOW} helps children aged 2 to 4 learn their first American English words: "
        "slow, calm and repetitive, with time to answer.",
    ]).replace("\n\n\n\n", "\n\n")
    playlists = list(dict.fromkeys(PLAYLISTS.get(ep.biome, ep.biome) for ep in episodes)) + [ALL_EPISODES]
    meta = {
        "title": (clean_title(title) + TITLE_SUFFIX) if len(title) + len(TITLE_SUFFIX) <= 100 else clean_title(title),
        "description": description,
        "tags": [SHOW, "learn English for kids", "English for toddlers", "first words", "compilation"],
        "playlists": playlists,
        "publish_at_local": local.isoformat(),
        "publish_at_utc": local.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "made_for_kids": True,
        "altered_or_synthetic_content": False,
        "language": "en-US",
        "category": "Education",
        "subtitles_file": f"{name}.srt",
        "duration_s": round(offset, 1),
        "episodes": [ep.id for ep in episodes],
    }
    write_metadata(meta, out_dir / "metadata.json")
    (out_dir / "intro.mp4").unlink(missing_ok=True)
    return final
