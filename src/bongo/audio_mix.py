"""Mixage : voix + musique de fond (20 dB sous la voix, coupée pendant les pauses où l'enfant répond)
+ bruitages + comptines, normalisation loudnorm (I=-14 LUFS, TP=-1,5 dB), puis assemblage avec la vidéo."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import numpy as np

from bongo.errors import BongoError
from bongo.render import find_ffmpeg

MIX_RATE = 48_000
TRUE_PEAK_DB = -1.5
LRA = 11
SFX_DB_UNDER_VOICE = -10.0
MUSIC_RAMP_S = 0.3
MUSIC_FADE_IN_S = 1.5
MUSIC_FADE_OUT_S = 2.5
LOOP_CROSSFADE_S = 1.0
AUDIO_EXTS = (".wav", ".mp3", ".ogg", ".m4a", ".flac")
SFX_NAMES = ("card", "jump", "drum")


def find_audio(root: Path, folder: str, *names: str) -> Path | None:
    """Premier fichier trouvé, en préférant un vrai son à un son provisoire du même nom."""
    from bongo.placeholders import placeholder_paths

    provisional = placeholder_paths(root)
    base = root / "assets" / "audio" / folder
    for name in names:
        found = [base / f"{name}{ext}" for ext in AUDIO_EXTS if (base / f"{name}{ext}").is_file()]
        real = [p for p in found if p.relative_to(root).as_posix() not in provisional]
        if real or found:
            return (real or found)[0]
    return None


def find_music(root: Path, biome: str) -> Path | None:
    return find_audio(root, "music", biome, "default")


def decode(path: Path, rate: int = MIX_RATE) -> np.ndarray:
    """Décode n'importe quel fichier audio en stéréo float32 (n, 2) à `rate` Hz, avec FFmpeg."""
    proc = subprocess.run(
        [find_ffmpeg(), "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "2", "-ar", str(rate), "-"],
        capture_output=True,
    )
    if proc.returncode != 0:
        raise BongoError(f"Impossible de lire {path.name} : {proc.stderr.decode('utf-8', 'replace').strip()[-300:]}")
    return np.frombuffer(proc.stdout, dtype="<f4").reshape(-1, 2).copy()


def audio_duration(path: Path) -> float:
    return len(decode(path)) / MIX_RATE


def speech_rms(voice: np.ndarray, rate: int = MIX_RATE) -> float:
    """Niveau moyen de la voix quand quelqu'un parle (les silences ne comptent pas)."""
    mono = voice.mean(axis=1)
    win = int(0.05 * rate)
    n = len(mono) // win
    if n == 0:
        return 0.0
    frames = mono[: n * win].reshape(n, win)
    rms = np.sqrt((frames**2).mean(axis=1))
    active = rms[rms > rms.max() * 0.1]
    return float(np.sqrt((active**2).mean())) if len(active) else 0.0


def loop_to(track: np.ndarray, length: int, rate: int = MIX_RATE) -> np.ndarray:
    """Répète la musique jusqu'à `length` échantillons, avec un fondu enchaîné à chaque raccord."""
    if len(track) == 0:
        return np.zeros((length, 2), dtype=np.float32)
    xf = min(int(LOOP_CROSSFADE_S * rate), len(track) // 4)
    out = track.copy()
    while len(out) < length:
        if xf:
            ramp = np.linspace(0, 1, xf, dtype=np.float32)[:, None]
            seam = out[-xf:] * (1 - ramp) + track[:xf] * ramp
            out = np.concatenate([out[:-xf], seam, track[xf:]])
        else:
            out = np.concatenate([out, track])
    return out[:length]


def _ramp_envelope(length: int, quiet: list[tuple[float, float]], rate: int = MIX_RATE) -> np.ndarray:
    """1 partout, 0 dans les intervalles `quiet`, avec des rampes douces."""
    env = np.ones(length, dtype=np.float32)
    r = int(MUSIC_RAMP_S * rate)
    for start, end in quiet:
        a, b = int(start * rate), int(end * rate)
        a, b = max(0, a), min(length, b)
        if b <= a:
            continue
        env[a:b] = 0
        lo = max(0, a - r)
        env[lo:a] = np.minimum(env[lo:a], np.linspace(1, 0, a - lo, dtype=np.float32))
        hi = min(length, b + r)
        env[b:hi] = np.minimum(env[b:hi], np.linspace(0, 1, hi - b, dtype=np.float32))
    fi, fo = int(MUSIC_FADE_IN_S * rate), int(MUSIC_FADE_OUT_S * rate)
    env[:fi] *= np.linspace(0, 1, min(fi, length), dtype=np.float32)
    env[-fo:] *= np.linspace(1, 0, min(fo, length), dtype=np.float32)
    return env


def child_pauses(timeline: dict) -> list[tuple[float, float]]:
    """Pauses où l'enfant répond ou mime : la musique s'y arrête."""
    return [(l["end"], l["pause_end"]) for l in timeline["lines"] if l["pause_end"] - l["end"] > 0.5]


def sfx_events(timeline: dict) -> list[tuple[str, float]]:
    from bongo.render import BOUNCE_PERIOD_S

    events = [("card", c["start"]) for c in timeline["cards"]]
    for m in timeline["motions"]:
        if m["motion"] == "bounce":
            t = m["start"]
            while t < m["end"] - 0.1:
                events.append(("jump", t))
                t += BOUNCE_PERIOD_S
        elif m["motion"] == "drum":
            t = m["start"]
            while t < m["end"] - 0.1:
                events.append(("drum", t))
                t += timeline["drum_period_s"]
    return events


def _add(track: np.ndarray, clip: np.ndarray, start_s: float, gain: float, rate: int = MIX_RATE) -> None:
    a = int(start_s * rate)
    if a >= len(track):
        return
    clip = clip[: len(track) - a]
    track[a : a + len(clip)] += clip * gain


def mix_tracks(
    root: Path,
    timeline: dict,
    voice_path: Path,
    music_db_under_voice: float,
    log=print,
) -> tuple[np.ndarray, list[str]]:
    """Renvoie le mélange stéréo 48 kHz et la liste des avertissements."""
    warnings: list[str] = []
    voice = decode(voice_path)
    length = int(round(timeline["duration_s"] * MIX_RATE))
    if len(voice) < length:
        voice = np.concatenate([voice, np.zeros((length - len(voice), 2), dtype=np.float32)])
    voice = voice[:length]
    mix = voice.copy()
    ref = speech_rms(voice) or 0.1

    def level(clip: np.ndarray, db_under: float) -> float:
        rms = speech_rms(clip) or float(np.sqrt((clip**2).mean())) or 1.0
        return ref * 10 ** (db_under / 20) / rms

    # Comptines
    for chant in timeline.get("chants", []):
        path = find_audio(root, "chants", chant["name"])
        if path:
            clip = decode(path)
            _add(mix, clip, chant["start"], level(clip, 0.0))

    # Musique
    music_path = find_music(root, timeline["biome"])
    if music_path is None:
        warnings.append(f"pas de musique pour le milieu « {timeline['biome']} » (assets/audio/music/{timeline['biome']}.mp3)")
    else:
        music = decode(music_path)
        quiet = child_pauses(timeline) + [(c["start"], c["end"]) for c in timeline.get("chants", [])]
        env = _ramp_envelope(length, quiet)
        mix += loop_to(music, length) * level(music, music_db_under_voice) * env[:, None]

    # Bruitages
    clips: dict[str, np.ndarray | None] = {}
    for name, t in sfx_events(timeline):
        if name not in clips:
            path = find_audio(root, "sfx", name)
            clips[name] = decode(path) if path else None
            if path is None:
                warnings.append(f"bruitage « {name} » absent (assets/audio/sfx/{name}.wav)")
        if clips[name] is not None:
            _add(mix, clips[name], t, level(clips[name], SFX_DB_UNDER_VOICE))
    return mix, warnings


# --- Normalisation et assemblage ----------------------------------------------------------------------


def _loudnorm_filter(target: float, measured: dict | None = None) -> str:
    base = f"loudnorm=I={target}:TP={TRUE_PEAK_DB}:LRA={LRA}"
    if not measured:
        return base + ":print_format=json"
    return (base + f":measured_I={measured['input_i']}:measured_TP={measured['input_tp']}"
            f":measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}"
            f":offset={measured['target_offset']}:linear=true:print_format=json")


def _parse_loudnorm(stderr: str) -> dict:
    blocks = re.findall(r"\{[^{}]*\}", stderr)
    if not blocks:
        raise BongoError("FFmpeg n'a pas renvoyé la mesure de volume (loudnorm).")
    return json.loads(blocks[-1])


def measure_loudness(inputs: list[str], target: float = -14.0) -> dict:
    proc = subprocess.run([find_ffmpeg(), "-hide_banner", "-nostats", *inputs, "-af", _loudnorm_filter(target),
                           "-f", "null", "-"], capture_output=True, text=True)
    if proc.returncode != 0:
        raise BongoError(f"Mesure du volume impossible : {proc.stderr.strip()[-300:]}")
    return _parse_loudnorm(proc.stderr)


def master(mix: np.ndarray, video: Path, out: Path, target_lufs: float, work_dir: Path) -> dict:
    """Normalise le mélange (2 passes loudnorm) et l'assemble avec la vidéo : H.264 + AAC 192k."""
    raw = work_dir / "mix.f32"
    raw.write_bytes(np.ascontiguousarray(mix, dtype="<f4").tobytes())
    raw_in = ["-f", "f32le", "-ar", str(MIX_RATE), "-ac", "2", "-i", str(raw)]
    try:
        measured = measure_loudness(raw_in, target_lufs)
        cmd = [find_ffmpeg(), "-y", "-hide_banner", "-nostats", "-i", str(video), *raw_in,
               "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
               "-af", _loudnorm_filter(target_lufs, measured), "-ar", str(MIX_RATE),
               "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-shortest", str(out)]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise BongoError(f"FFmpeg n'a pas pu assembler l'épisode : {proc.stderr.strip()[-400:]}")
    finally:
        raw.unlink(missing_ok=True)
    final = measure_loudness(["-i", str(out)], target_lufs)
    return {"integrated_lufs": float(final["input_i"]), "true_peak_db": float(final["input_tp"])}
