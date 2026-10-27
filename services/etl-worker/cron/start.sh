#!/bin/sh
set -eu

export TZ=Europe/Paris
# Cron ne transmet pas automatiquement l'environnement Docker aux tâches.
# Le fichier privé est sourcé par job.sh ; shlex.quote protège les caractères spéciaux.
umask 027
python - <<'PY'
import os
import shlex
from pathlib import Path

keys = (
    "DATABASE_URL", "ENERGY_API_BASE_URL", "ENERGY_API_USERNAME", "ENERGY_API_PASSWORD",
    "BRONZE_BUCKET", "AWS_DEFAULT_REGION", "LOG_LEVEL", "PYTHONUNBUFFERED", "TZ",
)
Path("/run/etl-worker/etl-worker.env").write_text(
    "".join(f"export {key}={shlex.quote(os.environ[key])}\n" for key in keys if key in os.environ),
    encoding="utf-8",
)
PY
chown appuser:appuser /run/etl-worker/etl-worker.env
chmod 0640 /run/etl-worker/etl-worker.env

# Remplir la table au premier démarrage ; une table déjà remplie attendra 16 h.
etl-worker init-sites
# Profils de référence à chaque démarrage (fichier livré avec l'image) ; un échec ne bloque pas la collecte.
etl-worker sync-site-profiles || echo "Profils de référence non chargés ; la collecte continue." >&2
printf '%s Cron démarré : consommations et alertes chaque minute ; rattrapage à H+1 min ; agrégats des 6 dernières heures à H+2 min ; sites à 16 h, profils à 16 h 01 (Europe/Paris).\n' "$(date -Iseconds)"
exec cron -f
