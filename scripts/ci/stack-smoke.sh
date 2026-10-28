#!/usr/bin/env bash
# Vérifie une stack docker compose démarrée (db, migrate, core-api, web, scheduler) :
# migrations, collecte réelle de l'ETL sur l'API Mock, API authentifiée et front.
# Utilisé par le job CI « Stack » (_ci-stack.yml) ; lançable en local depuis la racine du dépôt,
# avec le .env de la stack. Usage : scripts/ci/stack-smoke.sh
set -euo pipefail

API=${API_URL:-http://127.0.0.1:8080}
WEB=${WEB_URL:-http://127.0.0.1:4200}
# Le cron tourne à chaque minute : une collecte doit aboutir en moins de 2 min 30.
COLLECT_TIMEOUT=${COLLECT_TIMEOUT:-150}
compose=(docker compose --env-file .env)

step() { printf '\n== %s\n' "$*"; }
# Lecture du JSON sur l'entrée standard avec python3 (présent en CI comme sur les postes) :
# `json 'expression'` affiche l'expression, `json_check 'condition'` échoue si elle est fausse.
json() { python3 -c "import json, sys; d = json.load(sys.stdin); print($1)"; }
json_check() { python3 -c "import json, sys; d = json.load(sys.stdin); sys.exit(0 if ($1) else 1)"; }
fail() { printf 'ÉCHEC : %s\n' "$*" >&2; exit 1; }
env_value() { sed -n "s/^$1=//p" .env | tail -n 1; }
sql() {
  # POSTGRES_* sont lues dans le conteneur db, d'où les apostrophes.
  # shellcheck disable=SC2016
  "${compose[@]}" exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -c "$1"' sh "$1"
}

step "Comptes PostgreSQL (db-bootstrap)"
status=$(docker inspect -f '{{.State.Status}} {{.State.ExitCode}}' "$("${compose[@]}" ps -aq db-bootstrap)")
[[ $status == "exited 0" ]] || fail "db-bootstrap : $status"
roles=$(sql "SELECT count(*) FROM pg_roles WHERE rolname IN ('core_api', 'etl_worker', 'prediction_jobs', 'monitoring', 'enervision_migrator', 'enervision_owner')")
[[ $roles == 6 ]] || fail "$roles comptes de service sur 6"
echo "6 comptes de service créés"

step "Migrations Liquibase"
status=$(docker inspect -f '{{.State.Status}} {{.State.ExitCode}}' "$("${compose[@]}" ps -aq migrate)")
[[ $status == "exited 0" ]] || fail "migrate : $status"
expected=$(grep -c 'include:' infra/db/changelog/changelog.yaml)
files=$(sql "SELECT count(DISTINCT filename) FROM databasechangelog")
[[ $files == "$expected" ]] || fail "$files fichiers de changeset appliqués sur $expected"
echo "$files fichiers de changeset appliqués sur une base vierge"

step "Démarrage de core-api"
for _ in $(seq 60); do
  curl -sf -o /dev/null "$API/v3/api-docs" && break
  sleep 2
done
curl -sf -o /dev/null "$API/v3/api-docs" || fail "core-api ne répond pas sur $API"
echo "core-api prêt (schéma validé par Hibernate au démarrage)"

step "Collecte de l'ETL sur l'API Mock (jusqu'à ${COLLECT_TIMEOUT} s)"
deadline=$((SECONDS + COLLECT_TIMEOUT))
until logs=$("${compose[@]}" logs --no-color scheduler 2>&1) &&
  grep -q 'Fin sync-readings' <<<"$logs" && grep -q 'Fin sync-alerts' <<<"$logs"; do
  if grep -q 'Échec' <<<"$logs"; then
    grep -E 'Échec|Error|Traceback' <<<"$logs" | tail -20 >&2
    fail "une tâche de l'ETL a échoué"
  fi
  ((SECONDS < deadline)) || { tail -30 <<<"$logs" >&2; fail "aucune collecte terminée"; }
  sleep 5
done
grep -E 'Fin sync-' <<<"$logs" | tail -4
readings=$(sql "SELECT count(*) FROM readings_raws")
sites=$(sql "SELECT count(*) FROM sites")
((readings > 0)) || fail "aucune mesure en base après la collecte"
((sites > 0)) || fail "table sites vide"
echo "$sites sites, $readings mesures en base"

step "API authentifiée"
login=$(ADMIN_EMAIL=$(env_value ADMIN_EMAIL) ADMIN_PASSWORD=$(env_value ADMIN_PASSWORD) python3 -c \
  'import json, os; print(json.dumps({"email": os.environ["ADMIN_EMAIL"], "password": os.environ["ADMIN_PASSWORD"]}))')
token=$(curl -sf -H 'Content-Type: application/json' -d "$login" "$API/api/v1/auth/login" |
  json 'd["accessToken"]') || fail "connexion de l'administrateur refusée"
[[ -n $token ]] || fail "aucun jeton dans la réponse de connexion"
get() { curl -sf -H "Authorization: Bearer $token" "$API$1"; }
code=$(curl -s -o /dev/null -w '%{http_code}' "$API/api/v1/sites")
[[ $code == 401 ]] || fail "/api/v1/sites sans jeton : HTTP $code au lieu de 401"
api_sites=$(get /api/v1/sites | json 'len(d)')
[[ $api_sites == "$sites" ]] || fail "/api/v1/sites : $api_sites sites au lieu de $sites"
site=$(get /api/v1/sites | json 'd[0]["siteId"]')
get /api/v1/stats/summary | json_check 'd["totalSites"] > 0' || fail "/api/v1/stats/summary"
get "/api/v1/sites/$site/readings/latest" | json_check 'd["ts"]' ||
  fail "/api/v1/sites/$site/readings/latest : aucune mesure"
get /api/v1/alerts | json_check 'd["page"]["totalElements"] >= 0' || fail "/api/v1/alerts"
echo "connexion JWT, 401 sans jeton, sites, synthèse du parc, dernière mesure de $site, alertes : OK"

step "Front"
curl -sf "$WEB/" | grep -q '<app-root' || fail "le front ne sert pas l'application Angular"
echo "front servi par nginx"

printf '\nStack vérifiée.\n'
