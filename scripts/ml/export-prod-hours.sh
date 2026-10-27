#!/usr/bin/env bash
# Exporte, en lecture seule, les heures mesurées (readings_hours) et les prévisions publiées de la
# production vers .data/ml/prod/, pour le notebook 02_recalage_niveau_prod.ipynb.
# Passe par SSM Run Command sur l'EC2 applicative : aucune connexion directe à la base.
# Un appel par site : la sortie d'une commande SSM est tronquée au-delà de 24 000 caractères.
# Usage : scripts/ml/export-prod-hours.sh [profil-aws]
set -euo pipefail

profile=${1:-enervision}
root=$(cd "$(dirname "$0")/../.." && pwd)
output=$root/.data/ml/prod
instance=$(aws ec2 describe-instances --profile "$profile" \
  --filters Name=tag:Name,Values=enervision-app Name=instance-state-name,Values=running \
  --query 'Reservations[].Instances[].InstanceId' --output text)
test -n "$instance"

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

# Exécute une requête SQL (COPY ... TO STDOUT) sur l'EC2 et écrit le résultat dans $2.
# Le SQL voyage en base64 jusqu'à l'entrée de psql : aucun échappement de guillemets.
run_sql() {
  local sql=$1 target=$2 parameters=$work/parameters.json command_id encoded
  # base64 ne contient ni guillemet ni antislash : insertion sûre dans le JSON.
  encoded=$(printf '%s\n' "$sql" | base64 -w0)
  cat >"$parameters" <<EOF
{"commands":[
"cd /opt/enervision",
"C='docker compose --profile ml -f compose.yaml -f compose.prod.yaml --env-file .env --env-file deploy.env'",
"echo $encoded | base64 -d | \$C exec -T db sh -c 'psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -At -v ON_ERROR_STOP=1' | gzip | base64 -w0"
]}
EOF
  command_id=$(aws ssm send-command --profile "$profile" --instance-ids "$instance" \
    --document-name AWS-RunShellScript --comment "export lecture seule pour le notebook ML" \
    --parameters "file://$parameters" --query Command.CommandId --output text)
  aws ssm wait command-executed --profile "$profile" --instance-id "$instance" \
    --command-id "$command_id"
  aws ssm get-command-invocation --profile "$profile" --instance-id "$instance" \
    --command-id "$command_id" --query StandardOutputContent --output text |
    base64 -d | gunzip >"$target"
}

run_sql "SELECT site_id FROM sites ORDER BY site_id" "$work/sites.txt"
echo "site_id,ts,consumption_kwh,minutes_received,minutes_consumption" >"$work/readings_hours.csv"
echo "site_id,predicted_for,prediction_kwh,generated_at,model_version" >"$work/predictions.csv"
while read -r site; do
  [[ $site =~ ^SITE[0-9]+$ ]] || { echo "Identifiant de site inattendu : $site" >&2; exit 1; }
  run_sql "COPY (SELECT site_id, ts, consumption_kwh, minutes_received, minutes_consumption \
FROM readings_hours WHERE site_id = '$site' ORDER BY ts) TO STDOUT WITH CSV" "$work/hours.csv"
  cat "$work/hours.csv" >>"$work/readings_hours.csv"
  # Pour chaque heure, la dernière prévision publiée avant cette heure.
  run_sql "COPY (SELECT DISTINCT ON (p.predicted_for) p.site_id, p.predicted_for, p.prediction_kwh, \
r.generated_at, r.model_version FROM predictions p JOIN prediction_runs r USING (run_id) \
WHERE p.site_id = '$site' AND r.generated_at < p.predicted_for \
ORDER BY p.predicted_for, r.generated_at DESC) TO STDOUT WITH CSV" "$work/site_predictions.csv"
  cat "$work/site_predictions.csv" >>"$work/predictions.csv"
  echo "$site exporté"
done <"$work/sites.txt"

mkdir -p "$output"
mv "$work/readings_hours.csv" "$work/predictions.csv" "$output/"
wc -l "$output"/*.csv
