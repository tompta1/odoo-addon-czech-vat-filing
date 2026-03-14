#!/usr/bin/env bash

set -euo pipefail

db_name="${1:-odoo19_cz_test}"
podman_cmd="/var/home/tom/Documents/Projects/odoo-podman-codex/scripts/host-podman.sh"
odoo_conf="${ODOO_CONF:-/etc/odoo/odoo.conf}"

${podman_cmd} exec -i odoo_web sh -lc "odoo shell -d '${db_name}' -c '${odoo_conf}' --no-http --log-level=error <<'PY'
company = env.company

Account = env['account.account']
Country = env['res.country']
Journal = env['account.journal']
Move = env['account.move']
Partner = env['res.partner']
Tax = env['account.tax']
Tag = env['account.account.tag']


def find_account(account_types):
    account = Account.search([
        ('account_type', 'in', account_types),
    ], limit=1, order='id')
    if not account:
        raise RuntimeError(f'Missing account for {account_types!r}')
    return account


def find_tax(type_tax_use, required_tags):
    required = set(required_tags)
    for tax in Tax.search([('type_tax_use', '=', type_tax_use)]):
        tags = {
            tag.name
            for rep in tax.invoice_repartition_line_ids
            for tag in rep.tag_ids
        }
        if required.issubset(tags):
            return tax
    raise RuntimeError(f'Missing {type_tax_use} tax with tags {sorted(required)!r}')


def find_country(code):
    country = Country.search([('code', '=', code)], limit=1)
    if not country:
        raise RuntimeError(f'Missing country {code}')
    return country


def ensure_partner(name, vat, country_code, company_type='company'):
    search_domain = [('vat', '=', vat)] if vat else [('name', '=', name), ('country_id', '=', find_country(country_code).id)]
    partner = Partner.search(search_domain, limit=1)
    if not partner:
        partner = Partner.with_context(no_vat_validation=True).create({
            'name': name,
            'vat': vat,
            'country_id': find_country(country_code).id,
            'company_type': company_type,
            'street': 'Testovaci 1',
            'city': 'Praha',
            'zip': '11000',
        })
    return partner


def ensure_tag(name):
    tag = Tag.search([('name', '=', name)], limit=1)
    if tag:
        return tag
    if name in {
        'VAT 40 Coefficient',
        'VAT 41 Coefficient',
        'VAT 42 Coefficient',
        'VAT 45 Full',
        'VAT 45 Reduced',
    }:
        return Tag.create({
            'name': name,
            'applicability': 'taxes',
            'country_id': find_country('CZ').id,
        })
    raise RuntimeError(f'Missing tag {name!r}')


def tag_id(name):
    return ensure_tag(name).id


def ensure_tax_copy(source_tax, new_name, base_tags=None, invoice_tax_tags=None, refund_tax_tags=None):
    tax = Tax.search([('name', '=', new_name), ('type_tax_use', '=', source_tax.type_tax_use)], limit=1)
    if not tax:
        tax = source_tax.copy({
            'name': new_name,
            'description': new_name,
            'invoice_label': new_name,
        })

    if base_tags is not None:
        target_ids = [tag_id(name) for name in base_tags]
        for line in tax.invoice_repartition_line_ids.filtered(lambda l: l.repartition_type == 'base'):
            line.tag_ids = [(6, 0, target_ids)]
        for line in tax.refund_repartition_line_ids.filtered(lambda l: l.repartition_type == 'base'):
            line.tag_ids = [(6, 0, target_ids)]

    if invoice_tax_tags is not None:
        target_ids = [tag_id(name) for name in invoice_tax_tags]
        for line in tax.invoice_repartition_line_ids.filtered(lambda l: l.repartition_type == 'tax' and l.tag_ids):
            line.tag_ids = [(6, 0, target_ids)]

    if refund_tax_tags is not None:
        target_ids = [tag_id(name) for name in refund_tax_tags]
        for line in tax.refund_repartition_line_ids.filtered(lambda l: l.repartition_type == 'tax' and l.tag_ids):
            line.tag_ids = [(6, 0, target_ids)]

    return tax


