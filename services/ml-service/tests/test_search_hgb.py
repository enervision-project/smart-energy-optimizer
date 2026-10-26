"""Validation des campagnes HGB, sans lire les Parquet ni joindre MLflow."""

from collections import Counter
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

import yaml

from training.search_hgb import build_trials, existing_result

CONFIGS = Path(__file__).resolve().parents[1] / "configs"
SPEC = CONFIGS / "hgb_search_no_weather.yaml"
COMMON = ["site_id", "hour", "day_of_week", "month", "is_working_hours"]
LAGS = {
    "both_lags": ["lag_24h", "lag_168h"],
    "lag_24h": ["lag_24h"],
    "lag_168h": ["lag_168h"],
    "no_lags": [],
}


def parameter_key(config):
    parameters = config["parameters"]
    return tuple(parameters[key] for key in (
        "max_leaf_nodes", "min_samples_leaf", "l2_regularization", "learning_rate", "max_iter",
    ))


class HgbSearchTests(unittest.TestCase):
    def test_no_weather_plan_has_96_unique_trials_on_four_comparable_variants(self):
        base, trials, _ = build_trials(SPEC)
        self.assertEqual(base["experiment"], "consommation-horaire-sans-meteo-v1")
        self.assertEqual(len(trials), 96)
        self.assertEqual(len({trial["tags"]["trial_key"] for trial in trials}), 96)
        self.assertEqual(len({trial["run_name"] for trial in trials}), 96)
        self.assertEqual(
            Counter(trial["tags"]["feature_variant"] for trial in trials),
            Counter({variant: 24 for variant in LAGS}),
        )
        grids = {}
        for variant, lags in LAGS.items():
            selected = [trial for trial in trials if trial["tags"]["feature_variant"] == variant]
            grids[variant] = {parameter_key(trial) for trial in selected}
            self.assertEqual(len(grids[variant]), 24)
            self.assertEqual(sum(trial["parameters"] == base["parameters"] for trial in selected), 1)
            for trial in selected:
                self.assertEqual(trial["features"], [*COMMON, *lags])
                self.assertNotIn("temperature_celsius", trial["features"])
                self.assertEqual(trial["tags"]["weather_enabled"], "false")
                self.assertEqual(trial["tags"]["study_phase"], "grid")
                self.assertEqual(trial["parameters"]["loss"], "absolute_error")
                self.assertFalse(trial["parameters"]["early_stopping"])
                self.assertEqual(trial["parameters"]["random_state"], 42)
                self.assertEqual(trial["parameters"]["max_bins"], 255)
        self.assertTrue(all(grid == grids["both_lags"] for grid in grids.values()))

    def test_legacy_campaigns_still_have_their_original_structure(self):
        _, original, _ = build_trials(CONFIGS / "hgb_search.yaml")
        self.assertEqual(len(original), 32)
        self.assertEqual(sum(trial["tags"]["study_phase"] == "ablation" for trial in original), 8)
        self.assertEqual(sum(trial["tags"]["study_phase"] == "grid" for trial in original), 24)
        self.assertTrue(original[0]["run_name"].startswith("HGB_without_"))
        self.assertTrue(original[8]["run_name"].startswith("HGB_grid_01_"))
        _, no_lags, _ = build_trials(CONFIGS / "hgb_search_without_lags.yaml")
        self.assertEqual(len(no_lags), 24)
        self.assertTrue(all(len(trial["features"]) == 6 for trial in no_lags))
        self.assertTrue(all("temperature_celsius" in trial["features"] for trial in no_lags))

    def test_invalid_or_duplicate_variants_fail_before_training(self):
        specification = yaml.safe_load(SPEC.read_text())
        invalid = [
            {},
            {"bad": []},
            {"bad": [*COMMON, "temperature_celsius"]},
            {"bad": [*COMMON, "hour"]},
            {"bad name": COMMON},
            {"first": COMMON, "duplicate": COMMON},
        ]
        with TemporaryDirectory() as temporary:
            directory = Path(temporary)
            base_name = specification["base_config"]
            (directory / base_name).write_text((CONFIGS / base_name).read_text())
            path = directory / "search.yaml"
            for variants in invalid:
                with self.subTest(variants=variants):
                    mutated = deepcopy(specification)
                    mutated["feature_variants"] = variants
                    path.write_text(yaml.safe_dump(mutated))
                    with self.assertRaises(ValueError):
                        build_trials(path)

    def test_resumed_result_keeps_feature_variant(self):
        _, trials, _ = build_trials(SPEC)
        config = trials[-1]
        previous = SimpleNamespace(
            info=SimpleNamespace(run_id="existing"),
            data=SimpleNamespace(metrics={
                "train_macro_nmae_pct": 10, "val_macro_nmae_pct": 12,
                "val_mae_kwh": 50, "val_rmse_kwh": 100,
            }),
        )
        result = existing_result(previous, config)
        self.assertEqual(result["run_id"], "existing")
        self.assertEqual(result["feature_variant"], "no_lags")
        self.assertEqual(result["features"], COMMON)


if __name__ == "__main__":
    unittest.main()
