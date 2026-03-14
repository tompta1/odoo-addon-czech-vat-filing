`l10n_cz_kh_draft` is deprecated.

The active technical addon name is `l10n_cz_vat_filing` in `addons/custom/l10n_cz_vat_filing`.

This legacy directory is kept only as a compatibility copy while the repository transition settles.
Its module manifest has been disabled, so Odoo should no longer discover it as an installable addon.

For database migration from the old module name to the new one, run:

```bash
./scripts/migrate_l10n_cz_vat_filing_module.sh
```
