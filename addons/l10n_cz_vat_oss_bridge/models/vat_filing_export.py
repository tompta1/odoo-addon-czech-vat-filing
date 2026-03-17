from odoo import models
from odoo.addons.l10n_cz_vat_filing.models.vat_filing_export import STANDARD_CZ_FILING_TAGS


class L10nCzVatFilingExport(models.AbstractModel):
    _inherit = "l10n_cz.vat.filing.export"

    def _move_tag_names(self, move):
        tag_names = super()._move_tag_names(move)
        if (
            move.l10n_cz_vat_regime in {"oss", "ioss"}
            and hasattr(move, "_l10n_cz_oss_bridge_has_oss_tax_tag")
            and move._l10n_cz_oss_bridge_has_oss_tax_tag()
        ):
            # Odoo OSS taxes intentionally include local report tags plus the OSS marker.
            # Once the move is excluded by regime, those local tags should not trigger
            # Czech filing validation errors on excluded OSS/IOSS records.
            return tag_names - STANDARD_CZ_FILING_TAGS
        return tag_names
