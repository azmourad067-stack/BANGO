import json

import pytest

from bongo.errors import BongoError
from bongo.script_gen import (
    GeminiClient,
    build_request,
    build_system_prompt,
    extract_json,
    generate_script,
    pick_flash_model,
)
from conftest import find_line
from fakes import FakeLLM


def test_pick_flash_model():
    names = ["models/gemini-2.5-flash", "models/gemini-3.8-flash", "models/gemini-3.8-flash-lite",
             "models/gemini-4-pro", "models/gemini-3.9-flash-preview-11-2026", "models/gemini-3.10-flash-image"]
    assert pick_flash_model(names) == "gemini-3.8-flash"
    assert pick_flash_model(["models/gemma-3"]) is None


def test_extract_json():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Voici : {"a": 2} fin') == {"a": 2}
    with pytest.raises(ValueError):
        extract_json("[1, 2]")


def test_prompts(config, curriculum, rules):
    ep = curriculum.get(3)
    system = build_system_prompt(config, ep)
    assert "at least 8 times" in system and "at most 6 words" in system and "200 to 260" in system
    request = build_request(ep, curriculum, rules, example=None)
    assert '"new_words": [\n  "frog",\n  "leaf"\n ]' in request or '"frog"' in request
    assert "jumps everywhere" in request
    assert "elephant" not in request.split("ALLOWED WORDS")[1].split("BANNED")[0]


def test_generate_first_try(config, curriculum, rules, example):
    example["episode_id"] = 99  # corrigé d'office : le numéro vient du programme
    llm = FakeLLM([json.dumps(example)])
    gen = generate_script(llm, curriculum.get(3), curriculum, config, rules, log=lambda m: None)
    assert gen.attempts == 1 and gen.script.episode_id == 3 and gen.check.status == "ok"


def test_generate_retries_with_feedback(config, curriculum, rules, example):
    bad = json.loads(json.dumps(example))
    find_line(bad, "I am Bongo the gorilla.")["text"] = "I am Bongo the big happy gorilla here."
    rejected = []
    llm = FakeLLM(["pas du json", json.dumps(bad), json.dumps(example)])
    gen = generate_script(llm, curriculum.get(3), curriculum, config, rules, log=lambda m: None,
                          on_rejected=lambda n, a, e: rejected.append((n, e)))
    assert gen.attempts == 3
    assert [n for n, _ in rejected] == [1, 2]
    last_history = llm.histories[-1]
    assert last_history[-1][0] == "user" and "phrase de 8 mots" in last_history[-1][1]
    assert [role for role, _ in last_history] == ["user", "model", "user", "model", "user"]


def test_generate_gives_up(config, curriculum, rules):
    llm = FakeLLM(["{}", "{}", "{}"])
    with pytest.raises(BongoError, match="3 essais"):
        generate_script(llm, curriculum.get(3), curriculum, config, rules, log=lambda m: None)


class _Err(Exception):
    def __init__(self, code, msg=""):
        super().__init__(msg)
        self.code = code


def test_gemini_errors_in_french():
    client = GeminiClient.__new__(GeminiClient)
    assert "Quota" in str(client._explain(_Err(429, "RESOURCE_EXHAUSTED")))
    assert "Clé Gemini refusée" in str(client._explain(_Err(400, "API key not valid")))
    assert "introuvable" in str(client._explain(_Err(404)))
    assert "indisponible" in str(client._explain(_Err(503)))


def test_retry_delay():
    from bongo.script_gen import retry_delay

    assert retry_delay("429 RESOURCE_EXHAUSTED ... 'retryDelay': '37s'") == 39
    assert retry_delay("429 Please retry in 12.5s.") == 14.5
    assert retry_delay("429 quota GenerateRequestsPerDayPerProjectPerModel") is None
    assert retry_delay("429 RESOURCE_EXHAUSTED") == 60


def test_rate_limit_waits_then_succeeds():
    calls, slept = [], []

    class Resp:
        text = "{}"

    class Models:
        def generate_content(self, **kw):
            calls.append(kw)
            if len(calls) < 3:
                raise _Err(429, "RESOURCE_EXHAUSTED retryDelay: '5s'")
            return Resp()

    google = pytest.importorskip("google.genai")
    client = GeminiClient.__new__(GeminiClient)
    client._genai = google
    client.client = type("C", (), {"models": Models()})()
    client.model_name, client.temperature, client.seed = "m", 0.7, 1
    client.sleep = slept.append
    assert client.complete("sys", [("user", "hi")]) == "{}"
    assert slept == [7, 7]


def test_daily_quota_stops_immediately():
    class Models:
        def generate_content(self, **kw):
            raise _Err(429, "RESOURCE_EXHAUSTED GenerateRequestsPerDay")

    google = pytest.importorskip("google.genai")
    client = GeminiClient.__new__(GeminiClient)
    client._genai = google
    client.client = type("C", (), {"models": Models()})()
    client.model_name, client.temperature, client.seed = "m", 0.7, 1
    client.sleep = lambda s: pytest.fail("ne doit pas attendre")
    with pytest.raises(BongoError, match="Quota"):
        client.complete("sys", [("user", "hi")])
