#!/bin/sh
set -eu
. /run/etl-worker.env

case "${1:-}" in
    sync-readings|sync-sites) ;;
    *) echo "Commande cron inconnue." >&2; exit 2 ;;
esac

# Un verrou par tâche évite d'empiler les collectes si l'API ralentit.
exec 9>"/run/etl-$1.lock"
if ! flock -n 9; then
    printf '%s %s ignoré : exécution précédente encore en cours.\n' "$(date -Iseconds)" "$1"
    exit 0
fi

printf '%s Début %s.\n' "$(date -Iseconds)" "$1"
if etl-worker "$1"; then
    printf '%s Fin %s.\n' "$(date -Iseconds)" "$1"
else
    status=$?
    printf '%s Échec %s (code %s).\n' "$(date -Iseconds)" "$1" "$status" >&2
    exit "$status"
fi
