from odoo import fields, models
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = "account.move"

    l10n_cz_vat_regime = fields.Selection(
        selection=[
            ("standard", "Standard CZ Filing"),
            ("third_country_import", "3rd-Country Import"),
            ("oss", "OSS Outside CZ Return"),
            ("ioss", "IOSS Outside CZ Return"),
        ],
        string="CZ VAT Filing Regime",
        default="standard",
        help=(
            "Use OSS/IOSS to exclude the move from the standard Czech DPH/KH/SH XML exports. "
            "Use 3rd-Country Import to keep the move in Czech DPH while applying import-specific guards."
        ),
    )
    l10n_cz_customs_mrn = fields.Char(
        string="CZ Customs MRN",
        help="Movement Reference Number (MRN) or other customs declaration reference for 3rd-country imports.",
    )
    l10n_cz_customs_decision_number = fields.Char(
        string="CZ Customs Decision Number",
        help="Customs office decision or JSD reference linked to the import evidence.",
    )
    l10n_cz_customs_release_date = fields.Date(
        string="CZ Customs Release Date",
        help="Date when the goods were released by customs.",
    )
    l10n_cz_customs_office = fields.Char(
        string="CZ Customs Office",
        help="Customs office that handled the import declaration.",
    )
    l10n_cz_customs_value_amount = fields.Float(
        string="CZ Customs Value",
        digits=(16, 2),
        help="Customs value declared for the import document.",
    )
    l10n_cz_customs_vat_amount = fields.Float(
        string="CZ Import VAT Amount",
        digits=(16, 2),
        help="VAT amount assessed from the customs declaration or JSD evidence.",
    )
    l10n_cz_customs_note = fields.Text(
        string="CZ Customs Note",
        help="Free-form customs/import note for audit trail and accountant review.",
    )
    l10n_cz_import_correction_origin_id = fields.Many2one(
        "account.move",
        string="CZ Import Correction Origin",
        help=(
            "Original posted 3rd-country import document (JSD evidence) that this import correction amends "
            "for DPH row 45 handling."
        ),
    )
    l10n_cz_import_correction_reason = fields.Char(
        string="CZ Import Correction Reason",
        help="Short audit note for the import correction under section 42/74 flow (e.g. customs value revision).",
    )

    l10n_cz_kh_document_reference = fields.Char(
        string="CZ KH Document Reference",
        help="Optional override for the evidence/document number used in Czech KH sections.",
    )
    l10n_cz_dph_tax_date = fields.Date(
        string="CZ DPH Tax Date (DUZP)",
        help="Tax-point date used for Czech DPH/KH period selection when it differs from the accounting date.",
    )
    l10n_cz_kh_tax_point_date = fields.Date(
        string="CZ KH Tax Point Date",
        help="Optional override for the Czech KH tax point date used in A1/A2/A4/B1/B2 rows.",
    )
    l10n_cz_kh_deduction_date = fields.Date(
        string="CZ KH Deduction Date",
        help="Reserved field for Czech filing deduction-date tracking on purchase documents.",
    )
    l10n_cz_kh_reverse_charge_code = fields.Selection(
        selection=[(str(code), str(code)) for code in range(1, 21)],
        string="CZ KH Reverse Charge Code",
        help="Required for KH A1 and B1 rows generated from Czech reverse-charge tags.",
    )
    l10n_cz_kh_proportional_deduction = fields.Boolean(
        string="CZ KH Proportional Deduction",
        help="Routes deductible VAT to proportional-deduction fields and marks KH B2 rows as POMER=A.",
    )
    l10n_cz_dph_line_45_full_deduction = fields.Float(
        string="CZ DPH Line 45 Full Deduction",
        digits=(16, 2),
        help="Special Czech DPH row 45 deduction amount in full.",
    )
    l10n_cz_dph_line_45_reduced_deduction = fields.Float(
        string="CZ DPH Line 45 Reduced Deduction",
        digits=(16, 2),
        help="Special Czech DPH row 45 deduction amount in reduced scope.",
    )
    l10n_cz_dph_line_48_base_amount = fields.Float(
        string="CZ DPH Line 48 Base",
        digits=(16, 2),
        help="Special Czech DPH row 48 base amount for registration-cancellation corrections.",
    )
    l10n_cz_dph_line_48_full_deduction = fields.Float(
        string="CZ DPH Line 48 Full Deduction",
        digits=(16, 2),
        help="Special Czech DPH row 48 deduction amount in full.",
    )
    l10n_cz_dph_line_48_reduced_deduction = fields.Float(
        string="CZ DPH Line 48 Reduced Deduction",
        digits=(16, 2),
        help="Special Czech DPH row 48 deduction amount in reduced scope.",
    )
    l10n_cz_dph_line_60_adjustment = fields.Float(
        string="CZ DPH Line 60 Adjustment",
        digits=(16, 2),
        help="Special Czech DPH row 60 long-term adjustment amount under sections 78 to 78d.",
    )
    l10n_cz_vat_registry_check_id = fields.Many2one(
        "l10n_cz.vat.registry.check",
        string="CZ VAT Registry Check",
        readonly=True,
        copy=False,
    )
    l10n_cz_vat_registry_note = fields.Text(
        string="CZ VAT Registry Note",
        readonly=True,
        copy=False,
        help="Latest VAT-registry shield result captured for this vendor document.",
    )
    l10n_cz_vat_fx_manual_rate = fields.Float(
        string="CZ VAT FX Manual Rate",
        digits=(16, 8),
        help="Optional manual DUZP VAT FX rate to CZK for this foreign-currency document.",
    )
    l10n_cz_vat_fx_rate = fields.Float(
        string="CZ VAT FX Applied Rate",
        digits=(16, 8),
        readonly=True,
        copy=False,
        help="Resolved DUZP VAT FX rate to CZK used by Czech VAT export decoupling.",
    )
    l10n_cz_vat_fx_rate_source = fields.Selection(
        [("manual", "Manual"), ("cnb", "CNB/API")],
        string="CZ VAT FX Source",
        readonly=True,
        copy=False,
    )
    l10n_cz_vat_fx_rate_record_id = fields.Many2one(
        "l10n_cz.vat.fx.rate",
        string="CZ VAT FX Rate Record",
        readonly=True,
        copy=False,
    )
    l10n_cz_vat_fx_note = fields.Text(
        string="CZ VAT FX Note",
        readonly=True,
        copy=False,
        help="Latest VAT FX resolution note for Czech VAT export purposes.",
    )

    def l10n_cz_kh_draft_payload(self):
        return self.env["l10n_cz.kh.draft.export"].build_payload(self)

    def l10n_cz_kh_draft_json(self):
        return self.env["l10n_cz.kh.draft.export"].build_json(self)

    def _l10n_cz_registry_bank_account_number(self):
        self.ensure_one()
        return (self.partner_bank_id.acc_number or "").strip()

    def _l10n_cz_apply_vat_fx_rate(self):
        for move in self:
            if move.move_type not in {"out_invoice", "out_refund", "in_invoice", "in_refund"}:
                continue
            company = move.company_id
            if not company._l10n_cz_vat_fx_move_enabled(move):
                move.write(
                    {
                        "l10n_cz_vat_fx_rate": 0.0,
                        "l10n_cz_vat_fx_rate_source": False,
                        "l10n_cz_vat_fx_rate_record_id": False,
                        "l10n_cz_vat_fx_note": "",
                    }
                )
                continue

            if move.l10n_cz_vat_fx_manual_rate and move.l10n_cz_vat_fx_manual_rate > 0:
                move.write(
                    {
                        "l10n_cz_vat_fx_rate": move.l10n_cz_vat_fx_manual_rate,
                        "l10n_cz_vat_fx_rate_source": "manual",
                        "l10n_cz_vat_fx_rate_record_id": False,
                        "l10n_cz_vat_fx_note": "Using manual CZ VAT FX rate override.",
                    }
                )
                continue

            resolved_rate, rate_record = company.l10n_cz_vat_fx_rate_for_move(move)
            values = {
                "l10n_cz_vat_fx_rate_record_id": rate_record.id or False,
                "l10n_cz_vat_fx_rate_source": "cnb",
            }
            if resolved_rate:
                values["l10n_cz_vat_fx_rate"] = resolved_rate
                values["l10n_cz_vat_fx_note"] = "Using DUZP VAT FX rate from CZ VAT FX API cache."
            else:
                values["l10n_cz_vat_fx_rate"] = 0.0
                values["l10n_cz_vat_fx_note"] = rate_record.error_message or "VAT FX lookup failed."
            move.write(values)

    def _l10n_cz_check_registry_shield(self):
        for move in self:
            if move.move_type not in {"in_invoice", "in_refund"}:
                continue
            company = move.company_id
            if not company.l10n_cz_vat_registry_enabled or not company.l10n_cz_vat_registry_block_on_post:
                continue
            evaluation = company.l10n_cz_vat_registry_evaluate_partner(
                move.commercial_partner_id,
                bank_account=move._l10n_cz_registry_bank_account_number(),
            )
            note_lines = list(evaluation["messages"])
            note_lines.extend(evaluation["violations"])
            move.write(
                {
                    "l10n_cz_vat_registry_check_id": evaluation["check"].id or False,
                    "l10n_cz_vat_registry_note": "\n".join(note_lines),
                }
            )
            if evaluation["violations"]:
                raise UserError("\n".join(evaluation["violations"]))

    def action_post(self):
        self._l10n_cz_apply_vat_fx_rate()
        self._l10n_cz_check_registry_shield()
        return super().action_post()
