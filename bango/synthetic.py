"""Données simulées au format tennis-data, pour tester le moteur sans connexion.

Les résultats viennent de niveaux de joueurs cachés. Pinnacle voit ces niveaux
avec un peu de bruit et une petite marge ; Bet365 avec plus de bruit et une
marge plus grosse. Ces données servent à vérifier que le moteur fonctionne,
pas à prouver qu'une stratégie gagne dans la réalité.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

SURFACES = ["Hard", "Clay", "Grass"]
SURFACE_SHARE = [0.6, 0.3, 0.1]
ROUNDS = ["1st Round", "2nd Round", "Quarterfinals", "Semifinals", "The Final"]


def _price(p: float, margin: float, noise: float, rng: np.random.Generator) -> tuple[float, float]:
    """Cote à deux issues autour de la proba p, bruitée puis margée."""
    logit = np.log(p / (1 - p)) + rng.normal(0, noise)
    q = 1 / (1 + np.exp(-logit))
    qa, qb = q * (1 + margin), (1 - q) * (1 + margin)
    return round(max(1.01, 1 / qa), 2), round(max(1.01, 1 / qb), 2)


def generate(
    n_players: int = 120,
    n_matches: int = 12000,
    start: str = "2019-01-01",
    seed: int = 7,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    base = rng.normal(0, 1.0, n_players)
    surface_skill = {s: base + rng.normal(0, 0.35, n_players) for s in SURFACES}
    names = [f"Joueur{i:03d} X." for i in range(n_players)]

    days = pd.date_range(start, periods=max(1, n_matches // 10), freq="D")
    rows = []
    for i in range(n_matches):
        date = days[min(i // 10, len(days) - 1)]
        surface = rng.choice(SURFACES, p=SURFACE_SHARE)
        a, b = rng.choice(n_players, 2, replace=False)
        diff = surface_skill[surface][a] - surface_skill[surface][b]
        p_a = 1 / (1 + np.exp(-1.1 * diff))
        a_wins = rng.random() < p_a
        w, l = (a, b) if a_wins else (b, a)
        p_w = p_a if a_wins else 1 - p_a

        ps_w, ps_l = _price(p_w, margin=0.025, noise=0.12, rng=rng)
        b365_w, b365_l = _price(p_w, margin=0.055, noise=0.15, rng=rng)
        comment = "Completed" if rng.random() > 0.03 else "Retired"
        rows.append(
            {
                "Date": date.strftime("%d/%m/%Y"),
                "Tournament": f"Tournoi {date.isocalendar().week}",
                "Surface": surface,
                "Round": ROUNDS[rng.integers(0, len(ROUNDS))],
                "Best of": 3,
                "Winner": names[w],
                "Loser": names[l],
                "WRank": int(np.argsort(-base).tolist().index(w)) + 1,
                "LRank": int(np.argsort(-base).tolist().index(l)) + 1,
                "Comment": comment,
                "B365W": b365_w,
                "B365L": b365_l,
                "PSW": ps_w,
                "PSL": ps_l,
                "MaxW": max(b365_w, ps_w),
                "MaxL": max(b365_l, ps_l),
                "AvgW": round((b365_w + ps_w) / 2, 2),
                "AvgL": round((b365_l + ps_l) / 2, 2),
            }
        )
    return pd.DataFrame(rows)
