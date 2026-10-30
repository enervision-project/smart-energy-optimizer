#!/usr/bin/env bash
# Run on the monitoring EC2 (root, via SSM) by the Deploy workflow.
set -euo pipefail

cd "$(dirname "$0")"

# one deployment at a time
exec 9>.deploy.lock
flock 9

# .env rebuilt from SSM Parameter Store (/enervision/prod/monitoring/<NAME>)
aws ssm get-parameters-by-path --path /enervision/prod/monitoring --with-decryption \
  --query 'Parameters[].[Name,Value]' --output text |
  while IFS=$'\t' read -r name value; do echo "${name##*/}=$value"; done >.env.tmp
chmod 600 .env.tmp
mv .env.tmp .env

compose=(docker compose --env-file .env)
"${compose[@]}" pull
# compose does not track bind-mounted config files (prometheus.yml, loki.yaml, provisioning):
# recreate every container so they are reloaded
"${compose[@]}" up -d --remove-orphans --force-recreate --wait --wait-timeout 180
docker image prune -f
"${compose[@]}" ps
