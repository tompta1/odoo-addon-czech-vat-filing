from odoo import api, models


class AccountMove(models.Model):
    _inherit = "account.move"

    def _l10n_cz_oss_bridge_is_cz_sale_invoice(self):
        self.ensure_one()
        return (
            self.company_id.account_fiscal_country_id.code == "CZ"
            and self.move_type in {"out_invoice", "out_refund"}
            and self.is_invoice(include_receipts=True)
        )

    def _l10n_cz_oss_bridge_has_oss_tax_tag(self):
        self.ensure_one()
        oss_tag = self.env.ref("l10n_eu_oss.tag_oss", raise_if_not_found=False)
        if not oss_tag:
            return False
        return bool(self.line_ids.filtered(lambda line: oss_tag in line.tax_tag_ids))

    def _l10n_cz_oss_bridge_has_non_eu_origin_product(self):
        self.ensure_one()
        non_eu_tag = self.env.ref("l10n_eu_oss.tag_eu_import", raise_if_not_found=False)
        if not non_eu_tag:
            return False
        invoice_lines = self.invoice_line_ids.filtered(
            lambda line: line.display_type not in {"line_section", "line_note", "rounding"}
        )
        for line in invoice_lines:
            product = line.product_id
            if not product:
                continue
            account_tags = product.account_tag_ids | product.product_tmpl_id.account_tag_ids
            if non_eu_tag in account_tags:
                return True
        return False

    def _l10n_cz_oss_bridge_detect_regime(self):
        self.ensure_one()
        if not self._l10n_cz_oss_bridge_is_cz_sale_invoice():
            return False
        if not self._l10n_cz_oss_bridge_has_oss_tax_tag():
            return False
        if self._l10n_cz_oss_bridge_has_non_eu_origin_product():
            return "ioss"
        return "oss"

    def _l10n_cz_oss_bridge_sync_regime(self):
        if self.env.context.get("skip_l10n_cz_oss_bridge"):
            return
        for move in self:
            if move.l10n_cz_vat_regime == "third_country_import":
                continue
            detected = move._l10n_cz_oss_bridge_detect_regime()
            if detected and move.l10n_cz_vat_regime != detected:
                move.with_context(skip_l10n_cz_oss_bridge=True).write(
                    {"l10n_cz_vat_regime": detected}
                )
            elif not detected and move.l10n_cz_vat_regime in {"oss", "ioss"}:
                move.with_context(skip_l10n_cz_oss_bridge=True).write(
                    {"l10n_cz_vat_regime": "standard"}
                )

    @api.model_create_multi
    def create(self, vals_list):
        moves = super().create(vals_list)
        moves._l10n_cz_oss_bridge_sync_regime()
        return moves

    def write(self, vals):
        result = super().write(vals)
        if not self.env.context.get("skip_l10n_cz_oss_bridge"):
            watched_fields = {
                "line_ids",
                "invoice_line_ids",
                "move_type",
                "company_id",
                "l10n_cz_vat_regime",
            }
            if watched_fields.intersection(vals.keys()):
                self._l10n_cz_oss_bridge_sync_regime()
        return result

    def action_post(self):
        result = super().action_post()
        self._l10n_cz_oss_bridge_sync_regime()
        return result
