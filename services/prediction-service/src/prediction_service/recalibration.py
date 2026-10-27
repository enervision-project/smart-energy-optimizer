"""Recalage de niveau : prévision du champion multipliée par le ratio mesuré / prévu du site.

Le champion a appris la forme journalière sur le CSV historique, mais l'API Mock produit des
niveaux plus bas (0,66 à 0,83 fois selon le site, stables d'un jour à l'autre). Le ratio,
calculé sur les dernières heures mesurées, corrige ce niveau sans toucher au modèle.
Un ratio par site, séparé entre heures travaillées et non travaillées.
"""

from collections.abc import Iterable
from dataclasses import dataclass

#: Fenêtre d'observation : une semaine couvre un cycle complet semaine / week-end.
WINDOW_HOURS = 168
#: En dessous, pas assez de recul : prévision du champion inchangée (ratio 1).
MIN_HOURS = 24
#: En dessous, le groupe (heures travaillées ou non) reprend le ratio global du site.
MIN_GROUP_HOURS = 12
#: Garde-fou contre une donnée aberrante (panne de collecte, changement d'unité).
MIN_RATIO, MAX_RATIO = 0.5, 1.5


@dataclass(frozen=True)
class LevelRatios:
    """Ratios d'un site ; `clamped` signale un ratio ramené dans les bornes."""

    overall: float
    working: float
    off: float
    hours: int
    clamped: bool = False

    def for_hour(self, is_working_hours: int) -> float:
        return self.working if is_working_hours else self.off


NEUTRAL = LevelRatios(1.0, 1.0, 1.0, 0)


def _ratio(measured: float, predicted: float) -> float | None:
    return measured / predicted if predicted > 0 else None


def _clamp(value: float) -> tuple[float, bool]:
    bounded = min(max(value, MIN_RATIO), MAX_RATIO)
    return bounded, bounded != value


def level_ratios(observations: Iterable[tuple[int, float, float]]) -> LevelRatios:
    """Ratios à partir de `(is_working_hours, mesuré, prévu par le champion)` d'heures passées.

    Somme des mesures divisée par la somme des prévisions : une heure de nuit à faible
    consommation ne pèse pas plus qu'une heure de pointe.
    """
    sums = {0: [0.0, 0.0, 0], 1: [0.0, 0.0, 0]}
    for is_working, measured, predicted in observations:
        group = sums[1 if is_working else 0]
        group[0] += measured
        group[1] += predicted
        group[2] += 1
    hours = sums[0][2] + sums[1][2]
    overall = _ratio(sums[0][0] + sums[1][0], sums[0][1] + sums[1][1])
    if hours < MIN_HOURS or overall is None:
        return LevelRatios(1.0, 1.0, 1.0, hours)

    clamped = False
    overall, was_clamped = _clamp(overall)
    clamped |= was_clamped
    by_group = {}
    for flag, (measured, predicted, count) in sums.items():
        ratio = _ratio(measured, predicted) if count >= MIN_GROUP_HOURS else None
        if ratio is None:
            by_group[flag] = overall
        else:
            by_group[flag], was_clamped = _clamp(ratio)
            clamped |= was_clamped
    return LevelRatios(overall, by_group[1], by_group[0], hours, clamped)
