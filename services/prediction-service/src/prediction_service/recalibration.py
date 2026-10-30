"""The Mock API runs lower than the training CSV: a per-site ratio fixes the level."""

from collections.abc import Iterable
from dataclasses import dataclass

# One week covers a full weekday / weekend cycle.
WINDOW_HOURS = 168
# Below this, too little history: unchanged champion forecast (ratio 1).
MIN_HOURS = 24
# Below this, the group (working hours or not) uses the site's overall ratio.
MIN_GROUP_HOURS = 12
# Guards against aberrant data (collection failure, unit change).
MIN_RATIO, MAX_RATIO = 0.5, 1.5


@dataclass(frozen=True)
class LevelRatios:
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
    """Sum over sum: a low night hour does not weigh more than a peak hour."""
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
