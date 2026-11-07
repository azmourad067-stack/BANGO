"""Point d'entrée : python -m bongo <commande>."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from bongo.errors import BongoError

NOT_YET: dict[str, int] = {}


def _root() -> Path:
    from bongo.config import find_root

    return find_root()


def cmd_check_setup(args: argparse.Namespace) -> int:
    from bongo.setup_check import MISSING, format_checks, run_checks

    checks = run_checks(_root())
    print(format_checks(checks))
    return 1 if any(c.status == MISSING for c in checks) else 0


def cmd_placeholders(args: argparse.Namespace) -> int:
    from bongo.curriculum import load_curriculum
    from bongo.placeholders import generate_placeholders

    root = _root()
    print("Création des assets provisoires…")
    stats = generate_placeholders(root, load_curriculum(root), force=args.force)
    print(
        f"{stats['created']} créé(s), {stats['replaced']} régénéré(s), "
        f"{stats['kept']} déjà présent(s) laissé(s) tels quels."
    )
    print("Les vrais dessins ne sont jamais écrasés. Liste des provisoires : assets/placeholders.txt")
    return 0


def cmd_voices(args: argparse.Namespace) -> int:
    from bongo.config import load_config
    from bongo.tts import AMERICAN_VOICES, preview_voices

    root = _root()
    speed = args.speed if args.speed is not None else load_config(root).voices["bongo"].speed
    voices = [v.strip() for v in args.voices.split(",")] if args.voices else list(AMERICAN_VOICES)
    print(f"Synthèse de « {args.text} » par {len(voices)} voix (vitesse {speed:g})…")
    page = preview_voices(args.text, root / "out" / "voices", speed, voices)
    print(f"Terminé. Ouvre cette page pour écouter et comparer :\n  {page}")
    return 0


def cmd_check_script(args: argparse.Namespace) -> int:
    from bongo.config import load_config
    from bongo.curriculum import load_curriculum
    from bongo.schema import load_script
    from bongo.script_check import check_script, load_rules

    root = _root()
    path = Path(args.file)
    script = load_script(path)
    curriculum = load_curriculum(root)
    episode = curriculum.get(args.episode or script.episode_id)
    result = check_script(script, episode, curriculum, load_config(root), load_rules(root))
    print(result.summary_fr())
    if args.json:
        Path(args.json).write_text(json.dumps(result.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Détail enregistré dans {args.json}")
    return 1 if result.status == "error" else 0


def cmd_build_episode(args: argparse.Namespace) -> int:
    from bongo.pipeline import build_episode_audio, episode_dir

    root = _root()
    script_file = Path(args.script_file) if args.script_file else None
    report = build_episode_audio(root, args.episode, script_file=script_file, new_script=args.new_script,
                                 render=not args.no_video)
    folder = episode_dir(root, args.episode)
    print()
    print(report.summary_fr())
    print(f"\nFichiers : {folder}")
    final = folder / f"ep{args.episode:03d}.mp4"
    if final.is_file() and report.status != "error":
        print(f"Vidéo : {final}")
    if "report" in report.steps:
        print(f"Rapport de la semaine (métadonnées à copier dans YouTube Studio) :\n  {report.steps['report']}")
    return 1 if report.status == "error" else 0


def cmd_render(args: argparse.Namespace) -> int:
    from bongo.pipeline import render_episode

    root = _root()
    script_file = Path(args.script_file) if args.script_file else None
    out = render_episode(root, args.episode, script_file=script_file, max_seconds=args.seconds, still_at=args.image)
    print(f"Terminé : {out}")
    return 0


def _date(text: str):
    import datetime as dt

    try:
        return dt.date.fromisoformat(text)
    except ValueError:
        raise BongoError(f"Date invalide : {text} (format attendu : 2026-12-01)") from None


def cmd_build_week(args: argparse.Namespace) -> int:
    from bongo.week import build_week, duration_advice

    root = _root()
    results = build_week(root, _date(args.start), force=args.force)
    print("\nBilan de la semaine :")
    labels = {"ok": "OK", "warning": "OK avec avertissements", "error": "BLOQUÉ", "non fabriqué": "non fabriqué"}
    for ep_id, status in results.items():
        print(f"  Épisode {ep_id:>2} : {labels.get(status, status)}")
    advice = duration_advice(root, list(results))
    if advice:
        print(f"\n{advice}")
    from bongo.report import week_dir

    print(f"\nOuvre le rapport : {week_dir(root, _date(args.start)) / 'report.html'}")
    return 1 if any(s in ("error", "non fabriqué") for s in results.values()) else 0


def cmd_compile(args: argparse.Namespace) -> int:
    from bongo.compile import compile_range, default_title
    from bongo.curriculum import load_curriculum

    root = _root()
    if args.week:
        from bongo.week import check_week_start

        curriculum = load_curriculum(root)
        start = _date(args.week)
        check_week_start(curriculum, start)
        eps = curriculum.week(start)
        first, last = eps[0].id, eps[-1].id
    elif args.from_ is not None and args.to is not None:
        first, last = args.from_, args.to
    else:
        raise BongoError("Indique la semaine (--week 2026-12-01) ou les épisodes (--from 1 --to 7).")
    title = args.title or default_title(load_curriculum(root), first, last)
    out = compile_range(root, first, last, title)
    print(f"Compilation : {out}\nMiniature, sous-titres et métadonnées dans le même dossier.")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    import datetime as dt

    from bongo.curriculum import load_curriculum
    from bongo.report import write_week_report

    start = _date(args.start)
    root = _root()
    print(f"Rapport : {write_week_report(root, load_curriculum(root), start)}")
    return 0


def cmd_pronounce(args: argparse.Namespace) -> int:
    from bongo.pipeline import pronounce_words

    words = [w.strip().lower() for w in args.words.split(",")] if args.words else None
    page = pronounce_words(_root(), words=words)
    print(f"Terminé. Ouvre cette page pour écouter chaque mot :\n  {page}")
    return 0


def cmd_programme(args: argparse.Namespace) -> int:
    from bongo.curriculum import load_curriculum

    curriculum = load_curriculum(_root())
    for e in curriculum.episodes:
        words = ", ".join(e.new_words) if e.new_words else f"révision ({len(e.review_words)} mots)"
        print(f"{e.id:>2}  {e.date}  {e.biome:<9} {words:<28} amis : {', '.join(e.friends)}")
    return 0


def _not_yet(step: int):
    def run(args: argparse.Namespace) -> int:
        print(f"Cette commande arrive à l'étape {step} de la construction. Elle n'est pas encore disponible.")
        return 2

    return run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m bongo", description="Fabrication des épisodes de Bongo the Gorilla")
    sub = parser.add_subparsers(dest="command", metavar="commande")

    p = sub.add_parser("check-setup", help="vérifie l'installation (outils, clés, assets)")
    p.set_defaults(func=cmd_check_setup)

    p = sub.add_parser("placeholders", help="crée des assets provisoires pour développer")
    p.add_argument("--force", action="store_true", help="régénère aussi les provisoires existants (jamais les vrais dessins)")
    p.set_defaults(func=cmd_placeholders)

    p = sub.add_parser("voices", help="fait dire une phrase par toutes les voix américaines de Kokoro")
    p.add_argument("--text", default="Hello, little explorer!", help="phrase à faire dire")
    p.add_argument("--speed", type=float, default=None, help="vitesse (par défaut : celle de Bongo dans config.yaml)")
    p.add_argument("--voices", default=None, help="liste de voix séparées par des virgules (par défaut : toutes)")
    p.set_defaults(func=cmd_voices)

    p = sub.add_parser("check-script", help="contrôle un scénario écrit à la main (fichier JSON)")
    p.add_argument("file", help="chemin du fichier script.json")
    p.add_argument("--episode", type=int, default=None, help="numéro d'épisode (par défaut : celui du fichier)")
    p.add_argument("--json", default=None, help="enregistre le détail des contrôles dans ce fichier")
    p.set_defaults(func=cmd_check_script)

    p = sub.add_parser("build-episode", help="fabrique un épisode (pour l'instant : scénario, voix, bouches, audio)")
    p.add_argument("episode", type=int, help="numéro de l'épisode")
    p.add_argument("--script-file", default=None, help="utiliser un scénario écrit à la main (mêmes contrôles)")
    p.add_argument("--new-script", action="store_true", help="redemander un scénario à Gemini même s'il en existe un")
    p.add_argument("--no-video", action="store_true", help="s'arrêter au son (plus rapide)")
    p.set_defaults(func=cmd_build_episode)

    p = sub.add_parser("render", help="refait l'image d'un épisode (ou une maquette muette sans les voix)")
    p.add_argument("episode", type=int, help="numéro de l'épisode")
    p.add_argument("--script-file", default=None, help="maquette muette à partir de ce scénario")
    p.add_argument("--seconds", type=float, default=None, help="ne rendre que les N premières secondes")
    p.add_argument("--image", type=float, default=None, help="ne rendre qu'une image, à cet instant (en secondes)")
    p.set_defaults(func=cmd_render)

    p = sub.add_parser("build-week", help="fabrique les 7 épisodes d'une semaine et le rapport")
    p.add_argument("--start", required=True, help="premier jour de la semaine, ex. 2026-12-01")
    p.add_argument("--force", action="store_true", help="refaire aussi les épisodes déjà terminés")
    p.set_defaults(func=cmd_build_week)

    p = sub.add_parser("compile", help="fabrique une compilation d'épisodes")
    p.add_argument("--week", default=None, help="toute une semaine, ex. 2026-12-01")
    p.add_argument("--from", dest="from_", type=int, default=None, help="premier épisode")
    p.add_argument("--to", type=int, default=None, help="dernier épisode")
    p.add_argument("--title", default=None, help="titre (par défaut : « Bongo's Week in the Jungle », selon le milieu)")
    p.set_defaults(func=cmd_compile)

    p = sub.add_parser("report", help="refait le rapport d'une semaine")
    p.add_argument("--start", required=True, help="premier jour de la semaine, ex. 2026-12-01")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("pronounce", help="fait dire chaque mot du programme par la voix de Bongo")
    p.add_argument("--words", default=None, help="seulement ces mots (séparés par des virgules)")
    p.set_defaults(func=cmd_pronounce)

    p = sub.add_parser("programme", help="affiche le programme de la saison")
    p.set_defaults(func=cmd_programme)

    for name, step in NOT_YET.items():
        p = sub.add_parser(name, help=f"(étape {step}, pas encore disponible)")
        p.set_defaults(func=_not_yet(step))
    return parser


def main(argv: list[str] | None = None) -> int:
    import os
    import warnings

    # Avertissements techniques de PyTorch (Kokoro), sans conséquence et incompréhensibles
    warnings.filterwarnings("ignore", module=r"torch(\.|$)")
    # Avertissement sans conséquence sous Windows (cache des modèles sans liens symboliques)
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except AttributeError:
            pass
    parser = build_parser()
    args, extra = parser.parse_known_args(argv)
    if extra and args.command not in NOT_YET:
        parser.error(f"argument(s) non reconnu(s) : {' '.join(extra)}")
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    try:
        return args.func(args)
    except BongoError as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrompu.", file=sys.stderr)
        return 130
