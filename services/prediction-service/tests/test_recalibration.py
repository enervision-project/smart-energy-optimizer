import pytest

from prediction_service.recalibration import MAX_RATIO, MIN_RATIO, level_ratios


def week(working_measured, working_predicted, off_measured, off_predicted, hours=84):
    return [(1, working_measured, working_predicted)] * hours + [
        (0, off_measured, off_predicted)
    ] * hours


def test_ratio_is_measured_over_predicted_per_group():
    ratios = level_ratios(week(76.0, 100.0, 40.0, 50.0))

    assert ratios.working == pytest.approx(0.76)
    assert ratios.off == pytest.approx(0.8)
    assert ratios.overall == pytest.approx((76 + 40) / (100 + 50))
    assert ratios.for_hour(1) == ratios.working
    assert ratios.for_hour(0) == ratios.off
    assert not ratios.clamped


def test_sum_ratio_is_not_driven_by_low_night_hours():
    # A very low night hour does not weigh as much as a peak hour.
    observations = [(1, 80.0, 100.0)] * 30 + [(1, 1.0, 0.5)]
    ratio = level_ratios(observations).working
    assert ratio == pytest.approx((30 * 80 + 1) / (30 * 100 + 0.5))
    # An average of hourly ratios would give (30 * 0.8 + 2) / 31, about 0.84.
    assert ratio < 0.81


def test_without_enough_history_the_champion_is_kept():
    ratios = level_ratios([(1, 50.0, 100.0)] * 23)

    assert (ratios.overall, ratios.working, ratios.off) == (1.0, 1.0, 1.0)
    assert ratios.hours == 23


def test_small_group_falls_back_to_the_site_ratio():
    # Data center: always active, no non-working hour.
    ratios = level_ratios([(1, 77.0, 100.0)] * 48)

    assert ratios.working == pytest.approx(0.77)
    assert ratios.off == ratios.overall


@pytest.mark.parametrize(("measured", "expected"), [(10.0, MIN_RATIO), (300.0, MAX_RATIO)])
def test_aberrant_ratio_is_bounded_and_flagged(measured, expected):
    ratios = level_ratios(week(measured, 100.0, measured, 100.0))

    assert ratios.overall == ratios.working == ratios.off == expected
    assert ratios.clamped


def test_zero_prediction_keeps_the_champion():
    assert level_ratios([(0, 10.0, 0.0)] * 48).overall == 1.0
