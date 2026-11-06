import pytest
from pydantic import ValidationError

from bongo.errors import BongoError
from bongo.schema import format_validation_error, load_script, parse_script


def test_example_is_valid(example):
    script = parse_script(example)
    assert script.episode_id == 3
    assert script.scenes[0].segment == "hello"
    assert script.all_lines()[0].text == "Hello, little explorer!"


def test_claude_md_example_is_valid():
    parse_script({
        "episode_id": 3, "title": "Frog and Leaf",
        "quest_summary": "Frog lost his favorite leaf and Bongo helps him find it.",
        "scenes": [{
            "id": "s1", "segment": "hello", "background": "nest",
            "characters": [{"name": "bongo", "pose": "stand", "position": "center"}],
            "lines": [
                {"speaker": "bongo", "text": "Hello, little explorer!", "pose": "arms_up"},
                {"speaker": "bongo", "text": "Can you say frog?", "prompt_word": "frog", "pause_after": 3.0},
                {"speaker": "bongo", "text": "Frog! Great job!", "card": "frog"},
            ],
        }],
    })


def test_unknown_field_rejected(example):
    example["scenes"][0]["lines"][0]["volume"] = 3
    with pytest.raises(ValidationError):
        parse_script(example)


def test_bad_segment_and_position(example):
    example["scenes"][0]["segment"] = "intro"
    example["scenes"][0]["characters"][0]["position"] = "top"
    with pytest.raises(ValidationError) as info:
        parse_script(example)
    messages = format_validation_error(info.value)
    assert any(m.startswith("scenes[0].segment") for m in messages)
    assert any(m.startswith("scenes[0].characters[0].position") for m in messages)


def test_negative_pause_rejected(example):
    example["scenes"][0]["lines"][0]["pause_after"] = -1
    with pytest.raises(ValidationError):
        parse_script(example)


def test_values_are_lowercased(example):
    example["scenes"][0]["lines"][0]["speaker"] = "Bongo"
    assert parse_script(example).scenes[0].lines[0].speaker == "bongo"


def test_load_script_errors_in_french(tmp_path):
    bad = tmp_path / "script.json"
    bad.write_text("{pas du json", encoding="utf-8")
    with pytest.raises(BongoError, match="n'est pas un JSON valide"):
        load_script(bad)
    bad.write_text('{"episode_id": 3}', encoding="utf-8")
    with pytest.raises(BongoError, match="ne respecte pas le format"):
        load_script(bad)
    with pytest.raises(BongoError, match="introuvable"):
        load_script(tmp_path / "absent.json")
