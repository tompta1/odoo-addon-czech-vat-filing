#!/usr/bin/env bash

set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "Usage: $0 <signed-payload.p7s|signed-payload.p7m> [email]" >&2
  exit 1
fi

payload="$1"
email="${2:-}"

if [[ ! -f "${payload}" ]]; then
  echo "Payload not found: ${payload}" >&2
  exit 1
fi

case "${payload}" in
  *.p7s|*.p7m) ;;
  *)
    echo "The EPO test submission endpoint should be called with a signed PKCS#7 payload." >&2
    exit 1
    ;;
esac

url="https://adisspr.mfcr.cz/dpr/epo_podani?test=1"
if [[ -n "${email}" ]]; then
  url="${url}&email=${email}"
fi

curl \
  --fail \
  --silent \
  --show-error \
  -X POST \
  -H "Content-Type: application/pkcs7-signature" \
  --data-binary @"${payload}" \
  "${url}"
