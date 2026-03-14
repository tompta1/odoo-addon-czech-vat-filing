Place local addons here.

This directory is mounted into the container as `/mnt/custom-addons` and is included in `addons_path`.

Suggested use:

- Czech-specific KH export/integration addons
- small compatibility patches that should not live inside the Odoo Mates worktree
- one-off test helpers for invoice/import/export flows

Current local addon:

- `l10n_cz_vat_filing`: Czech VAT filing addon with XML export for `DPHDP3`, `DPHKH1`, and `DPHSHV`; this is the canonical technical addon name, is not Odoo Mates-specific, and now covers VAT 30-34 in addition to the baseline domestic/EU path
- `l10n_cz_vat_oss_bridge`: bridge addon that integrates `l10n_eu_oss` with `l10n_cz_vat_filing` and auto-classifies OSS/IOSS documents into Czech filing regime exclusions
- `odoo19_report_compat`: small report overrides for Odoo 19 compatibility issues in third-party addons; this addon is Odoo Mates-specific

License note:

- Custom addons in this directory are licensed as `MIT` unless explicitly stated otherwise.
- External third-party addons keep their upstream licenses.
