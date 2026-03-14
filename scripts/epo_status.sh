#!/usr/bin/env bash

set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "Usage: $0 <podaci_cislo> <password>" >&2
  exit 1
fi

curl \
  --fail \
  --silent \
  --show-error \
  -X POST \
  --data-urlencode "C=$1" \
  --data-urlencode "H=$2" \
  "https://adisspr.mfcr.cz/dpr/epo_stav"
