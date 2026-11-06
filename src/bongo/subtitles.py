"""Sous-titres .srt à partir de la timeline."""

from __future__ import annotations

from pathlib import Path

MIN_SUB_S = 1.2


def _ts(t: float) -> str:
    ms = int(round(max(0.0, t) * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def build_srt(timeline: dict) -> str:
    """Une réplique = un sous-titre. Il reste au moins 1,2 s à l'écran, sans chevaucher le suivant."""
    lines = timeline["lines"]
    blocks = []
    for i, line in enumerate(lines):
        start = line["start"]
        end = max(line["end"], start + MIN_SUB_S)
        if i + 1 < len(lines):
            end = min(end, lines[i + 1]["start"] - 0.05)
        end = min(end, timeline["duration_s"])
        blocks.append(f"{i + 1}\n{_ts(start)} --> {_ts(end)}\n{line['text'].strip()}\n")
    return "\n".join(blocks)


def write_srt(timeline: dict, path: Path) -> Path:
    path.write_text(build_srt(timeline), encoding="utf-8")
    return path
