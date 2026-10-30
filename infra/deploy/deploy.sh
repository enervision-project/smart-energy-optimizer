#!/usr/bin/env bash
# Run on the EC2 through SSM. Usage: deploy.sh <sha> <ECR registry> <service>...
# Usage : deploy.sh <sha> <registre ECR> <service>...
set -euo pipefail
umask 077

sha=$1 registry=$2
shift 2
cd "${ENERVISION_DIR:-/opt/enervision}"

exec 9>.deploy.lock
flock 9

read_var() {
  if [[ -f $1 ]]; then sed -n "s/^$2=//p" "$1" | tail -n 1; fi
}
set_var() {
  local file=$1 name=$2 value=$3
  sed -i "/^$name=/d" "$file"
  printf '%s=%s\n' "$name" "$value" >>"$file"
}
restore_var() {
  local name=$1 value=$2
  sed -i "/^$name=/d" deploy.env
  if [[ -n $value ]]; then printf '%s=%s\n' "$name" "$value" >>deploy.env; fi
}
compose_command() {
  compose=(docker compose --profile ml -f compose.yaml -f compose.prod.yaml --env-file .env --env-file "$1")
}

dataset_uri=
for svc in "$@"; do
  if [[ $svc == prediction-service ]]; then
    # Checks the commit, the completeness marker and the three hashes on S3.
    dataset_uri=$(python3 infra/deploy/dataset_release.py verify \
      --release dataset-release.json --git-revision "$sha" --remote)
  fi
done

old_prediction_tag=$(read_var deploy.env PREDICTION_SERVICE_TAG)
old_dataset_override=$(read_var deploy.env TRAINING_BOOTSTRAP_URI)
candidate=$(mktemp .deploy.env.XXXXXX)
activation_started=false
finish() {
  local status=$?
  trap - EXIT
  set +e
  if [[ $status != 0 && $activation_started == true ]]; then
    echo "Échec : restauration de la configuration précédente des jobs ML." >&2
    restore_var PREDICTION_SERVICE_TAG "$old_prediction_tag"
    restore_var TRAINING_BOOTSTRAP_URI "$old_dataset_override"
    compose_command deploy.env
    if [[ -n $old_prediction_tag ]]; then
      "${compose[@]}" up -d --no-deps --no-build --force-recreate \
        prediction-service prediction-jobs \
        || echo "La restauration des conteneurs ML a échoué ; intervention requise." >&2
    else
      # First deployment: no old tag to restart.
      "${compose[@]}" stop prediction-jobs \
        || echo "Impossible d'arrêter les nouveaux jobs ML." >&2
    fi
  fi
  if [[ -n $candidate ]]; then rm -f -- "$candidate"; fi
  rm -f -- .env.tmp
  exit "$status"
}
trap finish EXIT

aws ssm get-parameters-by-path --path /enervision/prod/env --with-decryption \
  --query 'Parameters[].[Name,Value]' --output text |
  while IFS=$'\t' read -r name value; do echo "${name##*/}=$value"; done >.env.tmp
mv .env.tmp .env

if [[ -f deploy.env ]]; then cat deploy.env >"$candidate"; fi
set_var "$candidate" ECR_REGISTRY "$registry"
for svc in "$@"; do
  set_var "$candidate" "$(echo "$svc" | tr 'a-z-' 'A-Z_')_TAG" "$sha"
done
if [[ -n $dataset_uri ]]; then
  # The URI is tied to the release; CI updates SSM after it succeeds.
  set_var "$candidate" TRAINING_BOOTSTRAP_URI "$dataset_uri"
fi

aws ecr get-login-password | docker login --username AWS --password-stdin "$registry"
compose_command "$candidate"
deploy_services=()
check_mlflow=false
for svc in "$@"; do
  case "$svc" in
    etl-worker) deploy_services+=(scheduler) ;;
    mlflow) deploy_services+=(mlflow); check_mlflow=true ;;
    prediction-service) deploy_services+=(prediction-service prediction-jobs) ;;
    *) deploy_services+=("$svc") ;;
  esac
done
# `-a` removes every image no container uses, even stopped; before the pull, to make room for the new ones.
docker image prune -af
"${compose[@]}" pull "${deploy_services[@]}"
if [[ -n $dataset_uri ]]; then
  # Validation with the existing loader; no fit or model runs here.
  "${compose[@]}" run --rm --no-deps --entrypoint python prediction-jobs -c \
    'import os; from prediction_service.datasets import load_bootstrap; load_bootstrap(os.environ["TRAINING_BOOTSTRAP_URI"])'
fi
# Reconcile credentials before any application starts, including DB-only releases.
# Explicit runs also work when a previous one-shot Compose container already exists.
db_options=(--no-recreate)
for svc in "$@"; do
  if [[ $svc == db ]]; then db_options=(); fi
done
"${compose[@]}" up -d --no-build --wait --wait-timeout 120 "${db_options[@]}" db
"${compose[@]}" run --rm --no-deps db-bootstrap
"${compose[@]}" run --rm --no-deps migrate
mv "$candidate" deploy.env
candidate=
compose_command deploy.env
if [[ -n $dataset_uri ]]; then activation_started=true; fi
up_options=(-d --no-build --remove-orphans)
if "$check_mlflow"; then up_options+=(--wait --wait-timeout 180); fi
"${compose[@]}" up "${up_options[@]}" "${deploy_services[@]}"
# compose does not track mounted config files: reload them
for svc in "${deploy_services[@]}"; do
  case "$svc" in
    # graceful reload, no downtime
    proxy) "${compose[@]}" exec -T proxy caddy reload --config /etc/caddy/Caddyfile ;;
    # not user-facing; the WAL and log positions survive the restart
    alloy) "${compose[@]}" up -d --no-build --force-recreate alloy ;;
  esac
done
if "$check_mlflow"; then "${compose[@]}" exec -T mlflow python smoke_test.py; fi
if [[ -n $dataset_uri ]]; then
  "${compose[@]}" exec -T prediction-jobs python -c \
    'import os,sys; assert os.environ["TRAINING_BOOTSTRAP_URI"] == sys.argv[1]' "$dataset_uri"
fi
# Images replaced by this deployment are no longer needed.
docker image prune -af
"${compose[@]}" ps
activation_started=false
docker image prune -f || echo "Nettoyage des images reporté." >&2
