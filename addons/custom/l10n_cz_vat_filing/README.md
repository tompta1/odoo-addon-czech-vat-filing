`l10n_cz_vat_filing` is the canonical technical addon name.
It replaces the earlier `l10n_cz_kh_draft` module through an explicit database migration.

It currently provides:

- the original draft JSON helper for invoice VAT data
- Czech XML export for `DP3`, `KH1`, and `SHV`
- live smoke helpers for seeding representative Czech filing cases and exporting the resulting XML
- Czech DUZP-driven period selection through `CZ DPH Tax Date (DUZP)` on `account.move`

The supported XML scope is the baseline microSME path already classified by `l10n_cz` tax tags:

- domestic Czech sales and purchases
- domestic reverse-charge sales for `KH A1`
- vendor-side acquisition and adjustment rows for `KH A2`
- domestic reverse-charge purchase rows for `KH B1`
- triangular trade rows `VAT 30/31`, including `souhrnne hlaseni` code `2` for row `31`
- exempt import row `VAT 32`
- new-means-of-transport row `VAT 23`
- selected cross-border transaction row `VAT 24`
- third-country import rows `VAT 7/8` plus customs-deduction row `VAT 42`, while keeping those documents out of `KH`
- import-correction deductions via `VAT 45 Full` / `VAT 45 Reduced`, linked to original JSD evidence
- bad-debt correction rows `VAT 33/34`, including `KH A4/B2` detail with `zdph_44="P"`
- automatic domestic `KH` threshold routing (`10.000 CZK`) for `A4/A5` and `B2/B3`, evaluated in `CZK` (including foreign-currency invoices)
- domestic B2B refunds under `10.000 CZK` are detail-routed to `A4/B2` only when linked to an over-threshold origin invoice
- optional Czech VAT-registry shield checks for supplier reliability and published bank-account matching on vendor bills and supplier payments
- optional Czech VAT FX decoupling that resolves DUZP-based FX rates to CZK (with cache and manual override) for foreign-currency VAT export amounts
- asset-acquisition information row `VAT 47`
- coefficient-base rows `VAT 50` and `VAT 51`
- tax-refund row `VAT 61`
- EU goods/services supply rows for `souhrnne hlaseni`
- `DPH` output lines mapped from `VAT 1/2`, `VAT 3/4/5/6/7/8/9/10/11/12/13`, and `VAT 20/21/22/23/24/25/26`
- `DPH` additional-data lines mapped from `VAT 30/31/32/33/34`
- `DPH` deduction lines mapped from self-assessed `VAT 3/4/5/6/7/8/9/10/11/12/13`, purchase-deduction `VAT 40/41/42`, asset-acquisition row `VAT 47`, and bad-debt debtor correction row `VAT 34`
- coefficient-trigger tags (`VAT 40/41/42 Coefficient`) that keep `KH` tax lines intact while routing `DPH` deductions to reduced-claim fields
- auto-derived `DPH` row `46` totals from rows `40` to `45`
- auto-derived `DPH` rows `52` and year-end `53`
- wizard-driven year-end `ř. 53` settlement using actual annual coefficient (December / Q4 only)
- explicit move-field support for special `DPH` rows `45`, `48`, and `60`
- posted invoices, refunds, vendor bills, and vendor refunds
- period inclusion by Czech tax date (`DUZP`) with fallback order `CZ DPH Tax Date -> invoice date -> accounting date`

The exporter also accepts optional manual `DPH` row values through the `options` payload passed to `l10n_cz_vat_filing_exports()`:

- `line_45_full_deduction`
- `line_45_reduced_deduction`
- `line_48_base_amount`
- `line_48_full_deduction`
- `line_48_reduced_deduction`
- `line_52a_coefficient`
- `line_52b_deduction`
- `line_53a_settlement_coefficient`
- `line_53b_change_deduction`
- `line_60_adjustment`

The same `options` payload also controls the filing header (`VetaD`) metadata:

- `submission_date` -> `d_poddp`
- `tax_statement_date` -> `d_zjist` for dodatecne/opravne variants
- `dph_form` -> `dapdph_forma`
- `kh_form` -> `khdph_forma`
- `sh_form` -> `shvies_forma`
- `kh_challenge_reference` -> `c_jed_vyzvy`
- `kh_challenge_response` -> `vyzva_odp`
- `period_from` / `period_to` -> `zdobd_od` / `zdobd_do` for partial-period `DPH` or eligible `KH`
- `nace_code`, `former_vat`, `software_name`, `software_version`, and contact/address overrides

Form-selection flags are also accepted:

- `include_dphdp3`
- `include_dphkh1`
- `include_dphshv`

Those flags matter for quarterly hardening:

- quarterly `KH` is blocked for Czech legal entities, so quarterly `DPH` runs should set `include_dphkh1=false`
- quarterly `SH` is blocked when the quarter contains goods or triangular-trade rows, so those runs should set `include_dphshv=false` or export monthly
- dodatecne `DPH` forms `D` and `E` require an explicit `tax_statement_date`
- nasledne / opravne `KH` forms `N` and `E` require `tax_statement_date` or `kh_challenge_reference`

