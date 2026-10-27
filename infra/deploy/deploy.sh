#!/usr/bin/env bash
# Exécuté sur l'EC2 via SSM. La release contient dataset-release.json pour les jobs ML.
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
    # Vérifie le commit, le marqueur de complétude et les trois empreintes sur S3.
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
      # Premier déploiement : aucun ancien tag connu à redémarrer.
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
  # L'URI est attachée à la release ; SSM sera actualisé par CI après son succès.
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
# Images d'anciens commits : chaque déploiement en ajoute (une par service et par SHA), et
# `prune -f` seul ne retire que les images sans tag. `-a` supprime toute image qu'aucun conteneur
# n'utilise, même arrêté (migrate, mlflow-init) : les services en place restent intacts.
# Avant le pull, pour laisser la place aux nouvelles images ; un retour arrière les retélécharge d'ECR.
docker image prune -af
"${compose[@]}" pull "${deploy_services[@]}"
if [[ -n $dataset_uri ]]; then
  # Validation avec le chargeur existant ; aucun fit ni modèle n'est exécuté ici.
  "${compose[@]}" run --rm --no-deps --entrypoint python prediction-jobs -c \
    'import os; from prediction_service.datasets import load_bootstrap; load_bootstrap(os.environ["TRAINING_BOOTSTRAP_URI"])'
fi
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
# Les images remplacées par ce déploiement ne servent plus.
docker image prune -af
"${compose[@]}" ps
activation_started=false
docker image prune -f || echo "Nettoyage des images reporté." >&2
