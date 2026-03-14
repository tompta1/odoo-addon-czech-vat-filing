#!/usr/bin/env bash

set -euo pipefail

db_name="${1:-odoo19_cz_test}"
company_id="${2:-}"
odoo_conf="${ODOO_CONF:-/etc/odoo/odoo.conf}"
podman_cmd="/var/home/tom/Documents/Projects/odoo-podman-codex/scripts/host-podman.sh"

company_arg=""
if [[ -n "${company_id}" ]]; then
  company_arg="${company_id}"
fi

${podman_cmd} exec -i odoo_web sh -lc "odoo shell -d '${db_name}' -c '${odoo_conf}' --no-http --log-level=error <<'PY'
import os

company_id = '${company_arg}'.strip()
if company_id:
    company = env['res.company'].browse(int(company_id))
    if not company.exists():
        raise Exception(f'Company id {company_id} does not exist.')
else:
    company = env.company

def parse_bool(value):
    text = str(value or '').strip().lower()
    return text in {'1', 'true', 'yes', 'on'}

def parse_int(value, default_value):
    text = str(value or '').strip()
    if not text:
        return default_value
    try:
        return max(1, int(text))
    except ValueError:
        return default_value

mapping = {
    'l10n_cz_isds_enabled': ('L10N_CZ_ISDS_ENABLED', 'bool'),
    'l10n_cz_isds_mode': ('L10N_CZ_ISDS_MODE', 'str'),
    'l10n_cz_isds_api_url': ('L10N_CZ_ISDS_API_URL', 'str'),
    'l10n_cz_isds_username': ('L10N_CZ_ISDS_USERNAME', 'str'),
    'l10n_cz_isds_password': ('L10N_CZ_ISDS_PASSWORD', 'str'),
    'l10n_cz_isds_sender_box_id': ('L10N_CZ_ISDS_SENDER_BOX_ID', 'str'),
    'l10n_cz_isds_target_box_id': ('L10N_CZ_ISDS_TARGET_BOX_ID', 'str'),
    'l10n_cz_isds_timeout_seconds': ('L10N_CZ_ISDS_TIMEOUT_SECONDS', 'int'),
}

vals = {}
for field_name, (env_name, value_type) in mapping.items():
    raw = os.getenv(env_name)
    if raw is None:
        continue
    if value_type == 'bool':
        vals[field_name] = parse_bool(raw)
    elif value_type == 'int':
        vals[field_name] = parse_int(raw, company[field_name] or 20)
    else:
        vals[field_name] = str(raw).strip()

if not vals:
    print('No L10N_CZ_ISDS_* env values found in container. Nothing to apply.')
else:
    company.sudo().write(vals)
    env.cr.commit()
    visible = {k: ('***' if k == 'l10n_cz_isds_password' and vals.get(k) else vals.get(k)) for k in vals}
    print(f'Applied ISDS env config to company {company.display_name} (id={company.id}): {visible}')
PY"