Deprecated aliases still accepted for backward compatibility:

- `line_45_in_full_amount` -> `line_48_full_deduction`
- `line_45_reduced_claim` -> `line_48_reduced_deduction`

It is still not a full legal filing engine for every Czech VAT scenario, and it does not by itself provide a qualified signing certificate.
The exporter uses the current MF form identifiers in the generated XML and is intended to cover the common accounting path for a Czech microSME.
On March 14, 2026, the generated `DPHDP3`, `DPHKH1`, and `DPHSHV` XML were revalidated against the official MF form opener after correcting the current field names for `A1`, `A2`, `B1`, and the `DPH` section-4 deduction and coefficient workflow.

The exporter now covers all stock `l10n_cz` VAT tax-tag families used by the Czech VAT return. It derives `DPH` rows `45`, `52`, and year-end `53` from posted data plus the advance coefficient workflow, while `48` and `60` are supported through explicit move fields or option overrides.
It now also hard-fails on quarterly combined exports for legal entities, because Czech `KH` remains monthly even when the `DPH` return is quarterly, and it blocks quarterly `SH` exports that include goods or triangular-trade rows.

Additional filing controls exposed on `account.move`:

- `CZ VAT Filing Regime`
- `CZ Customs MRN`
- `CZ Customs Decision Number`
- `CZ Customs Release Date`
- `CZ Customs Office`
- `CZ Customs Value`
- `CZ Import VAT Amount`
- `CZ Customs Note`
- `CZ Import Correction Origin`
- `CZ Import Correction Reason`
- `CZ KH Document Reference`
- `CZ DPH Tax Date (DUZP)`
- `CZ KH Tax Point Date`
- `CZ KH Deduction Date`
- `CZ KH Reverse Charge Code`
- `CZ KH Proportional Deduction`
- `CZ KH Subject Code` (line-level on invoice lines)
- `CZ DPH Line 45 Full Deduction`
- `CZ DPH Line 45 Reduced Deduction`
- `CZ DPH Line 48 Base`
- `CZ DPH Line 48 Full Deduction`
- `CZ DPH Line 48 Reduced Deduction`
- `CZ DPH Line 60 Adjustment`
- `CZ VAT Registry Check`
- `CZ VAT Registry Note`
- `CZ VAT FX Manual Rate`
- `CZ VAT FX Applied Rate`
- `CZ VAT FX Source`
- `CZ VAT FX Rate Record`
- `CZ VAT FX Note`

Additional filing controls exposed on `res.company`:

- `Use Manual CZ DPH Advance Coefficient`
- `CZ DPH Advance Coefficient`
- `Enable CZ VAT Registry Shield`
- `CZ VAT Registry API URL`
- `CZ VAT Registry VAT Parameter`
- `CZ VAT Registry Timeout (s)`
- `CZ VAT Registry Cache (h)`
- `Block Vendor Bills On Registry Risk`
- `Block Supplier Payments On Registry Risk`
- `Block Unreliable VAT Payers`
- `Block Unpublished Supplier Bank Accounts`
- `Block On VAT Registry Lookup Errors`
- the shield fetcher accepts both JSON and XML responses; ADIS SOAP endpoint
  `.../rozhraniCRPDPH.rozhraniCRPDPHSOAP` is posted via
  `getStatusNespolehlivySubjektRozsireny`
- VIES-style JSON (`isValid` / `valid`, `userError`) is recognized for general VAT-validation checks
- `Enable CZ VAT FX Decoupling`
- `CZ VAT FX API URL`
- `CZ VAT FX Currency Parameter`
- `CZ VAT FX Date Parameter`
- `CZ VAT FX Timeout (s)`
- `CZ VAT FX Cache (days)`
- `Block On VAT FX Lookup Errors`
- default FX endpoint is prefilled to official ČNB `denni_kurz.txt`, parsed in native TXT format with `date=DD.MM.YYYY`
- `Enable Datova Schranka Submission`
- `ISDS Submission Mode` (`mock` or `http_json`)
- `ISDS Bridge API URL`, `ISDS Bridge Username`, `ISDS Bridge Password`
- `ISDS Sender Databox ID`, `ISDS Target Databox ID`, `ISDS Timeout (s)`

ISDS bridge response contract (HTTP JSON mode):

- success indicators: `status`/`result`/`success` (`ok`, `success`, `submitted`, `true`, or boolean `true`)
- message identifier: `message_id` (fallback `messageId` or `id`)
- optional delivery receipt fields: `delivery_receipt_base64` (+ optional filename/mimetype keys)
- when delivery receipt base64 is present and valid, it is persisted as `ISDS Delivery Receipt` attachment in filing history

Built-in Odoo UI export wizard:

- open `Settings -> Companies -> [your company] -> Czech VAT Filing -> Open Export Wizard`
- choose period, forms (`DPHDP3` / `DPHKH1` / `DPHSHV`), and filing metadata (`d_poddp`, optional `d_zjist`)
- click `Download ZIP` to get generated XML files (plus optional `debug.json`)
- the wizard passes the same validated options used by the shell flow, including period overrides and challenge-reference fields
- each wizard export is stored in persistent history (`Open Export History`) with linked XML/JSON/ZIP attachments

Repeatable local smoke flow:

```bash
./scripts/odoo_seed_cz_vat_cases.sh
./scripts/odoo_export_cz_vat_filings.sh 2026-03-01 2026-03-31 /tmp/cz-vat-filing
scripts/epo_open_form.sh /tmp/cz-vat-filing/dphdp3.xml
scripts/epo_open_form.sh /tmp/cz-vat-filing/dphkh1.xml
scripts/epo_open_form.sh /tmp/cz-vat-filing/dphshv.xml
```

Automated addon tests from the running Podman stack:

```bash
flatpak-spawn --host podman exec -i odoo_web sh -lc \
  "odoo -d odoo19_cz_test -c /etc/odoo/odoo.conf --http-port=10069 --stop-after-init -u l10n_cz_vat_filing --test-enable --test-tags /l10n_cz_vat_filing"
```

The smoke seed helper creates custom test taxes for `VAT 23`, `VAT 24`, `VAT 30`, `VAT 31`, `VAT 33`, and `VAT 34`, because the stock `l10n_cz` localization exposes those rows in the tax report but does not ship ready-made taxes for them.
It now does the same for `VAT 47`, `VAT 50`, `VAT 51`, and `VAT 61`, and it seeds:

- prior-year `2025` taxable/exempt turnover so `ř. 52` can be derived from real data
- a proportional customs-deduction case for `VAT 42`
- customs/JSD evidence fields on 3rd-country import moves, including `MRN` / customs decision and customs release date
- one `IOSS`-flagged sale that must stay out of the standard Czech XML exports
- one explicit move carrying `ř. 45`
- one proportional-deduction purchase for automatic `ř. 52`
- one coefficient-tagged domestic asset purchase (`VAT40-COEF70-ASSET-TEST`) for § 76 reduced-claim routing
- one explicit move carrying `ř. 48` and `ř. 60`
- one domestic reverse-charge A1/B1 pair with line-level subject code (`4`) for KH scaffolding
- three KH threshold-router markers (`KH-B2B-UNDER-10K-TEST`, `KH-B2B-OVER-10K-TEST`, `KH-B2C-OVER-10K-TEST`)
- cross-period `A2-EU-TEST` and `VAT23-NMT-TEST` documents with April accounting dates but March DUZP
- paired positive/negative `VAT 33` and `VAT 34` bad-debt correction documents
- no manual company coefficient is required for the default smoke run

The current import / dropshipping hardening is:

- `VAT 7/8` and `VAT 42` stay in `DPHDP3` but do not participate in `KH`
- documents that mix import tags with `KH`-driving tags now fail validation
- 3rd-country import moves must carry customs evidence: `MRN` or customs decision number, plus customs release date
- `VAT 45` correction-tagged documents must be purchase-side documents linked to an original posted 3rd-country import move
- linked import corrections can reuse customs evidence from the origin move instead of duplicating MRN/JSD data
- A1/B1 reverse-charge rows can now read subject code from line-level `CZ KH Subject Code` with move-level fallback
- temporary RPDP subject codes `11` and `14` now hard-fail below a `100.000 CZK` taxable base
- moves marked with filing regime `OSS` or `IOSS` are excluded from the standard Czech `DPHDP3`, `DPHKH1`, and `DPHSHV` exports
- moves marked with filing regime `OSS` or `IOSS` must use non-Czech taxes; if they still carry Czech filing tags, the export now fails validation
- DUZP-based Czech VAT FX rates can be refreshed daily by cron (`CZ VAT FX Rate Refresh`) and are cached in `l10n_cz.vat.fx.rate` (official ČNB TXT feed + JSON fallback)

That `OSS` / `IOSS` support is currently a guarded exclusion path, not a full Odoo `l10n_eu_oss` integration.

Example from `odoo shell`:

```python
exports = env.company.l10n_cz_vat_filing_exports(
    "2026-03-01",
    "2026-03-31",
    options={
        "submission_date": "2026-04-20",
        "dph_form": "B",
        "kh_form": "B",
        "sh_form": "R",
    },
)
print(exports["dphdp3_xml"])
print(exports["dphkh1_xml"])
print(exports["dphshv_xml"])
```

Run an explicit 70% coefficient scenario for the seeded `VAT40-COEF70-ASSET-TEST` case:

```bash
printf '%s' '{"line_52a_coefficient":70}' > /tmp/odoo_export_options_coef70.json
./scripts/odoo_export_cz_vat_filings.sh 2026-03-01 2026-03-31 /tmp/cz-vat-filing-coef70 odoo19_cz_test @/tmp/odoo_export_options_coef70.json
```
