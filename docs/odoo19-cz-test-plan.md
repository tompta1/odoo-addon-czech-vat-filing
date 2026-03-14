# Odoo 19 Czech Accounting Test Plan

## Why target Odoo 19

- Odoo 19 is the current stable major release.
- The existing `addons/odoomates` tree is pinned to `17.0`.
- The same upstream repository already provides a `19.0` branch, now checked out locally as `addons/odoomates-19`.

I do not recommend targeting Odoo 20 for this repo yet.

## Current repo layout

- `addons/odoomates`: legacy `17.0` checkout for comparison
- `addons/odoomates-19`: local worktree for runtime testing
- `addons/custom`: local custom modules

## Odoo Mates compatibility notes

Static review of the bundled `17.0` code shows that a direct in-place port would be expensive. The main blockers were:

- legacy payroll modules
- old security group references to `account.group_account_invoice`
- older accounting report and asset model assumptions

For that reason the runtime now uses upstream `19.0` instead of trying to mutate the `17.0` snapshot.

The local `19.0` worktree still needed one patch class:

- replace `account.group_account_invoice` references with `account.group_account_user`

That patch is already applied locally in `addons/odoomates-19`.

## Fresh-database recommendation

Do not start by trying to open the Odoo 17 database in Odoo 19.

For the first pass:

1. Start a clean Odoo 19 stack.
2. Create a fresh test database.
3. Validate base accounting and Czech localization on that clean database.
4. Only then decide whether a real data migration is worth doing.

## Czech accounting smoke test

Inside Odoo:

1. Create a company with country set to Czech Republic.
2. Install Accounting.
3. Install Czech localization (`l10n_cz`) and confirm the Czech chart, taxes, and fiscal settings load correctly.
4. Configure company VAT, address, bank account, and invoice numbering.
5. Create:
   - one customer in Czech Republic
   - one stockable or service product
   - one 21% VAT sale tax line
6. Create a sample outgoing invoice (`faktura`) with:
   - invoice date
   - due date
   - taxable supply date if the localization exposes it
   - one line with 21% VAT
7. Post the invoice and verify:
   - journal items
   - tax lines
   - VAT report placement
   - PDF output

## Odoo Mates smoke test order

Install and test in this order so failures are easier to isolate:

1. `om_fiscal_year`
2. `om_recurring_payments`
3. `om_account_followup`
4. `accounting_pdf_reports`
5. `om_account_asset`
6. `om_account_budget`
7. `om_account_daily_reports`
8. `om_account_accountant`

If `om_account_accountant` fails, test its dependencies individually first instead of retrying the bundle immediately.

## Kontrolni hlaseni scope

This repo does not currently contain a Czech KH generator addon.

That means there are two separate tasks:

1. get Czech accounting and invoice posting working in Odoo 19
2. add or build a KH export addon that converts posted Czech VAT data into the `DPHKH1` XML structure

Without step 2, the EPO scripts below are only transport helpers.

## Czech EPO / KH test helpers

Scripts in `scripts/`:

- `epo_open_form.sh`: send XML or signed payload to the EPO form opener
- `epo_sign_pkcs7.sh`: wrap XML into a DER PKCS#7 signedData payload using a PEM certificate and key
- `epo_test_submit.sh`: send a signed PKCS#7 payload to the EPO test submission endpoint
- `epo_status.sh`: query submission status using podaci cislo and password

Endpoints:

- form opener: `https://adisspr.mfcr.cz/dpr/epo_podani?otevriFormular=1`
- test submission: `https://adisspr.mfcr.cz/dpr/epo_podani?test=1`
- status lookup: `https://adisspr.mfcr.cz/dpr/epo_stav`

Use the form opener for structure validation and browser-side inspection. Use the test submission endpoint only with a signed PKCS#7 payload.

Use `epo_open_form.sh` first to validate structure and inspect what EPO accepts before attempting a signed test submission.

March 13, 2026 note: a self-signed PKCS#7 test payload was parsed by the EPO test endpoint, but it was rejected with:

- `Použitý certifikát není určen pro vytváření uznávaného elektronického podpisu.`

That means the remaining blocker for a real test submission is not the PKCS#7 envelope itself, but access to a certificate acceptable for a recognized electronic signature.

## Runtime gap

The current Codex execution environment does not have `podman` installed, so the actual UI smoke test, invoice posting, and EPO call still need to be executed on a machine with podman and network access.
