#!/usr/bin/env bash
# Copie immuable des Parquet historiques vers le bucket datalake existant.
# Usage : scripts/ml/upload-bootstrap.sh <bucket-datalake> [version]
set -euo pipefail

bucket=${1:?Nom du bucket datalake requis}
version=${2:-v1}
if [[ ! $version =~ ^[A-Za-z0-9._-]+$ ]]; then
  echo "Version invalide." >&2
  exit 2
fi
root=$(cd "$(dirname "$0")/../.." && pwd)
source_dir=$root/.data/ml/splits
prefix="ml/datasets/bootstrap/$version"
temporary=$(mktemp -d)
trap 'rm -rf "$temporary"' EXIT

for name in train validation test; do
  test -f "$source_dir/$name.parquet"
  if aws s3api head-object --bucket "$bucket" --key "$prefix/$name.parquet" >/dev/null 2>&1; then
    echo "Objet déjà présent : s3://$bucket/$prefix/$name.parquet" >&2
    exit 1
  fi
  aws s3 cp "$source_dir/$name.parquet" "s3://$bucket/$prefix/$name.parquet" --only-show-errors
  aws s3 cp "s3://$bucket/$prefix/$name.parquet" "$temporary/$name.parquet" --only-show-errors
  original=$(sha256sum "$source_dir/$name.parquet" | cut -d ' ' -f 1)
  uploaded=$(sha256sum "$temporary/$name.parquet" | cut -d ' ' -f 1)
  if [[ $original != "$uploaded" ]]; then
    echo "Empreinte différente après transfert : $name.parquet" >&2
    exit 1
  fi
  printf '%s  %s\n' "$original" "$name.parquet" >> "$temporary/sha256.txt"
done

aws s3 cp "$temporary/sha256.txt" "s3://$bucket/$prefix/sha256.txt" --only-show-errors
echo "Snapshot vérifié : s3://$bucket/$prefix/"
