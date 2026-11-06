"""`python -m bongo check-setup` : vérifie que tout est prêt pour fabriquer des épisodes."""

from __future__ import annotations

import importlib.util
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from bongo.assets import FONT_FILE, missing_assets_for_biome, validate_rig
from bongo.config import PLACEHOLDER, get_secret, load_config
from bongo.curriculum import load_curriculum
from bongo.errors import BongoError
from bongo.placeholders import count_placeholders_in_use
from bongo.tts import KOKORO_REPO

OK, WARN, MISSING = "OK", "ATTENTION", "MANQUANT"
WHISPER_REPO = "Systran/faster-whisper-small.en"


@dataclass
class Check:
    name: str
    status: str
    detail: str
    fix: str = ""


def _has_module(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def _run(cmd: list[str]) -> str | None:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return (out.stdout or "") + (out.stderr or "")


def _hf_cached(repo: str, filename: str) -> bool:
    try:
        from huggingface_hub import try_to_load_from_cache
    except ImportError:
        return False
    try:
        found = try_to_load_from_cache(repo, filename)
    except Exception:
        return False
    return isinstance(found, str)


def rhubarb_path(root: Path) -> Path | None:
    for name in ("rhubarb.exe", "rhubarb"):
        candidate = root / "tools" / "rhubarb" / name
        if candidate.is_file():
            return candidate
    # Si l'archive a été dézippée avec son dossier d'origine
    for candidate in sorted((root / "tools" / "rhubarb").glob("*/rhubarb*")):
        if candidate.is_file() and candidate.suffix in ("", ".exe"):
            return candidate
    return None


def find_espeak() -> str | None:
    found = shutil.which("espeak-ng")
    if found:
        return found
    for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
        if base:
            candidate = Path(base) / "eSpeak NG" / "espeak-ng.exe"
            if candidate.is_file():
                return str(candidate)
    return None


def run_checks(root: Path) -> list[Check]:
    checks: list[Check] = []
    add = checks.append

    # Python
    v = sys.version_info
    version = f"{v.major}.{v.minor}.{v.micro}"
    if (v.major, v.minor) in ((3, 11), (3, 12)):
        add(Check("Python", OK, version))
    else:
        add(Check("Python", MISSING, f"version {version} non prise en charge",
                  "Installe Python 3.12 depuis python.org (Kokoro ne fonctionne pas avec 3.13), "
                  "puis refais l'installation décrite dans le README."))

    # Bibliothèques de base
    base = {"yaml": "PyYAML", "pydantic": "pydantic", "PIL": "Pillow", "numpy": "numpy", "jinja2": "jinja2"}
    absent = [pkg for mod, pkg in base.items() if not _has_module(mod)]
    if absent:
        add(Check("Bibliothèques de base", MISSING, ", ".join(absent), 'Lance : pip install -e ".[tout]"'))
    else:
        add(Check("Bibliothèques de base", OK, "PyYAML, pydantic, Pillow, numpy, jinja2"))

    # Configuration et programme
    try:
        config = load_config(root)
        to_choose = sorted(n for n, vc in config.voices.items() if PLACEHOLDER in vc.voice)
        if to_choose:
            add(Check("Voix (config.yaml)", WARN, f"à choisir : {', '.join(to_choose)}",
                      "Lance `python -m bongo voices`, écoute, puis écris les noms choisis dans config.yaml."))
        else:
            add(Check("Voix (config.yaml)", OK, ", ".join(f"{n}={vc.voice}" for n, vc in config.voices.items())))
        if PLACEHOLDER in config.llm.model:
            add(Check("Modèle Gemini (config.yaml)", WARN, "à choisir",
                      "Dans Google AI Studio, repère un modèle « Flash » gratuit et écris son nom dans "
                      "config.yaml (llm: model)."))
        else:
            add(Check("Modèle Gemini (config.yaml)", OK, config.llm.model))
    except BongoError as exc:
        add(Check("config.yaml", MISSING, str(exc), "Corrige config.yaml (voir CLAUDE.md, section config.yaml)."))
        config = None

    try:
        curriculum = load_curriculum(root)
        add(Check("Programme", OK, f"{len(curriculum.episodes)} épisodes, {len(curriculum.all_words())} mots"))
        if config is not None:
            voiceless = [f for f in ["bongo", *curriculum.all_friends()] if f not in config.voices]
            if voiceless:
                add(Check("Voix des amis", MISSING, f"aucune voix pour : {', '.join(voiceless)}",
                          "Ajoute-les dans config.yaml (rubrique voices), après écoute avec `python -m bongo voices`."))
    except BongoError as exc:
        add(Check("Programme", MISSING, str(exc), "Corrige content/curriculum.yaml."))
        curriculum = None

    # FFmpeg
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        add(Check("FFmpeg", MISSING, "FFmpeg introuvable",
                  "Installe FFmpeg (dans PowerShell : winget install Gyan.FFmpeg), ferme puis rouvre le "
                  "terminal et relance `check-setup`."))
    else:
        encoders = _run([ffmpeg, "-hide_banner", "-encoders"]) or ""
        first = (_run([ffmpeg, "-version"]) or "").splitlines()[:1]
        if "libx264" not in encoders:
            add(Check("FFmpeg", MISSING, "trouvé, mais sans l'encodeur libx264",
                      "Installe une version « full » de FFmpeg (winget install Gyan.FFmpeg)."))
        else:
            add(Check("FFmpeg", OK, first[0] if first else ffmpeg))

    # Rhubarb
    rhubarb = rhubarb_path(root)
    if not rhubarb:
        add(Check("Rhubarb Lip Sync", MISSING, "absent de tools/rhubarb/",
                  "Suis les instructions de tools/rhubarb/LISEZMOI.txt (nécessaire à l'étape 2)."))
    else:
        out = _run([str(rhubarb), "--version"])
        if out is None:
            add(Check("Rhubarb Lip Sync", MISSING, f"{rhubarb.name} ne démarre pas",
                      "Retélécharge la version Windows et copie tout le dossier dézippé dans tools/rhubarb/."))
        else:
            add(Check("Rhubarb Lip Sync", OK, out.strip().splitlines()[0] if out.strip() else str(rhubarb)))

    # Kokoro
    if not _has_module("kokoro"):
        add(Check("Kokoro (voix)", MISSING, "non installé", 'Lance : pip install -e ".[voix]"'))
    else:
        cached = _hf_cached(KOKORO_REPO, "kokoro-v1_0.pth")
        add(Check("Kokoro (voix)", OK if cached else WARN,
                  "installé, modèle présent" if cached else "installé, modèle pas encore téléchargé",
                  "" if cached else "Lance `python -m bongo voices` une fois avec Internet : le modèle se télécharge."))
        if not find_espeak():
            add(Check("espeak-ng", WARN, "introuvable (utile pour les mots rares)",
                      "Installe espeak-ng depuis https://github.com/espeak-ng/espeak-ng/releases "
                      "(fichier .msi), puis rouvre le terminal."))
        else:
            add(Check("espeak-ng", OK, "trouvé"))

    # Whisper
    if not _has_module("faster_whisper"):
        add(Check("faster-whisper (contrôle)", MISSING, "non installé", 'Lance : pip install -e ".[controle]"'))
    else:
        cached = _hf_cached(WHISPER_REPO, "model.bin")
        add(Check("faster-whisper (contrôle)", OK if cached else WARN,
                  "installé, modèle small.en présent" if cached else "installé, modèle small.en pas encore téléchargé",
                  "" if cached else "Il se téléchargera à la première utilisation (étape 2), connexion Internet requise."))

    # Gemini
    if not _has_module("google.genai"):
        add(Check("SDK Gemini", MISSING, "google-genai non installé", 'Lance : pip install -e ".[scenarios]"'))
    else:
        add(Check("SDK Gemini", OK, "google-genai installé"))
    if get_secret(root, "GEMINI_API_KEY"):
        add(Check("Clé Gemini", OK, "trouvée dans .env"))
    else:
        add(Check("Clé Gemini", MISSING, "GEMINI_API_KEY absente",
                  "Crée une clé gratuite sur https://aistudio.google.com/apikey, copie .env.example en .env "
                  "et colle la clé après GEMINI_API_KEY="))

    # Police
    font = root / FONT_FILE
    if font.is_file() and (font.parent / "OFL.txt").is_file():
        add(Check("Police", OK, f"{font.name} (licence OFL présente)"))
    else:
        add(Check("Police", MISSING, f"{FONT_FILE} ou sa licence OFL.txt manquante",
                  "Remets Fredoka.ttf et OFL.txt dans assets/fonts/."))

    # Assets par milieu
    if curriculum is not None:
        for biome in dict.fromkeys(e.biome for e in curriculum.episodes):
            missing = missing_assets_for_biome(root, curriculum, biome)
            if missing:
                cats = sorted({m.category for m in missing})
                add(Check(f"Assets « {biome} »", MISSING, f"{len(missing)} fichier(s) manquant(s) : {', '.join(cats)}",
                          "Lance `python -m bongo placeholders` pour des assets provisoires, ou ajoute les dessins."))
            else:
                add(Check(f"Assets « {biome} »", OK, "complets"))
        from bongo.audio_mix import find_audio, find_music

        no_music = [b for b in dict.fromkeys(e.biome for e in curriculum.episodes) if not find_music(root, b)]
        no_sfx = [n for n in ("card", "jump", "drum") if not find_audio(root, "sfx", n)]
        if no_music or no_sfx:
            add(Check("Musique et bruitages", WARN,
                      "manquants : " + ", ".join([f"musique {b}" for b in no_music] + [f"bruitage {n}" for n in no_sfx]),
                      "Lance `python -m bongo placeholders` (sons provisoires) ou ajoute les fichiers dans assets/audio/ "
                      "(musique : bibliothèque audio YouTube ; bruitages : CC0) et note-les dans LICENSES.md."))
        else:
            add(Check("Musique et bruitages", OK, "présents"))
        rig_problems = []
        for name in ["bongo", *curriculum.all_friends()]:
            if (root / "assets" / "characters" / name).is_dir():
                rig_problems += validate_rig(root, name)
        if rig_problems:
            add(Check("Dessins (rig.json)", MISSING, f"{len(rig_problems)} problème(s) : " + " ; ".join(rig_problems[:4]),
                      "Voir docs/DESSINS.md, section rig.json."))
        provisional = count_placeholders_in_use(root)
        if provisional:
            add(Check("Assets provisoires", WARN, f"{provisional} fichier(s) encore provisoire(s)",
                      "Normal pendant le développement : remplace-les par les vrais dessins avant de publier."))

    # Licences
    if not (root / "LICENSES.md").is_file():
        add(Check("LICENSES.md", MISSING, "registre des licences absent", "Recrée LICENSES.md."))
    return checks


def format_checks(checks: list[Check]) -> str:
    width = max(len(c.name) for c in checks)
    lines = [f"Vérification de l'installation ({platform.system()} {platform.release()})", ""]
    for c in checks:
        lines.append(f"[{c.status:<9}] {c.name:<{width}}  {c.detail}")
        if c.fix and c.status != OK:
            lines.append(f"{'':12}{'':<{width}}  → {c.fix}")
    n_missing = sum(c.status == MISSING for c in checks)
    n_warn = sum(c.status == WARN for c in checks)
    lines.append("")
    if n_missing:
        lines.append(f"{n_missing} élément(s) manquant(s), {n_warn} point(s) d'attention. Corrige-les puis relance `python -m bongo check-setup`.")
    elif n_warn:
        lines.append(f"Tout l'indispensable est là. {n_warn} point(s) d'attention ci-dessus.")
    else:
        lines.append("Tout est prêt.")
    return "\n".join(lines)