def ensure_move(marker, move_type, partner, account, tax, amount, invoice_date, **extra):
    existing_moves = Move.search(['|', ('invoice_origin', '=', marker), ('ref', '=', marker)])
    if existing_moves:
        for existing_move in existing_moves:
            if existing_move.state == 'posted':
                existing_move.button_draft()
            existing_move.with_context(force_delete=True).unlink()

    journal_type = 'sale' if move_type in {'out_invoice', 'out_refund'} else 'purchase'
    journal = Journal.search([('type', '=', journal_type)], limit=1)
    if not journal:
        raise RuntimeError(f'Missing {journal_type} journal')

    line_extra = dict(extra.pop('line_extra', {}))
    line_vals = {
        'name': marker,
        'quantity': 1,
        'price_unit': amount,
        'account_id': account.id,
        'tax_ids': [(6, 0, [tax.id])] if tax else [],
    }
    line_vals.update(line_extra)

    vals = {
        'move_type': move_type,
        'partner_id': partner.id,
        'journal_id': journal.id,
        'invoice_date': invoice_date,
        'date': invoice_date,
        'invoice_line_ids': [(0, 0, line_vals)],
        **extra,
    }
    if move_type in {'out_invoice', 'out_refund'}:
        vals['invoice_origin'] = marker
    else:
        vals['ref'] = marker

    move = Move.create(vals)
    move.action_post()
    print(marker, move.id, move.name or '', move.ref or '')
    return move


sale_account = find_account(['income', 'income_other'])
purchase_account = find_account(['expense', 'expense_direct_cost', 'expense_depreciation'])

tax_sale_rc = find_tax('sale', ['VAT 25'])
tax_purchase_a2 = find_tax('purchase', ['VAT 3 Base', 'VAT 3 Tax'])
tax_purchase_b1 = find_tax('purchase', ['VAT 10 Base', 'VAT 10 Tax'])
tax_purchase_import = find_tax('purchase', ['VAT 7 Base', 'VAT 7 Tax'])
tax_purchase_import_exempt = find_tax('purchase', ['VAT 32'])
tax_purchase_vat12 = find_tax('purchase', ['VAT 12 Base', 'VAT 12 Tax'])
tax_purchase_vat13 = find_tax('purchase', ['VAT 13 Base', 'VAT 13 Tax'])
tax_purchase_vat9 = find_tax('purchase', ['VAT 9 Base', 'VAT 9 Tax'])
tax_sale_domestic = find_tax('sale', ['VAT 1 Base', 'VAT 1 Tax'])
tax_sale_ioss_placeholder = ensure_tax_copy(
    tax_sale_domestic,
    '21% IOSS Placeholder',
    base_tags=[],
    invoice_tax_tags=[],
    refund_tax_tags=[],
)
tax_purchase_domestic = find_tax('purchase', ['VAT 40 Base', 'VAT 40 Total'])
tax_sale_eu = find_tax('sale', ['VAT 20'])
try:
    tax_purchase_customs = find_tax('purchase', ['VAT 42 Base', 'VAT 42 Total'])
except RuntimeError:
    tax_purchase_customs = ensure_tax_copy(
        tax_purchase_domestic,
        '21% Customs Deduction',
        base_tags=['VAT 42 Base'],
        invoice_tax_tags=['VAT 42 Total'],
        refund_tax_tags=['VAT 42 Total'],
    )
