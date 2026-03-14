from odoo import fields, models
from odoo.exceptions import ValidationError


class ResPartner(models.Model):
    _inherit = "res.partner"

    def do_button_print(self):
        self.ensure_one()
        company_id = self.env.user.company_id.id
        overdue_domain = [
            ("partner_id", "=", self.id),
            ("account_id.account_type", "=", "asset_receivable"),
            ("full_reconcile_id", "=", False),
            ("company_id", "=", company_id),
            "|",
            ("date_maturity", "=", False),
            ("date_maturity", "<=", fields.Date.today()),
        ]
        if not self.env["account.move.line"].search(overdue_domain, limit=1):
            raise ValidationError(
                "The partner does not have any accounting entries to print in the overdue report for the current company."
            )

        self.message_post(body="Printed overdue payments report")
        wizard_partner_ids = [self.id * 10000 + company_id]
        followup_ids = self.env["followup.followup"].search([("company_id", "=", company_id)], limit=1)
        if not followup_ids:
            raise ValidationError("There is no followup plan defined for the current company.")

        data = {
            "date": fields.Date.today(),
            "followup_id": followup_ids.id,
        }
        return self.do_partner_print(wizard_partner_ids, data)
