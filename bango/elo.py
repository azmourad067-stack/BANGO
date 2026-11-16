"""Elo tennis par surface.

Chaque joueur a une note globale et une note par surface. La probabilité d'un
match vient du mélange des deux. Le facteur K diminue avec l'expérience du
joueur (formule popularisée par FiveThirtyEight) : un nouveau joueur bouge
vite, un joueur établi bouge lentement.
"""

from __future__ import annotations

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


@dataclass
class _Player:
    rating: float
    matches: int = 0
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

    def _player(self, name: str) -> _Player:
        if name not in self._players:
            self._players[name] = _Player(rating=self.config.initial_rating)
        return self._players[name]

    def _k(self, matches: int) -> float:
        c = self.config
        return c.k_numerator / (matches + c.k_offset) ** c.k_shape

    def matches_played(self, name: str) -> int:
        p = self._players.get(name)
        return p.matches if p else 0

    def rating(self, name: str, surface: str | None = None) -> float:
        p = self._player(name)
        if surface is None:
            return p.rating
        surf = p.surface_rating.get(surface, self.config.initial_rating)
        w = self.config.surface_weight
        return (1 - w) * p.rating + w * surf

    def predict(self, player_a: str, player_b: str, surface: str | None = None, best_of: int = 3) -> float:
        """Probabilité que ``player_a`` batte ``player_b``."""
        p = win_probability(self.rating(player_a, surface), self.rating(player_b, surface))
        if best_of == 5 and self.config.bo5_adjust:
            p = bo3_to_bo5(p)
        return p

    def update(self, winner: str, loser: str, surface: str | None = None) -> None:
        w, l = self._player(winner), self._player(loser)

        expected = win_probability(w.rating, l.rating)
        kw, kl = self._k(w.matches), self._k(l.matches)
        w.rating += kw * (1 - expected)
        l.rating -= kl * (1 - expected)
        w.matches += 1
        l.matches += 1

        if surface:
            init = self.config.initial_rating
            ws = w.surface_rating.get(surface, init)
            ls = l.surface_rating.get(surface, init)
            expected_s = win_probability(ws, ls)
            kws, kls = self._k(w.surface_matches[surface]), self._k(l.surface_matches[surface])
            w.surface_rating[surface] = ws + kws * (1 - expected_s)
            l.surface_rating[surface] = ls - kls * (1 - expected_s)
            w.surface_matches[surface] += 1
            l.surface_matches[surface] += 1

    def top(self, n: int = 20, surface: str | None = None) -> list[tuple[str, float, int]]:
        rows = [(name, self.rating(name, surface), p.matches) for name, p in self._players.items()]
        return sorted(rows, key=lambda r: r[1], reverse=True)[:n]
