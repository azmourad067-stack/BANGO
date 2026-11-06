from dataclasses import replace

import pytest

from bongo.script_check import (
    count_word,
    quest_similarity,
    sentence_lengths,
    tokenize,
    word_forms,
)
from conftest import codes, find_line


# --- Outils de texte -------------------------------------------------------------


def test_tokenize():
    assert tokenize("Bye-bye, Frog! Let’s go.") == ["bye", "bye", "frog", "let's", "go"]


def test_count_word_case_and_plural():
    tokens = tokenize("Frog! FROGS. The frog's leaf. Leaves!")
    assert count_word("frog", tokens) == 3
    assert count_word("leaf", tokens) == 2


def test_word_forms():
    assert "bush" in word_forms("bushes")
    assert "berry" in word_forms("berries")
    assert "leaf" in word_forms("leaves")


def test_sentence_lengths():
    assert sentence_lengths("Look! A frog! The frog is green.") == [("Look", 1), ("A frog", 2), ("The frog is green", 4)]
    assert sentence_lengths("Bye-bye, little explorer!") == [("Bye-bye, little explorer", 3)]


def test_quest_similarity():
    a = "Frog lost his favorite leaf and Bongo helps him find it."
    assert quest_similarity(a, a) == 1.0
    assert quest_similarity(a, "Duck lost his favorite rock and Bongo helps him find it.") > 0.75
    assert quest_similarity(a, "Elephant wants to share bananas with all the friends.") < 0.6


# --- Exemple valide ------------------------------------------------------------------


def test_example_passes(run_check):
    result = run_check(_example())
    assert result.status == "ok", result.summary_fr()
    assert result.word_counts["frog"] >= 8
    assert 200 <= result.estimated_duration_s <= 260


def _example():
    import copy
    import json

    from conftest import EXAMPLE

    return copy.deepcopy(json.loads(EXAMPLE.read_text(encoding="utf-8")))


# --- Erreurs bloquantes ------------------------------------------------------------------


def test_word_heard_too_few_times(run_check, example):
    # On remplace presque tous les « leaf » par « tree »
    for scene in example["scenes"]:
        for line in scene["lines"]:
            line["text"] = line["text"].replace("leaf", "tree").replace("Leaf", "Tree").replace("leaves", "trees")
            if line.get("prompt_word") == "leaf":
                line["prompt_word"] = "tree"
            if line.get("card") == "leaf":
                line["card"] = "tree"
    result = run_check(example)
    assert "word_repeats" in codes(result)
    assert "word_cards" in codes(result)
    assert result.status == "error"


def test_plural_counts_toward_repeats(run_check, example):
    for scene in example["scenes"]:
        for line in scene["lines"]:
            line["text"] = line["text"].replace("Frog!", "Frogs!")
    result = run_check(example)
    assert "word_repeats" not in codes(result)


def test_not_enough_cards(run_check, example):
    for scene in example["scenes"]:
        for line in scene["lines"]:
            if line.get("card") == "frog":
                line.pop("card")
    find_line(example, "Frog! Great job!")["card"] = "frog"
    result = run_check(example)
    assert "word_cards" in codes(result)
    assert result.card_counts["frog"] == 1


def test_prompt_pause_too_short(run_check, example):
    find_line(example, "Can you say leaf?")["pause_after"] = 2.0
    result = run_check(example)
    assert "prompt_pause" in codes(result)


def test_prompt_not_followed_by_model(run_check, example):
    find_line(example, "Leaf! Great job!")["text"] = "Great job!"
    result = run_check(example)
    assert "prompt_no_model" in codes(result)


def test_prompt_followed_by_friend_is_error(run_check, example):
    scene = example["scenes"][1]  # s2 : Bongo et Frog
    idx = next(i for i, l in enumerate(scene["lines"]) if l.get("prompt_word") == "frog")
    scene["lines"][idx + 1]["speaker"] = "frog"
    result = run_check(example)
    assert "prompt_no_model" in codes(result)


def test_prompt_as_last_line(run_check, example):
    example["scenes"][-1]["lines"].append(
        {"speaker": "bongo", "text": "Can you say frog?", "prompt_word": "frog", "pause_after": 3.0}
    )
    assert "prompt_no_model" in codes(run_check(example))


def test_sentence_too_long(run_check, example):
    find_line(example, "I am Bongo the gorilla.")["text"] = "I am Bongo the big happy gorilla here."
    result = run_check(example)
    assert "sentence_too_long" in codes(result)


def test_long_sentence_by_friend_is_allowed(run_check, example):
    find_line(example, "My favorite leaf!", )["text"] = "It is my favorite little leaf, Bongo!"
    assert "sentence_too_long" not in codes(run_check(example))


def test_unknown_word(run_check, example):
    find_line(example, "Today is a fun day!")["text"] = "Today is a green day!"
    result = run_check(example)
    issue = next(i for i in result.issues if i.code == "unknown_word")
    assert "green" in issue.message
    assert issue.where == "s1, réplique 4"


def test_future_program_word_is_unknown(run_check, example):
    find_line(example, "Today is a fun day!")["text"] = "Look! An elephant!"
    assert "unknown_word" in codes(run_check(example))


def test_friend_name_and_bongo_allowed(run_check, example):
    find_line(example, "Today is a fun day!")["text"] = "Bongo and Frog and Parrot!"
    assert "unknown_word" not in codes(run_check(example))


