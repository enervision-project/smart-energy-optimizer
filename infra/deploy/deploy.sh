#!/usr/bin/env bash
# Exécuté sur l'EC2 (root, via SSM Run Command) par le workflow Deploy (services.yml).
# Les fichiers de la release (compose*.yaml, infra/…) sont déjà copiés dans /opt/enervision.
# Redéploie uniquement les services passés en argument, les autres ne sont pas touchés.
# Usage : deploy.sh <sha> <registre ECR> <service>...
set -euo pipefail

sha=$1 registry=$2
shift 2
cd /opt/enervision

# un seul déploiement à la fois
exec 9>.deploy.lock
flock 9

# .env reconstruit depuis SSM Parameter Store (/enervision/prod/env/<NOM>)
aws ssm get-parameters-by-path --path /enervision/prod/env --with-decryption \
  --query 'Parameters[].[Name,Value]' --output text |
  while IFS=$'\t' read -r name value; do echo "${name##*/}=$value"; done >.env.tmp
chmod 600 .env.tmp
mv .env.tmp .env

# deploy.env : registre + tag courant de chaque service (les tags des autres services sont conservés)
touch deploy.env
set_var() {
  sed -i "/^$1=/d" deploy.env
  echo "$1=$2" >>deploy.env
}
set_var ECR_REGISTRY "$registry"
for svc in "$@"; do
  set_var "$(echo "$svc" | tr 'a-z-' 'A-Z_')_TAG" "$sha"
done

aws ecr get-login-password | docker login --username AWS --password-stdin "$registry"

# profil ml actif pour pouvoir deployer et inspecter MLflow ; les up ciblent toujours des services precis
compose=(docker compose --profile ml -f compose.yaml -f compose.prod.yaml --env-file .env --env-file deploy.env)
# Le scheduler utilise la même image et le même tag que le worker ponctuel.
deploy_services=()
check_mlflow=false
for svc in "$@"; do
  case "$svc" in
    etl-worker) deploy_services+=(scheduler) ;;
    mlflow) deploy_services+=(mlflow); check_mlflow=true ;;
    *) deploy_services+=("$svc") ;;
  esac
done
"${compose[@]}" pull "${deploy_services[@]}"
up_options=(-d --no-build --remove-orphans)
if "$check_mlflow"; then
  # mlflow-init doit reussir et le serveur etre sain avant le test S3.
  up_options+=(--wait --wait-timeout 180)
fi
"${compose[@]}" up "${up_options[@]}" "${deploy_services[@]}"
if "$check_mlflow"; then
  # Parametre, metrique et aller-retour d'un fichier via le serveur vers S3.
  "${compose[@]}" exec -T mlflow python smoke_test.py
fi
docker image prune -f
"${compose[@]}" ps
