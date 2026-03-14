import calendar

from odoo import _, fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    l10n_cz_dph_use_manual_advance_coefficient = fields.Boolean(
        string="Use Manual CZ DPH Advance Coefficient",
        help="Use the manual Czech DPH advance coefficient below instead of deriving row 52 from the previous calendar year.",
    )
    l10n_cz_dph_advance_coefficient = fields.Float(
        string="CZ DPH Advance Coefficient",
        digits=(16, 2),
        help="Advance coefficient percentage for Czech DPH row 52 when the company is not deriving it from the previous calendar year.",
    )
    l10n_cz_vat_filing_history_count = fields.Integer(
        string="Czech VAT Filing Exports",
        compute="_compute_l10n_cz_vat_filing_history_count",
    )

    def _compute_l10n_cz_vat_filing_history_count(self):
        History = self.env["l10n_cz.vat.filing.history"]
        for company in self:
            company.l10n_cz_vat_filing_history_count = History.search_count([("company_id", "=", company.id)])

    def l10n_cz_vat_filing_exports(self, date_from, date_to, options=None):
        self.ensure_one()
        return self.env["l10n_cz.vat.filing.export"].build_exports(
            self,
            date_from,
            date_to,
            options=options or {},
        )

    def action_open_l10n_cz_vat_filing_export_wizard(self):
        self.ensure_one()
        today = fields.Date.context_today(self)
        period_start = today.replace(day=1)
        period_end = today.replace(day=calendar.monthrange(today.year, today.month)[1])
        return {
            "type": "ir.actions.act_window",
            "name": _("Czech VAT Filing Export"),
            "res_model": "l10n_cz.vat.filing.export.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_company_id": self.id,
                "default_date_from": period_start,
                "default_date_to": period_end,
            },
        }

    def action_open_l10n_cz_vat_filing_history(self):
        self.ensure_one()
        action = self.env.ref("l10n_cz_vat_filing.action_l10n_cz_vat_filing_history").read()[0]
        action["domain"] = [("company_id", "=", self.id)]
        action["context"] = {"default_company_id": self.id}
        return action