tax_purchase_triangular = ensure_tax_copy(
    tax_purchase_import_exempt,
    '0% TRI Purchase',
    base_tags=['VAT 30'],
    invoice_tax_tags=[],
    refund_tax_tags=[],
)
tax_purchase_import_correction_full = ensure_tax_copy(
    tax_purchase_import,
    '21% Import Correction Full',
    base_tags=['VAT 7 Base'],
    invoice_tax_tags=['VAT 7 Tax', 'VAT 45 Full'],
    refund_tax_tags=['VAT 7 Tax', 'VAT 45 Full'],
)
tax_sale_triangular = ensure_tax_copy(
    tax_sale_eu,
    '0% TRI Sale',
    base_tags=['VAT 31'],
    invoice_tax_tags=[],
    refund_tax_tags=[],
)
tax_sale_bad_debt = ensure_tax_copy(
    tax_sale_domestic,
    '21% BD Creditor',
    base_tags=['VAT 1 Base'],
    invoice_tax_tags=['VAT 1 Tax', 'VAT 33'],
    refund_tax_tags=['VAT 1 Tax', 'VAT 33'],
)
tax_purchase_bad_debt = ensure_tax_copy(
    tax_purchase_domestic,
    '21% BD Debtor',
    base_tags=['VAT 40 Base'],
    invoice_tax_tags=['VAT 40 Total', 'VAT 34'],
    refund_tax_tags=['VAT 40 Total', 'VAT 34'],
)
tax_purchase_asset = ensure_tax_copy(
    tax_purchase_domestic,
    '21% Asset Deduction',
    base_tags=['VAT 47 Base'],
    invoice_tax_tags=['VAT 47 Total'],
    refund_tax_tags=['VAT 47 Total'],
)
tax_purchase_domestic_coefficient = ensure_tax_copy(
    tax_purchase_domestic,
    '21% Domestic Purchase Coefficient',
    base_tags=['VAT 40 Base'],
    invoice_tax_tags=['VAT 40 Total', 'VAT 40 Coefficient'],
    refund_tax_tags=['VAT 40 Total', 'VAT 40 Coefficient'],
)
tax_sale_vat50 = ensure_tax_copy(
    tax_sale_eu,
    '0% Exempt No Deduction',
    base_tags=['VAT 50'],
    invoice_tax_tags=[],
    refund_tax_tags=[],
)
tax_sale_vat51_with = ensure_tax_copy(
    tax_sale_eu,
    '0% Excluded With Deduction',
    base_tags=['VAT 51 with deduction'],
    invoice_tax_tags=[],
    refund_tax_tags=[],
)
tax_sale_vat51_without = ensure_tax_copy(
    tax_sale_eu,
    '0% Excluded Without Deduction',
    base_tags=['VAT 51 without deduction'],
    invoice_tax_tags=[],
    refund_tax_tags=[],
)
tax_sale_vat61 = ensure_tax_copy(
    tax_sale_domestic,
    '21% Tax Refund Section 84',
    base_tags=[],
    invoice_tax_tags=['VAT 61'],
    refund_tax_tags=['VAT 61'],
)
tax_sale_vat23 = ensure_tax_copy(
    tax_sale_eu,
    '0% New Means Of Transport',
    base_tags=['VAT 23'],
    invoice_tax_tags=[],
    refund_tax_tags=[],
)
tax_sale_vat24 = ensure_tax_copy(
    tax_sale_eu,
    '0% Selected Transactions',
    base_tags=['VAT 24'],
    invoice_tax_tags=[],
    refund_tax_tags=[],
)

partner_cz_customer = ensure_partner('CZ RC Customer a.s.', 'CZ87654323', 'CZ')
partner_cz_supplier = ensure_partner('CZ RC Supplier s.r.o.', 'CZ87654324', 'CZ')
partner_cz_private = ensure_partner('CZ Private Buyer', '', 'CZ', company_type='person')
partner_sk_supplier = ensure_partner('SK EU Supplier s.r.o.', 'SK1234567891', 'SK')
partner_de_supplier = ensure_partner('DE Import Supplier GmbH', 'DE123456789', 'DE')
partner_pl_customer = ensure_partner('PL Triangle Buyer sp. z o.o.', 'PL1234567890', 'PL')
partner_us_supplier = ensure_partner('US Import Supplier Inc.', 'US123456789', 'US')
partner_de_private = ensure_partner('DE Private Buyer', '', 'DE', company_type='person')
partner_at_private = ensure_partner('AT Selected Supply Buyer', '', 'AT', company_type='person')

company.write({
    'l10n_cz_dph_use_manual_advance_coefficient': False,
    'l10n_cz_dph_advance_coefficient': 0.0,
})

ensure_move(
    'COEF2025-TAXABLE-TEST',
    'out_invoice',
    partner_cz_customer,
    sale_account,
    tax_sale_domestic,
    8000,
    '2025-11-15',
    l10n_cz_kh_document_reference='COEF2025-TAXABLE-TEST',
)
ensure_move(
    'COEF2025-EXEMPT-TEST',
    'out_invoice',
    partner_cz_customer,
    sale_account,
    tax_sale_vat50,
    2000,
    '2025-11-16',
    l10n_cz_kh_document_reference='COEF2025-EXEMPT-TEST',
)

