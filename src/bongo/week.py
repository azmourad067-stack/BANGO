"""`build-week` : les 7 épisodes d'une semaine, puis le rapport.

Robustesse : un épisode en échec n'arrête pas les autres ; quota Gemini épuisé = arrêt propre
(les épisodes restants sont signalés) ; relancer reprend là où on s'était arrêté.
"""

from __future__ import annotations

import datetime as dt
import json
import shutil
import time
import traceback
from pathlib import Path
from typing import Callable

from bongo.curriculum import Curriculum, load_curriculum
from bongo.errors import BongoError

MIN_FREE_GB = 3.0
QUOTA_MARK = "Quota gratuit de Gemini"


def week_starts(curriculum: Curriculum) -> list[dt.date]:
    first = curriculum.episodes[0].date
    last = curriculum.episodes[-1].date
    return [first + dt.timedelta(days=7 * k) for k in range((last - first).days // 7 + 1)]


def check_week_start(curriculum: Curriculum, start: dt.date) -> None:
    starts = week_starts(curriculum)
    if start not in starts:
        raise BongoError(
            f"Le {start} n'est pas un début de semaine du programme. Dates possibles : "
            + ", ".join(d.isoformat() for d in starts)
        )


def check_disk(root: Path, needed_gb: float = MIN_FREE_GB) -> None:
    free = shutil.disk_usage(root).free / 1e9
    if free < needed_gb:
        raise BongoError(
            f"Il reste {free:.1f} Go sur le disque ; il en faut au moins {needed_gb:g}. "
            "Libère de la place (vieux dossiers episodes\\ et out\\ déjà publiés) puis relance."
        )


def is_done(root: Path, episode_id: int) -> bool:
    """Épisode déjà fabriqué sans erreur, et rien n'a changé depuis."""
    from bongo.pipeline import episode_dir

    folder = episode_dir(root, episode_id)
    final, qa = folder / f"ep{episode_id:03d}.mp4", folder / "qa.json"
    if not (final.is_file() and qa.is_file()):
        return False
    try:
        if json.loads(qa.read_text(encoding="utf-8")).get("status") == "error":
            return False
    except json.JSONDecodeError:
        return False
    sources = [folder / "script.json", folder / "timeline.json"]
    return all(not s.exists() or s.stat().st_mtime <= final.stat().st_mtime for s in sources)


def _record_failure(root: Path, episode_id: int, message: str, code: str) -> None:
    from bongo.pipeline import episode_dir

    folder = episode_dir(root, episode_id)
    folder.mkdir(parents=True, exist_ok=True)
    qa = {"episode_id": episode_id, "status": "error", "duration_s": 0,
          "issues": [{"level": "error", "code": code, "message": message, "where": None}], "steps": {}}
    (folder / "qa.json").write_text(json.dumps(qa, indent=2, ensure_ascii=False), encoding="utf-8")


def build_week(
    root: Path,
    start: dt.date,
    force: bool = False,
    build: Callable[..., object] | None = None,
    log: Callable[[str], None] = print,
) -> dict:
    """Fabrique la semaine. Renvoie {episode_id: statut}. `build` est remplaçable pour les tests."""
    from bongo.pipeline import build_episode_audio, episode_dir
    from bongo.report import publish_to_week, week_dir, write_week_report

    curriculum = load_curriculum(root)
    check_week_start(curriculum, start)
    check_disk(root)
    episodes = curriculum.week(start)
    target = week_dir(root, start)
    target.mkdir(parents=True, exist_ok=True)
    journal = (target / "journal.txt").open("a", encoding="utf-8")

    def say(msg: str) -> None:
        log(msg)
        journal.write(f"{dt.datetime.now():%H:%M:%S} {msg}\n")
        journal.flush()

    build = build or build_episode_audio
    results: dict[int, str] = {}
    quota_hit = False
    say(f"=== Semaine du {start} : épisodes {episodes[0].id} à {episodes[-1].id} ===")
    try:
        for ep in episodes:
            has_script = (episode_dir(root, ep.id) / "script.json").is_file()
            if quota_hit and not has_script:  # il faudrait Gemini
                msg = "Pas fabriqué : quota Gemini épuisé. Relance build-week plus tard (demain au plus tard)."
                _record_failure(root, ep.id, msg, "not_built")
                results[ep.id] = "non fabriqué"
                continue
            if (not force or quota_hit) and is_done(root, ep.id):
                say(f"Épisode {ep.id} : déjà fait, conservé (--force pour le refaire).")
                results[ep.id] = json.loads((root / "episodes" / f"ep{ep.id:03d}" / "qa.json").read_text(encoding="utf-8"))["status"]
                publish_to_week(root, ep.id, results[ep.id], target)
                continue
            say(f"--- Épisode {ep.id} ({', '.join(ep.new_words) or 'révision'}) ---")
            started = time.monotonic()
            try:
                report = build(root, ep.id, log=say)
                results[ep.id] = report.status
                say(f"Épisode {ep.id} : {report.status} en {(time.monotonic() - started) / 60:.1f} min")
            except BongoError as exc:
                say(f"Épisode {ep.id} : ÉCHEC — {exc}")
                _record_failure(root, ep.id, str(exc), "build_failed")
                results[ep.id] = "error"
                publish_to_week(root, ep.id, "error", target)
                if QUOTA_MARK in str(exc):
                    quota_hit = True
            except Exception as exc:  # erreur imprévue : on la note et on continue
                journal.write(traceback.format_exc())
                say(f"Épisode {ep.id} : ERREUR INATTENDUE — {exc!r} (détail dans journal.txt)")
                _record_failure(root, ep.id, f"Erreur inattendue : {exc!r}. Détail dans journal.txt.", "crash")
                results[ep.id] = "error"
                publish_to_week(root, ep.id, "error", target)
    finally:
        report_path = write_week_report(root, curriculum, start)
        say(f"Rapport : {report_path}")
        journal.close()
    return results


def speaking_rate(root: Path, episode_ids: list[int]) -> float | None:
    """Mots par seconde réellement prononcés (pour recaler estimate_words_per_s)."""
    from bongo.pipeline import episode_dir
    from bongo.script_check import tokenize
    from bongo.tts import wav_duration

    words, seconds = 0, 0.0
    for ep_id in episode_ids:
        audio = episode_dir(root, ep_id) / "audio"
        for txt in sorted(audio.glob("l*.txt")):
            wav = txt.with_suffix(".wav")
            if wav.is_file():
                words += len(tokenize(txt.read_text(encoding="utf-8")))
                seconds += wav_duration(wav)
    return words / seconds if seconds else None


def duration_advice(root: Path, episode_ids: list[int]) -> str | None:
    """Compare durées estimées et réelles ; propose un réglage si l'écart dépasse 10 %."""
    from bongo.config import load_config
    from bongo.pipeline import episode_dir

    est = real = 0.0
    for ep_id in episode_ids:
        qa_path = episode_dir(root, ep_id) / "qa.json"
        try:
            qa = json.loads(qa_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            continue
        e = qa.get("steps", {}).get("script", {}).get("estimated_duration_s")
        r = qa.get("duration_s")
        if e and r:
            est, real = est + e, real + r
    if not est:
        return None
    ratio = real / est
    if abs(ratio - 1) <= 0.10:
        return None
    rate = load_config(root).qa.estimate_words_per_s
    return (f"À noter : les épisodes durent en vrai {ratio:.0%} de la durée estimée. "
            f"Dans config.yaml (qa: estimate_words_per_s), {rate / ratio:.2f} au lieu de {rate:g} "
            "rendrait les estimations plus justes.")
