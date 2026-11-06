import datetime as dt

import pytest
import yaml

from bongo.curriculum import load_curriculum, load_word_list
from bongo.errors import BongoError


def test_season_from_bible(curriculum):
    assert curriculum.season == 1
    assert len(curriculum.episodes) == 28
    words = curriculum.all_words()
    assert len(words) == len(set(words)) == 48
    dates = [e.date for e in curriculum.episodes]
    assert dates == [dt.date(2026, 12, d) for d in range(1, 29)]
    assert [e.id for e in curriculum.episodes if e.is_review] == [7, 14, 21, 28]
    assert len(curriculum.all_friends()) == 12


def test_episodes_copied_from_bible(curriculum):
    ep3 = curriculum.get(3)
    assert ep3.new_words == ["frog", "leaf"]
    assert ep3.review_words == ["parrot"]
    assert ep3.friends == ["frog"]
    assert curriculum.get(12).review_words == ["red", "yellow", "green", "blue"]
    assert curriculum.get(20).review_words == ["one", "two", "three", "four", "five"]
    assert curriculum.get(14).review_words[-1] == "friend"
    assert len(curriculum.get(28).review_words) == 48
    assert curriculum.get(27).new_words == ["sleep", "goodnight"]


def test_review_week_one_matches_claude_md(curriculum):
    ep7 = curriculum.get(7)
    assert ep7.review_words == [
        "hello", "gorilla", "parrot", "tree", "frog", "leaf",
        "elephant", "big", "banana", "small", "flower", "friend",
    ]
    assert ep7.friends == ["parrot", "frog", "elephant"]


def test_vocabulary_grows(curriculum):
    v3 = curriculum.vocabulary_until(3)
    assert {"hello", "gorilla", "parrot", "tree", "frog", "leaf", "jump"} <= v3
    assert "elephant" not in v3
    assert "green" not in v3  # enseigné à l'épisode 8
    assert curriculum.words_taught_until(7) == set(curriculum.get(7).review_words)


def test_week(curriculum):
    assert [e.id for e in curriculum.week(dt.date(2026, 12, 8))] == list(range(8, 15))
    with pytest.raises(BongoError):
        curriculum.week(dt.date(2027, 6, 1))


def test_unknown_episode(curriculum):
    with pytest.raises(BongoError, match="n'existe pas"):
        curriculum.get(99)


def test_word_lists_consistent(root, curriculum):
    allowed = load_word_list(root / "content" / "allowed_words.txt")
    banned = load_word_list(root / "content" / "banned_words.txt")
    program = set(curriculum.all_words())
    assert not allowed & program, "un mot du programme ne doit pas être dans allowed_words.txt"
    assert not allowed & banned
    assert not banned & program
    assert {"i", "you", "look", "the", "a", "is", "can", "say", "yes", "wow"} <= allowed
    assert {"scary", "monster", "hurt", "dead"} <= banned


def _write(tmp_path, episodes):
    (tmp_path / "content").mkdir()
    (tmp_path / "content" / "curriculum.yaml").write_text(
        yaml.safe_dump({"season": 1, "episodes": episodes}), encoding="utf-8"
    )


def _ep(i, **kw):
    base = {"id": i, "date": f"2026-12-{i:02d}", "type": "lesson", "biome": "jungle",
            "backgrounds": ["nest"], "new_words": [f"w{i}a", f"w{i}b"], "friends": []}
    base.update(kw)
    return base


def test_too_many_new_words(tmp_path):
    _write(tmp_path, [_ep(1, new_words=["a", "b", "c", "d"])])
    with pytest.raises(BongoError, match="mots nouveaux"):
        load_curriculum(tmp_path)


def test_review_word_must_be_taught(tmp_path):
    _write(tmp_path, [_ep(1), _ep(2, review_words=["zzz"])])
    with pytest.raises(BongoError, match="jamais enseigné"):
        load_curriculum(tmp_path)


def test_review_episode_without_new_words(tmp_path):
    _write(tmp_path, [_ep(1), _ep(2, type="review", new_words=["x"])])
    with pytest.raises(BongoError, match="révision"):
        load_curriculum(tmp_path)


def test_duplicate_ids(tmp_path):
    _write(tmp_path, [_ep(1), _ep(1)])
    with pytest.raises(BongoError, match="même numéro"):
        load_curriculum(tmp_path)
