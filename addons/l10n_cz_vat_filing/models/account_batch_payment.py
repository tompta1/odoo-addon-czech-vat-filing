from odoo import models
from odoo.exceptions import UserError


class AccountBatchPayment(models.Model):
    _inherit = "account.batch.payment"

    def _l10n_cz_check_registry_shield(self):
        for batch in self:
            if batch.batch_type != "outbound":
                continue
            company = batch.company_id
            if not company.l10n_cz_vat_registry_enabled or not company.l10n_cz_vat_registry_block_on_payment:
                continue
            all_violations = []
            for payment in batch.payment_ids:
                if (
                    payment.payment_type != "outbound"
                    or payment.partner_type != "supplier"
                    or not payment.partner_id
                ):
                    continue
                bank_account = (payment.partner_bank_id.acc_number or "").strip()
                evaluation = company.l10n_cz_vat_registry_evaluate_partner(
                    payment.partner_id.commercial_partner_id,
                    bank_account=bank_account,
                    require_bank_account=True,
                )
                for violation in evaluation["violations"]:
                    all_violations.append(f"[{payment.partner_id.display_name}] {violation}")
            if all_violations:
                raise UserError("\n\n".join(all_violations))

    def validate(self):
        self._l10n_cz_check_registry_shield()
        return super().validate()
