# Changelog

## 2026-03-14 - Release Candidate `v19.0.23.0.0`

### `l10n_cz_vat_filing` `19.0.23.0.0`
- Removed the obsolete `l10n_cz_kh_draft` addon tree and the leftover draft KH export model from the main filing addon.
- Hardened VAT registry payment shielding so outbound supplier payments require a selected bank account when unpublished-account blocking is enabled.
- Reduced Czech filing move selection to a DUZP-aware search domain instead of scanning all posted invoice/refund moves.
- Fixed tag-presence checks so correction/bad-debt logic no longer depends on summed tag amounts being non-zero.
- Added regression tests for payment shielding and tag-presence behavior.

### `l10n_cz_vat_oss_bridge` `19.0.3.0.0`
- Reset `l10n_cz_vat_regime` back to `standard` when OSS/IOSS markers are removed from a move.
- Added regression coverage for regime reset after tax-tag changes.

### `odoo19_report_compat` `19.0.2.0.0`
- Fixed multi-record payslip refunds so the returned action includes all generated refund payslips.
- Guarded the contribution-register report against empty register selections.
- Render analytic distribution names instead of raw analytic account IDs in the journal entries report.
- Added focused compatibility tests for the report helper methods.

## 2026-03-14 - Workspace Licensing Update

- Switched workspace `LICENSE` from `LGPL-3.0-or-later` to `MIT`.
- Updated custom addon manifests to `license: MIT`.
- Added explicit README notes clarifying MIT no-warranty terms for custom code and upstream-license boundaries for third-party addons.

## 2026-03-14 - Release Candidate `v19.0.22.0.0`

### `l10n_cz_vat_filing` `19.0.22.0.0`
- Added Czech VAT FX decoupling settings on company for DUZP-based foreign-currency conversion.
- Added cached DUZP FX-rate model (`l10n_cz.vat.fx.rate`) and a daily cron refresher.
- Added move-level VAT FX audit fields (`manual rate`, `applied rate`, `source`, `rate record`, `note`).
- Added posting-time VAT FX resolution before Czech VAT export logic.
- Updated VAT export amount computation to use DUZP VAT FX conversion for foreign-currency lines instead of accounting balances when enabled.
- Added automated tests for CBN/API-rate decoupling, manual rate override, and blocking lookup-error policy.

## 2026-03-14 - Release Candidate `v19.0.21.0.0`

### `l10n_cz_vat_filing` `19.0.21.0.0`
- Added Czech VAT-registry shield settings on company (`API URL`, timeout, cache TTL, blocking policy toggles).
- Added cached supplier registry-check model for audit and re-use (`l10n_cz.vat.registry.check`).
- Added vendor-bill posting guard (`in_invoice`, `in_refund`) for unreliable payer and unpublished supplier bank-account checks.
- Added supplier-payment posting guard (`account.payment` outbound supplier payments) using the same registry evaluation.
- Added vendor-document audit fields: latest registry check link and note.
- Added automated tests for unreliable-payer blocking, bank mismatch blocking, positive pass path, cache reuse, and lookup-error non-blocking mode.

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
