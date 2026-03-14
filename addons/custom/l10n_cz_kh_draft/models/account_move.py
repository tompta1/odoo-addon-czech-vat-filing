from odoo import fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    l10n_cz_kh_document_reference = fields.Char(
        string="CZ KH Document Reference",
        help="Optional override for the evidence/document number used in Czech KH sections.",
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
        selection=[(str(code), str(code)) for code in range(8)],
        string="CZ KH Reverse Charge Code",
        help="Required for KH A1 and B1 rows generated from Czech reverse-charge tags.",
    )
    l10n_cz_kh_proportional_deduction = fields.Boolean(
        string="CZ KH Proportional Deduction",
        help="Routes deductible VAT to proportional-deduction fields and marks KH B2 rows as POMER=A.",
    )

    def l10n_cz_kh_draft_payload(self):
        return self.env["l10n_cz.kh.draft.export"].build_payload(self)

    def l10n_cz_kh_draft_json(self):
        return self.env["l10n_cz.kh.draft.export"].build_json(self)
