"""Contrôles pédagogiques et techniques d'un scénario, avant toute fabrication.

Niveau « error » : l'épisode est bloqué. Niveau « warning » : à regarder, mais non bloquant.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

import yaml

from bongo.config import Config
from bongo.curriculum import Curriculum, Episode, load_word_list
from bongo.errors import BongoError
from bongo.schema import (
    BONGO,
    BONGO_POSES,
    FRIEND_POSES,
    REVIEW_SEGMENTS,
    SEGMENTS,
    Script,
)

ERROR = "error"
WARNING = "warning"

_WORD_RE = re.compile(r"[a-z]+(?:'[a-z]+)?")
_SENTENCE_SPLIT_RE = re.compile(r"[.!?]+")
_DIGIT_RE = re.compile(r"\d")


# --- Découpage du texte --------------------------------------------------------


def tokenize(text: str) -> list[str]:
    """Mots en minuscules. « Bye-bye » donne deux mots, « let's » reste un mot."""
    text = text.lower().replace("’", "'").replace("‘", "'")
    return _WORD_RE.findall(text)


# Pluriels irréguliers des mots du programme (et de quelques petits mots)
IRREGULAR_PLURALS = {"leaves": "leaf", "children": "child", "feet": "foot", "mice": "mouse"}


def word_forms(token: str) -> set[str]:
    """Formes de base possibles d'un mot : frogs → frog, bushes → bush, frog's → frog, leaves → leaf."""
    forms = {token}
    if token in IRREGULAR_PLURALS:
        forms.add(IRREGULAR_PLURALS[token])
    if token.endswith("'s"):
        token = token[:-2]
        forms.add(token)
    if token.endswith("ies") and len(token) > 4:
        forms.add(token[:-3] + "y")
    if token.endswith("es") and len(token) > 3:
        forms.add(token[:-2])
    if token.endswith("s") and len(token) > 2:
        forms.add(token[:-1])
    return forms


def count_word(word: str, tokens: list[str]) -> int:
    """Occurrences d'un mot (casse ignorée, pluriel en -s / -es compté)."""
    word = word.lower()
    return sum(1 for t in tokens if word in word_forms(t))


def sentence_lengths(text: str) -> list[tuple[str, int]]:
    """Chaque phrase et son nombre de mots (« Bye-bye » compte pour un mot)."""
    result = []
    for sentence in _SENTENCE_SPLIT_RE.split(text):
        words = [w for w in sentence.split() if re.search(r"[A-Za-z]", w)]
        if words:
            result.append((sentence.strip(), len(words)))
    return result


def quest_similarity(a: str, b: str, ignore: set[str] | None = None) -> float:
    """Score de 0 à 1 : ressemblance de forme (phrase) ou de contenu (mots importants)."""
    a_n, b_n = " ".join(tokenize(a)), " ".join(tokenize(b))
    shape = SequenceMatcher(None, a_n, b_n).ratio()
    ignore = ignore or set()
    ca = {t for t in tokenize(a) if t not in ignore and t != BONGO}
    cb = {t for t in tokenize(b) if t not in ignore and t != BONGO}
    content = len(ca & cb) / len(ca | cb) if ca and cb else 0.0
    return max(shape, content)


# --- Résultat ------------------------------------------------------------------


@dataclass
class Issue:
    level: str
    code: str
    message: str
    where: str | None = None

    def to_dict(self) -> dict:
        return {"level": self.level, "code": self.code, "message": self.message, "where": self.where}


@dataclass
class CheckResult:
    episode_id: int
    issues: list[Issue] = field(default_factory=list)
    estimated_duration_s: float = 0.0
    word_counts: dict[str, int] = field(default_factory=dict)
    card_counts: dict[str, int] = field(default_factory=dict)

    def error(self, code: str, message: str, where: str | None = None) -> None:
        self.issues.append(Issue(ERROR, code, message, where))

    def warning(self, code: str, message: str, where: str | None = None) -> None:
        self.issues.append(Issue(WARNING, code, message, where))

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.level == ERROR]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.level == WARNING]

    @property
    def status(self) -> str:
        if self.errors:
            return "error"
        if self.warnings:
            return "warning"
        return "ok"

    def to_dict(self) -> dict:
        return {
            "episode_id": self.episode_id,
            "status": self.status,
            "estimated_duration_s": round(self.estimated_duration_s, 1),
            "word_counts": self.word_counts,
            "card_counts": self.card_counts,
            "issues": [i.to_dict() for i in self.issues],
        }

    def summary_fr(self) -> str:
        label = {"ok": "OK", "warning": "OK avec avertissements", "error": "BLOQUÉ"}[self.status]
        lines = [
            f"Épisode {self.episode_id} : {label}",
            f"  Durée estimée : {self.estimated_duration_s:.0f} s",
        ]
        if self.word_counts:
            counts = ", ".join(
                f"{w} ×{n} (cartes ×{self.card_counts.get(w, 0)})" for w, n in self.word_counts.items()
            )
            lines.append(f"  Mots nouveaux : {counts}")
        for issue in self.issues:
            tag = "ERREUR" if issue.level == ERROR else "Attention"
            where = f" [{issue.where}]" if issue.where else ""
            lines.append(f"  - {tag}{where} : {issue.message}")
        return "\n".join(lines)


