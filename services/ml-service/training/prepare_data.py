import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from .data import COLUMNS, TARGET, validate_frame

PERIODS = {
    "train": ("2023-01-01", "2024-07-01"),
    "validation": ("2024-07-01", "2024-10-01"),
    "test": ("2024-10-01", "2025-01-01"),
}


def load_site_schedules(metadata_dir: Path, site_ids) -> dict:
    schedules = {}
    for site in sorted(site_ids):
        path = metadata_dir / f"{site}_metadata.json"
        if not path.is_file():
            raise FileNotFoundError(f"Métadonnées manquantes pour {site} : {path}")
        metadata = json.loads(path.read_text(encoding="utf-8-sig"))
        profile = metadata.get("profile", {})
        hours, days = profile.get("working_hours"), profile.get("working_days")
        valid_hours = (
            isinstance(hours, list) and len(hours) == 2
            and all(type(value) is int for value in hours)
            and 0 <= hours[0] < hours[1] <= 24
        )
        valid_days = (
            isinstance(days, list)
            and all(type(value) is int and 0 <= value <= 6 for value in days)
        )
        if metadata.get("site_id") != site or not valid_hours or not valid_days:
            raise ValueError(f"Planning invalide pour {site} dans {path}")
        schedules[site] = {"working_hours": hours, "working_days": sorted(set(days))}
    return schedules


def recalculate_working_hours(frame: pd.DataFrame, schedules: dict) -> pd.DataFrame:
    result = frame.copy()
    unknown = set(result.site_id.dropna()) - set(schedules)
    if result.site_id.isna().any() or unknown:
        raise ValueError(f"Site sans planning : {sorted(unknown)}")
    timestamps = pd.to_datetime(result["timestamp"], errors="raise")
    if timestamps.isna().any():
        raise ValueError("Timestamp manquant pour le calcul du planning.")
    flags = pd.Series(0, index=result.index, dtype="int8")
    for site in result.site_id.unique():
        start, end = schedules[site]["working_hours"]
        selected = result.site_id.eq(site)
        flags.loc[selected] = (
            timestamps.loc[selected].dt.dayofweek.isin(schedules[site]["working_days"])
            & timestamps.loc[selected].dt.hour.ge(start)
            & timestamps.loc[selected].dt.hour.lt(end)
        ).astype("int8")
    result["is_working_hours"] = flags
    return result


def prepare_hourly_dataset(source_frame: pd.DataFrame, schedules: dict) -> pd.DataFrame:
    required = set(COLUMNS) - {"is_working_hours", "lag_24h", "lag_168h"}
    missing = required - set(source_frame.columns)
    if missing:
        raise ValueError(f"Colonnes source manquantes : {sorted(missing)}")
    dataset = source_frame.copy()
    dataset["timestamp"] = pd.to_datetime(dataset["timestamp"], errors="raise")
    if dataset.timestamp.isna().any():
        raise ValueError("Timestamp manquant dans le CSV.")
    dataset = dataset.sort_values(["timestamp", "site_id"]).reset_index(drop=True)
    if dataset.duplicated(["site_id", "timestamp"]).any():
        raise ValueError("Clés site/heure dupliquées.")
    for column, expected in [
        ("hour", dataset.timestamp.dt.hour),
        ("day_of_week", dataset.timestamp.dt.dayofweek),
        ("month", dataset.timestamp.dt.month),
    ]:
        if not dataset[column].eq(expected).all():
            raise ValueError(f"{column} ne correspond pas au timestamp.")
    dataset = recalculate_working_hours(dataset, schedules)
    history = dataset.set_index(["site_id", "timestamp"])[TARGET]
    for column, hours in {"lag_24h": 24, "lag_168h": 168}.items():
        previous = dataset.timestamp - pd.Timedelta(hours=hours)
        lookup = pd.MultiIndex.from_arrays(
            [dataset.site_id, previous], names=history.index.names,
        )
        dataset[column] = history.reindex(lookup).to_numpy()
        if not (previous + pd.Timedelta(hours=1) <= dataset.timestamp.dt.normalize()).all():
            raise ValueError("Un lag utilise une heure indisponible au début de la journée.")
    # Missing targets stay in the history until the lags are computed.
    dataset = dataset.dropna(subset=[TARGET]).reset_index(drop=True)
    dataset = dataset.loc[:, COLUMNS]
    validate_frame(dataset, "Données préparées")
    return dataset


def split_dataset(dataset: pd.DataFrame) -> dict[str, pd.DataFrame]:
    splits = {
        name: dataset.loc[
            dataset.timestamp.ge(pd.Timestamp(start))
            & dataset.timestamp.lt(pd.Timestamp(end))
        ].reset_index(drop=True)
        for name, (start, end) in PERIODS.items()
    }
    if sum(len(part) for part in splits.values()) != len(dataset):
        raise ValueError("Des lignes sont en dehors des périodes prévues de 2023 et 2024.")
    sites = set(splits["train"].site_id)
    for name, part in splits.items():
        validate_frame(part, name)
        if set(part.site_id) != sites:
            raise ValueError(f"{name} : les mêmes sites doivent être présents dans les trois jeux.")
    return splits


def export_parquets(source: Path, metadata_dir: Path, output_dir: Path) -> dict:
    source, metadata_dir, output_dir = map(Path, (source, metadata_dir, output_dir))
    targets = {name: output_dir / f"{name}.parquet" for name in PERIODS}
    if source.resolve() in {path.resolve() for path in targets.values()}:
        raise ValueError("Un fichier de sortie ne peut pas remplacer le CSV source.")
    source_frame = pd.read_csv(source)
    if "site_id" not in source_frame:
        raise ValueError("Colonne source manquante : site_id")
    schedules = load_site_schedules(metadata_dir, source_frame.site_id.dropna().unique())
    splits = split_dataset(prepare_hourly_dataset(source_frame, schedules))
    # All validations come before creating or replacing outputs.
    output_dir.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".prepare-", dir=output_dir) as temporary:
        staged = {}
        for name, part in splits.items():
            path = Path(temporary) / f"{name}.parquet"
            part.to_parquet(path, engine="pyarrow", compression="snappy", index=False)
            pd.testing.assert_frame_equal(pd.read_parquet(path), part)
            staged[name] = path
        for name, path in staged.items():
            path.replace(targets[name])
    return {
        "source": str(source), "metadata_dir": str(metadata_dir),
        "splits": {
            name: {
                "path": str(targets[name]), "rows": len(part), "columns": part.columns.tolist(),
                "first_timestamp": part.timestamp.min().isoformat(),
                "last_timestamp": part.timestamp.max().isoformat(),
                "sites": sorted(part.site_id.unique().tolist()),
            }
            for name, part in splits.items()
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Générer train, validation et test depuis le CSV et les métadonnées.",
    )
    parser.add_argument(
        "--source", type=Path, default=Path(".data/ml/raw/all_sites_combined.csv"),
    )
    parser.add_argument(
        "--metadata-dir", type=Path, default=Path(".data/ml/raw/metadata"),
    )
    parser.add_argument("--output-dir", type=Path, default=Path(".data/ml/splits"))
    args = parser.parse_args()
    summary = export_parquets(args.source, args.metadata_dir, args.output_dir)
    print(json.dumps(summary, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
