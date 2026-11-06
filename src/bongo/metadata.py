"""metadata.json : tout ce qu'il faut recopier dans YouTube Studio (sans bourrage de mots-clés)."""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from bongo.config import Config
from bongo.curriculum import Episode
from bongo.errors import BongoError

SHOW = "Bongo the Gorilla"
TITLE_SUFFIX = f" — Learn English with {SHOW}"
MAX_TITLE = 100
PLAYLISTS = {
    "jungle": "Bongo in the Jungle",
    "forest": "Bongo in the Forest",
    "river": "Bongo at the River",
    "mountain": "Bongo in the Mountains",
}
ALL_EPISODES = "All episodes"
MAX_TAGS = 10
GESTURE_PHRASES = {
    "jump": "jump", "wave": "wave hello", "flap": "flap your wings", "stomp": "stomp your feet",
    "crouch": "crouch down small", "sniff": "sniff a flower", "blink": "blink like an owl", "reach": "reach up high",
    "wiggle": "wiggle", "yawn": "yawn", "clap": "clap", "stretch": "stretch", "waddle": "waddle like a duck",
    "swim": "swim", "crawl": "crawl", "tiptoe": "tiptoe", "wash": "wash your hands", "splash": "splash",
    "climb": "climb", "fly": "fly", "run": "run", "shiver": "shiver", "drum": "drum like Bongo",
}


def clean_title(title: str) -> str:
    title = re.sub(r"\s+", " ", title).strip().strip('"').strip()
    title = re.sub(r"[<>]", "", title)  # caractères refusés par YouTube
    room = MAX_TITLE - len(TITLE_SUFFIX)
    return title[:room].rstrip()


def publish_time(episode: Episode, config: Config) -> tuple[str, str]:
    try:
        zone = ZoneInfo(config.publish.timezone)
    except ZoneInfoNotFoundError:
        raise BongoError(
            f"Fuseau horaire {config.publish.timezone} inconnu : lance pip install tzdata (inclus dans l'installation)."
        ) from None
    hour, minute = (int(x) for x in config.publish.time.split(":"))
    local = dt.datetime.combine(episode.date, dt.time(hour, minute), tzinfo=zone)
    return local.isoformat(), local.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_metadata(episode: Episode, title: str, quest_summary: str, config: Config, srt_name: str) -> dict:
    words = episode.new_words if not episode.is_review else episode.review_words
    words_txt = ", ".join(words)
    lines = [quest_summary.strip()]
    if episode.is_review:
        lines.append(f"Today we review: {words_txt}.")
    else:
        lines.append(f"Today's words: {words_txt}.")
    action = GESTURE_PHRASES.get(episode.action or "")
    lines.append("Say each word with Bongo" + (f", then {action} together!" if action else "!"))
    lines.append(
        f"{SHOW} helps children aged 2 to 4 learn their first American English words: "
        "slow, calm and repetitive, with time to answer."
    )
    local, utc = publish_time(episode, config)
    tags = [SHOW, "learn English for kids", "English for toddlers", "first words"]
    tags += [w for w in words if w not in tags][: MAX_TAGS - len(tags)]
    return {
        "episode_id": episode.id,
        "title": clean_title(title) + TITLE_SUFFIX,
        "description": "\n\n".join(lines),
        "tags": tags[:MAX_TAGS],
        "playlists": [PLAYLISTS.get(episode.biome, f"Bongo — {episode.biome}"), ALL_EPISODES],
        "publish_at_local": local,
        "publish_at_utc": utc,
        "made_for_kids": True,
        "altered_or_synthetic_content": False,
        "language": "en-US",
        "category": "Education",
        "subtitles_file": srt_name,
    }


def write_metadata(meta: dict, path: Path) -> Path:
    path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return path
