# `l10n_cz_vat_filing` — Czech VAT Filing for Odoo 19 CE

Generates `DPHDP3`, `DPHKH1`, and `DPHSHV` XML files validated against the official MF XSD schemas.

## Dependencies

`account`, `l10n_cz`

Soft optional: `account_batch_payment` (Enterprise — Batch Payment Shield only)

## Export Scope

### KH (Kontrolní hlášení — DPHKH1)

| Section | Tags / Condition |
|---|---|
| A1 | Domestic reverse-charge sales (`VAT 25`) |
| A2 | EU acquisitions / vendor-side RC purchases (`VAT 3/4/5/6`) |
| A4 | Domestic B2B sales ≥ 10 000 CZK |
| A5 | Domestic B2B sales < 10 000 CZK (aggregate) |
| B1 | Domestic RC purchases (`VAT 3/4/5/6`) |
| B2 | Domestic purchases from CZ VAT payers ≥ 10 000 CZK |
| B3 | Domestic purchases < 10 000 CZK (aggregate) |

KH threshold is evaluated in CZK (including foreign-currency invoices).  
B2B refunds under 10 000 CZK are routed to B2 only when linked to an over-threshold origin invoice.

### DPH (Daňové přiznání — DPHDP3)

All stock `l10n_cz` tag families: VAT 1–13, 20–26, 30–34, 40–42, 45, 47, 50–51, 61.  
Auto-derived rows 46, 52, and year-end 53.  
Explicit move fields for rows 45, 48, 60.

### SHV (Souhrnné hlášení — DPHSHV)

EU goods/services supplies and triangular trade (`VAT 30/31`).

## Period Inclusion

Documents are selected by Czech tax date with fallback order:

```
CZ DPH Tax Date (l10n_cz_dph_tax_date) → invoice_date → date
```

## `l10n_cz_vat_filing_exports()` API

```python
exports = env.company.l10n_cz_vat_filing_exports(
    "2026-03-01",
    "2026-03-31",
    options={
        # Filing header
        "submission_date": "2026-04-20",   # d_poddp
        "dph_form": "B",                    # B = řádné, D/E = dodatečné
        "kh_form":  "B",
        "sh_form":  "R",

        # Form selection (default True)
        "include_dphdp3": True,
        "include_dphkh1": True,
        "include_dphshv": True,

        # Manual DPH row overrides
        "line_52a_coefficient": 70,
        "line_60_adjustment": 1000,
    },
)
print(exports["dphdp3_xml"])
print(exports["dphkh1_xml"])
print(exports["dphshv_xml"])
```

### Options Reference

| Option | XML field | Notes |
|---|---|---|
| `submission_date` | `d_poddp` | Date of filing submission |
| `tax_statement_date` | `d_zjist` | Required for dodatečné/opravné forms |
| `dph_form` | `dapdph_forma` | `B` regular, `D`/`E` addl., `A` corrective |
| `kh_form` | `khdph_forma` | `B` regular, `N`/`E` subsequent/corrective |
| `sh_form` | `shvies_forma` | `R` regular, `O` corrective |
| `kh_challenge_reference` | `c_jed_vyzvy` | For KH challenge responses |
| `kh_challenge_response` | `vyzva_odp` | `A`/`N` |
| `period_from` / `period_to` | `zdobd_od`/`zdobd_do` | Partial-period override |
| `include_dphdp3/dphkh1/dphshv` | — | Form selection flags |
| `line_45_full_deduction` | ř. 45 | |
| `line_45_reduced_deduction` | ř. 45 | |
| `line_48_base_amount` | ř. 48 | |
| `line_48_full_deduction` | ř. 48 | |
| `line_48_reduced_deduction` | ř. 48 | |
| `line_52a_coefficient` | ř. 52a | |
| `line_52b_deduction` | ř. 52b | |
| `line_53a_settlement_coefficient` | ř. 53a | December/Q4 only |
| `line_53b_change_deduction` | ř. 53b | |
| `line_60_adjustment` | ř. 60 | |

## Fields on `account.move`

| Field | Technical name |
|---|---|
| CZ VAT Filing Regime | `l10n_cz_vat_regime` |
| CZ DPH Tax Date (DUZP) | `l10n_cz_dph_tax_date` |
| CZ KH Document Reference | `l10n_cz_kh_document_reference` |
| CZ KH Tax Point Date | `l10n_cz_kh_tax_point_date` |
| CZ KH Deduction Date | `l10n_cz_kh_deduction_date` |
| CZ KH Reverse Charge Code | `l10n_cz_kh_reverse_charge_code` |
| CZ KH Proportional Deduction | `l10n_cz_kh_proportional_deduction` |
| CZ Customs MRN | `l10n_cz_customs_mrn` |
| CZ Customs Decision Number | `l10n_cz_customs_decision_number` |
| CZ Customs Release Date | `l10n_cz_customs_release_date` |
| CZ Customs Office | `l10n_cz_customs_office` |
| CZ Customs Value | `l10n_cz_customs_value` |
| CZ Import VAT Amount | `l10n_cz_import_vat_amount` |
| CZ Import Correction Origin | `l10n_cz_import_correction_origin_id` |
| CZ VAT FX Manual Rate | `l10n_cz_vat_fx_manual_rate` |
| CZ VAT FX Applied Rate | `l10n_cz_vat_fx_rate` |
| CZ VAT FX Source | `l10n_cz_vat_fx_rate_source` |
| CZ DPH Line 45 Full/Reduced | `l10n_cz_dph_line_45_*` |
| CZ DPH Line 48 Base/Full/Reduced | `l10n_cz_dph_line_48_*` |
| CZ DPH Line 60 Adjustment | `l10n_cz_dph_line_60_adjustment` |

