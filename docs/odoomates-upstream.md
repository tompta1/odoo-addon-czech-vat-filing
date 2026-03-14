# Odoo Mates Upstream Refs

This repository should not vendor Odoo Mates source code in GitHub.
Instead, it records the upstream refs used during local testing and recreates local worktrees on demand.

## Upstream Remote

- Repository: `https://github.com/odoomates/odooapps.git`

## Recorded Local Refs

Captured on March 14, 2026:

- `17.0` reference checkout: `f5d14f360967a26455c5819a217102fa18af4cf1`
- `19.0` test worktree: `c50361783368262d2a96bcd04dffb94d1441d50d`

The local `19.0` worktree matched the upstream `origin/19.0` commit at the time these refs were captured.

## Modules Used Here

Accounting and reporting smoke tests used these Odoo Mates addons:

- `accounting_pdf_reports`
- `om_account_accountant`
- `om_account_asset`
- `om_account_budget`
- `om_account_daily_reports`
- `om_account_followup`
- `om_fiscal_year`
- `om_hr_payroll`
- `om_hr_payroll_account`
- `om_recurring_payments`

The custom addon `odoo19_report_compat` is Odoo Mates-specific and currently depends on:

- `accounting_pdf_reports`
- `om_account_followup`
- `om_hr_payroll`

The custom addon `l10n_cz_vat_filing` is not Odoo Mates-specific. It depends only on standard Odoo `account` and `l10n_cz`.

## Recreate The Local 19.0 Worktree

From a fresh clone of this repository:

```bash
./scripts/prepare_odoomates_worktree.sh 19.0
```
