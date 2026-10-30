from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import subprocess
import sys
import unittest

import numpy as np
import pandas as pd

from training.data import COLUMNS, TARGET
from training.prepare_data import (
    export_parquets, load_site_schedules, prepare_hourly_dataset,
    recalculate_working_hours, split_dataset,
)

SCHEDULES = {
    "SITE001": {"working_hours": [8, 19], "working_days": [0, 1, 2, 3, 4]},
    "SITE003": {"working_hours": [0, 24], "working_days": list(range(7))},
}


def make_source_frame():
    dates = pd.to_datetime([
        "2023-01-01 08:00", "2023-01-01 09:00",
        "2023-01-02 08:00", "2023-01-02 09:00", "2023-01-02 10:00",
        "2023-01-02 18:00", "2023-01-02 19:00",
        "2023-01-08 08:00", "2023-01-08 09:00",
        "2024-06-24 00:00", "2024-06-30 00:00", "2024-06-30 23:00",
        "2024-07-01 00:00", "2024-09-30 23:00",
        "2024-10-01 00:00", "2024-12-31 23:00",
    ])
    rows = []
    for site_index, site in enumerate(SCHEDULES):
        for index, timestamp in enumerate(dates):
            value = float(index + 10 + site_index * 100)
            if site == "SITE001" and timestamp == pd.Timestamp("2023-01-01 09:00"):
                value = np.nan
            if site == "SITE003" and timestamp == pd.Timestamp("2023-01-08 08:00"):
                value = 0.0
            rows.append({
                "timestamp": timestamp, "site_id": site,
                "hour": timestamp.hour, "day_of_week": timestamp.dayofweek,
                "month": timestamp.month, "is_working_hours": 1,
                "temperature_celsius": np.nan if index == 0 else 20.0,
                TARGET: value, "unused_column": "à exclure",
            })
    # The input is unordered and has an hour without an exact predecessor.
    return pd.DataFrame(rows).iloc[::-1].reset_index(drop=True)


def write_inputs(directory, frame):
    source = directory / "source.csv"
    frame.to_csv(source, index=False)
    metadata = directory / "metadata"
    metadata.mkdir()
    for site, schedule in SCHEDULES.items():
        (metadata / f"{site}_metadata.json").write_text(
            json.dumps({"site_id": site, "profile": schedule}), encoding="utf-8",
        )
    return source, metadata


