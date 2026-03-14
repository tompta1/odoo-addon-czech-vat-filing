#!/usr/bin/env bash

set -euo pipefail

if [[ $# -lt 3 || $# -gt 4 ]]; then
  echo "Usage: $0 <payload.xml> <signer-cert.pem> <signer-key.pem> [output.p7m]" >&2
  echo "Optional env: OPENSSL_PASSIN=pass:secret or OPENSSL_PASSIN=file:/path/to/pass" >&2
  exit 1
fi

payload="$1"
signer_cert="$2"
signer_key="$3"
output="${4:-${payload%.*}.p7m}"

for path in "${payload}" "${signer_cert}" "${signer_key}"; do
  if [[ ! -f "${path}" ]]; then
    echo "File not found: ${path}" >&2
    exit 1
  fi
done

openssl_args=(
  smime
  -sign
  -binary
  -nodetach
  -outform DER
  -in "${payload}"
  -signer "${signer_cert}"
  -inkey "${signer_key}"
  -out "${output}"
)

if [[ -n "${OPENSSL_PASSIN:-}" ]]; then
  openssl_args+=(-passin "${OPENSSL_PASSIN}")
fi

openssl "${openssl_args[@]}"

echo "${output}"
