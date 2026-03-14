#!/usr/bin/env bash

set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <payload.xml|payload.p7s>" >&2
  exit 1
fi

payload="$1"

if [[ ! -f "${payload}" ]]; then
  echo "Payload not found: ${payload}" >&2
  exit 1
fi

content_type="application/octet-stream"
case "${payload}" in
  *.p7s|*.p7m) content_type="application/pkcs7-signature" ;;
esac

curl \
  --fail \
  --silent \
  --show-error \
  -X POST \
  -H "Content-Type: ${content_type}" \
  --data-binary @"${payload}" \
  "https://adisspr.mfcr.cz/dpr/epo_podani?otevriFormular=1"
