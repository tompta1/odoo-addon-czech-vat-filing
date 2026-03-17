from odoo import _, models


class ResCompany(models.Model):
    _inherit = "res.company"

    def action_l10n_cz_oss_bridge_backfill(self):
        self.ensure_one()
        Move = self.env["account.move"]
        domain = [
            ("company_id", "=", self.id),
            ("state", "=", "posted"),
            ("move_type", "in", ["out_invoice", "out_refund"]),
        ]
        moves = Move.search(domain, order="id")
        scanned = len(moves)
        detected_candidates = 0
        updated = 0
        for move in moves:
            if not move._l10n_cz_oss_bridge_is_cz_sale_invoice():
                continue
            detected = move._l10n_cz_oss_bridge_detect_regime()
            if not detected:
                continue
            detected_candidates += 1
            if move.l10n_cz_vat_regime == "third_country_import":
                continue
            if move.l10n_cz_vat_regime != detected:
                move.with_context(skip_l10n_cz_oss_bridge=True).write(
                    {"l10n_cz_vat_regime": detected}
                )
                updated += 1

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("OSS/IOSS Backfill Completed"),
                "type": "success",
                "sticky": False,
                "message": _(
                    "Scanned %(scanned)s posted sales moves, detected %(detected)s OSS/IOSS candidates, updated %(updated)s regime values."
                )
                % {
                    "scanned": scanned,
                    "detected": detected_candidates,
                    "updated": updated,
                },
            },
        }
