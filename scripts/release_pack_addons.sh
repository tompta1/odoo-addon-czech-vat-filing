#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/.." && pwd)"

release_tag="${1:-}"
out_dir="${2:-dist}"
shift $(( $# > 0 ? 1 : 0 )) || true
shift $(( $# > 0 ? 1 : 0 )) || true

if [[ -z "${release_tag}" ]]; then
  echo "Usage: $0 <release-tag> [output-dir] [addon ...]" >&2
  echo "Example: $0 v19.0.20.0.0 dist l10n_cz_vat_filing l10n_cz_vat_oss_bridge" >&2
  exit 1
fi

if ! command -v zip >/dev/null 2>&1; then
  echo "Missing 'zip' command. Install zip first." >&2
  exit 1
fi

if ! command -v sha256sum >/dev/null 2>&1; then
  echo "Missing 'sha256sum' command." >&2
  exit 1
fi

declare -a addons
if [[ $# -gt 0 ]]; then
  addons=("$@")
else
  addons=("l10n_cz_vat_filing" "l10n_cz_vat_oss_bridge" "odoo19_report_compat")
fi

release_dir="${repo_root}/${out_dir}/${release_tag}"
mkdir -p "${release_dir}"

declare -a archives
for addon in "${addons[@]}"; do
  addon_dir="${repo_root}/addons/custom/${addon}"
  manifest_path="${addon_dir}/__manifest__.py"
  if [[ ! -d "${addon_dir}" ]]; then
    echo "Addon not found: ${addon_dir}" >&2
    exit 1
  fi
  if [[ ! -f "${manifest_path}" ]]; then
    echo "Manifest not found: ${manifest_path}" >&2
    exit 1
  fi

  addon_version="$(sed -nE 's/.*"version":[[:space:]]*"([^"]+)".*/\1/p' "${manifest_path}" | head -n 1)"
  if [[ -z "${addon_version}" ]]; then
    echo "Could not parse version from ${manifest_path}" >&2
    exit 1
  fi

  archive_name="${addon}-${addon_version}.zip"
  archive_path="${release_dir}/${archive_name}"

  (
    cd "${repo_root}/addons/custom"
    zip -rq "${archive_path}" "${addon}"
  )

  archives+=("${archive_name}")
  echo "Packed ${archive_name}"
done

checksum_file="${release_dir}/SHA256SUMS.txt"
(
  cd "${release_dir}"
  sha256sum "${archives[@]}" > "${checksum_file##*/}"
)

echo
echo "Release artifacts:"
for archive in "${archives[@]}"; do
  echo "  ${release_dir}/${archive}"
done
echo "  ${checksum_file}"

