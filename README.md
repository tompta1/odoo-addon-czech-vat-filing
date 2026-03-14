# Czech Odoo 19 VAT Filing Workspace

Practical workspace for Czech VAT filing addons on Odoo 19 (`DPHDP3`, `DPHKH1`, `DPHSHV`) with Podman/Docker runtime helpers.

## What You Get

- `addons/custom/l10n_cz_vat_filing` (main CZ VAT export addon)
- `addons/custom/l10n_cz_vat_oss_bridge` (OSS/IOSS exclusion bridge)
- scripts for seeding data, exporting XML, and ISDS config sync
- `podman-compose.yaml` that is usable with `podman compose`, `podman-compose`, `docker compose`, and `docker-compose`

## Prerequisites

- Linux shell (tested in Fedora Silverblue Toolbox)
- `git`
- either:
  - `podman` + `podman-compose` (recommended), or
  - `docker` + `docker compose` / `docker-compose`

Optional on Silverblue/Toolbox:

- `flatpak-spawn` (for host Podman access)

## 1. Initial Setup

```bash
cp .env.example .env
cp config.example/odoo.conf config/odoo.conf
```

If you need Odoo Mates addons in this workspace:

```bash
./scripts/prepare_odoomates_worktree.sh 19.0
```

## 2. Configuration Examples

### `.env` minimal local profile (no ISDS submit)

```dotenv
ODOO_MAJOR=19
POSTGRES_VERSION=16
ODOO_HTTP_PORT=8069

L10N_CZ_ISDS_ENABLED=false
```

### `.env` ISDS SOAP credential-check profile (test env)

```dotenv
ODOO_MAJOR=19
POSTGRES_VERSION=16
ODOO_HTTP_PORT=8069

L10N_CZ_ISDS_ENABLED=true
L10N_CZ_ISDS_MODE=soap_owner_info
L10N_CZ_ISDS_API_URL=https://ws1.czebox.cz/DS/DsManage
L10N_CZ_ISDS_USERNAME=YOUR_TEST_ISDS_USERNAME
L10N_CZ_ISDS_PASSWORD=YOUR_TEST_ISDS_PASSWORD
# optional metadata only (not serialized into SOAP CreateMessage envelope)
L10N_CZ_ISDS_SENDER_BOX_ID=YOUR_BOX_ID
L10N_CZ_ISDS_TARGET_BOX_ID=avbq58e
L10N_CZ_ISDS_TIMEOUT_SECONDS=20
```

### `.env` ISDS SOAP submit profile (CreateMessage, test env)

```dotenv
ODOO_MAJOR=19
POSTGRES_VERSION=16
ODOO_HTTP_PORT=8069

L10N_CZ_ISDS_ENABLED=true
L10N_CZ_ISDS_MODE=soap_create_message
# /DS/dz is the CreateMessage endpoint in test env
L10N_CZ_ISDS_API_URL=https://ws1.czebox.cz/DS/dz
L10N_CZ_ISDS_USERNAME=YOUR_TEST_ISDS_USERNAME
L10N_CZ_ISDS_PASSWORD=YOUR_TEST_ISDS_PASSWORD
L10N_CZ_ISDS_SENDER_BOX_ID=YOUR_BOX_ID
L10N_CZ_ISDS_TARGET_BOX_ID=avbq58e
L10N_CZ_ISDS_TIMEOUT_SECONDS=20
```

### `config/odoo.conf` production-oriented baseline

Use this as a starting point for real deployments:

```ini
[options]
addons_path = /mnt/odoomates-addons,/mnt/custom-addons
data_dir = /var/lib/odoo

# Required: set a strong random value
admin_passwd = REPLACE_WITH_STRONG_RANDOM_PASSWORD

db_host = db
db_user = odoo
db_password = REPLACE_DB_PASSWORD

# Local/first-run defaults
proxy_mode = True
list_db = True
log_level = info
```

Notes:

- `admin_passwd` is for database management operations (not normal user login).
- keep `.env` and `config/odoo.conf` private; do not commit real secrets.
- after initial setup, for locked-down production use `list_db = False` and explicit `dbfilter = ^your_db_name$`.

## 3. Start Containers

Podman:

```bash
podman compose -f podman-compose.yaml up -d
```

Legacy Podman Compose binary:

```bash
podman-compose -f podman-compose.yaml up -d
```

