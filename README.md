# Czech Odoo 19 VAT Filing Workspace

Official workspace for Czech VAT filing add-ons and reproducible local runtime tooling.
This repository is intended to be published as an add-on/tooling project, not as a full vendored Odoo distribution.

## Project Scope

Main modules:

- `addons/custom/l10n_cz_vat_filing`: Czech XML filing export for `DPHDP3`, `DPHKH1`, `DPHSHV`
- `addons/custom/l10n_cz_vat_oss_bridge`: exclusion bridge for `OSS`/`IOSS` flows (`l10n_eu_oss`)
- `addons/custom/odoo19_report_compat`: compatibility helpers for selected Odoo Mates report modules

Current filing coverage (microSME focus) includes:

- `KH` sections `A1`, `A2`, `A4`, `A5`, `B1`, `B2`, `B3`
- DUZP-based period selection
- automatic `KH` threshold routing (`10 000 CZK`) including refund handling
- import and reverse-charge hardening (`KH` exclusion where legally required)
- `DPH` rows including derived `46`, `52`, year-end settlement `53`, and explicit support for `45`, `48`, `60`
- optional CZ VAT Registry Shield checks (supplier reliability and published bank account matching)
- optional DUZP-based CZ VAT FX decoupling (ČNB feed + cache + manual override)

For detailed addon behavior and field-level documentation, see:

- `addons/custom/l10n_cz_vat_filing/README.md`

## Prerequisites

- Linux environment (tested in Fedora Silverblue Toolbox)
- `git`
- `podman` + `podman-compose` (recommended)
- or `docker` + `docker compose` / `docker-compose`
- free disk space for Odoo/PostgreSQL images and volumes

Optional but useful:

- `flatpak-spawn` on Silverblue/Toolbox for host Podman access (`flatpak-spawn --host podman ...`)

## Quick Start

1. Prepare local config:

```bash
cp .env.example .env
cp config.example/odoo.conf config/odoo.conf
```

2. Prepare Odoo Mates worktree (if needed for your run):

```bash
./scripts/prepare_odoomates_worktree.sh 19.0
```

3. Start stack (Podman):

```bash
podman compose -f podman-compose.yaml up -d
```

Alternative invocation (legacy binary):

```bash
podman-compose -f podman-compose.yaml up -d
```

4. The same compose file can also be started with Docker Compose:

```bash
docker compose -f podman-compose.yaml up -d
docker-compose -f podman-compose.yaml up -d
```

Notes:

- `podman-compose.yaml` uses a standard Compose format and is generally interchangeable for this project.
- On some Docker installations, SELinux volume suffixes (`:Z,U`) may require adjustment.

## Common Workflows

Seed test data and export sample filings:

```bash
./scripts/odoo_seed_cz_vat_cases.sh
./scripts/odoo_export_cz_vat_filings.sh 2026-03-01 2026-03-31 /tmp/cz-vat-filing
```

Open generated XML in MF/EPO helper:

```bash
scripts/epo_open_form.sh /tmp/cz-vat-filing/dphdp3.xml
scripts/epo_open_form.sh /tmp/cz-vat-filing/dphkh1.xml
scripts/epo_open_form.sh /tmp/cz-vat-filing/dphshv.xml
```

Run module test suite from running container:

```bash
flatpak-spawn --host podman exec -i odoo_web sh -lc \
  "odoo -d odoo19_cz_test -c /etc/odoo/odoo.conf --http-port=10069 --stop-after-init -u l10n_cz_vat_filing --test-enable --test-tags /l10n_cz_vat_filing"
```

## Publication Guidance

Recommended to keep in GitHub:

- `addons/custom/`
- `docs/`
- `scripts/`
- `podman-compose.yaml`
- `.env.example`
- `config.example/odoo.conf`
- `.gitignore`
- `README.md`
- `CHANGELOG.md`

Recommended to keep out of GitHub:

- `addons/odoomates/`
- `addons/odoomates-19/`
- `addons/.odoomates-source/`
- `config/odoo.conf`
- `.env`
- generated signing material, XML exports, caches, local secrets
- local data blobs such as `accountant_laws_rag_v3_chunked.jsonl` unless intentionally published

Track upstream refs instead of vendoring Odoo Mates code:

- `docs/odoomates-upstream.md`

## Release

Release staging, tagging, and packaging:

- `docs/release-publishing.md`

Build addon zip artifacts:

```bash
./scripts/release_pack_addons.sh v19.0.22.0.0
```

## TODO

- [ ] Add optional UI action for one-time historical backfill of VAT filing regimes on posted moves
- [ ] Expand end-to-end reverse-charge (RPDP) scenarios and validation matrix
- [ ] Add stronger import-correction (`row 45`) scenarios covering customs revaluation variants
- [ ] Add optional direct submission pipeline integration (Datová schránka / ISDS), including delivery receipt capture
- [ ] Add dedicated integration test harness for live-like ADIS/VIES/ARES responses (local mock server profile)
- [ ] Improve contributor guide with troubleshooting for Toolbox/Silverblue networking and container permissions

## References

- Addon internals: `addons/custom/l10n_cz_vat_filing/README.md`
- Odoo Mates upstream refs: `docs/odoomates-upstream.md`
- Release process: `docs/release-publishing.md`
- Test plan notes: `docs/odoo19-cz-test-plan.md`
