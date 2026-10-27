#!/usr/bin/env bash
# Publication immuable et relançable des Parquet ; aucun entraînement.
# Usage : scripts/ml/upload-bootstrap.sh <bucket-datalake> [version]
# Pipeline : scripts/ml/upload-bootstrap.sh --release <manifeste-json>
set -euo pipefail

root=$(cd "$(dirname "$0")/../.." && pwd)
if [[ ${1:-} == --release ]]; then
  [[ $# == 2 ]] || { echo "Usage : $0 --release <manifeste-json>" >&2; exit 2; }
  exec python3 "$root/infra/deploy/dataset_release.py" publish --root "$root" --release "$2"
fi
bucket=${1:?Nom du bucket datalake requis}
version=${2:-v1}
exec python3 "$root/infra/deploy/dataset_release.py" publish --root "$root" \
  --bucket "$bucket" --version "$version"
