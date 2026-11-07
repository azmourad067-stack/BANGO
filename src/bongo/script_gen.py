"""Écriture des scénarios par Gemini (palier gratuit).

Le modèle met en scène les mots du programme ; il ne choisit jamais quoi enseigner.
Aucun script n'est accepté sans passer schema + script_check. Aucune donnée personnelle
n'est envoyée : seulement le programme, les règles et les listes de mots.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol

from pydantic import ValidationError

from bongo.config import Config, get_secret
from bongo.curriculum import Curriculum, Episode
from bongo.errors import BongoError
from bongo.schema import BONGO_POSES, FRIEND_POSES, REVIEW_SEGMENTS, SEGMENTS, Script, format_validation_error, parse_script
from bongo.script_check import CheckResult, ContentRules, check_script

# Traits des amis (bible de la chaîne)
FRIEND_TRAITS = {
    "parrot": "repeats everything people say (useful: he repeats the target words)",
    "frog": "jumps everywhere",
    "elephant": "is big and gentle",
    "owl": "stays awake at night",
    "squirrel": "is very fast",
    "bear": "is always sleepy",
    "duck": "loves splashing",
    "fish": "is shy",
    "turtle": "is very slow",
    "goat": "climbs everywhere",
    "eagle": "flies very high",
    "rabbit": "runs fast",
}

SYSTEM_PROMPT = """You write scripts for "Bongo the Gorilla", a slow, gentle YouTube show that teaches
American English to children aged 2 to 4. You stage the words given by the curriculum.
You NEVER choose what to teach.

BONGO: a calm, curious, encouraging young gorilla, a kind big brother, a little clumsy
(he sneezes, slips gently, makes a mistake on purpose so the child corrects him).
He loves fruit, leaves and building a nest to sleep. He always talks to the child, "little explorer".
Fixed lines: "Hello, little explorer!" / "Let's explore!" / "Great job!" / "You did it!" /
"Bye-bye, little explorer! See you tomorrow!". Signature gesture: he drums his chest when happy:
"Boom, boom, boom! Can you drum like me?". At most one real gorilla fact per episode.
Bongo NEVER scares, mocks, uses irony or talks fast. He never says a harsh "no": he says
"Hmm, let's look again!" and gives a second chance. He says please and thank you, and he shares.
Friends are named after their species ("Hello, Parrot!"), so every greeting repeats a word.

