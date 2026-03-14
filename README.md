# Czech Odoo 19 VAT Filing Sandbox

This repository is best published as a small addon-and-tooling workspace, not as a full vendored Odoo distribution.

It currently contains:

- `addons/custom/l10n_cz_vat_filing`: Czech VAT filing export for `DP3`, `KH1`, and `SHV`
- `addons/custom/l10n_cz_vat_oss_bridge`: bridge module that maps `l10n_eu_oss` transactions into Czech filing regime exclusions
- `addons/custom/odoo19_report_compat`: Odoo 19 compatibility fixes for specific Odoo Mates report modules
- optional local runtime helpers for Podman, EPO submission testing, and Odoo Mates worktree setup

## Is It Odoo Mates-Specific?

- `l10n_cz_vat_filing`: no. It depends only on core Odoo `account` plus `l10n_cz`.
- `l10n_cz_vat_oss_bridge`: mostly no. It depends on `l10n_cz_vat_filing` and Odoo's `l10n_eu_oss`.
- `odoo19_report_compat`: yes. It exists only to patch/report around Odoo Mates modules.

If you want a clean public GitHub repository focused on Czech filing work, the most important things to publish are `addons/custom/l10n_cz_vat_filing` and `addons/custom/l10n_cz_vat_oss_bridge`.

## What To Publish

Recommended to keep in GitHub:

- `addons/custom/`
- `docs/`
- `scripts/`
- `podman-compose.yaml`
- `.env.example`
- `config.example/odoo.conf`
- `.gitignore`
- `README.md`

Recommended to keep out of GitHub:

- `addons/odoomates/`
- `addons/odoomates-19/`
- `addons/.odoomates-source/`
- `config/odoo.conf`
- `.env`
- `accountant_laws_rag_v3_chunked.jsonl`
- generated signing material, XML exports, caches, and local secrets

The repo should record upstream Odoo Mates refs, not vendor their code. See [docs/odoomates-upstream.md](/var/home/tom/Documents/Projects/odoo-podman-codex/docs/odoomates-upstream.md).

## Why Keep Compose And Scripts?

Yes, I would keep the Podman compose file and shell scripts in the public repo, but as optional convenience tooling rather than as the core product.

That gives you:

- a fast local smoke-test path for contributors
- a reproducible way to fetch Odoo Mates dependencies
- reusable EPO open/sign/submit helpers for Czech filing tests

The only change needed for GitHub is to publish a config example, not your live `config/odoo.conf`.

## Quick Start

```bash
cp .env.example .env
cp config.example/odoo.conf config/odoo.conf
./scripts/prepare_odoomates_worktree.sh 19.0
podman compose up -d
```

On Fedora Silverblue with Toolbox or a host Podman wrapper, you can still use the included helper scripts if direct container access needs `flatpak-spawn --host`.

## Current Addon Scope

`l10n_cz_vat_filing` currently covers a tested Czech microSME path:

- posted Czech VAT invoices and vendor bills
- XML generation for `DP3`, `KH1`, and `SHV`
- `KH` sections `A1`, `A2`, `A4`, `A5`, `B1`, `B2`, and `B3`
- `DPH` output and deduction lines driven by `l10n_cz` tags for domestic VAT, EU acquisitions, domestic reverse charge received supplies, triangular trade, exempt import, vehicle purchases, bad-debt corrections, import/customs deduction, and non-established-supplier adjustments
- third-country import hardening that keeps import-tagged moves out of `KH`
- move-level `OSS` / `IOSS` exclusion from the standard Czech XML exports
- derived `DPH` rows `46`, `52`, and year-end `53`, plus explicit move-field support for special rows `45`, `48`, and `60`
- `SH` rows for intra-EU goods, services, and triangular-trade supply (`k_pln_eu=2`)
- period selection by Czech DUZP through `CZ DPH Tax Date (DUZP)`, not just by accounting date
- `VetaD` header control through export options such as `submission_date`, `tax_statement_date`, `dph_form`, `kh_form`, and `sh_form`
- form-selection flags such as `include_dphkh1=false` for quarterly `DPH` runs on legal entities
- quarterly hardening that blocks legally invalid combined exports for legal entities and quarterly `SH` with goods/triangular rows
- structure validation against the official MF opener
- test submission transport up to certificate-policy validation

It is still not a full legal Czech VAT filing engine for every edge case and still does not include qualified signing credentials. The exporter now covers `VAT 23/24/47/50/51/61` and the rest of the stock `l10n_cz` VAT tax tags, derives `DPH` rows `46`, `52`, and year-end `53`, and supports special `DPH` rows `45`, `48`, and `60` through explicit move fields.

Repeatable local smoke helpers are included:

```bash
./scripts/migrate_l10n_cz_vat_filing_module.sh
./scripts/odoo_seed_cz_vat_cases.sh
./scripts/odoo_export_cz_vat_filings.sh 2026-03-01 2026-03-31 /tmp/cz-vat-filing
```

## Release Workflow

Release staging, tagging, and packaging steps are documented in
[docs/release-publishing.md](/var/home/tom/Documents/Projects/odoo-podman-codex/docs/release-publishing.md).

Build addon zip artifacts for GitHub Releases / Odoo Apps:

```bash
./scripts/release_pack_addons.sh v19.0.21.0.0
```

## Odoo Mates Refs

The exact upstream remote, tested branch, and local commit refs are recorded in [docs/odoomates-upstream.md](/var/home/tom/Documents/Projects/odoo-podman-codex/docs/odoomates-upstream.md).
