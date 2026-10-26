"""Commandes ponctuelles de collecte et de calcul horaire."""

import argparse
import json
from datetime import UTC, datetime

from etl_worker.bronze import write_readings_bronze
from etl_worker.extract import extract_readings, extract_sites, read_site_profiles
from etl_worker.load import load_readings, load_site_profiles, load_sites, read_site_ids
from etl_worker.transform import aggregate_hour


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
    print(f"Profils de référence : {len(profiles)} ; insérés ou mis à jour : {changed}.")


def cmd_extract_readings(args: argparse.Namespace) -> None:
    print(json.dumps(extract_readings(_require_site_ids()), ensure_ascii=False))


def cmd_sync_readings(args: argparse.Namespace) -> None:
    collected_at = datetime.now(UTC)
    readings = extract_readings(_require_site_ids())
    # Bronze d'abord : la donnée brute est archivée même si la base échoue.
    bronze_key = write_readings_bronze(readings, collected_at=collected_at)
    if bronze_key is not None:
        print(f"Bronze : {bronze_key}.")
    inserted = load_readings(readings)
    print(
        f"Mesures reçues : {len(readings)} ; insérées : {inserted} ; "
        f"déjà présentes : {len(readings) - inserted}."
    )


def cmd_sync_hours(args: argparse.Namespace) -> None:
    updated = aggregate_hour(end_time=args.end_time)
    print(f"Lignes horaires calculées dans readings_hours : {updated}.")


COMMANDS = {
    "init-sites": cmd_init_sites,
    "sync-sites": cmd_sync_sites,
    "sync-site-profiles": cmd_sync_site_profiles,
    "extract-readings": cmd_extract_readings,
    "sync-readings": cmd_sync_readings,
    "sync-hours": cmd_sync_hours,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Collecte des données EnerVision.")
    parser.add_argument("command", nargs="?", default="sync-sites", choices=COMMANDS)
    parser.add_argument(
        "--end-time",
        type=datetime.fromisoformat,
        help="Référence ISO 8601 avec fuseau pour rejouer sync-hours (ex. 2026-10-20T14:00:00+02:00).",
    )
    args = parser.parse_args()
    if args.end_time is not None and args.command != "sync-hours":
        parser.error("--end-time est réservé à sync-hours.")

    COMMANDS[args.command](args)


if __name__ == "__main__":
    main()