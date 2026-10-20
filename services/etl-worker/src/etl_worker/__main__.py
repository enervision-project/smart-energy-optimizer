"""Point d'entrée : synchronisation des sites et collecte ponctuelle des consommations."""

import argparse
import json

from etl_worker.extract import extract_readings, extract_sites
from etl_worker.load import load_readings, load_sites


def main() -> None:
    parser = argparse.ArgumentParser(description="Collecte des données EnerVision.")
    parser.add_argument(
        "command",
        nargs="?",
        default="sync-sites",
        choices=("sync-sites", "extract-readings", "sync-readings"),
    )
    args = parser.parse_args()

    sites = extract_sites()
    if args.command == "sync-sites":
        changed = load_sites(sites)
        print(f"Sites reçus : {len(sites)} ; insérés ou mis à jour : {changed}.")
    else:
        site_ids = [site["site_id"] for site in sites]
        readings = extract_readings(site_ids)
        if args.command == "extract-readings":
            print(json.dumps(readings, ensure_ascii=False))
        else:
            inserted = load_readings(readings)
            print(
                f"Mesures reçues : {len(readings)} ; insérées : {inserted} ; "
                f"déjà présentes : {len(readings) - inserted}."
            )


if __name__ == "__main__":
    main()
