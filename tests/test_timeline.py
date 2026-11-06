import pytest

from bongo.schema import parse_script
from bongo.timeline import CARD_S, LEAD_IN_S, TAIL_S, build_timeline, check_timeline


@pytest.fixture
def tl(example, config, curriculum):
    script = parse_script(example)
    durations = [1.0 + 0.1 * (i % 5) for i in range(len(script.all_lines()))]
    cues = {"l002": [{"start": 0.0, "end": 0.5, "shape": "D"}, {"start": 0.5, "end": 1.1, "shape": "X"}]}
    return script, durations, build_timeline(script, curriculum.get(3), config, durations, cues)


def test_lines_back_to_back(tl, config):
    script, durations, t = tl
    lines = t["lines"]
    assert lines[0]["start"] == LEAD_IN_S
    flat = script.all_lines()
    for i, (a, b) in enumerate(zip(lines, lines[1:])):
        assert a["end"] == pytest.approx(a["start"] + durations[i], abs=1e-3)
        assert a["pause_end"] == pytest.approx(a["end"] + flat[i].pause_after, abs=1e-3)
        gap = b["start"] - a["pause_end"]
        expected = config.qa.gap_between_lines_s + (config.qa.scene_fade_s if a["scene"] != b["scene"] else 0)
        assert gap == pytest.approx(expected, abs=1e-3)
    assert t["duration_s"] == pytest.approx(lines[-1]["pause_end"] + TAIL_S, abs=1e-3)


def test_scenes_and_fades(tl, config):
    _, _, t = tl
    scenes = t["scenes"]
    assert scenes[0]["start"] == 0
    for a, b in zip(scenes, scenes[1:]):
        assert b["start"] - a["end"] == pytest.approx(config.qa.scene_fade_s, abs=1e-3)
    assert all(0.02 <= s["zoom"] <= 0.04 for s in scenes)
    assert check_timeline(t, config.qa.min_shot_s) == []


def test_min_shot(example, config, curriculum):
    example["scenes"][0]["lines"] = example["scenes"][0]["lines"][:1]
    script = parse_script(example)
    t = build_timeline(script, curriculum.get(3), config, [0.5] * len(script.all_lines()))
    first = t["scenes"][0]
    assert first["end"] - first["start"] == pytest.approx(config.qa.min_shot_s)
    assert t["lines"][1]["start"] >= first["end"] + config.qa.scene_fade_s - 1e-6


def test_cards(tl):
    _, _, t = tl
    cards = t["cards"]
    assert len(cards) >= 4
    for a, b in zip(cards, cards[1:]):
        assert a["end"] <= b["start"]
        assert a["end"] - a["start"] <= CARD_S + 1e-6
    line = next(l for l in t["lines"] if l["text"] == "Frog! Great job!")
    assert any(c["start"] == line["start"] and c["word"] == "frog" for c in cards)


def test_blinks(tl):
    _, _, t = tl
    by_char = {}
    for b in t["blinks"]:
        by_char.setdefault((b["scene"], b["character"]), []).append(b["start"])
    gaps = [b - a for starts in by_char.values() for a, b in zip(starts, starts[1:])]
    assert gaps and all(2.5 - 1e-6 <= g <= 5.0 + 1e-6 for g in gaps)


def test_reproducible(example, config, curriculum):
    script = parse_script(example)
    d = [1.0] * len(script.all_lines())
    assert build_timeline(script, curriculum.get(3), config, d) == build_timeline(script, curriculum.get(3), config, d)


def test_mouths_poses_looks_motions(tl):
    _, _, t = tl
    l2 = t["lines"][1]
    assert l2["mouth"][0] == {"start": l2["start"], "end": round(l2["start"] + 0.5, 3), "shape": "D"}
    assert any(p["pose"] == "arms_up" and p["character"] == "bongo" for p in t["poses"])
    frog_line = next(l for l in t["lines"] if l["speaker"] == "frog")
    look = next(lk for lk in t["looks"] if lk["start"] == frog_line["start"])
    assert look["direction"] == "right"  # Frog est à droite de Bongo
    motions = {m["motion"] for m in t["motions"]}
    assert {"bounce", "drum"} <= motions  # « jump » et « drum » dans l'exemple
    assert any(b["start"] for b in t["brows"])  # « Oh! Who is this? » / « Wow »
