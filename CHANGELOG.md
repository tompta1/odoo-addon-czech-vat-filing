# Changelog

## 2026-03-14 - Release Candidate `v19.0.20.0.0`

### `l10n_cz_vat_filing` `19.0.20.0.0`
- Added CZK-normalized KH threshold routing for domestic `A4/A5` and `B2/B3` classification, including foreign-currency invoices.
- Added origin-aware refund routing for under-threshold B2B credit notes through `reversed_entry_id`.
- Added XML-level KH assertions for `VetaA4`, `VetaA5`, `VetaB2`, and `VetaB3`.
- Added regression tests for `B2B` under/over `10.000 CZK`, `B2C` over `10.000 CZK`, refund routing, and foreign-currency threshold behavior.

### `l10n_cz_vat_oss_bridge` `19.0.2.0.0`
- No code changes in this release candidate.

### `odoo19_report_compat` `19.0.1.0.0`
- No code changes in this release candidate.

