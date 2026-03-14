import json
from collections import defaultdict

from odoo import fields, models, _
from odoo.exceptions import UserError


class L10nCzKhDraftExport(models.AbstractModel):
    _name = "l10n_cz.kh.draft.export"
    _description = "Czech KH Draft Export"

    def _invoice_content_lines(self, move):
        return move.invoice_line_ids.filtered(
            lambda line: line.display_type not in {"line_section", "line_note", "rounding"}
        )

    def _validate_moves(self, moves):
        moves = moves.filtered(lambda move: move.is_invoice(include_receipts=True))
        if not moves:
            raise UserError(_("Select at least one invoice or receipt for the Czech KH draft export."))

        not_posted = moves.filtered(lambda move: move.state != "posted")
        if not_posted:
            raise UserError(_("The Czech KH draft export only supports posted accounting documents."))

        companies = moves.company_id
        if len(companies) != 1:
            raise UserError(_("The Czech KH draft export expects moves from a single company."))

        company = companies[0]
        if company.account_fiscal_country_id.code != "CZ":
            raise UserError(_("The Czech KH draft export only supports companies with Czech fiscal country."))

        return moves.sorted(lambda move: ((move.invoice_date or move.date or fields.Date.today()), move.id))

    def _build_tax_rows(self, move):
        base_by_tax_id = defaultdict(float)
        for line in self._invoice_content_lines(move):
            for tax in line.tax_ids:
                base_by_tax_id[tax.id] += line.price_subtotal

        tax_rows = []
        for line in move.line_ids.filtered(lambda aml: aml.tax_line_id):
            tax = line.tax_line_id
            tax_rows.append({
                "tax_id": tax.id,
                "tax_name": tax.name,
                "tax_rate": tax.amount,
                "base_amount": round(base_by_tax_id.get(tax.id, 0.0), 2),
                "tax_amount": round(-line.balance, 2),
                "tax_group": tax.tax_group_id.name,
            })
        return tax_rows

    def _build_move_payload(self, move):
        partner = move.commercial_partner_id
        return {
            "id": move.id,
            "number": move.name,
            "move_type": move.move_type,
            "state": move.state,
            "invoice_date": str(move.invoice_date or move.date or ""),
            "date": str(move.date or ""),
            "due_date": str(move.invoice_date_due or ""),
            "journal": move.journal_id.code,
            "partner": {
                "name": partner.name,
                "vat": partner.vat or "",
                "country_code": partner.country_id.code or "",
                "city": partner.city or "",
            },
            "amount_untaxed": round(move.amount_untaxed, 2),
            "amount_tax": round(move.amount_tax, 2),
            "amount_total": round(move.amount_total, 2),
            "currency": move.currency_id.name,
            "invoice_lines": [
                {
                    "name": line.name,
                    "account_code": line.account_id.code,
                    "price_subtotal": round(line.price_subtotal, 2),
                    "taxes": [tax.name for tax in line.tax_ids],
                }
                for line in self._invoice_content_lines(move)
            ],
            "tax_rows": self._build_tax_rows(move),
        }

    def build_payload(self, moves):
        moves = self._validate_moves(moves)
        company = moves.company_id[0]
        company_partner = company.partner_id.commercial_partner_id

        payload = {
            "draft_only": True,
            "warning": "This payload is not a legal Czech KH filing. It is a draft data export for mapping and testing.",
            "generated_at": fields.Datetime.now().isoformat(),
            "company": {
                "id": company.id,
                "name": company.name,
                "vat": company_partner.vat or "",
                "country_code": company.account_fiscal_country_id.code or "",
                "currency": company.currency_id.name,
                "chart_template": company.chart_template or "",
            },
            "moves": [self._build_move_payload(move) for move in moves],
        }
        payload["summary"] = {
            "move_count": len(payload["moves"]),
            "amount_untaxed": round(sum(move["amount_untaxed"] for move in payload["moves"]), 2),
            "amount_tax": round(sum(move["amount_tax"] for move in payload["moves"]), 2),
            "amount_total": round(sum(move["amount_total"] for move in payload["moves"]), 2),
        }
        return payload

    def build_json(self, moves):
        return json.dumps(self.build_payload(moves), ensure_ascii=False, indent=2, sort_keys=True)
