"""Ligne de commande : ``python -m bango <commande>``."""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import pandas as pd

from .backtest import BacktestResult, run_backtest
from .data import load_matches, normalize
from .elo import SurfaceElo
from .odds import expected_value, fair_probabilities, kelly_fraction
from .strategy import MODELS, StrategyConfig
from .synthetic import generate

LABELS = {
    "paris": "Paris",
    "mise_totale": "Mise totale",
    "gain_net": "Gain net",
    "roi": "ROI",
    "taux_reussite": "Taux de réussite",
    "cote_moyenne": "Cote moyenne",
    "valeur_attendue_moyenne": "Valeur attendue moyenne",
    "clv_moyen": "CLV moyen (vs Pinnacle)",
    "part_clv_positif": "Paris avec CLV positif",
    "drawdown_max": "Drawdown maximal",
    "bankroll_initiale": "Bankroll initiale",
    "bankroll_finale": "Bankroll finale",
    "t_stat": "Statistique t",
}
PERCENT = {"roi", "taux_reussite", "valeur_attendue_moyenne", "clv_moyen", "part_clv_positif", "drawdown_max"}
EUROS = {"mise_totale", "gain_net", "bankroll_initiale", "bankroll_finale"}


def _fmt(key: str, value) -> str:
    if isinstance(value, float) and math.isnan(value):
        return "n/d"
    if key in PERCENT:
        return f"{value * 100:+.2f} %" if key in {"roi", "clv_moyen", "valeur_attendue_moyenne"} else f"{value * 100:.1f} %"
    if key in EUROS:
        return f"{value:,.2f} €".replace(",", " ")
    if key in {"cote_moyenne", "t_stat"}:
        return f"{value:.2f}"
    return str(value)


def print_result(result: BacktestResult, title: str) -> None:
    print(f"\n=== {title} ===")
    for key, value in result.summary.items():
        print(f"  {LABELS.get(key, key):<28} {_fmt(key, value)}")
    if result.summary.get("paris", 0):
        t = result.summary["t_stat"]
        verdict = (
            "résultat significatif (t > 2)"
            if t > 2
            else "pas encore significatif : impossible de distinguer l'avantage de la chance"
        )
        print(f"  → {verdict}")
    if result.calibration:
        c = result.calibration
        print(
            f"  Précision sur {c['matchs']} matchs : log-loss Elo {c['log_loss_elo']:.4f}"
            f" / Pinnacle {c['log_loss_pinnacle']:.4f} (plus bas = meilleur)"
        )
    if not result.by_year.empty:
        print("\n  Par année :")
        print(result.by_year.to_string().replace("\n", "\n  ").join(["  ", ""]))
    if not result.by_surface.empty:
        print("\n  Par surface :")
        print(result.by_surface.to_string().replace("\n", "\n  ").join(["  ", ""]))


def _strategy_from(args) -> StrategyConfig:
    return StrategyConfig(
        model=args.model,
        price_source=args.price,
        price_haircut=args.haircut,
        min_edge=args.min_edge,
        max_edge=args.max_edge,
        min_odds=args.min_odds,
        max_odds=args.max_odds,
        min_matches=args.min_matches,
        staking=args.staking,
        flat_stake=args.stake,
    )


def cmd_backtest(args) -> int:
    matches = load_matches(args.files)
    result = run_backtest(matches, _strategy_from(args), bet_from=args.bet_from, initial_bankroll=args.bankroll)
    print(f"{len(matches)} matchs chargés, du {matches['date'].min():%d/%m/%Y} au {matches['date'].max():%d/%m/%Y}.")
    print_result(result, f"Backtest modèle « {args.model} », cotes {args.price} ×{args.haircut}")
    if result.summary["paris"] == 0:
        print(
            "\nAucun pari. Par défaut, la première année ne sert qu'à construire les notes Elo :"
            " chargez plusieurs saisons ou avancez --bet-from."
        )
    if args.export and not result.bets.empty:
        result.bets.to_csv(args.export, index=False)
        print(f"\nDétail des paris exporté dans {args.export}")
    return 0


def cmd_demo(args) -> int:
    raw = generate(seed=args.seed)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    raw.to_csv(out, index=False)
    print(f"Données simulées écrites dans {out} ({len(raw)} matchs).")
    print("Rappel : ce sont des données inventées, elles testent la mécanique, pas la rentabilité réelle.")
    matches = normalize(raw)
    for model in MODELS:
        result = run_backtest(matches, StrategyConfig(model=model))
        print_result(result, f"Démo, modèle « {model} »")
    return 0


def _build_elo(files) -> SurfaceElo:
    elo = SurfaceElo()
    for row in load_matches(files).itertuples(index=False):
        if row.completed:
            elo.update(row.winner, row.loser, row.surface)
    return elo


