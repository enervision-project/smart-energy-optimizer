#!/bin/sh
set -eu
. /run/etl-worker/etl-worker.env

case "${1:-}" in
    sync-readings|sync-sites|sync-site-profiles|sync-hours|sync-alerts|backfill-readings) ;;
    *) echo "Commande cron inconnue." >&2; exit 2 ;;
esac

# Un verrou par tâche évite d'empiler les collectes si l'API ralentit.
exec 9>"/run/etl-worker/etl-$1.lock"
if ! flock -n 9; then
    printf '%s %s ignoré : exécution précédente encore en cours.\n' "$(date -Iseconds)" "$1"
    exit 0
fi

run_job() {
    if [ "$1" = sync-alerts ]; then
        setpriv --reuid=appuser --regid=appuser --init-groups etl-sync-alerts
    else
        setpriv --reuid=appuser --regid=appuser --init-groups etl-worker "$1"
    fi
}

printf '%s Début %s.\n' "$(date -Iseconds)" "$1"
if run_job "$1"; then
    printf '%s Fin %s.\n' "$(date -Iseconds)" "$1"
else
    status=$?
    printf '%s Échec %s (code %s).\n' "$(date -Iseconds)" "$1" "$status" >&2
    exit "$status"
fi
