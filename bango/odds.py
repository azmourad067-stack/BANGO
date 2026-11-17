"""Outils sur les cotes décimales : probabilités implicites, marge, dévigage, valeur, Kelly."""

from __future__ import annotations

import math


def implied_probability(odds: float) -> float:
    """Probabilité implicite brute d'une cote décimale (marge incluse)."""
    if odds <= 1.0:
        raise ValueError(f"Cote invalide : {odds}")
    return 1.0 / odds


def overround(odds_a: float, odds_b: float) -> float:
    """Marge du bookmaker sur un marché à deux issues (0.05 = 5 %)."""
    return implied_probability(odds_a) + implied_probability(odds_b) - 1.0


def fair_probabilities_n(odds: list[float], method: str = "power") -> list[float]:
    """Retire la marge d'un marché à n issues (2 pour le tennis, 3 pour le football).

    - ``proportional`` : divise chaque probabilité implicite par leur somme.
    - ``power`` : trouve k tel que la somme des p**k vaut 1. Corrige mieux le biais
      favori/outsider (les bookmakers chargent davantage la marge sur l'outsider).
    """
    implied = [implied_probability(o) for o in odds]
    if method == "proportional":
        total = sum(implied)
        return [p / total for p in implied]
    if method == "power":
        lo, hi = 0.5, 3.0
        for _ in range(100):
            k = (lo + hi) / 2
            if sum(p**k for p in implied) > 1.0:
                lo = k
            else:
                hi = k
        k = (lo + hi) / 2
        powered = [p**k for p in implied]
        total = sum(powered)
        return [p / total for p in powered]
    raise ValueError(f"Méthode de dévigage inconnue : {method}")


def fair_probabilities(odds_a: float, odds_b: float, method: str = "power") -> tuple[float, float]:
    """Version à deux issues de :func:`fair_probabilities_n`."""
    a, b = fair_probabilities_n([odds_a, odds_b], method)
    return a, b


def margin(odds: list[float]) -> float:
    """Marge du bookmaker sur un marché à n issues (0.05 = 5 %)."""
    return sum(implied_probability(o) for o in odds) - 1.0


def expected_value(probability: float, odds: float) -> float:
    """Espérance de gain pour 1 € misé. 0.05 = +5 % de rendement attendu."""
    return probability * odds - 1.0


def kelly_fraction(probability: float, odds: float) -> float:
    """Fraction de bankroll optimale selon Kelly (0 si le pari n'a pas de valeur)."""
    b = odds - 1.0
    f = (probability * b - (1.0 - probability)) / b
    return max(0.0, f)


def logit(p: float) -> float:
    p = min(max(p, 1e-9), 1 - 1e-9)
    return math.log(p / (1 - p))


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))