class PrepareDataTests(unittest.TestCase):
    def test_schedule_respects_days_boundaries_and_continuous_sites(self):
        raw = make_source_frame()
        before = raw.copy(deep=True)
        result = recalculate_working_hours(raw, SCHEDULES)
        selected = result.set_index(["site_id", "timestamp"])
        for day, expected in [
            ("2023-01-01 08:00", 0), ("2023-01-02 08:00", 1),
            ("2023-01-02 18:00", 1), ("2023-01-02 19:00", 0),
        ]:
            self.assertEqual(selected.loc[("SITE001", pd.Timestamp(day)), "is_working_hours"], expected)
        self.assertTrue(result.loc[result.site_id.eq("SITE003"), "is_working_hours"].eq(1).all())
        pd.testing.assert_frame_equal(raw, before)

    def test_exact_lags_nulls_zero_and_history_across_split(self):
        raw = make_source_frame()
        result = prepare_hourly_dataset(raw, SCHEDULES)
        selected = result.set_index(["site_id", "timestamp"])
        self.assertEqual(result.columns.tolist(), COLUMNS)
        self.assertTrue(result.timestamp.is_monotonic_increasing)
        self.assertTrue(result[TARGET].notna().all())
        self.assertNotIn(("SITE001", pd.Timestamp("2023-01-01 09:00")), selected.index)
        self.assertEqual(selected.loc[("SITE001", pd.Timestamp("2023-01-02 08:00")), "lag_24h"], 10)
        self.assertTrue(pd.isna(selected.loc[("SITE001", pd.Timestamp("2023-01-02 09:00")), "lag_24h"]))
        self.assertTrue(pd.isna(selected.loc[("SITE001", pd.Timestamp("2023-01-02 10:00")), "lag_24h"]))
        self.assertEqual(selected.loc[("SITE001", pd.Timestamp("2023-01-08 08:00")), "lag_168h"], 10)
        self.assertEqual(selected.loc[("SITE003", pd.Timestamp("2023-01-08 08:00")), TARGET], 0)
        self.assertTrue(pd.isna(selected.loc[("SITE001", pd.Timestamp("2023-01-01 08:00")), "temperature_celsius"]))
        boundary = selected.loc[("SITE001", pd.Timestamp("2024-07-01 00:00"))]
        self.assertEqual(boundary.lag_24h, selected.loc[("SITE001", pd.Timestamp("2024-06-30 00:00")), TARGET])
        self.assertEqual(boundary.lag_168h, selected.loc[("SITE001", pd.Timestamp("2024-06-24 00:00")), TARGET])

    def test_split_boundaries_and_sites(self):
        dataset = prepare_hourly_dataset(make_source_frame(), SCHEDULES)
        splits = split_dataset(dataset)
        self.assertEqual(splits["train"].timestamp.max(), pd.Timestamp("2024-06-30 23:00"))
        self.assertEqual(splits["validation"].timestamp.min(), pd.Timestamp("2024-07-01 00:00"))
        self.assertEqual(splits["validation"].timestamp.max(), pd.Timestamp("2024-09-30 23:00"))
        self.assertEqual(splits["test"].timestamp.min(), pd.Timestamp("2024-10-01 00:00"))
        pd.testing.assert_frame_equal(pd.concat(splits.values(), ignore_index=True), dataset)
        for part in splits.values():
            self.assertEqual(set(part.site_id), set(SCHEDULES))
        outside = dataset.copy()
        outside.loc[0, "timestamp"] = pd.Timestamp("2022-12-31 08:00")
        with self.assertRaisesRegex(ValueError, "en dehors"):
            split_dataset(outside)

    def test_invalid_inputs_never_replace_outputs(self):
        for invalid in ["duplicate", "calendar", "target", "temperature", "site_missing_from_test"]:
            with self.subTest(invalid=invalid), TemporaryDirectory() as temporary:
                directory = Path(temporary)
                frame = make_source_frame()
                if invalid == "duplicate":
                    frame = pd.concat([frame, frame.iloc[[0]]], ignore_index=True)
                elif invalid == "calendar":
                    frame.loc[0, "hour"] = -1
                elif invalid == "target":
                    frame.loc[0, TARGET] = -1
                elif invalid == "temperature":
                    frame.loc[0, "temperature_celsius"] = np.inf
                else:
                    frame = frame.loc[~(
                        frame.site_id.eq("SITE003") & frame.timestamp.ge(pd.Timestamp("2024-10-01"))
                    )]
                source, metadata = write_inputs(directory, frame)
                output = directory / "output"
                output.mkdir()
                existing = output / "train.parquet"
                existing.write_bytes(b"existing-output")
                with self.assertRaises(ValueError):
                    export_parquets(source, metadata, output)
                self.assertEqual(existing.read_bytes(), b"existing-output")
                self.assertEqual(sorted(p.name for p in output.iterdir()), ["train.parquet"])

    def test_missing_or_invalid_metadata_fails(self):
        with TemporaryDirectory() as temporary:
            directory = Path(temporary)
            with self.assertRaises(FileNotFoundError):
                load_site_schedules(directory, ["SITE001"])
            path = directory / "SITE001_metadata.json"
            path.write_text(json.dumps({
                "site_id": "SITE001",
                "profile": {"working_hours": [8, 19], "working_days": [True]},
            }))
            with self.assertRaisesRegex(ValueError, "Planning invalide"):
                load_site_schedules(directory, ["SITE001"])

    def test_cli_exports_only_three_files_and_preserves_sources(self):
        with TemporaryDirectory() as temporary:
            directory = Path(temporary)
            frame = make_source_frame()
            source, metadata = write_inputs(directory, frame)
            inputs = [source, *metadata.iterdir()]
            original = {path: sha256(path.read_bytes()).hexdigest() for path in inputs}
            output = directory / "output"
            outcome = subprocess.run([
                sys.executable, "-B", "-m", "training.prepare_data",
                "--source", str(source), "--metadata-dir", str(metadata),
                "--output-dir", str(output),
            ], capture_output=True, text=True, check=True)
            summary = json.loads(outcome.stdout)
            self.assertEqual(set(summary["splits"]), {"train", "validation", "test"})
            self.assertEqual(sorted(p.name for p in output.iterdir()), [
                "test.parquet", "train.parquet", "validation.parquet",
            ])
            expected = split_dataset(prepare_hourly_dataset(frame, SCHEDULES))
            for name, part in expected.items():
                pd.testing.assert_frame_equal(pd.read_parquet(output / f"{name}.parquet"), part)
                self.assertEqual(summary["splits"][name]["rows"], len(part))
            self.assertEqual(original, {path: sha256(path.read_bytes()).hexdigest() for path in inputs})
            # Check the preparation import in a fresh interpreter: other suites may import MLflow.
            subprocess.run([
                sys.executable, "-B", "-c",
                "import sys; import training.prepare_data; assert 'mlflow' not in sys.modules",
            ], capture_output=True, text=True, check=True)


if __name__ == "__main__":
    unittest.main()
