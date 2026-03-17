#!/usr/bin/env bash

set -euo pipefail

db_name="${1:-odoo19_cz_test}"
odoo_conf="${ODOO_CONF:-/etc/odoo/odoo.conf}"
podman_cmd="/var/home/tom/Documents/Projects/odoo-podman-codex/scripts/host-podman.sh"

${podman_cmd} exec -i odoo_web sh -lc "odoo shell -d '${db_name}' -c '${odoo_conf}' --no-http --log-level=error <<'PY'
env = odoo.api.Environment(env.cr, odoo.SUPERUSER_ID, {})
History = env['l10n_cz.vat.filing.history']
company = env.company

history = History.search([('company_id', '=', company.id)], order='id desc', limit=1)
if not history:
    options = {
        'include_dphdp3': True,
        'include_dphkh1': False,
        'include_dphshv': False,
        'submission_date': '2026-03-14',
        'dph_form': 'B',
        'kh_form': 'B',
        'sh_form': 'R',
    }
    exports = {
        'dphdp3_xml': \"<Pisemnost id='ISDS-SMOKE'/>\",
        'dphkh1_xml': '',
        'dphshv_xml': '',
        'debug_json': '{}',
        'debug': {
            'metadata': {
                'submission_date': '2026-03-14',
                'dph_form': 'B',
                'kh_form': 'B',
                'sh_form': 'R',
            },
            'validation': {'warnings': []},
        },
    }
    history = History.create_export_record(
        company,
        '2026-03-01',
        '2026-03-31',
        options,
        exports,
        include_debug_json=False,
    )

result = history.action_submit_isds()

print(f'mode={company.l10n_cz_isds_mode}')
print(f'history_id={history.id}')
print(f'isds_status={history.isds_status}')
print(f'isds_message_id={history.isds_message_id or \"\"}')
print(f'isds_target_box={history.isds_target_box_id or \"\"}')
print(f'isds_error={(history.isds_last_error or \"\").replace(chr(10), \" \")}')
print(f'isds_delivery={(history.isds_delivery_info or \"\").replace(chr(10), \" \")}')
print(f'action_tag={result.get(\"tag\")}')
PY"
