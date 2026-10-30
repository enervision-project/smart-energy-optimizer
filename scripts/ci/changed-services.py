#!/usr/bin/env python3
"""List the services to build and deploy from .github/services.json, and write them to $GITHUB_OUTPUT."""

import argparse
import json
import os
import subprocess
import sys

CONFIG = ".github/services.json"


def changed_files(base: str, head: str) -> list[str] | None:
    if not base or set(base) == {"0"}:
        return None
    try:
        out = subprocess.run(
            ["git", "diff", "--name-only", f"{base}...{head}"],
            check=True, capture_output=True, text=True,
        ).stdout
    except subprocess.CalledProcessError:
        return None
    return out.splitlines()


def select(config: dict, base: str, head: str, only: str) -> tuple[list[str], str]:
    services = config["services"]
    if only:
        if only == "all":
            return list(services), "sélection manuelle : all"
        names = [n.strip() for n in only.split(",") if n.strip()]
        unknown = [n for n in names if n not in services]
        if unknown:
            sys.exit(f"services inconnus : {', '.join(unknown)} (connus : {', '.join(services)})")
        return names, "sélection manuelle"

    files = changed_files(base, head)
    if files is None:
        return list(services), f"base « {base or 'aucune'} » introuvable : tous les services"
    if any(f.startswith(tuple(config["global"])) for f in files):
        return list(services), "fichier commun modifié : tous les services"
    names = [n for n, s in services.items() if any(f.startswith(tuple(s["paths"])) for f in files)]
    return names, f"{len(files)} fichier(s) modifié(s) depuis {base[:7]}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--only", default="")
    args = parser.parse_args()

    with open(CONFIG) as f:
        config = json.load(f)
    names, reason = select(config, args.base, args.head, args.only)
    builds = [
        {"name": n, **config["services"][n]["build"]}
        for n in names if "build" in config["services"][n]
    ]

    summary = f"{reason} → {', '.join(names) or 'aucun service'}"
    print(summary)
    if path := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(path, "a") as f:
            f.write(f"### Services sélectionnés\n{summary}\n")
    if path := os.environ.get("GITHUB_OUTPUT"):
        with open(path, "a") as f:
            f.write(f"services={json.dumps(names)}\n")
            f.write(f"builds={json.dumps(builds)}\n")


if __name__ == "__main__":
    main()
