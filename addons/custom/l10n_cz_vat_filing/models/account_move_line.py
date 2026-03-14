from odoo import fields, models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    l10n_cz_kh_subject_code = fields.Selection(
        selection=[(str(code), str(code)) for code in range(1, 21)],
        string="CZ KH Subject Code",
        help=(
            "Line-level KH reverse-charge subject code (kód předmětu plnění). "
            "Used for domestic reverse-charge A1/B1 rows; when not set, the move-level code is used."
        ),
    )