def cmd_predict(args) -> int:
    elo = _build_elo(args.files)
    for name in (args.a, args.b):
        n = elo.matches_played(name)
        if n == 0:
            print(f"Joueur inconnu dans l'historique : « {name} » (format attendu : « Nom I. »).")
            return 1
        if n < 30:
            print(f"Attention : seulement {n} matchs pour {name}, la note est peu fiable.")

    p = elo.predict(args.a, args.b, args.surface, args.best_of)
    print(f"\n{args.a} vs {args.b} ({args.surface}, {args.best_of} sets)")
    print(f"  Probabilité Elo : {args.a} {p:.1%}  |  {args.b} {1 - p:.1%}")
    print(f"  Cotes justes    : {1 / p:.2f}  |  {1 / (1 - p):.2f}")

    if args.odds_a and args.odds_b:
        fa, fb = fair_probabilities(args.odds_a, args.odds_b)
        print(f"  Cotes proposées : {args.odds_a:.2f}  |  {args.odds_b:.2f}  (proba sans marge {fa:.1%} | {fb:.1%})")
        best = None
        for name, prob, odds in ((args.a, p, args.odds_a), (args.b, 1 - p, args.odds_b)):
            ev = expected_value(prob, odds)
            print(f"  Valeur attendue sur {name} : {ev:+.1%}")
            if ev >= args.min_edge and (best is None or ev > best[2]):
                best = (name, odds, ev, prob)
        if best:
            name, odds, ev, prob = best
            stake = min(kelly_fraction(prob, odds) * 0.25, 0.02) * args.bankroll
            print(f"\n  → Pari à valeur : {name} à {odds:.2f} (valeur {ev:+.1%}). Mise conseillée : {stake:.2f} €")
        else:
            print(f"\n  → Pas de pari : aucune valeur au-dessus de {args.min_edge:.0%}.")
    return 0


def cmd_ranking(args) -> int:
    elo = _build_elo(args.files)
    print(f"\nClassement Elo{' ' + args.surface if args.surface else ''} :")
    for i, (name, rating, n) in enumerate(elo.top(args.top, args.surface), 1):
        print(f"  {i:>3}. {name:<28} {rating:7.1f}  ({n} matchs)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bango", description="Moteur de value betting tennis.")
    sub = parser.add_subparsers(dest="command", required=True)

    bt = sub.add_parser("backtest", help="Rejoue une stratégie sur l'historique.")
    bt.add_argument("files", nargs="+", help="Fichiers tennis-data.co.uk (.xlsx ou .csv)")
    bt.add_argument("--model", choices=MODELS, default="elo")
    bt.add_argument("--price", default="b365", choices=["b365", "avg", "max", "ps"], help="Cote utilisée pour parier")
    bt.add_argument("--haircut", type=float, default=1.0, help="Ex. 0.97 pour simuler un opérateur français")
    bt.add_argument("--min-edge", type=float, default=0.03)
    bt.add_argument("--max-edge", type=float, default=0.20)
    bt.add_argument("--min-odds", type=float, default=1.30)
    bt.add_argument("--max-odds", type=float, default=4.00)
    bt.add_argument("--min-matches", type=int, default=30)
    bt.add_argument("--staking", choices=["flat", "kelly"], default="flat")
    bt.add_argument("--stake", type=float, default=10.0, help="Mise fixe en mode flat")
    bt.add_argument("--bankroll", type=float, default=1000.0)
    bt.add_argument("--bet-from", default=None, help="Date du premier pari (AAAA-MM-JJ)")
    bt.add_argument("--export", default=None, help="Exporte le détail des paris en CSV")
    bt.set_defaults(func=cmd_backtest)

    demo = sub.add_parser("demo", help="Génère des données simulées et lance un backtest.")
    demo.add_argument("--output", default="data/demo.csv")
    demo.add_argument("--seed", type=int, default=7)
    demo.set_defaults(func=cmd_demo)

    pr = sub.add_parser("predict", help="Probabilité et valeur pour un match à venir.")
    pr.add_argument("files", nargs="+")
    pr.add_argument("--a", required=True, help="Joueur A, ex. « Sinner J. »")
    pr.add_argument("--b", required=True, help="Joueur B")
    pr.add_argument("--surface", default="Hard", choices=["Hard", "Clay", "Grass", "Carpet"])
    pr.add_argument("--best-of", type=int, default=3, choices=[3, 5])
    pr.add_argument("--odds-a", type=float)
    pr.add_argument("--odds-b", type=float)
    pr.add_argument("--min-edge", type=float, default=0.03)
    pr.add_argument("--bankroll", type=float, default=1000.0)
    pr.set_defaults(func=cmd_predict)

    rk = sub.add_parser("ranking", help="Classement Elo actuel.")
    rk.add_argument("files", nargs="+")
    rk.add_argument("--surface", choices=["Hard", "Clay", "Grass", "Carpet"])
    rk.add_argument("--top", type=int, default=20)
    rk.set_defaults(func=cmd_ranking)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (ValueError, FileNotFoundError) as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
