#!/bin/sh
set -eu

export TZ=Europe/Paris
# Cron ne transmet pas automatiquement l'environnement Docker aux tâches.
# Le fichier privé est sourcé par job.sh ; shlex.quote protège les caractères spéciaux.
umask 077
python - <<'PY'
import os
import shlex
from pathlib import Path

keys = ("DATABASE_URL", "ENERGY_API_BASE_URL", "LOG_LEVEL", "PYTHONUNBUFFERED", "TZ")
Path("/run/etl-worker.env").write_text(
    "".join(f"export {key}={shlex.quote(os.environ[key])}\n" for key in keys if key in os.environ),
    encoding="utf-8",
)
PY

# Remplir la table au premier démarrage ; une table déjà remplie attendra 16 h.
etl-worker init-sites
printf '%s Cron démarré : consommations chaque minute ; agrégats à H+2 min ; sites à 16 h (Europe/Paris).\n' "$(date -Iseconds)"
exec cron -f
