from odoo import models
from odoo.exceptions import UserError


class AccountPayment(models.Model):
    _inherit = "account.payment"

    def _l10n_cz_registry_bank_account_number(self):
        self.ensure_one()
        return (self.partner_bank_id.acc_number or "").strip()

    def _l10n_cz_check_registry_shield(self):
        for payment in self:
            if payment.payment_type != "outbound" or payment.partner_type != "supplier" or not payment.partner_id:
                continue
            company = payment.company_id
            if not company.l10n_cz_vat_registry_enabled or not company.l10n_cz_vat_registry_block_on_payment:
                continue
            evaluation = company.l10n_cz_vat_registry_evaluate_partner(
                payment.partner_id.commercial_partner_id,
                bank_account=payment._l10n_cz_registry_bank_account_number(),
            )
            if evaluation["violations"]:
                raise UserError("\n".join(evaluation["violations"]))

    def action_post(self):
        self._l10n_cz_check_registry_shield()
        return super().action_post()

