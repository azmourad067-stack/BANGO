"""Fabrication d'un épisode, étape par étape.

Étape 2 de la construction : scénario → voix → contrôle de prononciation → bouches,
plus un aperçu audio de l'épisode entier (epNNN_audio.wav). L'image arrive aux étapes 3 et 4.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np
import yaml

from bongo.asr_check import Transcriber, check_line, load_whisper, target_words
from bongo.config import Config, load_config
from bongo.curriculum import Curriculum, Episode, load_curriculum
from bongo.errors import BongoError
from bongo.lipsync import find_rhubarb, lipsync_lines, run_rhubarb
from bongo.schema import Script, load_script
from bongo.script_check import ERROR, WARNING, CheckResult, ContentRules, Issue, check_script, load_rules
from bongo.tts import (
    SAMPLE_RATE,
    LineAudio,
    Synth,
    load_pronunciations,
    read_wav,
    silence,
    synthesize_script,
    write_wav,
)

EXAMPLE_SCRIPT = Path("content/examples/ep003_frog_leaf.json")


def episode_dir(root: Path, episode_id: int) -> Path:
    return root / "episodes" / f"ep{episode_id:03d}"


def script_to_json(script: Script) -> str:
    data = script.model_dump(exclude_none=True)
    for scene in data["scenes"]:
        for line in scene["lines"]:
            if line.get("pause_after") == 0:
                line.pop("pause_after")
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


@dataclass
class EpisodeReport:
    episode_id: int
    issues: list[Issue] = field(default_factory=list)
    steps: dict = field(default_factory=dict)
    duration_s: float = 0.0

    @property
    def status(self) -> str:
        if any(i.level == ERROR for i in self.issues):
            return "error"
        if self.issues:
            return "warning"
        return "ok"

    def to_dict(self) -> dict:
        return {
            "episode_id": self.episode_id,
            "status": self.status,
            "duration_s": round(self.duration_s, 1),
            "issues": [i.to_dict() for i in self.issues],
            "steps": self.steps,
        }

    def summary_fr(self) -> str:
        label = {"ok": "OK", "warning": "OK avec avertissements", "error": "BLOQUÉ"}[self.status]
        lines = [f"Épisode {self.episode_id} : {label}"]
        if self.duration_s:
            lines.append(f"  Durée réelle de l'audio : {self.duration_s:.0f} s ({self.duration_s / 60:.1f} min)")
        for i in self.issues:
            tag = "ERREUR" if i.level == ERROR else "Attention"
            where = f" [{i.where}]" if i.where else ""
            lines.append(f"  - {tag}{where} : {i.message}")
        return "\n".join(lines)


# --- Étape scénario ----------------------------------------------------------------------------


def obtain_script(
    root: Path,
    episode: Episode,
    curriculum: Curriculum,
    config: Config,
    rules: ContentRules,
    folder: Path,
    script_file: Path | None,
    new_script: bool,
    llm_factory: Callable[[], object] | None,
    log: Callable[[str], None],
) -> tuple[Script | None, CheckResult | None, dict]:
    target = folder / "script.json"
    info: dict = {}
    if script_file is not None:
        script = load_script(script_file)
        info["source"] = f"fichier : {script_file.name}"
    elif target.is_file() and not new_script:
        script = load_script(target)
        info["source"] = "script.json existant (ajoute --new-script pour en demander un nouveau)"
    else:
        from bongo.script_gen import generate_script, make_client

        llm = llm_factory() if llm_factory else make_client(root, config, episode.id)
        rejected_dir = folder / "rejected"

        def keep_rejected(attempt: int, answer: str, errors: list[str]) -> None:
            rejected_dir.mkdir(parents=True, exist_ok=True)
            (rejected_dir / f"essai_{attempt}.json").write_text(answer, encoding="utf-8")
            (rejected_dir / f"essai_{attempt}_problemes.txt").write_text("\n".join(errors), encoding="utf-8")

        example = (root / EXAMPLE_SCRIPT).read_text(encoding="utf-8") if (root / EXAMPLE_SCRIPT).is_file() else None
        gen = generate_script(llm, episode, curriculum, config, rules, example, log=log, on_rejected=keep_rejected)
        info.update(source="gemini", model=gen.model, attempts=gen.attempts)
        script = gen.script
    log(f"  Scénario : {info['source']}")
    result = check_script(script, episode, curriculum, config, rules)
    if result.status != "error":
        target.write_text(script_to_json(script), encoding="utf-8")
    return script, result, info


# --- Contrôle de prononciation ---------------------------------------------------------------------


def _wav_digest(path: Path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()


def run_asr(
    lines: list[LineAudio],
    script: Script,
    episode: Episode,
    config: Config,
    transcribe: Transcriber,
    folder: Path,
    resynthesize: Callable[[dict[str, int]], list[LineAudio]],
    report: EpisodeReport,
    log: Callable[[str], None],
) -> list[LineAudio]:
    cache_path = folder / "asr.json"
    try:
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        cache = {}

    flat = script.all_lines()
    candidates_base = set(episode.new_words) | set(episode.review_words)

    def heard(line: LineAudio) -> str:
        digest = _wav_digest(line.wav)
        hit = cache.get(line.id)
        if hit and hit.get("digest") == digest:
            return hit["heard"]
        text = transcribe(line.wav)
        cache[line.id] = {"digest": digest, "heard": text}
        cache_path.write_text(json.dumps(cache, indent=1, ensure_ascii=False), encoding="utf-8")
        return text

    def check(idx: int, line: LineAudio):
        src = flat[idx]
        cands = candidates_base | {w for w in (src.prompt_word, src.card) if w}
        return check_line(line.id, line.text, heard(line), target_words(line.text, cands))

    log(f"  Contrôle de prononciation de {len(lines)} réplique(s)…")
    results = []
    for i, line in enumerate(lines):
        results.append(check(i, line))
        if (i + 1) % 10 == 0 or i + 1 == len(lines):
            log(f"  … {i + 1}/{len(lines)} répliques écoutées")
    failed = {r.line_id for r in results if not r.ok}
    retry = {lid: 1 for lid in failed if next(l for l in lines if l.id == lid).variant == 0}
    if retry:
        log(f"  {len(retry)} réplique(s) mal reconnue(s) : nouvelle synthèse…")
        lines = resynthesize(retry)
        results = [check(i, line) for i, line in enumerate(lines)]

    max_mismatch = config.asr.max_mismatch
    for r, line in zip(results, lines):
        where = f"{line.scene_id}, réplique {line.index + 1}"
        if not r.ok:
            report.issues.append(Issue(ERROR, "asr_target",
                f"« {', '.join(r.missing_targets)} » mal prononcé dans « {r.text} » (entendu : « {r.heard} »). "
                "Écoute le fichier et ajoute une correction dans content/pronunciations.yaml.", where))
        elif r.mismatch > max_mismatch:
            report.issues.append(Issue(WARNING, "asr_mismatch",
                f"écart de {r.mismatch:.0%} : « {r.text} » entendu « {r.heard} »", where))
    report.steps["asr"] = [r.to_dict() for r in results]
    return lines


# --- Aperçu audio ---------------------------------------------------------------------------------


def assemble_voice_track(timeline: dict, lines: list[LineAudio], target: Path) -> float:
    """Place chaque réplique à son instant de la timeline (le son suit exactement l'image)."""
    total = int(round(timeline["duration_s"] * SAMPLE_RATE))
    track = np.zeros(total, dtype=np.float32)
    for entry, line in zip(timeline["lines"], lines):
        audio, rate = read_wav(line.wav)
        if rate != SAMPLE_RATE:
            raise BongoError(f"{line.wav.name} n'est pas en {SAMPLE_RATE} Hz.")
        start = int(round(entry["start"] * SAMPLE_RATE))
        chunk = audio[: max(0, total - start)]
        track[start : start + len(chunk)] += chunk
    write_wav(target, track)
    return total / SAMPLE_RATE


def load_mouth_cues(folder: Path, lines: list[LineAudio]) -> dict[str, list[dict]]:
    cues = {}
    for line in lines:
        path = folder / "lipsync" / f"{line.id}.json"
        if path.is_file():
            cues[line.id] = json.loads(path.read_text(encoding="utf-8")).get("cues", [])
    return cues


def chant_durations(root: Path) -> dict[str, float]:
    from bongo.audio_mix import audio_duration, find_audio

    result = {}
    for name in ("hello", "goodbye"):
        path = find_audio(root, "chants", name)
        if path:
            result[name] = audio_duration(path)
    return result


def make_timeline(folder: Path, script: Script, episode: Episode, config: Config, lines: list[LineAudio]) -> dict:
    from bongo.timeline import build_timeline, save_timeline

    root = folder.parent.parent
    timeline = build_timeline(script, episode, config, [l.duration_s for l in lines], load_mouth_cues(folder, lines),
                              chants=chant_durations(root))
    save_timeline(timeline, folder / "timeline.json")
    return timeline


def update_quest_history(root: Path, episode_id: int, title: str, summary: str) -> None:
    path = root / "content" / "quest_history.yaml"
    header = (
        "# Quêtes déjà utilisées, ajoutées automatiquement après chaque épisode fabriqué.\n"
        "# Sert à varier les histoires : une quête trop proche d'une ancienne bloque l'épisode.\n"
    )
    data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.is_file() else None
    quests = [q for q in ((data or {}).get("quests") or []) if q.get("episode_id") != episode_id]
    quests.append({"episode_id": episode_id, "title": title, "quest_summary": summary})
    quests.sort(key=lambda q: q.get("episode_id", 0))
    path.write_text(header + yaml.safe_dump({"quests": quests}, allow_unicode=True, sort_keys=False), encoding="utf-8")


# --- Enchaînement ------------------------------------------------------------------------------------


def build_episode_audio(
    root: Path,
    episode_id: int,
    script_file: Path | None = None,
    new_script: bool = False,
    llm_factory: Callable[[], object] | None = None,
    synth: Synth | None = None,
    transcriber: Transcriber | None = None,
    rhubarb_runner=None,
    render: bool = True,
    workers: int | None = None,
    log: Callable[[str], None] = print,
) -> EpisodeReport:
    config = load_config(root)
    curriculum = load_curriculum(root)
    rules = load_rules(root)
    episode = curriculum.get(episode_id)
    folder = episode_dir(root, episode_id)
    folder.mkdir(parents=True, exist_ok=True)
    report = EpisodeReport(episode_id)

    def finish() -> EpisodeReport:
        (folder / "qa.json").write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        return report

    # Outils vérifiés AVANT d'appeler Gemini (ne pas gaspiller le quota)
    rhubarb = None if rhubarb_runner else find_rhubarb(root)

    log(f"Épisode {episode_id} — {', '.join(episode.new_words) or 'révision'}")
    log("1/10 Scénario")
    script, check, info = obtain_script(
        root, episode, curriculum, config, rules, folder, script_file, new_script, llm_factory, log
    )
    report.steps["script"] = {**info, **check.to_dict()}
    report.issues += check.issues
    if check.status == "error":
        return finish()

    log("2/10 Voix")
    pronunciations = load_pronunciations(root)
    audio_dir = folder / "audio"
    variants_path = audio_dir / "variants.json"
    try:
        variants = json.loads(variants_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        variants = {}
    engine = {"synth": synth}

    def synthesize(extra: dict[str, int] | None = None) -> list[LineAudio]:
        if extra:
            variants.update(extra)
            audio_dir.mkdir(parents=True, exist_ok=True)
            variants_path.write_text(json.dumps(variants), encoding="utf-8")
        if engine["synth"] is None:
            from bongo.tts import load_kokoro

            engine["synth"] = load_kokoro()
        return synthesize_script(script, config, audio_dir, engine["synth"], pronunciations, variants, log)

    lines = synthesize()

    log("3/10 Contrôle de prononciation")
    if transcriber is None:
        transcriber = load_whisper(config.asr.model, config.asr.device, config.asr.compute_type)
    lines = run_asr(lines, script, episode, config, transcriber, folder, synthesize, report, log)

    log("4/10 Bouches")
    kwargs = {"runner": rhubarb_runner} if rhubarb_runner else {"runner": run_rhubarb}
    lipsync_lines(lines, folder / "lipsync", rhubarb or Path("rhubarb"), log=log, **kwargs)
    report.steps["lipsync"] = {"lines": len(lines)}

    log("5/10 Minutage")
    from bongo.timeline import check_timeline

    timeline = make_timeline(folder, script, episode, config, lines)
    for problem in check_timeline(timeline, config.qa.min_shot_s):
        report.issues.append(Issue(ERROR, "timeline", problem))
    voice = folder / "voice.wav"
    report.duration_s = assemble_voice_track(timeline, lines, voice)
    low, high = config.qa.review_duration_s if episode.is_review else config.qa.lesson_duration_s
    if not low <= report.duration_s <= high:
        report.issues.append(Issue(WARNING, "real_duration",
            f"durée réelle {report.duration_s:.0f} s, hors de l'intervalle prévu ({low:g} à {high:g} s)"))

    if render and report.status != "error":
        finish_episode(root, episode, script, config, timeline, voice, folder, report, workers, log)

    if report.status != "error":
        update_quest_history(root, episode_id, script.title, script.quest_summary)
    finish()
    if render:
        from bongo.report import publish_to_week, week_dir, week_start_for, write_week_report

        start = week_start_for(curriculum, episode)
        publish_to_week(root, episode_id, report.status, week_dir(root, start))
        report.steps["report"] = str(write_week_report(root, curriculum, start))
        finish()
    return report


def finish_episode(root, episode, script, config, timeline, voice, folder, report, workers, log) -> None:
    """Image, son mixé, sous-titres, miniature, métadonnées."""
    from bongo.audio_mix import master, mix_tracks
    from bongo.metadata import build_metadata, write_metadata
    from bongo.render import render_video
    from bongo.subtitles import write_srt
    from bongo.thumbnail import make_thumbnail

    stem = f"ep{episode.id:03d}"
    log("6/10 Image")
    video = render_video(root, timeline, config, folder / "video.mp4", workers=workers, log=log)
    log("7/10 Son : musique, bruitages, volume")
    mix, warnings = mix_tracks(root, timeline, voice, config.audio.music_db_under_voice, log=log)
    for w in warnings:
        report.issues.append(Issue(WARNING, "audio_asset", w))
    loud = master(mix, video, folder / f"{stem}.mp4", config.audio.loudness_lufs, folder)
    report.steps["mix"] = loud
    if abs(loud["integrated_lufs"] - config.audio.loudness_lufs) > 1.0:
        report.issues.append(Issue(WARNING, "loudness",
            f"volume final {loud['integrated_lufs']:.1f} LUFS au lieu de {config.audio.loudness_lufs:g}"))
    log("8/10 Sous-titres")
    write_srt(timeline, folder / f"{stem}.srt")
    log("9/10 Miniature")
    make_thumbnail(root, episode, script.title, folder / "thumb.png")
    log("10/10 Métadonnées et rapport")
    write_metadata(build_metadata(episode, script.title, script.quest_summary, config, f"{stem}.srt"),
                   folder / "metadata.json")
    report.steps["render"] = {"video": f"{stem}.mp4", "subtitles": f"{stem}.srt", "thumbnail": "thumb.png"}


# --- Rendu seul -------------------------------------------------------------------------------------


def render_episode(
    root: Path,
    episode_id: int,
    script_file: Path | None = None,
    max_seconds: float | None = None,
    still_at: float | None = None,
    workers: int | None = None,
    log: Callable[[str], None] = print,
) -> Path:
    """Refait le minutage et l'image d'un épisode.

    Avec les voix déjà fabriquées : minutage réel, bouches synchronisées, aperçu avec le son.
    Sans voix (ou avec --script-file) : maquette muette, durées estimées, bouches fermées.
    """
    from bongo.render import mux_preview, render_still, render_video
    from bongo.script_check import estimate_duration
    from bongo.tts import wav_duration
    from bongo.timeline import build_timeline, save_timeline

    config = load_config(root)
    curriculum = load_curriculum(root)
    episode = curriculum.get(episode_id)
    folder = episode_dir(root, episode_id)
    folder.mkdir(parents=True, exist_ok=True)
    script_path = script_file or folder / "script.json"
    if not script_path.is_file():
        raise BongoError(
            f"Pas de scénario pour l'épisode {episode_id} : lance d'abord `python -m bongo build-episode {episode_id}` "
            "ou donne un scénario avec --script-file."
        )
    script = load_script(script_path)
    audio_dir = folder / "audio"
    flat = script.all_lines()
    wavs = [audio_dir / f"l{i:03d}.wav" for i in range(1, len(flat) + 1)]
    with_audio = script_file is None and all(w.is_file() for w in wavs)
    if with_audio:
        lines = [LineAudio(w.stem, "", 0, l.speaker, l.text, w, w.with_suffix(".txt"), wav_duration(w))
                 for w, l in zip(wavs, flat)]
        timeline = make_timeline(folder, script, episode, config, lines)
    else:
        log("  Voix absentes : maquette muette avec durées estimées et bouches fermées.")
        qa = config.qa
        durations = [max(qa.estimate_min_line_s, len(l.text.split()) / qa.estimate_words_per_s) for l in flat]
        timeline = build_timeline(script, episode, config, durations, chants=chant_durations(root))
        save_timeline(timeline, folder / "timeline.json")
    if still_at is not None:
        out = render_still(root, timeline, config, still_at, folder / f"image_{still_at:g}s.png")
        return out
    video = render_video(root, timeline, config, folder / "video.mp4", workers=workers, max_seconds=max_seconds, log=log)
    if with_audio:
        voice = folder / "voice.wav"
        assemble_voice_track(timeline, lines, voice)
        return mux_preview(video, voice, folder / f"ep{episode_id:03d}_apercu.mp4")
    return video


# --- Écoute des mots du programme --------------------------------------------------------------------


def pronounce_words(
    root: Path,
    synth: Synth | None = None,
    transcriber: Transcriber | None = None,
    words: list[str] | None = None,
    log: Callable[[str], None] = print,
) -> Path:
    """Fait dire chaque mot du programme par la voix de Bongo ; page d'écoute avec les phonèmes."""
    import html

    from bongo.asr_check import check_line
    from bongo.tts import apply_pronunciations, load_kokoro

    config = load_config(root)
    curriculum = load_curriculum(root)
    pronunciations = load_pronunciations(root)
    vc = config.voices["bongo"]
    words = words or list(dict.fromkeys(curriculum.all_words()))
    unknown = [w for w in words if w not in curriculum.all_words()]
    if unknown:
        raise BongoError(f"Mot(s) absent(s) du programme : {', '.join(unknown)}")
    synth = synth or load_kokoro()
    if transcriber is None:
        try:
            transcriber = load_whisper(config.asr.model, config.asr.device, config.asr.compute_type)
        except BongoError as exc:
            log(f"  (contrôle Whisper désactivé : {exc})")
    out = root / "out" / "pronounce"
    rows = []
    doubtful = 0
    for i, word in enumerate(words, 1):
        log(f"  [{i}/{len(words)}] {word}")
        text = f"{word.capitalize()}!"
        write_wav(out / f"{word}.wav", synth(apply_pronunciations(text, pronunciations), vc.voice, vc.speed))
        phon = getattr(synth, "last_phonemes", "")
        heard, flag = "", ""
        if transcriber:
            heard = transcriber(out / f"{word}.wav")
            if not check_line(word, text, heard, [word]).ok:
                flag = "⚠ à écouter"
                doubtful += 1
        fixed = "corrigé" if word in pronunciations else ""
        rows.append(
            f"<tr><td><b>{word}</b></td><td><audio controls preload='none' src='{word}.wav'></audio></td>"
            f"<td><code>{html.escape(phon)}</code></td><td>{html.escape(heard)}</td><td>{flag} {fixed}</td></tr>"
        )
    page = out / "ecoute.html"
    page.write_text(
        "<!doctype html><meta charset='utf-8'><title>Prononciation</title>"
        "<style>body{font-family:sans-serif;margin:2em}td{padding:.3em .8em}tr:nth-child(even){background:#f3f3f3}</style>"
        f"<h1>Les {len(words)} mots du programme, voix de Bongo ({vc.voice}, vitesse {vc.speed:g})</h1>"
        "<p>Écoute chaque mot. S'il est mal prononcé, ajoute une ligne dans <code>content/pronunciations.yaml</code> : "
        "<code>mot: \"phonèmes\"</code> en partant des phonèmes affichés, puis relance <code>pronounce</code>.</p>"
        "<table><tr><th>Mot</th><th>Écoute</th><th>Phonèmes Kokoro</th><th>Whisper a entendu</th><th></th></tr>"
        f"{''.join(rows)}</table>",
        encoding="utf-8",
    )
    log(f"  {doubtful} mot(s) signalé(s) par Whisper." if transcriber else "")
    return page
