`l10n_cz_vat_oss_bridge` connects `l10n_eu_oss` with `l10n_cz_vat_filing`.

It automatically detects OSS/IOSS sales moves and syncs `l10n_cz_vat_regime` so those documents are excluded from standard Czech filing exports (`DPHDP3`, `DPHKH1`, `DPHSHV`) without manual tagging.

Detection logic:

- move must be a Czech company customer invoice/refund (`out_invoice` / `out_refund`)
- move must carry the OSS tax tag `l10n_eu_oss.tag_oss`
- if at least one invoice product is tagged `l10n_eu_oss.tag_eu_import` (`non-EU origin`), regime is set to `ioss`
- otherwise regime is set to `oss`

The bridge runs on `create`, `write`, and `action_post` for `account.move`.

Company UI backfill:

- on `Settings -> Companies -> [your company] -> Czech VAT Filing`, use `Backfill OSS/IOSS Regime`
- it scans historical posted customer invoices/refunds and syncs missing `l10n_cz_vat_regime` values for detected OSS/IOSS moves
- useful when installing the bridge mid-period on existing data
