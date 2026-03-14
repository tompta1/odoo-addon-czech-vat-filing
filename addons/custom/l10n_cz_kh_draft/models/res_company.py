from odoo import models


class ResCompany(models.Model):
    _inherit = "res.company"

    def l10n_cz_vat_filing_exports(self, date_from, date_to, options=None):
        self.ensure_one()
        return self.env["l10n_cz.vat.filing.export"].build_exports(
            self,
            date_from,
            date_to,
            options=options or {},
        )
