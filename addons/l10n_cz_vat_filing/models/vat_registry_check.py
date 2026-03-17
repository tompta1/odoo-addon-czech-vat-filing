from odoo import fields, models


class L10nCzVatRegistryCheck(models.Model):
    _name = "l10n_cz.vat.registry.check"
    _description = "Czech VAT Registry Check Cache"
    _order = "checked_at desc, id desc"

    company_id = fields.Many2one("res.company", required=True, index=True, ondelete="cascade")
    partner_id = fields.Many2one("res.partner", index=True, ondelete="set null")
    vat_number = fields.Char(required=True, index=True)
    checked_at = fields.Datetime(required=True, default=fields.Datetime.now, index=True)
    status = fields.Selection(
        [("ok", "OK"), ("error", "Error")],
        required=True,
        default="ok",
        index=True,
    )
    is_unreliable = fields.Boolean()
    bank_account_checked = fields.Char()
    published_bank_accounts = fields.Json(default=list)
    response_payload = fields.Json(default=dict)
    error_message = fields.Text()
    source_url = fields.Char()

