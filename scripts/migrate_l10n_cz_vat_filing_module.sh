#!/usr/bin/env bash

set -euo pipefail

db_name="${1:-odoo19_cz_test}"
old_module="${OLD_MODULE:-l10n_cz_kh_draft}"
new_module="${NEW_MODULE:-l10n_cz_vat_filing}"
podman_cmd="/var/home/tom/Documents/Projects/odoo-podman-codex/scripts/host-podman.sh"
odoo_conf="${ODOO_CONF:-/etc/odoo/odoo.conf}"

${podman_cmd} exec -i odoo_web sh -lc "odoo shell -d '${db_name}' -c '${odoo_conf}' --no-http --log-level=error <<'PY'
old_module = '${old_module}'
new_module = '${new_module}'

module_model = env['ir.module.module']
old = module_model.search([('name', '=', old_module)], limit=1)
new = module_model.search([('name', '=', new_module)], limit=1)
old_base_xmlid = f'module_{old_module}'
new_base_xmlid = f'module_{new_module}'

if old and new:
    raise RuntimeError(f'Both {old_module} and {new_module} exist in ir_module_module. Resolve manually before migration.')

if old:
    env.cr.execute('SELECT id FROM ir_model_data WHERE module=%s AND name=%s', ('base', new_base_xmlid))
    if env.cr.fetchone():
        raise RuntimeError(f'base.{new_base_xmlid} already exists before migration.')
    env.cr.execute('UPDATE ir_module_module SET name=%s WHERE name=%s', (new_module, old_module))
    env.cr.execute('UPDATE ir_model_data SET module=%s WHERE module=%s', (new_module, old_module))
    env.cr.execute('UPDATE ir_model_data SET name=%s WHERE module=%s AND name=%s', (new_base_xmlid, 'base', old_base_xmlid))
    env.cr.commit()
    print(f'Renamed module metadata from {old_module} to {new_module}.')
elif new:
    env.cr.execute('UPDATE ir_model_data SET module=%s WHERE module=%s', (new_module, old_module))
    env.cr.execute('UPDATE ir_model_data SET name=%s WHERE module=%s AND name=%s', (new_base_xmlid, 'base', old_base_xmlid))
    env.cr.commit()
    print(f'{new_module} already exists in ir_module_module; skipping metadata rename.')
else:
    raise RuntimeError(f'Neither {old_module} nor {new_module} exists in ir_module_module.')

for mod in module_model.search([('name', 'in', [old_module, new_module])], order='name'):
    print('MODULE', mod.name, mod.state, mod.installed_version or '', mod.latest_version or '')
PY"

${podman_cmd} exec -i odoo_web sh -lc "odoo -d '${db_name}' -c '${odoo_conf}' -u '${new_module}' --stop-after-init --no-http --log-level=error"
${podman_cmd} restart odoo_web >/dev/null

${podman_cmd} exec -i odoo_web sh -lc "odoo shell -d '${db_name}' -c '${odoo_conf}' --no-http --log-level=error <<'PY'
for mod in env['ir.module.module'].search([('name', 'in', ['${old_module}', '${new_module}'])], order='name'):
    print('MODULE', mod.name, mod.state, mod.installed_version or '', mod.latest_version or '')
PY"
