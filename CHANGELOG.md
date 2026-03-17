# Changelog

## 2026-03-17 — `v19.0.24.0.0`

### `l10n_cz_vat_filing` `19.0.24.0.0`

- **SEPA/Batch Payment Registry Shield** — hooks `account.batch.payment.validate()` via soft dependency on the Enterprise `account_batch_payment` module; collects all violations across the batch before raising a single `UserError`; silently skipped on Odoo CE.
- **Async EPO Status Polling** — manual "Check EPO Status" button on filing history (visible for `submitted` and `error` states); polls ADIS EPO `ZjistiStatus` SOAP endpoint only; never calls `GetListOfReceivedMessages`; opt-in cron inactive by default; security warning banner on ISDS credentials settings.
- **Default URL prefill** — `post_init_hook` backfills `l10n_cz_vat_registry_api_url` (ADIS SOAP) and `l10n_cz_vat_fx_api_url` (ČNB daily rate feed) for existing company records on fresh install.
- **Weekend/Holiday ČNB FX Fallback (§ 38 Czech VAT Act)** — when no ČNB rate is published for the DUZP (weekend/public holiday), retries up to 5 preceding calendar days; stores actual rate date separately from DUZP in `l10n_cz.vat.fx.rate.rate_date`; hard network errors abort the fallback immediately.
- Test isolation fix: `TestL10nCzVatFilingExport._setup_company` now explicitly resets `l10n_cz_vat_fx_enforce_cnb=False` to prevent cross-session DB contamination.

## 2026-03-14 — `v19.0.23.0.0`

### `l10n_cz_vat_filing` `19.0.23.0.0`
- Removed the obsolete `l10n_cz_kh_draft` addon tree.
- Hardened VAT registry payment shielding to require a selected bank account when unpublished-account blocking is enabled.
- Reduced filing move selection to a DUZP-aware search domain.
- Fixed tag-presence checks so bad-debt/correction logic no longer depends on summed tag amounts being non-zero.
- Added pre-flight XSD validation and admin XSD schema refresh action.

### `l10n_cz_vat_oss_bridge` `19.0.3.0.0`
- Reset `l10n_cz_vat_regime` to `standard` when OSS/IOSS tax tags are removed from a move.

### `odoo19_report_compat` `19.0.2.0.0`
- Fixed multi-record payslip refund action.
- Guarded contribution-register report against empty selection.
- Render analytic distribution names in journal entries report.

## 2026-03-14 — `v19.0.22.0.0`

### `l10n_cz_vat_filing` `19.0.22.0.0`
- Added ČNB FX decoupling: DUZP-based foreign-currency rate resolution, cached `l10n_cz.vat.fx.rate` model, daily cron refresher, move-level audit fields, and blocking-error policy.

## 2026-03-14 — `v19.0.21.0.0`

### `l10n_cz_vat_filing` `19.0.21.0.0`
- Added VAT Registry Shield: ADIS SOAP lookup, `l10n_cz.vat.registry.check` model, vendor-bill and supplier-payment posting guards, and audit fields.

## 2026-03-14 — `v19.0.20.0.0`

### `l10n_cz_vat_filing` `19.0.20.0.0`
- Added CZK-normalised KH threshold routing for A4/A5 and B2/B3 including foreign-currency invoices and origin-aware refund routing.