LESSON EPISODE (about 3 min 50), scenes in this exact segment order:
hello (Bongo in his nest, "Hello, little explorer!") -> quest (today's small problem, then "Let's explore!")
-> encounter_1 (first target word: Bongo shows it, says it, asks "Can you say ...?", pause, word card)
-> encounter_2 (second target word, same pattern, plus the gesture to mime)
-> review_word (a word from a previous episode comes back in the story)
-> success (problem solved, Bongo drums his chest with the child)
-> recap (today's word cards again, the child repeats each word) -> goodbye ("See you tomorrow!").
REVIEW EPISODE (5 to 6 minutes): hello -> recap (several scenes, ONE PER FRIEND, each revisiting
that friend and its words) -> goodbye. Review all the listed words.

STRICT RULES (scripts are checked automatically and rejected if they fail):
1. Each new word is heard at least {min_repeats} times in total (all lines, plural counts)
   and shown at least {min_cards} times as a word card ("card": "<word>" on the line where it is said).
2. Every question to the child leaves time to answer. Pattern: a line with
   "prompt_word": "<word>" and "pause_after": {pause} (or more), IMMEDIATELY followed by a Bongo line
   that says the word again, then praise. Example: "Can you say frog?" (pause) -> "Frog! Great job!".
3. Bongo's sentences have at most {max_words} words, present tense, one idea per sentence.
   Split long ideas: "Look! A frog! The frog is little."
4. CLOSED VOCABULARY: use only the allowed words given below. No other word, not even common ones.
   Write numbers in letters. Never use a banned word.
5. One gesture for the child to mime: put "gesture": "<action>" on the line inviting it, with a pause.
6. Gentle tone: no fear, danger, mockery or irony. Problems are small and solved kindly.
7. Slow rhythm: short lines, many pauses. Estimated length must be {duration} seconds
   (aim for about {lines} lines in total).
8. The quest must be NEW: different from all past quests listed below (different problem, not just
   a different animal or object).

OUTPUT: a single JSON object, no comments, matching this shape:
{{"episode_id": int, "title": "short title, e.g. Frog and Leaf", "quest_summary": "one sentence",
  "scenes": [{{"id": "s1", "segment": one of {segments}, "background": one of the episode backgrounds,
    "characters": [{{"name": "bongo" or a friend, "pose": ..., "position": "left"|"center"|"right"}}],
    "lines": [{{"speaker": name on stage, "text": "...", "pose"?: ..., "prompt_word"?: word,
               "pause_after"?: seconds, "card"?: word, "gesture"?: action}}]}}]}}
Bongo poses: {bongo_poses}. Friend poses: {friend_poses}. Optional keys are omitted when unused.
Each character in a scene has its own position. Only characters on stage speak.
"""


def build_system_prompt(config: Config, episode: Episode) -> str:
    qa = config.qa
    low, high = qa.review_duration_s if episode.is_review else qa.lesson_duration_s
    target = (low + high) / 2
    pauses = (20 if episode.is_review else 12) * qa.prompt_pause_s
    per_line = 4.5 / qa.estimate_words_per_s + qa.gap_between_lines_s  # environ 4,5 mots par réplique
    n = (target - pauses) / per_line
    return SYSTEM_PROMPT.format(
        lines=f"{int(n * 0.9)} to {int(n * 1.1)}",
        min_repeats=qa.min_word_repeats,
        min_cards=qa.min_cards_per_word,
        pause=qa.prompt_pause_s,
        max_words=qa.max_words_per_sentence,
        duration=f"{low:g} to {high:g}",
        segments=", ".join(REVIEW_SEGMENTS if episode.is_review else SEGMENTS),
        bongo_poses=", ".join(BONGO_POSES),
        friend_poses=", ".join(FRIEND_POSES),
    )


def build_request(episode: Episode, curriculum: Curriculum, rules: ContentRules, example: str | None) -> str:
    vocabulary = sorted(curriculum.vocabulary_until(episode.id) | rules.allowed_words | {"bongo"})
    entry = {
        "episode_id": episode.id,
        "type": episode.type,
        "biome": episode.biome,
        "backgrounds": episode.backgrounds,
        "new_words": episode.new_words,
        "review_words": episode.review_words,
        "friends": {f: FRIEND_TRAITS.get(f, "") for f in episode.friends},
        "gesture_to_mime": episode.action,
    }
    if episode.note:
        entry["note"] = episode.note
    past = [q["quest_summary"] for q in rules.quest_history if q.get("episode_id") != episode.id]
    parts = [
        "Write the script for this curriculum entry:",
        json.dumps(entry, ensure_ascii=False, indent=1),
        "ALLOWED WORDS (plural -s and possessive 's are fine): " + ", ".join(vocabulary),
        "BANNED WORDS: " + ", ".join(sorted(rules.banned_words)),
        "PAST QUESTS (do not reuse or imitate): " + (" | ".join(past) if past else "none yet"),
    ]
    if example:
        parts.append(
            "FORMAT EXAMPLE ONLY (another episode; do NOT copy its story, quest or lines):\n" + example
        )
    return "\n\n".join(parts)


def feedback_message(errors: list[str], result: CheckResult | None) -> str:
    lines = ["The script was rejected. Fix ALL these problems and return the full corrected JSON."]
    if result is not None and result.word_counts:
        counts = ", ".join(f"{w}: heard {n}, cards {result.card_counts.get(w, 0)}" for w, n in result.word_counts.items())
        lines.append(f"Current counts: {counts}. Estimated length: {result.estimated_duration_s:.0f} s.")
    lines.append("Problems (messages are in French):")
    lines += [f"- {e}" for e in errors]
    return "\n".join(lines)


def extract_json(text: str) -> dict:
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    if not text.startswith("{"):
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("la réponse n'est pas un objet JSON")
    return data


# --- Client Gemini -------------------------------------------------------------------------


class LLM(Protocol):
    model_name: str

    def complete(self, system: str, history: list[tuple[str, str]]) -> str: ...


def pick_flash_model(names: list[str]) -> str | None:
    """Le modèle « gemini-X-flash » stable le plus récent (ni lite, ni preview, ni image, ni audio)."""
    best: tuple[tuple[int, ...], str] | None = None
    for raw in names:
        name = raw.split("/")[-1]
        m = re.fullmatch(r"gemini-(\d+(?:\.\d+)*)-flash", name)
        if m:
            version = tuple(int(x) for x in m.group(1).split("."))
            if best is None or version > best[0]:
                best = (version, name)
    return best[1] if best else None


def flash_candidates(names: list[str]) -> list[str]:
    """Modèles gratuits par ordre de préférence : « Flash » stables du plus récent au plus ancien,
    puis « Flash-Lite ». Chaque modèle a son propre quota journalier."""
    found = []
    for raw in names:
        name = raw.split("/")[-1]
        m = re.fullmatch(r"gemini-(\d+(?:\.\d+)*)-flash(-lite)?", name)
        if m:
            version = tuple(int(x) for x in m.group(1).split("."))
            found.append((1 if m.group(2) else 0, tuple(-v for v in version), name))
    return [name for *_, name in sorted(found)]


MAX_RATE_WAITS = 3
MAX_WAIT_S = 90
# Serveurs Gemini surchargés (erreurs 500/503) : fréquent sur le palier gratuit, on patiente
OVERLOAD_WAITS_S = (20, 45, 90, 180)


def is_overloaded(exc: Exception) -> bool:
    code = getattr(exc, "code", None)
    text = str(exc)
    return (isinstance(code, int) and code >= 500) or any(
        k in text for k in ("UNAVAILABLE", "overloaded", "INTERNAL", "DEADLINE_EXCEEDED")
    )


def retry_delay(text: str) -> float | None:
    """Délai d'attente conseillé par Gemini pour une limite par minute ; None pour un quota journalier."""
    if re.search(r"per ?day|PerDay|daily", text, re.IGNORECASE):
        return None
    m = re.search(r"retry(?:Delay)?['\"]?\s*[:=]?\s*['\"]?(\d+(?:\.\d+)?)s", text, re.IGNORECASE) or \
        re.search(r"retry in (\d+(?:\.\d+)?)\s*s", text, re.IGNORECASE)
    delay = float(m.group(1)) + 2 if m else 60.0
    return delay if delay <= MAX_WAIT_S else None


class GeminiClient:
    sleep = staticmethod(__import__("time").sleep)

    def __init__(self, api_key: str, model: str, temperature: float, seed: int) -> None:
        try:
            from google import genai
        except ImportError:
            raise BongoError('Le SDK Gemini n\'est pas installé : lance pip install -e ".[scenarios]".') from None
        self._genai = genai
        self.client = genai.Client(api_key=api_key)
        self.temperature = temperature
        self.seed = seed
        self.fallbacks: list[str] = []
        self.model_name = self._resolve(model) if model == "auto" else model

    def _available(self) -> list[str]:
        names = []
        try:
            for m in self.client.models.list():
                actions = getattr(m, "supported_actions", None) or []
                if not actions or "generateContent" in actions:
                    names.append(m.name or "")
        except Exception as exc:
            raise self._explain(exc) from None
        return names

    def _resolve(self, model: str) -> str:
        candidates = flash_candidates(self._available())
        chosen = candidates[0] if candidates else None
        self.fallbacks = candidates[1:]
        if not chosen:
            raise BongoError(
                "Aucun modèle « Flash » trouvé pour ta clé Gemini. Ouvre Google AI Studio, repère un modèle "
                "Flash gratuit et écris son nom dans config.yaml (llm: model)."
            )
        return chosen

    def _explain(self, exc: Exception) -> BongoError:
        code = getattr(exc, "code", None)
        text = str(exc)
        if code == 429 or "RESOURCE_EXHAUSTED" in text:
            return BongoError(
                "Quota gratuit de Gemini dépassé. Aucun scénario non contrôlé n'a été utilisé. "
                "Réessaie plus tard (le quota journalier repart chaque jour), ou fabrique l'épisode "
                "avec un scénario écrit à la main : --script-file chemin.json"
            )
        if code in (401, 403) or "API_KEY_INVALID" in text or "API key not valid" in text:
            return BongoError("Clé Gemini refusée : vérifie GEMINI_API_KEY dans le fichier .env (aistudio.google.com/apikey).")
        if code == 404:
            return BongoError(
                f"Modèle Gemini introuvable. Mets llm: model: \"auto\" dans config.yaml, ou un nom de modèle "
                f"Flash vu dans Google AI Studio.\nDétail : {text}"
            )
        if code is not None and int(code) >= 500:
            return BongoError("Gemini est momentanément indisponible. Réessaie dans quelques minutes.")
        return BongoError(f"Échec de l'appel à Gemini (vérifie ta connexion Internet).\nDétail : {text}")

    def complete(self, system: str, history: list[tuple[str, str]]) -> str:
        types = self._genai.types
        contents = [types.Content(role=role, parts=[types.Part.from_text(text=text)]) for role, text in history]
        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=self.temperature,
            seed=self.seed,
            response_mime_type="application/json",
        )
        rate_waits = overload_waits = 0
        while True:
            try:
                response = self.client.models.generate_content(model=self.model_name, contents=contents, config=config)
                break
            except Exception as exc:
                is_rate = getattr(exc, "code", None) == 429 or "RESOURCE_EXHAUSTED" in str(exc)
                if is_rate:
                    delay = retry_delay(str(exc))
                    if delay is None and getattr(self, "fallbacks", None):  # quota du jour épuisé pour ce modèle
                        old, self.model_name = self.model_name, self.fallbacks.pop(0)
                        print(f"  Quota du jour épuisé pour {old} : on continue avec {self.model_name}.")
                        rate_waits = overload_waits = 0
                        continue
                    if delay is None or rate_waits >= MAX_RATE_WAITS:
                        raise self._explain(exc) from None
                    rate_waits += 1
                    print(f"  Limite par minute de Gemini atteinte : nouvel essai dans {delay:.0f} s…")
                elif is_overloaded(exc) and overload_waits < len(OVERLOAD_WAITS_S):
                    delay = OVERLOAD_WAITS_S[overload_waits]
                    overload_waits += 1
                    print(f"  Gemini est surchargé : nouvel essai dans {delay} s "
                          f"({overload_waits}/{len(OVERLOAD_WAITS_S)})…")
                else:
                    raise self._explain(exc) from None
                self.sleep(delay)
        text = response.text or ""
        if not text.strip():
            raise BongoError("Gemini a renvoyé une réponse vide. Relance la commande.")
        return text


def make_client(root: Path, config: Config, episode_id: int) -> GeminiClient:
    key = get_secret(root, "GEMINI_API_KEY")
    if not key:
        raise BongoError(
            "Clé Gemini absente : crée-la sur https://aistudio.google.com/apikey et colle-la dans .env "
            "(GEMINI_API_KEY=...). Ou utilise un scénario écrit à la main : --script-file chemin.json"
        )
    # Graine dérivée du numéro d'épisode (reproductibilité)
    return GeminiClient(key, config.llm.model, config.llm.temperature, seed=1000 + episode_id)


# --- Boucle génération / contrôle -------------------------------------------------------------


@dataclass
class Generation:
    script: Script
    check: CheckResult
    attempts: int
    model: str
    rejected: list[dict] = field(default_factory=list)


def generate_script(
    llm: LLM,
    episode: Episode,
    curriculum: Curriculum,
    config: Config,
    rules: ContentRules,
    example: str | None = None,
    log: Callable[[str], None] = print,
    on_rejected: Callable[[int, str, list[str]], None] | None = None,
) -> Generation:
    """Demande un scénario, le valide et le contrôle ; renvoie les erreurs au modèle (max_retries essais)."""
    system = build_system_prompt(config, episode)
    history: list[tuple[str, str]] = [("user", build_request(episode, curriculum, rules, example))]
    last_errors: list[str] = []
    for attempt in range(1, config.llm.max_retries + 1):
        log(f"  Gemini ({llm.model_name}), essai {attempt}/{config.llm.max_retries}…")
        answer = llm.complete(system, history)
        history.append(("model", answer))
        result = None
        try:
            data = extract_json(answer)
            data["episode_id"] = episode.id  # le numéro vient du programme, pas du modèle
            script = parse_script(data)
        except (ValueError, json.JSONDecodeError) as exc:
            last_errors = [f"JSON invalide : {exc}"]
        except ValidationError as exc:
            last_errors = format_validation_error(exc)
        else:
            result = check_script(script, episode, curriculum, config, rules)
            if result.status != "error":
                return Generation(script, result, attempt, llm.model_name)
            last_errors = [f"[{i.where}] {i.message}" if i.where else i.message for i in result.errors]
        log(f"  Scénario refusé ({len(last_errors)} problème(s)).")
        if on_rejected:
            on_rejected(attempt, answer, last_errors)
        history.append(("user", feedback_message(last_errors, result)))
    details = "\n  - ".join(last_errors[:15])
    raise BongoError(
        f"Gemini n'a pas produit de scénario conforme en {config.llm.max_retries} essais. "
        f"L'épisode {episode.id} n'est pas fabriqué. Derniers problèmes :\n  - {details}\n"
        "Relance la commande (le modèle varie), ou écris le scénario à la main (--script-file)."
    )
