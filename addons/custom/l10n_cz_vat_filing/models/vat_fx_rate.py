from odoo import fields, models


class L10nCzVatFxRate(models.Model):
    _name = "l10n_cz.vat.fx.rate"
    _description = "Czech VAT FX Rate Cache"
    _order = "tax_date desc, checked_at desc, id desc"

    company_id = fields.Many2one("res.company", required=True, index=True, ondelete="cascade")
    currency_id = fields.Many2one("res.currency", required=True, index=True, ondelete="cascade")
    tax_date = fields.Date(required=True, index=True)
    checked_at = fields.Datetime(required=True, default=fields.Datetime.now, index=True)
    status = fields.Selection(
        [("ok", "OK"), ("error", "Error")],
        required=True,
        default="ok",
        index=True,
    )
    rate_to_czk = fields.Float(
        string="Rate To CZK",
        digits=(16, 8),
        help="CZK amount for one unit of source currency on the Czech VAT tax date (DUZP).",
    )
    source_url = fields.Char()
    response_payload = fields.Json(default=dict)
    error_message = fields.Text()

    _sql_constraints = [
        (
            "l10n_cz_vat_fx_rate_unique",
            "unique(company_id,currency_id,tax_date)",
            "Only one CZ VAT FX cache record per company/currency/tax date is allowed.",
        )
    ]

