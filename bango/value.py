"""Analyse d'un match à venir : cote d'un bookmaker contre prix juste de Pinnacle."""

from __future__ import annotations

from dataclasses import dataclass

from .odds import expected_value, fair_probabilities, kelly_fraction, overround


@dataclass
class SideValue:
    label: str
    fair_probability: float
    fair_odds: float
    offered_odds: float
    edge: float


@dataclass
class ValueAssessment:
    sides: tuple[SideValue, SideValue]
    reference_margin: float
    bookmaker_margin: float
    pick: SideValue | None
    stake: float


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
    fa, fb = fair_probabilities(ref_a, ref_b)
    sides = tuple(
        SideValue(label, p, 1 / p, odds, expected_value(p, odds))
        for label, p, odds in ((labels[0], fa, odds_a), (labels[1], fb, odds_b))
    )
    eligible = [s for s in sides if min_edge <= s.edge <= max_edge]
    pick = max(eligible, key=lambda s: s.edge) if eligible else None
    stake = 0.0
    if pick:
        fraction = min(kelly_fraction(pick.fair_probability, pick.offered_odds) * kelly_multiplier, max_stake_pct)
        stake = round(fraction * bankroll, 2)
    return ValueAssessment(sides, overround(ref_a, ref_b), overround(odds_a, odds_b), pick, stake)
