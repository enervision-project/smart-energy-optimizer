"""Commandes ponctuelles de collecte et de calcul horaire."""

import argparse
from datetime import datetime
import json

from etl_worker.bronze import write_readings_bronze
from etl_worker.extract import extract_readings, extract_sites, read_site_profiles
from etl_worker.load import load_readings, load_site_profiles, load_sites, read_site_ids
from etl_worker.transform import aggregate_hour


def main() -> None:
    parser = argparse.ArgumentParser(description="Collecte des données EnerVision.")
    parser.add_argument(
        "command",
        nargs="?",
        default="sync-sites",
        choices=(
            "init-sites", "sync-sites", "sync-site-profiles",
            "extract-readings", "sync-readings", "sync-hours",
        ),
    )
    parser.add_argument(
        "--end-time",
        type=datetime.fromisoformat,
        help="Référence ISO 8601 avec fuseau pour rejouer sync-hours (ex. 2026-10-20T14:00:00+02:00).",
    )
    args = parser.parse_args()
    if args.end_time is not None and args.command != "sync-hours":
        parser.error("--end-time est réservé à sync-hours.")

    if args.command == "sync-hours":
        updated = aggregate_hour(end_time=args.end_time)
        print(f"Lignes horaires calculées dans readings_hours : {updated}.")
    elif args.command == "sync-site-profiles":
        # Fichier livré avec l'image ; un profil dont le site n'est pas encore en base est ignoré.
        profiles = read_site_profiles()
        changed = load_site_profiles(profiles)
        print(f"Profils de référence : {len(profiles)} ; insérés ou mis à jour : {changed}.")
    elif args.command in ("init-sites", "sync-sites"):
        if args.command == "init-sites" and read_site_ids():
            print("Sites déjà présents en base ; prochaine synchronisation à 16 h.")
            return
        sites = extract_sites()
        if args.command == "init-sites" and not sites:
            raise ValueError("Aucun site reçu : impossible d'initialiser la collecte.")
        changed = load_sites(sites)
        print(f"Sites reçus : {len(sites)} ; insérés ou mis à jour : {changed}.")
    else:
        site_ids = read_site_ids()
        if not site_ids:
            raise ValueError("Aucun site en base : lancer d'abord etl-worker sync-sites.")
        readings = extract_readings(site_ids)
        if args.command == "extract-readings":
            print(json.dumps(readings, ensure_ascii=False))
        else:
            # Bronze d'abord : la donnée brute est archivée même si la base échoue.
            bronze_key = write_readings_bronze(readings)
            if bronze_key is not None:
                print(f"Bronze : {bronze_key}.")
            inserted = load_readings(readings)
            print(
                f"Mesures reçues : {len(readings)} ; insérées : {inserted} ; "
                f"déjà présentes : {len(readings) - inserted}."
            )


if __name__ == "__main__":
    main()
