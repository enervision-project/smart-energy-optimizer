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

compose=(docker compose -f compose.yaml -f compose.prod.yaml --env-file .env --env-file deploy.env)
# Le scheduler utilise la même image et le même tag que le worker ponctuel.
deploy_services=()
for svc in "$@"; do
  case "$svc" in
    etl-worker) deploy_services+=(scheduler) ;;
    *) deploy_services+=("$svc") ;;
  esac
done
"${compose[@]}" pull "${deploy_services[@]}"
"${compose[@]}" up -d --no-build --remove-orphans "${deploy_services[@]}"
docker image prune -f
"${compose[@]}" ps
