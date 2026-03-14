#!/usr/bin/env bash

set -euo pipefail

date_from="${1:-2026-03-01}"
date_to="${2:-2026-03-31}"
out_dir="${3:-/tmp/cz-vat-filing}"
db_name="${4:-odoo19_cz_test}"
options_arg="${5:-${ODOO_EXPORT_OPTIONS_JSON:-{}}}"
if [[ "${options_arg}" == @* ]]; then
  options_path="${options_arg#@}"
  if [[ ! -f "${options_path}" && "${options_path}" == *"}" && -f "${options_path%\}}" ]]; then
    options_path="${options_path%\}}"
  fi
  if [[ -f "${options_path}" ]]; then
    options_json="$(cat "${options_path}")"
  else
    options_json="${options_arg}"
  fi
elif [[ -f "${options_arg}" ]]; then
  options_json="$(cat "${options_arg}")"
else
  options_json="${options_arg}"
fi
options_json_b64="$(printf '%s' "${options_json}" | base64 -w0)"
podman_cmd="/var/home/tom/Documents/Projects/odoo-podman-codex/scripts/host-podman.sh"
odoo_conf="${ODOO_CONF:-/etc/odoo/odoo.conf}"

tmp_json="$(mktemp)"
tmp_err="$(mktemp)"
trap 'rm -f "${tmp_json}" "${tmp_err}"' EXIT

if ! ${podman_cmd} exec -i odoo_web sh -lc "odoo shell -d '${db_name}' -c '${odoo_conf}' --no-http --log-level=error <<'PY'
import base64
import json
company = env.company
options = json.loads(base64.b64decode('${options_json_b64}').decode('utf-8'))
payload = company.l10n_cz_vat_filing_exports('${date_from}', '${date_to}', options=options)
print(json.dumps(payload))
PY" > "${tmp_json}" 2> "${tmp_err}"; then
  cat "${tmp_err}" >&2
  exit 1
fi

mkdir -p "${out_dir}"
python3 - "${tmp_json}" "${out_dir}" <<'PY'
import json
import pathlib
import sys

payload = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
out_dir = pathlib.Path(sys.argv[2])
out_dir.mkdir(parents=True, exist_ok=True)

if payload.get("dphdp3_xml"):
    (out_dir / "dphdp3.xml").write_text(payload["dphdp3_xml"], encoding="utf-8")
if payload.get("dphkh1_xml"):
    (out_dir / "dphkh1.xml").write_text(payload["dphkh1_xml"], encoding="utf-8")
if payload.get("dphshv_xml"):
    (out_dir / "dphshv.xml").write_text(payload["dphshv_xml"], encoding="utf-8")
(out_dir / "debug.json").write_text(payload["debug_json"], encoding="utf-8")

debug = json.loads(payload["debug_json"])
summary = {
    "date_from": debug["date_from"],
    "date_to": debug["date_to"],
    "options": debug["options"],
    "requested_forms": debug["requested_forms"],
    "excluded_regime_moves": [
        {
            "reference": row["reference"],
            "vat_regime": row["vat_regime"],
        }
        for row in debug.get("excluded_regime_moves", [])
    ],
    "kh_counts": {
        "A1": len(debug["kh"]["A1"]),
        "A2": len(debug["kh"]["A2"]),
        "A4": len(debug["kh"]["A4"]),
        "A5_count": debug["kh"]["A5"]["count"],
        "B1": len(debug["kh"]["B1"]),
        "B2": len(debug["kh"]["B2"]),
        "B3_count": debug["kh"]["B3"]["count"],
    },
    "tag_amounts": debug["tag_amounts"],
    "warnings": debug["validation"]["warnings"],
}
print(json.dumps(summary, indent=2, ensure_ascii=False))
print(f"Wrote XML and debug payload to {out_dir}")
PY
