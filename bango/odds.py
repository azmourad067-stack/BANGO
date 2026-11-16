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


def fair_probabilities(odds_a: float, odds_b: float, method: str = "power") -> tuple[float, float]:
    """Retire la marge d'un marché à deux issues et renvoie les probabilités « justes ».

    - ``proportional`` : divise chaque probabilité implicite par leur somme.
    - ``power`` : trouve k tel que pa**k + pb**k = 1. Corrige mieux le biais
      favori/outsider (les bookmakers chargent davantage la marge sur l'outsider).
    """
    pa, pb = implied_probability(odds_a), implied_probability(odds_b)
    if method == "proportional":
        total = pa + pb
        return pa / total, pb / total
    if method == "power":
        lo, hi = 0.5, 3.0
        for _ in range(100):
            k = (lo + hi) / 2
            if pa**k + pb**k > 1.0:
                lo = k
            else:
                hi = k
        k = (lo + hi) / 2
        fa, fb = pa**k, pb**k
        return fa / (fa + fb), fb / (fa + fb)
    raise ValueError(f"Méthode de dévigage inconnue : {method}")


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
