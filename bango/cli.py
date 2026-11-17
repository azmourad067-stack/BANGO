"""Ligne de commande : ``python -m bango <commande>``."""

from __future__ import annotations

import argparse
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .backtest import BacktestResult, run_backtest
from .data import load_matches, normalize
from .elo import SurfaceElo
from .odds import expected_value, fair_probabilities, kelly_fraction
from .strategy import MODELS, StrategyConfig
from .synthetic import generate
from .value import assess_value
from .schedule import DEFAULT_LEAGUES, FRENCH_BOOKS, SPORTS, OddsApiClient, OddsApiError, save_snapshot
from . import journal as journal_mod

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
    if args.tour:
        matches = matches[matches["tour"] == args.tour].reset_index(drop=True)
        if matches.empty:
            raise ValueError(f"Aucun match {args.tour.upper()} dans les fichiers fournis.")
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
            elo.update(row.winner, row.loser, row.surface, row.wrank, row.lrank)
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


def cmd_value(args) -> int:
    """Compare la cote d'un bookmaker au prix juste de Pinnacle pour un match à venir."""
    res = assess_value(*args.ref, *args.odds, min_edge=args.min_edge, bankroll=args.bankroll)
    a, b = res.sides
    print(
        f"\nPrix juste (Pinnacle sans marge) : A {a.fair_odds:.2f} ({a.fair_probability:.1%})"
        f"  |  B {b.fair_odds:.2f} ({b.fair_probability:.1%})"
    )
    print(f"Marge de votre bookmaker : {res.bookmaker_margin:.1%}")
    for side in res.sides:
        print(f"  Joueur {side.label} à {side.offered_odds:.2f} : valeur {side.edge:+.1%}")
    if res.pick:
        p = res.pick
        print(
            f"\n→ Pari à valeur : joueur {p.label} à {p.offered_odds:.2f} (valeur {p.edge:+.1%})."
            f" Mise conseillée : {res.stake:.2f} €"
        )
    else:
        print(f"\n→ Pas de pari : aucune valeur entre {args.min_edge:.0%} et 20 %.")
    return 0


def select_competitions(client: OddsApiClient, sports: list[str], leagues: list[str]) -> list[dict]:
    """Tous les tournois de tennis en cours, et les ligues demandées de football et de basket."""
    chosen = []
    for c in client.competitions():
        if c["sport"] not in sports:
            continue
        if c["sport"] == "tennis" or c["key"] in leagues:
            chosen.append(c)
    return chosen


def print_coverage(matches, books) -> None:
    """Combien de matchs ont pu être comparés, et quelles cotes s'approchaient le plus d'une valeur."""
    print("\nCouverture par sport :")
    closest = []
    for sport in sorted({m.sport for m in matches}):
        group = [m for m in matches if m.sport == sport]
        with_ref = [m for m in group if m.reference is not None]
        compared = [(m, m.assess(books, min_edge=1.0)) for m in with_ref]
        compared = [(m, r) for m, r in compared if r is not None]
        best = max((sd.edge for _, r in compared for sd in r.sides), default=None)
        best_txt = f", meilleure valeur {best:+.1%}" if best is not None else ""
        print(
            f"  {SPORTS.get(sport, sport):<9} {len(group):>4} matchs, {len(with_ref):>4} avec Pinnacle,"
            f" {len(compared):>4} comparables{best_txt}"
        )
        closest += [(sd.edge, m, sd) for m, r in compared for sd in r.sides]
    if closest:
        print("\nLes 5 cotes les plus proches d'une valeur :")
        for edge, m, sd in sorted(closest, key=lambda x: x[0], reverse=True)[:5]:
            print(f"  {edge:+.1%}  {m.label} : {sd.label} à {sd.offered_odds:.2f} ({sd.bookmaker}), juste {sd.fair_odds:.2f}")


def cmd_scan(args) -> int:
    """Relève les cotes, affiche les paris à valeur et les ajoute au journal."""
    key = os.environ.get("ODDS_API_KEY", "")
    if not key:
        raise ValueError("Définissez la variable d'environnement ODDS_API_KEY.")
    try:
        client = OddsApiClient(key)
        comps = select_competitions(client, args.sports, args.leagues)
        print(f"{len(comps)} compétition(s) relevée(s), coût estimé : {len(comps)} requête(s).")
        matches = client.upcoming([c["key"] for c in comps])
    except OddsApiError as exc:
        raise ValueError(str(exc)) from exc

    now = datetime.now(timezone.utc)
    if args.snapshot:
        save_snapshot(args.snapshot, client.raw_events, now, client.requests_remaining)
    journal, new = journal_mod.record(matches, args.books, args.journal, now=now)
    print(f"{len(matches)} matchs analysés, {new} nouvelle(s) opportunité(s) ajoutée(s) à {args.journal}.")
    print_coverage(matches, args.books)
    if client.requests_remaining is not None:
        print(f"Requêtes restantes ce mois-ci : {client.requests_remaining}")

    picks = []
    for m in matches:
        res = m.assess(args.books, min_edge=args.min_edge, bankroll=args.bankroll)
        if res and res.pick:
            picks.append((m, res))
    print(f"\nParis à valeur (≥ {args.min_edge:.0%}) : {len(picks)}")
    for m, res in picks:
        p = res.pick
        print(
            f"  {m.start:%d/%m %H:%M} UTC  [{SPORTS.get(m.sport, m.sport)}] {m.label} : {p.label} à {p.offered_odds:.2f}"
            f" chez {p.bookmaker} (valeur {p.edge:+.1%}, mise {res.stake:.2f} €)"
        )
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
    bt.add_argument("--model", choices=MODELS, default="market")
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
    bt.add_argument("--tour", choices=["atp", "wta"], help="Limite le backtest à un circuit")
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

    va = sub.add_parser("value", help="Compare une cote à celle de Pinnacle pour un match à venir.")
    va.add_argument("--ref", nargs=2, type=float, required=True, metavar=("A", "B"), help="Cotes Pinnacle A et B")
    va.add_argument("--odds", nargs=2, type=float, required=True, metavar=("A", "B"), help="Cotes de votre bookmaker")
    va.add_argument("--min-edge", type=float, default=0.02)
    va.add_argument("--bankroll", type=float, default=1000.0)
    va.set_defaults(func=cmd_value)

    sc = sub.add_parser("scan", help="Relève les cotes du jour et alimente le journal des opportunités.")
    sc.add_argument("--sports", nargs="+", choices=list(SPORTS), default=list(SPORTS))
    sc.add_argument("--leagues", nargs="+", default=list(DEFAULT_LEAGUES), help="Ligues de football et de basket")
    sc.add_argument("--books", nargs="+", default=list(FRENCH_BOOKS), help="Vos bookmakers")
    sc.add_argument("--journal", default="data/journal.csv")
    sc.add_argument("--snapshot", default="data/latest.json", help="Relevé complet relu par l'application")
    sc.add_argument("--min-edge", type=float, default=0.02)
    sc.add_argument("--bankroll", type=float, default=1000.0)
    sc.set_defaults(func=cmd_scan)

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