Line-level field on `account.move.line`:

| Field | Technical name |
|---|---|
| CZ KH Subject Code | `l10n_cz_kh_subject_code` |

## Fields on `res.company`

### Coefficient

| Field | Technical name |
|---|---|
| Use Manual CZ DPH Advance Coefficient | `l10n_cz_dph_use_manual_advance_coefficient` |
| CZ DPH Advance Coefficient | `l10n_cz_dph_advance_coefficient` |

### VAT Registry Shield

| Field | Technical name |
|---|---|
| Enable CZ VAT Registry Shield | `l10n_cz_vat_registry_enabled` |
| CZ VAT Registry API URL | `l10n_cz_vat_registry_api_url` |
| CZ VAT Registry Timeout (s) | `l10n_cz_vat_registry_timeout_seconds` |
| CZ VAT Registry Cache (h) | `l10n_cz_vat_registry_cache_hours` |
| Block Vendor Bills On Registry Risk | `l10n_cz_vat_registry_block_on_post` |
| Block Supplier Payments On Registry Risk | `l10n_cz_vat_registry_block_on_payment` |
| Block Unreliable VAT Payers | `l10n_cz_vat_registry_block_unreliable` |
| Block Unpublished Supplier Bank Accounts | `l10n_cz_vat_registry_block_unpublished_bank` |
| Block On VAT Registry Lookup Errors | `l10n_cz_vat_registry_block_on_error` |

The shield fetcher posts to the ADIS SOAP endpoint (`getStatusNespolehlivySubjektRozsireny`) and also understands VIES-style JSON (`isValid` / `valid`, `userError`).

### ČNB FX Decoupling

| Field | Technical name |
|---|---|
| Enable CZ VAT FX Decoupling | `l10n_cz_vat_fx_enforce_cnb` |
| CZ VAT FX API URL | `l10n_cz_vat_fx_api_url` |
| CZ VAT FX Currency Parameter | `l10n_cz_vat_fx_currency_param` |
| CZ VAT FX Date Parameter | `l10n_cz_vat_fx_date_param` |
| CZ VAT FX Timeout (s) | `l10n_cz_vat_fx_timeout_seconds` |
| CZ VAT FX Cache (days) | `l10n_cz_vat_fx_cache_days` |
| Block On VAT FX Lookup Errors | `l10n_cz_vat_fx_block_on_lookup_error` |

Weekend/holiday fallback: per § 38 Czech VAT Act, if no ČNB rate is published for the DUZP (weekend or public holiday), the addon retries up to 5 preceding calendar days.  Hard network errors (connection refused, timeout) abort the retry immediately.  The actual rate date is stored in `l10n_cz.vat.fx.rate.rate_date` separately from `tax_date`.

### ISDS (Datová schránka)

| Field | Technical name |
|---|---|
| Enable Datova Schranka Submission | `l10n_cz_isds_enabled` |
| ISDS Submission Mode | `l10n_cz_isds_mode` |
| ISDS Endpoint URL | `l10n_cz_isds_api_url` |
| ISDS Username | `l10n_cz_isds_username` |
| ISDS Password | `l10n_cz_isds_password` |
| ISDS Sender Databox ID | `l10n_cz_isds_sender_box_id` |
| ISDS Target Databox ID | `l10n_cz_isds_target_box_id` |
| ISDS Timeout (s) | `l10n_cz_isds_timeout_seconds` |
| Enable EPO Status Polling | `l10n_cz_isds_epo_poll_enabled` |
| ADIS EPO Endpoint URL | `l10n_cz_isds_adis_epo_url` |

#### ISDS modes

| Mode | Behaviour |
|---|---|
| `mock` | Stores a deterministic local receipt; no external call |
| `http_json` | POSTs filing payload to a JSON bridge service |
| `soap_owner_info` | Calls `GetOwnerInfoFromLogin` to validate credentials (no filing) |
| `soap_create_message` | Calls `CreateMessage` to submit filing XML attachments directly |

HTTP JSON bridge response contract: `status`/`result`/`success` for success indicator, `message_id` for ISDS message ID, optional `delivery_receipt_base64` for receipt attachment.

> **Security:** The addon never calls `GetListOfReceivedMessages` or any inbox API.  ISDS credentials are for _Pověřená osoba_ (authorised person) use only.

#### EPO Status Polling

Manual "Check EPO Status" button on filing history records (visible when status is `submitted` or `error`).  Calls `ZjistiStatus` on the ADIS EPO SOAP endpoint.  An opt-in cron (`CZ VAT — Poll EPO Status`, inactive by default) is available for automatic polling.

## Validation Constraints

- Quarterly KH is blocked for Czech legal entities — set `include_dphkh1=False` for quarterly DPH runs
- Quarterly SHV is blocked when the quarter contains goods or triangular-trade rows
- Dodatečné DPH forms `D`/`E` require `tax_statement_date`
- Následné/opravné KH forms `N`/`E` require `tax_statement_date` or `kh_challenge_reference`
- Temporary RPDP subject codes `11`/`14` hard-fail below 100 000 CZK taxable base
- 3rd-country import moves must carry customs evidence (MRN or customs decision + release date)
- VAT 45 correction documents must be purchase-side and linked to an original 3rd-country import move
- Documents mixing import tags with KH-driving tags fail validation
- OSS/IOSS moves are excluded from all three Czech XML exports; if they still carry Czech filing tags, the export fails

## Known Scope Limits

- Not a complete legal filing engine for every Czech VAT scenario
- Does not provide a qualified signing certificate
- OSS/IOSS support is an exclusion path only — not a full `l10n_eu_oss` integration