Docker:

```bash
docker compose -f podman-compose.yaml up -d
# or
docker-compose -f podman-compose.yaml up -d
```

After changing `.env`, recreate the web container so env vars are reloaded.

## 4. Open Odoo UI

- URL: `http://localhost:${ODOO_HTTP_PORT}` (default `http://localhost:8069`)
- first-time DB creation uses `admin_passwd` from `config/odoo.conf`
- install at least:
  - `l10n_cz_vat_filing`
  - `l10n_cz_vat_oss_bridge` (if OSS/IOSS filtering is needed)

## 5. Where To Click In UI

Main configuration path:

- `Settings -> Users & Companies -> Companies -> <Your Company> -> Czech VAT Filing`

Key UI elements on that tab:

- `Open Export Wizard` (create filing export ZIP/XML)
- `Open Export History` (stored exports + attachments + ISDS status)
- VAT Registry Shield settings
- VAT FX (CNB) settings
- Datová schránka (ISDS) settings

History submission path:

- open any `Czech VAT Filing Export History` record
- use `Submit via Datová schránka` action/button
- review fields:
  - `Datova Schranka Status`
  - `ISDS Message ID`
  - `ISDS Last Error`
  - `ISDS Response JSON`
  - optional `ISDS Delivery Receipt`

If ISDS values are in container env, sync them to the company record:

```bash
./scripts/odoo_apply_isds_env.sh odoo19_cz_test
```

## 6. Common CLI Flows

Seed representative CZ VAT cases:

```bash
./scripts/odoo_seed_cz_vat_cases.sh
```

Export XML filings:

```bash
./scripts/odoo_export_cz_vat_filings.sh 2026-03-01 2026-03-31 /tmp/cz-vat-filing
```

Open XML in EPO helper:

```bash
scripts/epo_open_form.sh /tmp/cz-vat-filing/dphdp3.xml
scripts/epo_open_form.sh /tmp/cz-vat-filing/dphkh1.xml
scripts/epo_open_form.sh /tmp/cz-vat-filing/dphshv.xml
```

Run addon tests:

```bash
flatpak-spawn --host podman exec -i odoo_web sh -lc \
  "odoo -d odoo19_cz_test -c /etc/odoo/odoo.conf --http-port=10069 --stop-after-init -u l10n_cz_vat_filing --test-enable --test-tags /l10n_cz_vat_filing"
```

## 7. Publish/Release

- release docs: `docs/release-publishing.md`
- upstream references: `docs/odoomates-upstream.md`
- tag workflow: `.github/workflows/main.yml`

Create addon release archives:

```bash
./scripts/release_pack_addons.sh v19.0.22.0.0
```

## 8. TODO

- [ ] Add optional UI action for one-time historical backfill of VAT filing regimes on posted moves
- [ ] Expand end-to-end reverse-charge (RPDP) scenarios and validation matrix
- [ ] Add stronger import-correction (`row 45`) scenarios covering customs revaluation variants
- [ ] Expand ISDS lifecycle support (delivery-state polling, message metadata retrieval, and retries)
- [ ] Add dedicated integration test harness for live-like ADIS/VIES/ARES responses (local mock server profile)
- [ ] Improve contributor guide with troubleshooting for Toolbox/Silverblue networking and container permissions

## 9. Appendix (Technical Scope)

Main module paths:

- `addons/custom/l10n_cz_vat_filing`
- `addons/custom/l10n_cz_vat_oss_bridge`
- `addons/custom/odoo19_report_compat`

Current filing scope (microSME-focused):

- KH sections `A1`, `A2`, `A4`, `A5`, `B1`, `B2`, `B3`
- DUZP-based period selection
- automatic `KH` threshold routing (`10 000 CZK`) including refund logic
- import/reverse-charge hardening (`KH` exclusion where legally required)
- DPH rows including derived `46`, `52`, year-end `53`, plus explicit `45`, `48`, `60`
- optional CZ VAT Registry Shield
- optional CZ VAT FX (ČNB) decoupling

Deep addon behavior and field-level mapping:

- `addons/custom/l10n_cz_vat_filing/README.md`

## License

- this repository custom code is under `MIT` (`LICENSE`)
- MIT includes explicit `AS IS` / no-warranty terms
- third-party addons (for example `addons/odoomates*`) remain under upstream licenses
