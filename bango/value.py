"""Analyse d'un match à venir : cotes d'un bookmaker contre prix juste de Pinnacle.

Fonctionne pour un marché à deux issues (tennis, basket) comme à trois
(football : victoire, nul, défaite).
"""

from __future__ import annotations

from dataclasses import dataclass

from .odds import expected_value, fair_probabilities_n, kelly_fraction, margin


@dataclass
class SideValue:
    label: str
    fair_probability: float
    fair_odds: float
    offered_odds: float
    edge: float
    bookmaker: str = ""


@dataclass
class ValueAssessment:
    sides: tuple[SideValue, ...]
    reference_margin: float
    bookmaker_margin: float
    pick: SideValue | None
    stake: float


def assess_market(
    reference: list[float],
    offered: list[float],
    labels: list[str],
    bookmakers: list[str] | None = None,
    min_edge: float = 0.02,
    max_edge: float = 0.20,
    bankroll: float = 1000.0,
    kelly_multiplier: float = 0.25,
    max_stake_pct: float = 0.02,
) -> ValueAssessment:
    """Compare chaque issue au prix juste et retient la meilleure valeur, s'il y en a une."""
    if not (len(reference) == len(offered) == len(labels)):
        raise ValueError("Il faut autant de cotes de référence, de cotes proposées et d'issues.")
    fair = fair_probabilities_n(reference)
    books = bookmakers or [""] * len(labels)
    sides = tuple(
        SideValue(label, p, 1 / p, odds, expected_value(p, odds), book)
        for label, p, odds, book in zip(labels, fair, offered, books)
    )
    eligible = [s for s in sides if min_edge <= s.edge <= max_edge]
    pick = max(eligible, key=lambda s: s.edge) if eligible else None
    stake = 0.0
    if pick:
        fraction = min(kelly_fraction(pick.fair_probability, pick.offered_odds) * kelly_multiplier, max_stake_pct)
        stake = round(fraction * bankroll, 2)
    return ValueAssessment(sides, margin(reference), margin(offered), pick, stake)


def assess_value(
    ref_a: float,
    ref_b: float,
    odds_a: float,
    odds_b: float,
    min_edge: float = 0.02,
    max_edge: float = 0.20,
    bankroll: float = 1000.0,
    kelly_multiplier: float = 0.25,
    max_stake_pct: float = 0.02,
    labels: tuple[str, str] = ("A", "B"),
) -> ValueAssessment:
    """Raccourci pour un marché à deux issues."""
    return assess_market(
        [ref_a, ref_b], [odds_a, odds_b], list(labels),
        min_edge=min_edge, max_edge=max_edge, bankroll=bankroll,
        kelly_multiplier=kelly_multiplier, max_stake_pct=max_stake_pct,
    )