ensure_move(
    'A1-RC-TEST',
    'out_invoice',
    partner_cz_customer,
    sale_account,
    tax_sale_rc,
    15000,
    '2026-03-10',
    l10n_cz_kh_document_reference='A1-RC-TEST',
    l10n_cz_kh_tax_point_date='2026-03-10',
    l10n_cz_kh_reverse_charge_code='4',
    line_extra={'l10n_cz_kh_subject_code': '4'},
)
ensure_move(
    'A2-EU-TEST',
    'in_invoice',
    partner_sk_supplier,
    purchase_account,
    tax_purchase_a2,
    20000,
    '2026-04-05',
    date='2026-04-05',
    l10n_cz_dph_tax_date='2026-03-11',
    l10n_cz_kh_document_reference='A2-EU-TEST',
    l10n_cz_kh_tax_point_date='2026-03-11',
)
ensure_move(
    'B1-RC-TEST',
    'in_invoice',
    partner_cz_supplier,
    purchase_account,
    tax_purchase_b1,
    18000,
    '2026-03-12',
    l10n_cz_kh_document_reference='B1-RC-TEST',
    l10n_cz_kh_tax_point_date='2026-03-12',
    l10n_cz_kh_deduction_date='2026-03-20',
    l10n_cz_kh_reverse_charge_code='4',
    line_extra={'l10n_cz_kh_subject_code': '4'},
)
ensure_move(
    'DPH7-IMPORT-TEST',
    'in_invoice',
    partner_de_supplier,
    purchase_account,
    tax_purchase_import,
    14000,
    '2026-03-13',
    l10n_cz_vat_regime='third_country_import',
    l10n_cz_customs_mrn='26CZMRN0000001',
    l10n_cz_customs_release_date='2026-03-13',
    l10n_cz_customs_office='Celni urad Praha Ruzyne',
    l10n_cz_customs_value_amount=14000,
    l10n_cz_customs_vat_amount=2940,
    l10n_cz_customs_note='Seed import invoice matched to customs evidence for DPH row 7.',
    l10n_cz_kh_document_reference='DPH7-IMPORT-TEST',
    l10n_cz_kh_tax_point_date='2026-03-13',
)
import_correction_origin = ensure_move(
    'DPH45-CORR-ORIG',
    'in_invoice',
    partner_de_supplier,
    purchase_account,
    tax_purchase_import,
    5000,
    '2026-03-14',
    l10n_cz_vat_regime='third_country_import',
    l10n_cz_customs_mrn='26CZMRN0000045',
    l10n_cz_customs_release_date='2026-03-14',
    l10n_cz_customs_office='Celni urad Praha Ruzyne',
    l10n_cz_customs_value_amount=5000,
    l10n_cz_customs_vat_amount=1050,
    l10n_cz_customs_note='Original import bill for row-45 correction linkage test.',
    l10n_cz_kh_document_reference='DPH45-CORR-ORIG',
    l10n_cz_kh_tax_point_date='2026-03-14',
)
ensure_move(
    'DPH45-CORR-REFUND',
    'in_refund',
    partner_de_supplier,
    purchase_account,
    tax_purchase_import_correction_full,
    1200,
    '2026-03-26',
    l10n_cz_vat_regime='third_country_import',
    l10n_cz_import_correction_origin_id=import_correction_origin.id,
    l10n_cz_import_correction_reason='Customs value revision under section 42/74 flow.',
    l10n_cz_kh_document_reference='DPH45-CORR-REFUND',
    l10n_cz_kh_tax_point_date='2026-03-26',
)
ensure_move(
    'VAT42-PROP-TEST',
    'in_invoice',
    partner_us_supplier,
    purchase_account,
    tax_purchase_customs,
    2500,
    '2026-03-14',
    l10n_cz_vat_regime='third_country_import',
    l10n_cz_customs_decision_number='JSD-2026-0001',
    l10n_cz_customs_release_date='2026-03-14',
    l10n_cz_customs_office='Celni urad Praha 1',
    l10n_cz_customs_value_amount=2500,
    l10n_cz_customs_vat_amount=525,
    l10n_cz_customs_note='Seed customs deduction document for DPH row 43/42 proportional case.',
    l10n_cz_kh_document_reference='VAT42-PROP-TEST',
    l10n_cz_kh_proportional_deduction=True,
)
ensure_move(
    'A2-VAT12-TEST',
    'in_refund',
    partner_de_supplier,
    purchase_account,
    tax_purchase_vat12,
    3000,
    '2026-03-15',
    l10n_cz_kh_document_reference='A2-VAT12-TEST',
    l10n_cz_kh_tax_point_date='2026-03-15',
)
ensure_move(
    'A2-VAT13-TEST',
    'in_refund',
    partner_de_supplier,
    purchase_account,
    tax_purchase_vat13,
    2000,
    '2026-03-16',
    l10n_cz_kh_document_reference='A2-VAT13-TEST',
    l10n_cz_kh_tax_point_date='2026-03-16',
)
ensure_move(
    'A2-VAT9-TEST',
    'in_invoice',
    partner_de_supplier,
    purchase_account,
    tax_purchase_vat9,
    7000,
    '2026-03-17',
    l10n_cz_kh_document_reference='A2-VAT9-TEST',
    l10n_cz_kh_tax_point_date='2026-03-17',
)
ensure_move(
    'VAT30-TRI-TEST',
    'in_invoice',
    partner_sk_supplier,
    purchase_account,
    tax_purchase_triangular,
    9000,
    '2026-03-18',
    l10n_cz_kh_document_reference='VAT30-TRI-TEST',
)
ensure_move(
    'VAT31-TRI-TEST',
    'out_invoice',
    partner_pl_customer,
    sale_account,
    tax_sale_triangular,
    11000,
    '2026-03-19',
    l10n_cz_kh_document_reference='VAT31-TRI-TEST',
)
ensure_move(
    'VAT32-IMPORT-EXEMPT-TEST',
    'in_invoice',
    partner_us_supplier,
    purchase_account,
    tax_purchase_import_exempt,
    6000,
    '2026-03-20',
    l10n_cz_kh_document_reference='VAT32-IMPORT-EXEMPT-TEST',
)
ensure_move(
    'VAT33-BD-TEST',
    'out_invoice',
    partner_cz_customer,
    sale_account,
    tax_sale_bad_debt,
    5000,
    '2026-03-21',
    l10n_cz_kh_document_reference='VAT33-BD-TEST',
    l10n_cz_kh_tax_point_date='2026-03-21',
)
ensure_move(
    'VAT33-BD-REVERSAL-TEST',
    'out_refund',
    partner_cz_customer,
    sale_account,
    tax_sale_bad_debt,
    1500,
    '2026-03-24',
    l10n_cz_kh_document_reference='VAT33-BD-REVERSAL-TEST',
    l10n_cz_kh_tax_point_date='2026-03-24',
)
ensure_move(
    'VAT34-BD-TEST',
    'in_refund',
    partner_cz_supplier,
    purchase_account,
    tax_purchase_bad_debt,
    4000,
    '2026-03-22',
    l10n_cz_kh_document_reference='VAT34-BD-TEST',
    l10n_cz_kh_tax_point_date='2026-03-22',
)
ensure_move(
    'VAT34-BD-REVERSAL-TEST',
    'in_invoice',
    partner_cz_supplier,
    purchase_account,
    tax_purchase_bad_debt,
    1000,
    '2026-03-25',
    l10n_cz_kh_document_reference='VAT34-BD-REVERSAL-TEST',
    l10n_cz_kh_tax_point_date='2026-03-25',
)
ensure_move(
    'VAT40-PROP-TEST',
    'in_invoice',
    partner_cz_supplier,
    purchase_account,
    tax_purchase_domestic,
    6000,
    '2026-03-23',
    l10n_cz_kh_document_reference='VAT40-PROP-TEST',
    l10n_cz_kh_proportional_deduction=True,
)
ensure_move(
    'VAT40-COEF70-ASSET-TEST',
    'in_invoice',
    partner_cz_supplier,
    purchase_account,
    tax_purchase_domestic_coefficient,
    100000,
    '2026-03-24',
    l10n_cz_kh_document_reference='VAT40-COEF70-ASSET-TEST',
)
ensure_move(
    'KH-B2B-UNDER-10K-TEST',
    'in_invoice',
    partner_cz_supplier,
    purchase_account,
    tax_purchase_domestic,
    5000,
    '2026-03-24',
    l10n_cz_kh_document_reference='KH-B2B-UNDER-10K-TEST',
)
ensure_move(
    'KH-B2B-OVER-10K-TEST',
    'in_invoice',
    partner_cz_supplier,
    purchase_account,
    tax_purchase_domestic,
    15000,
    '2026-03-24',
    l10n_cz_kh_document_reference='KH-B2B-OVER-10K-TEST',
)
ensure_move(
    'KH-B2C-OVER-10K-TEST',
    'out_invoice',
    partner_cz_private,
    sale_account,
    tax_sale_domestic,
    20000,
    '2026-03-24',
    l10n_cz_kh_document_reference='KH-B2C-OVER-10K-TEST',
)
ensure_move(
    'VAT47-ASSET-TEST',
    'in_invoice',
    partner_cz_supplier,
    purchase_account,
    tax_purchase_asset,
    8000,
    '2026-03-24',
    l10n_cz_kh_document_reference='VAT47-ASSET-TEST',
    l10n_cz_kh_proportional_deduction=True,
)
ensure_move(
    'VAT50-EXEMPT-TEST',
    'out_invoice',
    partner_cz_customer,
    sale_account,
    tax_sale_vat50,
    7000,
    '2026-03-25',
    l10n_cz_kh_document_reference='VAT50-EXEMPT-TEST',
)
ensure_move(
    'VAT51A-EXCLUDED-TEST',
    'out_invoice',
    partner_cz_customer,
    sale_account,
    tax_sale_vat51_with,
    5000,
    '2026-03-26',
    l10n_cz_kh_document_reference='VAT51A-EXCLUDED-TEST',
)
ensure_move(
    'VAT51B-EXCLUDED-TEST',
    'out_invoice',
    partner_cz_customer,
    sale_account,
    tax_sale_vat51_without,
    4000,
    '2026-03-27',
    l10n_cz_kh_document_reference='VAT51B-EXCLUDED-TEST',
)
ensure_move(
    'VAT61-REFUND-TEST',
    'out_invoice',
    partner_cz_customer,
    sale_account,
    tax_sale_vat61,
    3000,
    '2026-03-28',
    l10n_cz_kh_document_reference='VAT61-REFUND-TEST',
)
ensure_move(
    'DPH45-TEST',
    'in_invoice',
    partner_cz_supplier,
    purchase_account,
    None,
    1000,
    '2026-03-29',
    l10n_cz_kh_document_reference='DPH45-TEST',
    l10n_cz_dph_line_45_full_deduction=420.0,
    l10n_cz_dph_line_45_reduced_deduction=105.0,
)
ensure_move(
    'DPH48-60-TEST',
    'in_invoice',
    partner_cz_supplier,
    purchase_account,
    None,
    1000,
    '2026-03-30',
    l10n_cz_kh_document_reference='DPH48-60-TEST',
    l10n_cz_dph_line_48_base_amount=1000.0,
    l10n_cz_dph_line_48_full_deduction=210.0,
    l10n_cz_dph_line_48_reduced_deduction=84.0,
    l10n_cz_dph_line_60_adjustment=315.0,
)
ensure_move(
    'VAT23-NMT-TEST',
    'out_invoice',
    partner_de_private,
    sale_account,
    tax_sale_vat23,
    4500,
    '2026-04-02',
    date='2026-04-02',
    l10n_cz_dph_tax_date='2026-03-31',
    l10n_cz_kh_document_reference='VAT23-NMT-TEST',
)
ensure_move(
    'VAT24-SELECTED-TEST',
    'out_invoice',
    partner_at_private,
    sale_account,
    tax_sale_vat24,
    3500,
    '2026-03-27',
    l10n_cz_kh_document_reference='VAT24-SELECTED-TEST',
)
ensure_move(
    'IOSS-SKIP-TEST',
    'out_invoice',
    partner_de_private,
    sale_account,
    tax_sale_ioss_placeholder,
    2400,
    '2026-03-31',
    l10n_cz_vat_regime='ioss',
    l10n_cz_kh_document_reference='IOSS-SKIP-TEST',
)

env.cr.commit()
PY"
