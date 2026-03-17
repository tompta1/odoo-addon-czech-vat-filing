# Czech VAT Filing — Odoo 19 Community Addons

Three Odoo 19 CE addons for Czech VAT compliance: XML filing export, OSS/IOSS exclusion, and report compatibility fixes.

## Addons

### `l10n_cz_vat_filing`

Full Czech VAT filing export for Odoo 19 CE.  Generates `DPHDP3`, `DPHKH1`, and `DPHSHV` XML files validated against the official MF XSD schemas, with a wizard UI, persistent export history, and optional ISDS (Datová schránka) submission.

**Requires:** `account`, `l10n_cz`

Key features:

- **DPH / KH / SHV export** — covers all stock `l10n_cz` VAT tag families including domestic sales/purchases, reverse charge (A1/B1), EU acquisitions (A2), import rows (VAT 7/8/42), bad-debt corrections (VAT 33/34), triangular trade (VAT 30/31), asset acquisition (VAT 47), coefficient rows (VAT 50/51), and souhrnné hlášení EU supplies
- **DUZP-based period selection** — period inclusion by Czech tax date with fallback `CZ DPH Tax Date → invoice_date → date`
- **KH threshold routing** — automatic `A4/A5` and `B2/B3` routing at 10 000 CZK, evaluated in CZK (including foreign-currency invoices)
- **Derived DPH rows** — auto-derives rows 46, 52, and year-end 53 (settlement coefficient wizard for December / Q4)
- **XSD pre-flight validation** — validates generated XML against bundled MF schemas before download
- **Export wizard** — `Settings → Companies → [Company] → Czech VAT Filing → Open Export Wizard`
- **Export history** — persistent `l10n_cz.vat.filing.history` records with attached XML/ZIP, ISDS status, and EPO status polling
- **VAT Registry Shield** — optional ADIS SOAP (`getStatusNespolehlivySubjektRozsireny`) checks for supplier reliability and published bank accounts; blocks vendor bill posting and/or supplier payment validation
- **Batch Payment Shield** — soft-dependency hook into `account.batch.payment.validate()` (Enterprise only; silently skipped on CE)
- **ČNB FX decoupling** — resolves DUZP-based exchange rates from the official ČNB `denni_kurz.txt` feed; weekend/holiday fallback per § 38 Czech VAT Act (up to 5 preceding working days); rate date stored separately from DUZP
- **ISDS submission** — four modes: `mock`, `http_json` bridge, `soap_owner_info` (credential check), `soap_create_message` (direct submit); security warning banner prevents accidental inbox polling
- **EPO status polling** — manual button + optional cron polling ADIS EPO `ZjistiStatus` endpoint (never calls `GetListOfReceivedMessages`)
- **post_init_hook** — prefills ADIS VAT registry URL and ČNB FX URL on install

---

### `l10n_cz_vat_oss_bridge`

Thin bridge that connects Odoo's `l10n_eu_oss` VAT regime markers to the Czech filing exclusion logic in `l10n_cz_vat_filing`.  Moves tagged `OSS` or `IOSS` are excluded from `DPHDP3`, `DPHKH1`, and `DPHSHV` exports.  Resets the regime field when OSS/IOSS tax tags are removed.

**Requires:** `l10n_cz_vat_filing`

---

### `odoo19_report_compat`

Small set of Odoo 19 CE compatibility fixes for built-in reports: payslip refund multi-record action, contribution-register report guard against empty selection, and analytic distribution rendering in journal entries.

**Requires:** `account`, `hr_payroll` (optional)

---

## Installation

Copy (or symlink) the addon directories into your Odoo `addons_path` and install via **Settings → Apps**:

```
addons/l10n_cz_vat_filing
addons/l10n_cz_vat_oss_bridge   (optional)
addons/odoo19_report_compat     (optional)
```

Minimum `odoo.conf`:

```ini
[options]
addons_path = /path/to/odoo/addons,/path/to/this/repo/addons
```

## Configuration

All settings live under **Settings → Companies → [Your Company] → Czech VAT Filing**.

### VAT Registry Shield

| Field | Default | Notes |
|---|---|---|
| Enable CZ VAT Registry Shield | off | Enables ADIS lookup on posting/payment |
| CZ VAT Registry API URL | `https://adisrws.mfcr.cz/…rozhraniCRPDPHSOAP` | Pre-filled on install |
| Block Vendor Bills On Registry Risk | off | Blocks posting if supplier is unreliable |
| Block Supplier Payments On Registry Risk | off | Blocks payment validation |
| Block Unpublished Supplier Bank Accounts | off | Requires a published account match |

### ČNB FX Decoupling

| Field | Default | Notes |
|---|---|---|
| Enable CZ VAT FX Decoupling | off | Uses ČNB rate for VAT amounts instead of accounting rate |
| CZ VAT FX API URL | `https://www.cnb.cz/…denni_kurz.txt` | Pre-filled on install |
| Block On VAT FX Lookup Errors | off | Blocks invoice posting when rate fetch fails |

Weekend / holiday behaviour: if ČNB has no rate for the DUZP date (weekend or public holiday), the addon retries the 5 preceding calendar days.  The actual rate date is stored separately on `l10n_cz.vat.fx.rate.rate_date`.

### ISDS (Datová schránka)

| Field | Default | Notes |
|---|---|---|
| Enable Datova Schranka Submission | off | Shows submission actions on history records |
| ISDS Submission Mode | `mock` | `mock` / `http_json` / `soap_owner_info` / `soap_create_message` |
| ISDS Endpoint URL | — | e.g. `https://ws1.czebox.cz/DS/dz` for test `CreateMessage` |
| ISDS Username / Password | — | Stored in `groups="base.group_system"` |

> **Security note:** ISDS credentials are _Pověřená osoba_ credentials only.  The addon never calls `GetListOfReceivedMessages` or any inbox API.

### EPO Status Polling

Enable `l10n_cz_isds_epo_poll_enabled` on the company to activate the "Check EPO Status" button on filing history records.  An opt-in cron (`CZ VAT — Poll EPO Status`, inactive by default) can be enabled for automatic polling.

## Running the Test Suite

```bash
odoo -d <test_db> \
     -c /etc/odoo/odoo.conf \
     --test-enable \
     --test-tags=l10n_cz_vat_filing \
     -u l10n_cz_vat_filing \
     --http-port=8099 \
     --stop-after-init
```

Expected: **0 failures, 0 errors** across 72 tests.

## Releases

Release ZIPs (one per addon) are published as GitHub Release assets on every `v*` tag.  Each release includes a `SHA256SUMS.txt`.

To build locally:

```bash
./scripts/release_pack_addons.sh v19.0.24.0.0
```

## Changelog

See [CHANGELOG.md](CHANGELOG.md).

## License

Custom addon code: **MIT** — see [LICENSE](LICENSE).  
Third-party addons (e.g. Odoo Mates) retain their own upstream licenses.