# --- Règles de contenu -----------------------------------------------------------


@dataclass
class ContentRules:
    allowed_words: set[str]
    banned_words: set[str]
    quest_history: list[dict]


def load_quest_history(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise BongoError(f"{path.name} est mal formé : {exc}") from None
    quests = data.get("quests") or []
    return [q for q in quests if isinstance(q, dict) and q.get("quest_summary")]


def load_rules(root: Path) -> ContentRules:
    content = root / "content"
    return ContentRules(
        allowed_words=load_word_list(content / "allowed_words.txt"),
        banned_words=load_word_list(content / "banned_words.txt"),
        quest_history=load_quest_history(content / "quest_history.yaml"),
    )


# --- Durée -------------------------------------------------------------------------


def estimate_duration(script: Script, config: Config) -> float:
    qa = config.qa
    total = 0.0
    lines = script.all_lines()
    for line in lines:
        n_words = len(tokenize(line.text))
        total += max(qa.estimate_min_line_s, n_words / qa.estimate_words_per_s) + line.pause_after
    total += qa.gap_between_lines_s * max(0, len(lines) - 1)
    total += qa.scene_fade_s * max(0, len(script.scenes) - 1)
    return total


# --- Contrôle principal --------------------------------------------------------------


def check_script(
    script: Script,
    episode: Episode,
    curriculum: Curriculum,
    config: Config,
    rules: ContentRules,
) -> CheckResult:
    qa = config.qa
    res = CheckResult(episode_id=episode.id)

    if script.episode_id != episode.id:
        res.error("episode_id", f"le scénario porte le numéro {script.episode_id} au lieu de {episode.id}")

    _check_structure(script, episode, curriculum, res)

    vocabulary = curriculum.vocabulary_until(episode.id) | rules.allowed_words | {BONGO}
    taught = curriculum.words_taught_until(episode.id)
    all_tokens: list[str] = []
    flat = [(scene, i, line) for scene in script.scenes for i, line in enumerate(scene.lines)]

    unknown: dict[str, str] = {}
    banned: dict[str, str] = {}
    for idx, (scene, i, line) in enumerate(flat):
        where = f"{scene.id}, réplique {i + 1}"
        tokens = tokenize(line.text)
        all_tokens.extend(tokens)

        for token in tokens:
            forms = word_forms(token)
            if forms & rules.banned_words:
                banned.setdefault(token, where)
            elif not forms & vocabulary:
                unknown.setdefault(token, where)

        if _DIGIT_RE.search(line.text):
            res.error("digits", f"chiffre écrit en nombre dans « {line.text} » : l'écrire en lettres", where)

        if line.speaker == BONGO:
            for sentence, n in sentence_lengths(line.text):
                if n > qa.max_words_per_sentence:
                    res.error(
                        "sentence_too_long",
                        f"phrase de {n} mots (maximum {qa.max_words_per_sentence}) : « {sentence} »",
                        where,
                    )

        if line.prompt_word:
            _check_prompt(line, flat[idx + 1][2] if idx + 1 < len(flat) else None, taught, qa.prompt_pause_s, res, where)
        elif (
            line.speaker == BONGO
            and line.text.rstrip().endswith("?")
            and "you" in tokens
            and line.pause_after < qa.prompt_pause_s
        ):
            res.warning(
                "question_without_pause",
                f"question à l'enfant sans temps de réponse ({line.pause_after:g} s) : « {line.text} »",
                where,
            )

        if line.card and line.card not in taught:
            res.error("card_unknown", f"carte-mot « {line.card} » : ce mot n'est pas encore au programme", where)

    for token, where in banned.items():
        res.error("banned_word", f"mot interdit : « {token} »", where)
    for token, where in unknown.items():
        res.error(
            "unknown_word",
            f"mot hors vocabulaire : « {token} » (ni petit mot autorisé, ni mot du programme vu jusqu'ici)",
            where,
        )

    # Répétitions et cartes des mots nouveaux
    cards = Counter(line.card for _, _, line in flat if line.card)
    for word in episode.new_words:
        n = count_word(word, all_tokens)
        res.word_counts[word] = n
        res.card_counts[word] = cards.get(word, 0)
        if n < qa.min_word_repeats:
            res.error("word_repeats", f"« {word} » entendu {n} fois (minimum {qa.min_word_repeats})")
        if cards.get(word, 0) < qa.min_cards_per_word:
            res.error(
                "word_cards",
                f"« {word} » affiché {cards.get(word, 0)} fois en carte-mot (minimum {qa.min_cards_per_word})",
            )

    # Mots rappelés
    for word in episode.review_words:
        if count_word(word, all_tokens) == 0:
            res.warning("review_word_missing", f"mot rappelé absent : « {word} »")

    # Geste à mimer
    has_gesture = any(line.gesture for _, _, line in flat)
    if not has_gesture and not (episode.action and count_word(episode.action, all_tokens)):
        res.warning("no_gesture", "aucun geste à mimer dans l'épisode")

    # Durée
    res.estimated_duration_s = estimate_duration(script, config)
    low, high = qa.review_duration_s if episode.is_review else qa.lesson_duration_s
    if not low <= res.estimated_duration_s <= high:
        res.error(
            "duration",
            f"durée estimée {res.estimated_duration_s:.0f} s, hors de l'intervalle prévu ({low:g} à {high:g} s)",
        )

    # Quête déjà vue
    ignore = rules.allowed_words
    for past in rules.quest_history:
        if past.get("episode_id") == episode.id:
            continue
        score = quest_similarity(script.quest_summary, str(past["quest_summary"]), ignore)
        if score >= qa.quest_similarity_max:
            res.error(
                "quest_repeated",
                f"quête trop proche de celle de l'épisode {past.get('episode_id', '?')} "
                f"(« {past['quest_summary']} », ressemblance {score:.0%})",
            )
    return res


def _check_prompt(line, next_line, taught: set[str], pause_min: float, res: CheckResult, where: str) -> None:
    word = line.prompt_word
    if word not in taught:
        res.error("prompt_unknown", f"prompt_word « {word} » n'est pas un mot du programme vu jusqu'ici", where)
    if line.pause_after < pause_min:
        res.error(
            "prompt_pause",
            f"pause de {line.pause_after:g} s après « {line.text} » (minimum {pause_min:g} s)",
            where,
        )
    if next_line is None or next_line.speaker != BONGO or count_word(word, tokenize(next_line.text)) == 0:
        res.error(
            "prompt_no_model",
            f"après « {line.text} », Bongo doit redire « {word} » dans la réplique suivante",
            where,
        )


def _check_structure(script: Script, episode: Episode, curriculum: Curriculum, res: CheckResult) -> None:
    order = REVIEW_SEGMENTS if episode.is_review else SEGMENTS
    used = [scene.segment for scene in script.scenes]
    kind = "de révision" if episode.is_review else "leçon"

    foreign = sorted({s for s in used if s not in order}, key=SEGMENTS.index)
    if foreign:
        res.error("segment_not_allowed", f"segment(s) interdit(s) dans un épisode {kind} : {', '.join(foreign)}")
    ranks = [order.index(s) for s in used if s in order]
    if ranks != sorted(ranks):
        res.error("segment_order", f"segments dans le désordre : {' → '.join(used)} (ordre attendu : {', '.join(order)})")
    missing = [s for s in order if s not in used]
    if missing:
        res.error("segment_missing", f"segment(s) manquant(s) : {', '.join(missing)}")
    if episode.is_review:
        recaps = used.count("recap")
        if recaps < len(episode.friends):
            res.error(
                "recap_scenes",
                f"{recaps} scène(s) « recap » pour {len(episode.friends)} amis : il en faut une par ami",
            )

    ids = [s.id for s in script.scenes]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        res.error("scene_id", f"identifiant de scène en double : {', '.join(dupes)}")

    allowed_chars = {BONGO, *episode.friends}
    if "parrot" in curriculum.friends_until(episode.id):
        allowed_chars.add("parrot")  # Parrot peut faire une apparition dans les autres milieux

    for scene in script.scenes:
        where = scene.id
        if scene.background not in episode.backgrounds:
            res.error(
                "background",
                f"décor « {scene.background} » non prévu (décors de l'épisode : {', '.join(episode.backgrounds)})",
                where,
            )
        positions = [c.position for c in scene.characters]
        if len(positions) != len(set(positions)):
            res.error("position", "deux personnages à la même place", where)
        on_stage = {}
        for char in scene.characters:
            if char.name not in allowed_chars:
                res.error("character", f"personnage « {char.name} » absent du programme de l'épisode", where)
            _check_pose(char.name, char.pose, res, where)
            on_stage[char.name] = char
        for i, line in enumerate(scene.lines):
            lw = f"{scene.id}, réplique {i + 1}"
            if line.speaker not in on_stage:
                res.error("speaker", f"« {line.speaker} » parle mais n'est pas dans la scène", lw)
            elif line.pose:
                _check_pose(line.speaker, line.pose, res, lw)


def _check_pose(name: str, pose: str, res: CheckResult, where: str) -> None:
    poses = BONGO_POSES if name == BONGO else FRIEND_POSES
    if pose not in poses:
        res.error("pose", f"pose « {pose} » inconnue pour {name} (possibles : {', '.join(poses)})", where)
