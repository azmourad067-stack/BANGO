"""Elo tennis par surface.

Chaque joueur a une note globale et une note par surface. La probabilité d'un
match vient du mélange des deux. Le facteur K diminue avec l'expérience du
joueur (formule popularisée par FiveThirtyEight) : un nouveau joueur bouge
vite, un joueur établi bouge lentement.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class EloConfig:
    initial_rating: float = 1500.0
    k_numerator: float = 250.0
    k_offset: float = 5.0
    k_shape: float = 0.4
    surface_weight: float = 0.5  # part de la note surface dans le mélange
    bo5_adjust: bool = True  # les favoris gagnent plus souvent en 3 sets gagnants
    # Note de départ d'un joueur inconnu déduite de son classement ATP du moment :
    # note = seed_intercept + seed_slope × ln(classement). Sans cela, tout nouveau
    # joueur démarre à 1500, qu'il soit 5e ou 400e mondial.
    rank_seed: bool = True
    seed_intercept: float = 2100.0
    seed_slope: float = -110.0
    seed_k_matches: int = 10  # un joueur classé est traité comme ayant déjà ce nombre de matchs


@dataclass
class _Player:
    rating: float
    matches: int = 0
    initial: float = 1500.0
    k_bonus: int = 0
    surface_rating: dict[str, float] = field(default_factory=dict)
    surface_matches: dict[str, int] = field(default_factory=lambda: defaultdict(int))


def win_probability(rating_a: float, rating_b: float) -> float:
    return 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / 400.0))


def bo3_to_bo5(p_match_bo3: float) -> float:
    """Convertit une proba de match en 2 sets gagnants vers 3 sets gagnants.

    On retrouve la proba de gagner un set ``s`` telle que P(bo3) = s²(3 - 2s),
    puis P(bo5) = s³(10 - 15s + 6s²).
    """
    lo, hi = 0.0, 1.0
    for _ in range(60):
        s = (lo + hi) / 2
        if s * s * (3 - 2 * s) < p_match_bo3:
            lo = s
        else:
            hi = s
    s = (lo + hi) / 2
    return s**3 * (10 - 15 * s + 6 * s * s)


class SurfaceElo:
    def __init__(self, config: EloConfig | None = None):
        self.config = config or EloConfig()
        self._players: dict[str, _Player] = {}

    def seed_rating(self, rank: float | None) -> float | None:
        c = self.config
        if not c.rank_seed or rank is None or rank != rank or rank <= 0:
            return None
        return c.seed_intercept + c.seed_slope * math.log(rank)

    def _player(self, name: str, rank: float | None = None) -> _Player:
        if name not in self._players:
            seed = self.seed_rating(rank)
            if seed is None:
                self._players[name] = _Player(rating=self.config.initial_rating, initial=self.config.initial_rating)
            else:
                self._players[name] = _Player(rating=seed, initial=seed, k_bonus=self.config.seed_k_matches)
        return self._players[name]

    def _k(self, matches: int) -> float:
        c = self.config
        return c.k_numerator / (matches + c.k_offset) ** c.k_shape

    def matches_played(self, name: str) -> int:
        p = self._players.get(name)
        return p.matches if p else 0

    def rating(self, name: str, surface: str | None = None, rank: float | None = None) -> float:
        p = self._player(name, rank)
        if surface is None:
            return p.rating
        surf = p.surface_rating.get(surface, p.initial)
        w = self.config.surface_weight
        return (1 - w) * p.rating + w * surf

    def predict(
        self,
        player_a: str,
        player_b: str,
        surface: str | None = None,
        best_of: int = 3,
        rank_a: float | None = None,
        rank_b: float | None = None,
    ) -> float:
        """Probabilité que ``player_a`` batte ``player_b``."""
        p = win_probability(self.rating(player_a, surface, rank_a), self.rating(player_b, surface, rank_b))
        if best_of == 5 and self.config.bo5_adjust:
            p = bo3_to_bo5(p)
        return p

    def update(
        self,
        winner: str,
        loser: str,
        surface: str | None = None,
        winner_rank: float | None = None,
        loser_rank: float | None = None,
    ) -> None:
        w, l = self._player(winner, winner_rank), self._player(loser, loser_rank)

        expected = win_probability(w.rating, l.rating)
        kw, kl = self._k(w.matches + w.k_bonus), self._k(l.matches + l.k_bonus)
        w.rating += kw * (1 - expected)
        l.rating -= kl * (1 - expected)
        w.matches += 1
        l.matches += 1

        if surface:
            ws = w.surface_rating.get(surface, w.initial)
            ls = l.surface_rating.get(surface, l.initial)
            expected_s = win_probability(ws, ls)
            kws = self._k(w.surface_matches[surface] + w.k_bonus)
            kls = self._k(l.surface_matches[surface] + l.k_bonus)
            w.surface_rating[surface] = ws + kws * (1 - expected_s)
            l.surface_rating[surface] = ls - kls * (1 - expected_s)
            w.surface_matches[surface] += 1
            l.surface_matches[surface] += 1

    def top(self, n: int = 20, surface: str | None = None) -> list[tuple[str, float, int]]:
        rows = [(name, self.rating(name, surface), p.matches) for name, p in self._players.items()]
        return sorted(rows, key=lambda r: r[1], reverse=True)[:n]