def test_banned_word(run_check, example):
    find_line(example, "Today is a fun day!")["text"] = "It is a scary day!"
    result = run_check(example)
    assert "banned_word" in codes(result)
    assert "unknown_word" not in codes(result)


def test_digits_rejected(run_check, example):
    find_line(example, "Today is a fun day!")["text"] = "Today is day 3!"
    assert "digits" in codes(run_check(example))


def test_duration_too_short(run_check, example):
    for scene in example["scenes"]:
        for line in scene["lines"]:
            if line.get("pause_after") and not line.get("prompt_word"):
                line["pause_after"] = 0
                line["text"] = line["text"].rstrip("?") + "!"
    example["scenes"][3]["lines"] = example["scenes"][3]["lines"][:5]
    result = run_check(example)
    assert "duration" in codes(result)
    assert result.estimated_duration_s < 200


def test_duration_too_long(run_check, example):
    find_line(example, "Today is a fun day!")["pause_after"] = 10
    for scene in example["scenes"]:
        scene["lines"] = scene["lines"] + [dict(l) for l in scene["lines"] if not l.get("prompt_word")]
    assert "duration" in codes(run_check(example))


def test_quest_too_similar(run_check, rules, example):
    history = [{"episode_id": 18, "quest_summary": "Turtle lost his favorite rock and Bongo helps him find it."}]
    result = run_check(example, rules_override=replace(rules, quest_history=history))
    assert "quest_repeated" in codes(result)


def test_quest_history_same_episode_ignored(run_check, rules, example):
    history = [{"episode_id": 3, "quest_summary": example["quest_summary"]}]
    result = run_check(example, rules_override=replace(rules, quest_history=history))
    assert "quest_repeated" not in codes(result)


def test_quest_different_is_ok(run_check, rules, example):
    history = [{"episode_id": 2, "quest_summary": "Parrot wants to sing a song from the top of the tree."}]
    result = run_check(example, rules_override=replace(rules, quest_history=history))
    assert "quest_repeated" not in codes(result)


def test_card_for_unknown_word(run_check, example):
    find_line(example, "Frog! Great job!")["card"] = "elephant"
    assert "card_unknown" in codes(run_check(example))


def test_wrong_episode_id(run_check, example):
    assert "episode_id" in codes(run_check(example, episode_id=4))


# --- Structure ------------------------------------------------------------------------------


def test_segment_order(run_check, example):
    example["scenes"][0], example["scenes"][1] = example["scenes"][1], example["scenes"][0]
    assert "segment_order" in codes(run_check(example))


def test_segment_missing(run_check, example):
    example["scenes"] = [s for s in example["scenes"] if s["segment"] != "review_word"]
    assert "segment_missing" in codes(run_check(example))


def test_background_not_planned(run_check, example):
    example["scenes"][2]["background"] = "snowy_peak"
    assert "background" in codes(run_check(example))


def test_character_not_in_episode(run_check, example):
    example["scenes"][2]["characters"][1]["name"] = "elephant"
    result = run_check(example)
    assert "character" in codes(result)


def test_unknown_pose(run_check, example):
    find_line(example, "Hello, little explorer!")["pose"] = "dance"
    example["scenes"][1]["characters"][1]["pose"] = "stand"  # pose de Bongo donnée à Frog
    result = run_check(example)
    assert sum(i.code == "pose" for i in result.issues) == 2


def test_speaker_not_on_stage(run_check, example):
    find_line(example, "Hello, little explorer!")["speaker"] = "frog"
    assert "speaker" in codes(run_check(example))


def test_two_characters_same_place(run_check, example):
    example["scenes"][1]["characters"][1]["position"] = "left"
    assert "position" in codes(run_check(example))


def test_review_episode_structure(run_check, example):
    example["episode_id"] = 7
    result = run_check(example)
    assert {"segment_not_allowed", "recap_scenes"} <= codes(result)


# --- Avertissements ------------------------------------------------------------------------------


def test_no_gesture_warning(run_check, example):
    for scene in example["scenes"]:
        for line in scene["lines"]:
            line.pop("gesture", None)
            line["text"] = line["text"].replace("jump", "hop").replace("Jump", "Hop")
    allowed_hop = run_check(example)
    assert "no_gesture" in codes(allowed_hop)
    assert all(i.level == "warning" for i in allowed_hop.issues if i.code == "no_gesture")


def test_action_word_counts_as_gesture(run_check, example):
    for scene in example["scenes"]:
        for line in scene["lines"]:
            line.pop("gesture", None)
    assert "no_gesture" not in codes(run_check(example))


def test_review_word_missing_warning(run_check, example):
    for scene in example["scenes"]:
        scene["characters"] = [c for c in scene["characters"] if c["name"] != "parrot"] or scene["characters"]
        scene["lines"] = [l for l in scene["lines"] if "parrot" not in l["text"].lower() and l["speaker"] != "parrot"]
    result = run_check(example)
    assert "review_word_missing" in codes(result)
    assert next(i for i in result.issues if i.code == "review_word_missing").level == "warning"


def test_question_without_pause_warning(run_check, example):
    find_line(example, "Are you ready? Yes?")["pause_after"] = 0
    result = run_check(example)
    issue = next(i for i in result.issues if i.code == "question_without_pause")
    assert issue.level == "warning"


def test_result_to_dict(run_check, example):
    data = run_check(example).to_dict()
    assert data["status"] == "ok"
    assert set(data) == {"episode_id", "status", "estimated_duration_s", "word_counts", "card_counts", "issues"}
