"""Point d'entrée : synchronisation ponctuelle des sites."""

from etl_worker.extract import extract_sites
from etl_worker.load import load_sites


def main() -> None:
    sites = extract_sites()
    changed = load_sites(sites)
    print(f"Sites reçus : {len(sites)} ; insérés ou mis à jour : {changed}.")


if __name__ == "__main__":
    main()
