"""Commandes ponctuelles de collecte et de calcul horaire."""

import argparse
import json
import sys
from datetime import UTC, datetime

from etl_worker.backfill import backfill_readings
from etl_worker.bronze import write_readings_bronze
from etl_worker.extract import extract_readings, extract_sites, read_site_profiles
from etl_worker.load import load_readings, load_site_profiles, load_sites, read_site_ids
from etl_worker.transform import (
    PREVIOUS_VALUE_MAX_AGE,
    aggregate_hour,
    impute_consumption,
)


def _require_site_ids() -> list:
    site_ids = read_site_ids()
    if not site_ids:
        raise ValueError("Aucun site en base : lancer d'abord etl-worker sync-sites.")
    return site_ids


def _print_sites_summary(sites: list) -> None:
    changed = load_sites(sites)
    print(f"Sites reçus : {len(sites)} ; insérés ou mis à jour : {changed}.")


def cmd_init_sites(args: argparse.Namespace) -> None:
    if read_site_ids():
        print("Sites déjà présents en base ; prochaine synchronisation à 16 h.")
        return
    sites = extract_sites()
    if not sites:
        raise ValueError("Aucun site reçu : impossible d'initialiser la collecte.")
    _print_sites_summary(sites)


def cmd_sync_sites(args: argparse.Namespace) -> None:
    _print_sites_summary(extract_sites())


def cmd_sync_site_profiles(args: argparse.Namespace) -> None:
    # Fichier livré avec l'image ; un profil dont le site n'est pas encore en base est ignoré.
    profiles = read_site_profiles()
    changed = load_site_profiles(profiles)
    print(
        f"Profils de référence : {len(profiles)} ; insérés ou mis à jour : {changed}."
    )


def _exit_on_site_errors(errors: dict[str, str]) -> None:
    # Code 1 pour que job.sh journalise l'échec ; les sites reçus ont déjà été traités.
    for site_id, message in errors.items():
        print(f"{site_id} : {message}", file=sys.stderr)
    if errors:
        raise SystemExit(1)


def cmd_extract_readings(args: argparse.Namespace) -> None:
    readings, errors = extract_readings(_require_site_ids())
    print(json.dumps(readings, ensure_ascii=False))
    _exit_on_site_errors(errors)


def cmd_sync_readings(args: argparse.Namespace) -> None:
    collected_at = datetime.now(UTC)
    readings, errors = extract_readings(_require_site_ids())
    inserted = 0
    if readings:
        # Bronze d'abord : la donnée brute est archivée même si la base échoue.
        bronze_key = write_readings_bronze(readings, collected_at=collected_at)
        if bronze_key is not None:
            print(f"Bronze : {bronze_key}.")
        inserted = load_readings(readings, source="current")
    print(
        f"Mesures reçues : {len(readings)}/{len(readings) + len(errors)} ; "
        f"insérées : {inserted} ; déjà présentes : {len(readings) - inserted}."
    )
    if readings:
        # 15 minutes : une interpolation attend la valeur suivante, reçue aux passages d'après.
        _print_imputed(impute_consumption(minutes=_IMPUTE_RECENT_MINUTES))
    _exit_on_site_errors(errors)


_IMPUTE_RECENT_MINUTES = int(PREVIOUS_VALUE_MAX_AGE.total_seconds() // 60)


def _print_imputed(imputed: int) -> None:
    print(f"Consommations imputées : {imputed}.")


def cmd_sync_hours(args: argparse.Namespace) -> None:
    # 6 heures par défaut : les minutes comblées par backfill-readings y sont intégrées.
    updated = aggregate_hour(end_time=args.end_time, hours=args.hours or 6)
    print(f"Lignes horaires calculées dans readings_hours : {updated}.")


def cmd_backfill_readings(args: argparse.Namespace) -> None:
    hours = args.hours or 6
    result = backfill_readings(hours)
    print(
        f"Plages manquantes : {result.ranges} ; mesures rattrapées : {result.received} ; "
        f"insérées : {result.inserted}."
    )
    # Les minutes rattrapées peuvent compléter une interpolation restée en attente.
    _print_imputed(impute_consumption(minutes=hours * 60))
    for label, message in result.errors.items():
        print(f"{label} : {message}", file=sys.stderr)
    if result.errors:
        raise SystemExit(1)


def cmd_impute_readings(args: argparse.Namespace) -> None:
    # Rattrapage ponctuel, par exemple --hours 168 après le déploiement du changeset 005.
    _print_imputed(impute_consumption(minutes=(args.hours or 6) * 60))


COMMANDS = {
    "init-sites": cmd_init_sites,
    "sync-sites": cmd_sync_sites,
    "sync-site-profiles": cmd_sync_site_profiles,
    "extract-readings": cmd_extract_readings,
    "sync-readings": cmd_sync_readings,
    "sync-hours": cmd_sync_hours,
    "backfill-readings": cmd_backfill_readings,
    "impute-readings": cmd_impute_readings,
}


def _positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("doit valoir au moins 1")
    return number


def main() -> None:
    parser = argparse.ArgumentParser(description="Collecte des données EnerVision.")
    parser.add_argument("command", nargs="?", default="sync-sites", choices=COMMANDS)
    parser.add_argument(
        "--end-time",
        type=datetime.fromisoformat,
        help="Référence ISO 8601 avec fuseau pour rejouer sync-hours (ex. 2026-10-20T14:00:00+02:00).",
    )
    parser.add_argument(
        "--hours",
        type=_positive_int,
        help="Heures traitées par sync-hours, backfill-readings et impute-readings (6 par défaut).",
    )
    args = parser.parse_args()
    if args.end_time is not None and args.command != "sync-hours":
        parser.error("--end-time est réservé à sync-hours.")
    if args.hours is not None and args.command not in {
        "sync-hours",
        "backfill-readings",
        "impute-readings",
    }:
        parser.error(
            "--hours est réservé à sync-hours, backfill-readings et impute-readings."
        )

    COMMANDS[args.command](args)


if __name__ == "__main__":
    main()
