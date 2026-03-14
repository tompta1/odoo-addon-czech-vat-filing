import calendar
import json
import re
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from xml.dom import minidom
from xml.etree import ElementTree as ET

from odoo import fields, models, _
from odoo.exceptions import UserError


TWOPLACES = Decimal("0.01")

DPH_FIELD_SPECS_BY_TAG = {
    "VAT 1 Base": [("Veta1", "obrat23", None)],
    "VAT 1 Tax": [("Veta1", "dan23", None)],
    "VAT 2 Base": [("Veta1", "obrat5", None)],
    "VAT 2 Tax": [("Veta1", "dan5", None)],
    "VAT 3 Base": [("Veta1", "p_zb23", None), ("Veta4", "nar_zdp23", None)],
    "VAT 3 Tax": [("Veta1", "dan_pzb23", None), ("Veta4", "od_zdp23", "odkr_zdp23")],
    "VAT 4 Base": [("Veta1", "p_zb5", None), ("Veta4", "nar_zdp5", None)],
    "VAT 4 Tax": [("Veta1", "dan_pzb5", None), ("Veta4", "od_zdp5", "odkr_zdp5")],
    "VAT 5 Base": [("Veta1", "p_sl23_e", None), ("Veta4", "nar_zdp23", None)],
    "VAT 5 Tax": [("Veta1", "dan_psl23_e", None), ("Veta4", "od_zdp23", "odkr_zdp23")],
    "VAT 6 Base": [("Veta1", "p_sl5_e", None), ("Veta4", "nar_zdp5", None)],
    "VAT 6 Tax": [("Veta1", "dan_psl5_e", None), ("Veta4", "od_zdp5", "odkr_zdp5")],
    "VAT 7 Base": [("Veta1", "dov_zb23", None), ("Veta4", "nar_zdp23", None)],
    "VAT 7 Tax": [("Veta1", "dan_dzb23", None), ("Veta4", "od_zdp23", "odkr_zdp23")],
    "VAT 8 Base": [("Veta1", "dov_zb5", None), ("Veta4", "nar_zdp5", None)],
    "VAT 8 Tax": [("Veta1", "dan_dzb5", None), ("Veta4", "od_zdp5", "odkr_zdp5")],
    "VAT 9 Base": [("Veta1", "p_dop_nrg", None), ("Veta4", "nar_zdp23", None)],
    "VAT 9 Tax": [("Veta1", "dan_pdop_nrg", None), ("Veta4", "od_zdp23", "odkr_zdp23")],
    "VAT 10 Base": [("Veta1", "rez_pren23", None), ("Veta4", "nar_zdp23", None)],
    "VAT 10 Tax": [("Veta1", "dan_rpren23", None), ("Veta4", "od_zdp23", "odkr_zdp23")],
    "VAT 11 Base": [("Veta1", "rez_pren5", None), ("Veta4", "nar_zdp5", None)],
    "VAT 11 Tax": [("Veta1", "dan_rpren5", None), ("Veta4", "od_zdp5", "odkr_zdp5")],
    "VAT 12 Base": [("Veta1", "p_sl23_z", None), ("Veta4", "nar_zdp23", None)],
    "VAT 12 Tax": [("Veta1", "dan_psl23_z", None), ("Veta4", "od_zdp23", "odkr_zdp23")],
    "VAT 13 Base": [("Veta1", "p_sl5_z", None), ("Veta4", "nar_zdp5", None)],
    "VAT 13 Tax": [("Veta1", "dan_psl5_z", None), ("Veta4", "od_zdp5", "odkr_zdp5")],
    "VAT 20": [("Veta2", "dod_zb", None)],
    "VAT 21": [("Veta2", "pln_sluzby", None)],
    "VAT 22": [("Veta2", "pln_vyvoz", None)],
    "VAT 25": [("Veta2", "pln_rez_pren", None)],
    "VAT 26": [("Veta2", "pln_ost", None)],
    "VAT 40 Base": [("Veta4", "pln23", None)],
    "VAT 40 Total": [("Veta4", "odp_tuz23_nar", "odp_tuz23")],
    "VAT 41 Base": [("Veta4", "pln5", None)],
    "VAT 41 Total": [("Veta4", "odp_tuz5_nar", "odp_tuz5")],
    "VAT 42 Base": [("Veta4", "dov_cu", None)],
    "VAT 42 Total": [("Veta4", "odp_cu_nar", "odp_cu")],
}

KH_BASE_TAGS = {
    "VAT 1 Base": 1,
    "VAT 2 Base": 2,
    "VAT 40 Base": 1,
    "VAT 41 Base": 2,
}
KH_TAX_TAGS = {
    "VAT 1 Tax": 1,
    "VAT 2 Tax": 2,
    "VAT 40 Total": 1,
    "VAT 41 Total": 2,
}
SH_LINE_TAGS = {"VAT 20": "0", "VAT 21": "3"}
A1_TAGS = {"VAT 25"}
A2_BASE_TAGS = {
    "VAT 3 Base": 1,
    "VAT 4 Base": 2,
    "VAT 5 Base": 1,
    "VAT 6 Base": 2,
    "VAT 9 Base": None,
    "VAT 12 Base": None,
    "VAT 13 Base": None,
}
A2_TAX_TAGS = {
    "VAT 3 Tax": 1,
    "VAT 4 Tax": 2,
    "VAT 5 Tax": 1,
    "VAT 6 Tax": 2,
    "VAT 9 Tax": None,
    "VAT 12 Tax": None,
    "VAT 13 Tax": None,
}
B1_BASE_TAGS = {
    "VAT 10 Base": 1,
    "VAT 11 Base": 2,
}
B1_TAX_TAGS = {
    "VAT 10 Tax": 1,
    "VAT 11 Tax": 2,
}
SUPPORTED_VAT_TAGS = set(DPH_FIELD_SPECS_BY_TAG)
UNSUPPORTED_VAT_TAGS = {
    "VAT 23",
    "VAT 24",
    "VAT 30",
    "VAT 31",
    "VAT 32",
    "VAT 33",
    "VAT 34",
    "VAT 47 Base",
    "VAT 47 Total",
    "VAT 50",
    "VAT 51 with deduction",
    "VAT 51 without deduction",
    "VAT 61",
}


class L10nCzVatFilingExport(models.AbstractModel):
    _name = "l10n_cz.vat.filing.export"
    _description = "Czech VAT Filing Export"

    def _decimal(self, value):
        return Decimal(str(value or 0)).quantize(TWOPLACES, rounding=ROUND_HALF_UP)

    def _round_str(self, value):
        return format(self._decimal(value), "f")

    def _whole_str(self, value):
        return str(int(self._decimal(value).to_integral_value(rounding=ROUND_HALF_UP)))

    def _today_str(self):
        return fields.Date.today().strftime("%Y-%m-%d")

    def _first_day_of_month(self, value):
        return value.replace(day=1)

    def _last_day_of_month(self, value):
        return value.replace(day=calendar.monthrange(value.year, value.month)[1])

    def _normalize_date(self, value):
        if isinstance(value, str):
            return fields.Date.from_string(value)
        return value

    def _normalize_vat(self, vat):
        return re.sub(r"[^A-Z0-9]", "", (vat or "").upper())

    def _vat_core(self, vat):
        normalized = self._normalize_vat(vat)
        if len(normalized) > 2 and normalized[:2].isalpha():
            return normalized[2:]
        return normalized

    def _cz_vat(self, vat):
        normalized = self._normalize_vat(vat)
        if normalized.startswith("CZ"):
            return normalized
        if normalized:
            return f"CZ{normalized}"
        return ""

    def _xml_date(self, value):
        value = self._normalize_date(value)
        return value.strftime("%d.%m.%Y")

    def _eu_vat_parts(self, vat):
        normalized = self._normalize_vat(vat)
        if len(normalized) > 2 and normalized[:2].isalpha():
            return normalized[:2], normalized[2:]
        return "", normalized

    def _address_parts(self, partner):
        street = (partner.street or "").strip()
        match = re.match(r"^(?P<ulice>.*?)(?:\s+(?P<c_pop>\d+[A-Za-z/-]*))?$", street)
        if not match:
            return {"ulice": street, "c_pop": "", "c_orient": ""}
        return {
            "ulice": (match.group("ulice") or "").strip(),
            "c_pop": (match.group("c_pop") or "").strip(),
            "c_orient": "",
        }

    def _infer_period(self, date_from, date_to, period_kind=None):
        if period_kind:
            kind = period_kind
        elif date_from == self._first_day_of_month(date_from) and date_to == self._last_day_of_month(date_from):
            kind = "month"
        elif (
            date_from.month in {1, 4, 7, 10}
            and date_from.day == 1
            and date_to.month == date_from.month + 2
            and date_to == self._last_day_of_month(date_to)
        ):
            kind = "quarter"
        else:
            raise UserError(
                _("The Czech filing export expects either a full calendar month or a full calendar quarter.")
            )

        payload = {"kind": kind, "year": str(date_from.year)}
        if kind == "month":
            payload["mesic"] = f"{date_from.month:02d}"
        else:
            payload["ctvrt"] = str(((date_from.month - 1) // 3) + 1)
        return payload

    def _validate_company(self, company):
        partner = company.partner_id.commercial_partner_id
        if company.account_fiscal_country_id.code != "CZ":
            raise UserError(_("The Czech VAT filing export only supports companies with Czech fiscal country."))
        if not partner.vat:
            raise UserError(_("Set a Czech VAT number on the company before generating Czech filing XML."))
        return partner

    def _move_sign(self, move):
        return -1 if move.move_type in {"out_refund", "in_refund"} else 1

    def _posted_moves(self, company, date_from, date_to):
        domain = [
            ("company_id", "=", company.id),
            ("state", "=", "posted"),
            ("move_type", "in", ["out_invoice", "out_refund", "in_invoice", "in_refund"]),
            ("date", ">=", fields.Date.to_string(date_from)),
            ("date", "<=", fields.Date.to_string(date_to)),
        ]
        return self.env["account.move"].search(domain, order="date,id")

    def _line_amount_from_balance(self, line):
        return self._decimal(abs(line.balance) * self._move_sign(line.move_id))

    def _tax_tag_names(self, moves):
        names = set()
        for move in moves:
            for line in move.line_ids.filtered(lambda aml: aml.tax_tag_ids):
                for tag in line.tax_tag_ids:
                    names.add(tag.name)
        return names

    def _tag_amounts(self, moves):
        amounts = defaultdict(Decimal)
        for move in moves:
            for line in move.line_ids.filtered(lambda aml: aml.tax_tag_ids):
                line_amount = self._line_amount_from_balance(line)
                for tag in line.tax_tag_ids:
                    amounts[tag.name] += line_amount
        return amounts

    def _move_tag_amount(self, move, tag_names):
        total = Decimal("0.00")
        for line in move.line_ids.filtered(lambda aml: aml.tax_tag_ids):
            line_amount = self._line_amount_from_balance(line)
            for tag in line.tax_tag_ids:
                if tag.name in tag_names:
                    total += line_amount
        return total

    def _move_tag_amounts(self, move):
        amounts = defaultdict(Decimal)
        for line in move.line_ids.filtered(lambda aml: aml.tax_tag_ids):
            line_amount = self._line_amount_from_balance(line)
            for tag in line.tax_tag_ids:
                amounts[tag.name] += line_amount
        return amounts

    def _move_tag_names(self, move):
        names = set()
        for line in move.line_ids.filtered(lambda aml: aml.tax_tag_ids):
            for tag in line.tax_tag_ids:
                names.add(tag.name)
        return names

    def _tax_rate_slot(self, line):
        tax = line.tax_line_id or line.tax_ids[:1]
        rate = abs(getattr(tax, "amount", 0.0) or 0.0)
        if rate >= 18:
            return 1
        if rate >= 11:
            return 2
        if rate > 0:
            return 3
        return 1

    def _move_breakdown_from_tags(self, move, base_slots, tax_slots):
        breakdown = {
            1: {"base": Decimal("0.00"), "tax": Decimal("0.00")},
            2: {"base": Decimal("0.00"), "tax": Decimal("0.00")},
            3: {"base": Decimal("0.00"), "tax": Decimal("0.00")},
        }
        for line in move.line_ids.filtered(lambda aml: aml.tax_tag_ids):
            amount = self._line_amount_from_balance(line)
            rate_slot = self._tax_rate_slot(line)
            for tag in line.tax_tag_ids:
                if tag.name in base_slots:
                    slot = base_slots[tag.name] or rate_slot
                    breakdown[slot]["base"] += amount
                elif tag.name in tax_slots:
                    slot = tax_slots[tag.name] or rate_slot
                    breakdown[slot]["tax"] += amount
        return breakdown

    def _move_document_reference(self, move):
        return (
            move.l10n_cz_kh_document_reference
            or (move.ref if move.move_type in {"in_invoice", "in_refund"} else "")
            or move.name
            or move.ref
            or f"MOVE-{move.id}"
        )

    def _move_tax_point_date(self, move):
        return self._xml_date(
            move.l10n_cz_kh_tax_point_date
            or move.invoice_date
            or move.date
            or fields.Date.today()
        )

    def _move_deduction_date(self, move):
        return self._xml_date(
            move.l10n_cz_kh_deduction_date
            or move.date
            or move.invoice_date
            or fields.Date.today()
        )

    def _move_proportional_flag(self, move):
        return "A" if move.l10n_cz_kh_proportional_deduction else "N"

    def _move_reverse_charge_code(self, move):
        return move.l10n_cz_kh_reverse_charge_code or ""

    def _partner_vat_identifier(self, partner):
        country_code = partner.country_id.code or ""
        vat_country, vat_number = self._eu_vat_parts(partner.vat)
        return vat_country or country_code, vat_number or self._vat_core(partner.vat)

    def _move_base_tax_breakdown(self, move):
        breakdown = {
            1: {"base": Decimal("0.00"), "tax": Decimal("0.00")},
            2: {"base": Decimal("0.00"), "tax": Decimal("0.00")},
            3: {"base": Decimal("0.00"), "tax": Decimal("0.00")},
        }
        for line in move.line_ids.filtered(lambda aml: aml.tax_tag_ids):
            amount = self._line_amount_from_balance(line)
            for tag in line.tax_tag_ids:
                if tag.name in KH_BASE_TAGS:
                    breakdown[KH_BASE_TAGS[tag.name]]["base"] += amount
                elif tag.name in KH_TAX_TAGS:
                    breakdown[KH_TAX_TAGS[tag.name]]["tax"] += amount
        return breakdown

    def _breakdown_has_values(self, breakdown):
        return any(values["base"] or values["tax"] for values in breakdown.values())

    def _kh_a1_row(self, move):
        partner = move.commercial_partner_id
        if move.move_type not in {"out_invoice", "out_refund"}:
            return None
        if (partner.country_id.code or "") != "CZ":
            return None
        base_amount = self._move_tag_amount(move, A1_TAGS)
        if not base_amount:
            return None
        return {
            "vat": self._vat_core(partner.vat),
            "reference": self._move_document_reference(move),
            "date": self._move_tax_point_date(move),
            "reverse_charge_code": self._move_reverse_charge_code(move),
            "base_amount": base_amount,
        }

    def _kh_a2_row(self, move):
        if move.move_type not in {"in_invoice", "in_refund"}:
            return None
        breakdown = self._move_breakdown_from_tags(move, A2_BASE_TAGS, A2_TAX_TAGS)
        if not self._breakdown_has_values(breakdown):
            return None
        partner = move.commercial_partner_id
        country_code, vat_number = self._partner_vat_identifier(partner)
        return {
            "country_code": country_code,
            "vat_number": vat_number,
            "reference": self._move_document_reference(move),
            "date": self._move_tax_point_date(move),
            "breakdown": breakdown,
        }

    def _kh_domestic_sale_classification(self, move):
        partner = move.commercial_partner_id
        if move.move_type not in {"out_invoice", "out_refund"} or (partner.country_id.code or "") != "CZ":
            return None
        breakdown = self._move_base_tax_breakdown(move)
        if not self._breakdown_has_values(breakdown):
            return None
        total_base = sum(item["base"] for item in breakdown.values())
        amount_total = self._decimal(abs(move.amount_total))
        vat = self._vat_core(partner.vat)
        category = "A4" if vat and amount_total > Decimal("10000.00") else "A5"
        return {
            "category": category,
            "vat": vat,
            "reference": self._move_document_reference(move),
            "date": self._move_tax_point_date(move),
            "breakdown": breakdown,
            "total_base": total_base,
        }

    def _kh_b1_row(self, move):
        partner = move.commercial_partner_id
        if move.move_type not in {"in_invoice", "in_refund"} or (partner.country_id.code or "") != "CZ":
            return None
        breakdown = self._move_breakdown_from_tags(move, B1_BASE_TAGS, B1_TAX_TAGS)
        if not self._breakdown_has_values(breakdown):
            return None
        base_amount = self._move_tag_amount(move, B1_BASE_TAGS)
        return {
            "vat": self._vat_core(partner.vat),
            "reference": self._move_document_reference(move),
            "date": self._move_tax_point_date(move),
            "reverse_charge_code": self._move_reverse_charge_code(move),
            "base_amount": base_amount,
        }

    def _kh_domestic_purchase_classification(self, move):
        partner = move.commercial_partner_id
        if move.move_type not in {"in_invoice", "in_refund"} or (partner.country_id.code or "") != "CZ":
            return None
        if self._move_tag_amount(move, B1_BASE_TAGS):
            return None
        breakdown = self._move_base_tax_breakdown(move)
        if not self._breakdown_has_values(breakdown):
            return None
        total_base = sum(item["base"] for item in breakdown.values())
        amount_total = self._decimal(abs(move.amount_total))
        vat = self._vat_core(partner.vat)
        category = "B2" if vat and amount_total > Decimal("10000.00") else "B3"
        return {
            "category": category,
            "vat": vat,
            "reference": self._move_document_reference(move),
            "date": self._move_tax_point_date(move),
            "proportional": self._move_proportional_flag(move),
            "breakdown": breakdown,
            "total_base": total_base,
        }

    def _kh_payload(self, moves):
        detailed = {"A1": [], "A2": [], "A4": [], "B1": [], "B2": []}
        aggregate = {
            "A5": {
                "count": 0,
                "breakdown": {1: {"base": Decimal("0.00"), "tax": Decimal("0.00")}, 2: {"base": Decimal("0.00"), "tax": Decimal("0.00")}, 3: {"base": Decimal("0.00"), "tax": Decimal("0.00")}},
            },
            "B3": {
                "count": 0,
                "breakdown": {1: {"base": Decimal("0.00"), "tax": Decimal("0.00")}, 2: {"base": Decimal("0.00"), "tax": Decimal("0.00")}, 3: {"base": Decimal("0.00"), "tax": Decimal("0.00")}},
            },
        }
        totals = {
            "supply_count": 0,
            "supply_base": Decimal("0.00"),
            "deduction_count": 0,
            "deduction_base": Decimal("0.00"),
        }

        for move in moves:
            a1_row = self._kh_a1_row(move)
            if a1_row:
                detailed["A1"].append(a1_row)

            a2_row = self._kh_a2_row(move)
            if a2_row:
                detailed["A2"].append(a2_row)

            sale_row = self._kh_domestic_sale_classification(move)
            if sale_row:
                totals["supply_count"] += 1
                totals["supply_base"] += sale_row["total_base"]
                if sale_row["category"] == "A4":
                    detailed["A4"].append(sale_row)
                else:
                    bucket = aggregate["A5"]
                    bucket["count"] += 1
                    for rate_code, values in sale_row["breakdown"].items():
                        bucket["breakdown"][rate_code]["base"] += values["base"]
                        bucket["breakdown"][rate_code]["tax"] += values["tax"]

            b1_row = self._kh_b1_row(move)
            if b1_row:
                detailed["B1"].append(b1_row)

            purchase_row = self._kh_domestic_purchase_classification(move)
            if purchase_row:
                totals["deduction_count"] += 1
                totals["deduction_base"] += purchase_row["total_base"]
                if purchase_row["category"] == "B2":
                    detailed["B2"].append(purchase_row)
                else:
                    bucket = aggregate["B3"]
                    bucket["count"] += 1
                    for rate_code, values in purchase_row["breakdown"].items():
                        bucket["breakdown"][rate_code]["base"] += values["base"]
                        bucket["breakdown"][rate_code]["tax"] += values["tax"]

        return {
            "A1": detailed["A1"],
            "A2": detailed["A2"],
            "A4": detailed["A4"],
            "A5": aggregate["A5"],
            "B1": detailed["B1"],
            "B2": detailed["B2"],
            "B3": aggregate["B3"],
            "C": totals,
        }

    def _kh_control_attrs(self, snapshot):
        tag_amounts = snapshot["tag_amounts"]

        def amount(*tag_names):
            total = Decimal("0.00")
            for tag_name in tag_names:
                total += tag_amounts.get(tag_name, Decimal("0.00"))
            return self._round_str(total)

        return {
            "celk_zd_a2": amount(
                "VAT 3 Base",
                "VAT 4 Base",
                "VAT 5 Base",
                "VAT 6 Base",
                "VAT 9 Base",
                "VAT 12 Base",
                "VAT 13 Base",
            ),
            "obrat23": amount("VAT 1 Base"),
            "obrat5": amount("VAT 2 Base"),
            "pln23": amount("VAT 40 Base"),
            "pln5": amount("VAT 41 Base"),
            "pln_rez_pren": amount("VAT 25"),
            "rez_pren23": amount("VAT 10 Base"),
            "rez_pren5": amount("VAT 11 Base"),
        }

    def _sh_payload(self, moves):
        grouped = {}
        for move in moves.filtered(lambda record: record.move_type in {"out_invoice", "out_refund"}):
            partner = move.commercial_partner_id
            country_code = partner.country_id.code or ""
            if not country_code or country_code == "CZ":
                continue
            for line in move.line_ids.filtered(lambda aml: aml.tax_tag_ids):
                amount = self._line_amount_from_balance(line)
                for tag in line.tax_tag_ids:
                    if tag.name not in SH_LINE_TAGS:
                        continue
                    partner_country, vat_number = self._eu_vat_parts(partner.vat)
                    sh_country = partner_country or country_code
                    key = (sh_country, vat_number, SH_LINE_TAGS[tag.name])
                    grouped.setdefault(key, {"amount": Decimal("0.00"), "count": 0})
                    grouped[key]["amount"] += amount
                    grouped[key]["count"] += 1

        rows = []
        for row_no, ((country_code, vat_number, line_code), payload) in enumerate(sorted(grouped.items()), start=1):
            if not vat_number:
                continue
            rows.append(
                {
                    "c_rad": str(row_no),
                    "c_vat": vat_number,
                    "por_c_stran": "1",
                    "k_stat": country_code,
                    "k_pln_eu": line_code,
                    "pln_hodnota": self._whole_str(payload["amount"]),
                    "pln_pocet": str(payload["count"]),
                }
            )
        return rows

    def _validate_snapshot(self, snapshot):
        metadata = snapshot["metadata"]
        errors = []
        warnings = []

        if not metadata["ulice"] or not metadata["obec"] or not metadata["psc"]:
            errors.append(_("Company address must include street, city, and ZIP/PSC for Czech filing XML."))

        if not self._vat_core(metadata["dic"]):
            errors.append(_("Company VAT number must contain a usable core DIČ for Czech filing XML."))

        for move in snapshot["moves"]:
            partner = move.commercial_partner_id
            tag_names = self._move_tag_names(move)

            if tag_names & A1_TAGS:
                if move.move_type not in {"out_invoice", "out_refund"}:
                    errors.append(
                        _("Document %s uses VAT 25 tags but is not a customer invoice/refund for KH A1.")
                        % self._move_document_reference(move)
                    )
                if (partner.country_id.code or "") != "CZ":
                    errors.append(
                        _("Document %s uses VAT 25 tags but partner country is not CZ, so KH A1 cannot be generated.")
                        % self._move_document_reference(move)
                    )
                if not self._vat_core(partner.vat):
                    errors.append(
                        _("Document %s requires partner VAT for KH A1.")
                        % self._move_document_reference(move)
                    )
                if not move.l10n_cz_kh_reverse_charge_code:
                    errors.append(
                        _("Document %s requires CZ KH reverse charge code for KH A1.")
                        % self._move_document_reference(move)
                    )

            if tag_names & (set(A2_BASE_TAGS) | set(A2_TAX_TAGS)):
                if move.move_type not in {"in_invoice", "in_refund"}:
                    errors.append(
                        _("Document %s uses VAT 3/4/5/6/9/12/13 tags but is not a vendor bill/refund for KH A2.")
                        % self._move_document_reference(move)
                    )
                country_code, vat_number = self._partner_vat_identifier(partner)
                if not country_code or not vat_number:
                    errors.append(
                        _("Document %s requires partner country and VAT identifier for KH A2.")
                        % self._move_document_reference(move)
                    )

            if tag_names & (set(B1_BASE_TAGS) | set(B1_TAX_TAGS)):
                if move.move_type not in {"in_invoice", "in_refund"}:
                    errors.append(
                        _("Document %s uses VAT 10/11 tags but is not a vendor bill/refund for KH B1.")
                        % self._move_document_reference(move)
                    )
                if (partner.country_id.code or "") != "CZ":
                    errors.append(
                        _("Document %s uses VAT 10/11 tags but partner country is not CZ, so KH B1 cannot be generated.")
                        % self._move_document_reference(move)
                    )
                if not self._vat_core(partner.vat):
                    errors.append(
                        _("Document %s requires partner VAT for KH B1.")
                        % self._move_document_reference(move)
                    )
                if not self._move_reverse_charge_code(move):
                    errors.append(
                        _("Document %s requires CZ KH reverse charge code for KH B1.")
                        % self._move_document_reference(move)
                    )

            unsupported_tags = sorted(tag_names & UNSUPPORTED_VAT_TAGS)
            if unsupported_tags:
                errors.append(
                    _("Document %s uses Czech VAT tags that are not implemented in this exporter: %s.")
                    % (self._move_document_reference(move), ", ".join(unsupported_tags))
                )

            if move.move_type in {"out_invoice", "out_refund"} and (partner.country_id.code or "") == "CZ":
                if abs(move.amount_total) > 10000 and not self._vat_core(partner.vat):
                    warnings.append(
                        _("Domestic document %s exceeds 10.000 CZK but partner VAT is missing; it will not qualify for A4 detail.")
                        % self._move_document_reference(move)
                    )

            if move.move_type in {"in_invoice", "in_refund"} and (partner.country_id.code or "") == "CZ":
                has_b2_breakdown = self._breakdown_has_values(self._move_base_tax_breakdown(move))
                has_b1_breakdown = self._breakdown_has_values(self._move_breakdown_from_tags(move, B1_BASE_TAGS, B1_TAX_TAGS))
                if has_b2_breakdown and not has_b1_breakdown and abs(move.amount_total) > 10000 and not self._vat_core(partner.vat):
                    warnings.append(
                        _("Domestic document %s exceeds 10.000 CZK but partner VAT is missing; it will not qualify for KH B2 detail.")
                        % self._move_document_reference(move)
                    )

            has_sh_line = any(
                tag.name in SH_LINE_TAGS
                for line in move.line_ids.filtered(lambda aml: aml.tax_tag_ids)
                for tag in line.tax_tag_ids
            )
            if has_sh_line and not self._vat_core(partner.vat):
                errors.append(
                    _("EU document %s requires partner VAT for souhrnne hlaseni.")
                    % (move.name or move.ref or move.id)
                )

        return {"errors": errors, "warnings": warnings}

    def _period_options(self, company, date_from, date_to, options):
        partner = self._validate_company(company)
        period = self._infer_period(date_from, date_to, options.get("period_kind"))
        address = self._address_parts(partner)
        metadata = {
            "submission_date": options.get("submission_date", self._today_str()),
            "tax_statement_date": options.get("tax_statement_date", self._today_str()),
            "tax_office_code": options.get("tax_office_code", "200"),
            "tax_office_branch_code": options.get("tax_office_branch_code", "2000"),
            "nace_code": options.get("nace_code", "62010"),
            "phone": options.get("phone", partner.phone or "000000000"),
            "email": options.get("email", partner.email or "test@example.test"),
            "dph_taxpayer_type": options.get("dph_taxpayer_type", "P"),
            "dph_form": options.get("dph_form", "B"),
            "kh_form": options.get("kh_form", "B"),
            "sh_form": options.get("sh_form", "R"),
            "software_name": options.get("software_name", "OpenAI Codex"),
            "software_version": options.get("software_version", "19.0-test"),
            "name": partner.name or company.name,
            "dic": self._cz_vat(partner.vat),
            "dic_core": self._vat_core(partner.vat),
            "typ_ds": "P" if partner.company_type == "company" else "F",
            "jmeno": options.get("first_name", ""),
            "prijmeni": options.get("last_name", ""),
            "nazev_osoby": options.get("representative_name", ""),
            "trade_name_suffix": options.get("trade_name_suffix", ""),
            "dat_nar": options.get("birth_date", ""),
            "dic_puv": options.get("former_vat", ""),
            "ulice": options.get("street_name", address["ulice"]),
            "c_pop": options.get("street_number", address["c_pop"]),
            "c_orient": options.get("street_orient", address["c_orient"]),
            "obec": options.get("city", partner.city or ""),
            "psc": options.get("zip", (partner.zip or "").replace(" ", "")),
            "stat": options.get("country_code", partner.country_id.code or "CZ"),
        }
        return metadata, period

    def _build_snapshot(self, company, date_from, date_to, options):
        date_from = self._normalize_date(date_from)
        date_to = self._normalize_date(date_to)
        if date_from > date_to:
            raise UserError(_("The Czech VAT filing export requires date_from before date_to."))

        metadata, period = self._period_options(company, date_from, date_to, options)
        moves = self._posted_moves(company, date_from, date_to)
        snapshot = {
            "company": company,
            "date_from": date_from,
            "date_to": date_to,
            "metadata": metadata,
            "period": period,
            "moves": moves,
            "tag_names": sorted(self._tax_tag_names(moves)),
            "tag_amounts": self._tag_amounts(moves),
            "kh": self._kh_payload(moves),
            "sh": self._sh_payload(moves),
        }
        snapshot["validation"] = self._validate_snapshot(snapshot)
        if snapshot["validation"]["errors"]:
            raise UserError("\n".join(snapshot["validation"]["errors"]))
        return snapshot

    def _set_attrs(self, element, values):
        for key, value in values.items():
            if value in (None, "", False):
                continue
            element.set(key, str(value))

    def _add_form_root(self, form_name, metadata):
        root = ET.Element("Pisemnost")
        root.set("nazevSW", metadata["software_name"])
        root.set("verzeSW", metadata["software_version"])
        form = ET.SubElement(root, form_name)
        return root, form

    def _period_attrs(self, period):
        attrs = {"rok": period["year"]}
        if period["kind"] == "month":
            attrs["mesic"] = period["mesic"]
        else:
            attrs["ctvrt"] = period["ctvrt"]
        return attrs

    def _add_p_record(self, form, snapshot, form_name):
        metadata = snapshot["metadata"]
        attrs = {
            "c_ufo": metadata["tax_office_code"],
            "c_pracufo": metadata["tax_office_branch_code"],
            "dic": metadata["dic_core"],
            "typ_ds": metadata["typ_ds"],
            "ulice": metadata["ulice"],
            "c_pop": metadata["c_pop"],
            "c_orient": metadata["c_orient"],
            "naz_obce": metadata["obec"],
            "psc": metadata["psc"],
            "stat": metadata["stat"],
            "jmeno": metadata["jmeno"],
            "prijmeni": metadata["prijmeni"],
        }
        if metadata["typ_ds"] == "P":
            attrs["zkrobchjm"] = metadata["name"]
        if form_name in {"DPHDP3", "DPHKH1"}:
            attrs["c_telef"] = metadata["phone"]
            attrs["email"] = metadata["email"]
        if form_name == "DPHSHV":
            attrs["dodobchjm"] = metadata["trade_name_suffix"]

        record = ET.SubElement(form, "VetaP")
        self._set_attrs(record, attrs)

    def _serialize(self, root):
        raw = ET.tostring(root, encoding="utf-8")
        return minidom.parseString(raw).toprettyxml(indent="  ", encoding="utf-8").decode("utf-8")

    def _dph_totals_attrs(self, section_values):
        output_tax = sum(
            value
            for key, value in section_values["Veta1"].items()
            if key.startswith("dan") or key == "opr_dane_dan"
        )
        deduction_tax = sum(
            value
            for key, value in section_values["Veta4"].items()
            if key.startswith(("odp", "od_", "odkr_", "kor_odp_"))
        )
        attrs = {
            "dan_zocelk": self._whole_str(output_tax),
            "odp_zocelk": self._whole_str(deduction_tax),
        }
        difference = output_tax - deduction_tax
        if difference > 0:
            attrs["dano_da"] = self._whole_str(difference)
        elif difference < 0:
            attrs["dano_no"] = self._whole_str(-difference)
        return attrs

    def _dphdp3_xml(self, snapshot):
        metadata = snapshot["metadata"]
        root, form = self._add_form_root("DPHDP3", metadata)
        d_record = ET.SubElement(form, "VetaD")
        self._set_attrs(
            d_record,
            {
                "c_okec": metadata["nace_code"],
                "dokument": "DP3",
                "k_uladis": "DPH",
                "d_poddp": self._xml_date(metadata["submission_date"]),
                "dapdph_forma": metadata["dph_form"],
                **self._period_attrs(snapshot["period"]),
                "typ_platce": metadata["dph_taxpayer_type"],
                "dic_puv": metadata["dic_puv"],
            },
        )
        if metadata["dph_form"] in {"D", "E"}:
            d_record.set("d_zjist", self._xml_date(metadata["tax_statement_date"]))
        self._add_p_record(form, snapshot, "DPHDP3")

        section_values = defaultdict(lambda: defaultdict(Decimal))
        for move in snapshot["moves"]:
            proportional = move.l10n_cz_kh_proportional_deduction
            for tag_name, amount in self._move_tag_amounts(move).items():
                for section_name, field_name, proportional_field in DPH_FIELD_SPECS_BY_TAG.get(tag_name, []):
                    target_field = proportional_field if proportional and proportional_field else field_name
                    section_values[section_name][target_field] += amount

        for section_name in ["Veta1", "Veta2", "Veta3", "Veta4", "Veta5"]:
            values = section_values.get(section_name, {})
            if not any(values.values()):
                continue
            element = ET.SubElement(form, section_name)
            self._set_attrs(element, {key: self._whole_str(value) for key, value in values.items() if value})

        veta6_attrs = self._dph_totals_attrs(section_values)
        if any(veta6_attrs.values()):
            veta6 = ET.SubElement(form, "Veta6")
            self._set_attrs(veta6, veta6_attrs)
        return self._serialize(root)

    def _breakdown_attrs(self, breakdown):
        attrs = {}
        for slot in [1, 2, 3]:
            values = breakdown[slot]
            if values["base"]:
                attrs[f"zakl_dane{slot}"] = self._round_str(values["base"])
            if values["tax"]:
                attrs[f"dan{slot}"] = self._round_str(values["tax"])
        return attrs

    def _dphkh1_xml(self, snapshot):
        metadata = snapshot["metadata"]
        root, form = self._add_form_root("DPHKH1", metadata)
        d_record = ET.SubElement(form, "VetaD")
        self._set_attrs(
            d_record,
            {
                "dokument": "KH1",
                "k_uladis": "DPH",
                "d_poddp": self._xml_date(metadata["submission_date"]),
                "khdph_forma": metadata["kh_form"],
                **self._period_attrs(snapshot["period"]),
            },
        )
        if metadata["kh_form"] in {"N", "E"}:
            d_record.set("d_zjist", self._xml_date(metadata["tax_statement_date"]))
        self._add_p_record(form, snapshot, "DPHKH1")

        for index, row in enumerate(snapshot["kh"]["A1"], start=1):
            element = ET.SubElement(form, "VetaA1")
            self._set_attrs(
                element,
                {
                    "dic_odb": row["vat"],
                    "c_evid_dd": row["reference"],
                    "c_radku": str(index),
                    "duzp": row["date"],
                    "kod_pred_pl": row["reverse_charge_code"],
                    "zakl_dane1": self._round_str(row["base_amount"]),
                },
            )

        for index, row in enumerate(snapshot["kh"]["A2"], start=1):
            element = ET.SubElement(form, "VetaA2")
            attrs = {
                "c_evid_dd": row["reference"],
                "c_radku": str(index),
                "dppd": row["date"],
                "k_stat": row["country_code"],
                "vatid_dod": row["vat_number"],
            }
            attrs.update(self._breakdown_attrs(row["breakdown"]))
            self._set_attrs(element, attrs)

        for index, row in enumerate(snapshot["kh"]["A4"], start=1):
            element = ET.SubElement(form, "VetaA4")
            attrs = {
                "dic_odb": row["vat"],
                "c_evid_dd": row["reference"],
                "c_radku": str(index),
                "dppd": row["date"],
                "kod_rezim_pl": "0",
                "zdph_44": "N",
            }
            attrs.update(self._breakdown_attrs(row["breakdown"]))
            self._set_attrs(element, attrs)

        a5 = snapshot["kh"]["A5"]
        if a5["count"]:
            element = ET.SubElement(form, "VetaA5")
            self._set_attrs(element, self._breakdown_attrs(a5["breakdown"]))

        for index, row in enumerate(snapshot["kh"]["B1"], start=1):
            element = ET.SubElement(form, "VetaB1")
            self._set_attrs(
                element,
                {
                    "dic_dod": row["vat"],
                    "c_evid_dd": row["reference"],
                    "c_radku": str(index),
                    "duzp": row["date"],
                    "kod_pred_pl": row["reverse_charge_code"],
                    "zakl_dane1": self._round_str(row["base_amount"]),
                },
            )

        for index, row in enumerate(snapshot["kh"]["B2"], start=1):
            element = ET.SubElement(form, "VetaB2")
            attrs = {
                "dic_dod": row["vat"],
                "c_evid_dd": row["reference"],
                "c_radku": str(index),
                "dppd": row["date"],
                "pomer": row["proportional"],
                "zdph_44": "N",
            }
            attrs.update(self._breakdown_attrs(row["breakdown"]))
            self._set_attrs(element, attrs)

        b3 = snapshot["kh"]["B3"]
        if b3["count"]:
            element = ET.SubElement(form, "VetaB3")
            self._set_attrs(element, self._breakdown_attrs(b3["breakdown"]))

        veta_c = ET.SubElement(form, "VetaC")
        self._set_attrs(veta_c, self._kh_control_attrs(snapshot))
        return self._serialize(root)

    def _dphshv_xml(self, snapshot):
        metadata = snapshot["metadata"]
        root, form = self._add_form_root("DPHSHV", metadata)
        d_record = ET.SubElement(form, "VetaD")
        self._set_attrs(
            d_record,
            {
                "dokument": "SHV",
                "k_uladis": "DPH",
                "d_poddp": self._xml_date(metadata["submission_date"]),
                "shvies_forma": metadata["sh_form"],
                **self._period_attrs(snapshot["period"]),
            },
        )
        self._add_p_record(form, snapshot, "DPHSHV")
        for row in snapshot["sh"]:
            element = ET.SubElement(form, "VetaR")
            self._set_attrs(element, row)
        return self._serialize(root)

    def _debug_payload(self, snapshot):
        return {
            "date_from": str(snapshot["date_from"]),
            "date_to": str(snapshot["date_to"]),
            "period": snapshot["period"],
            "metadata": snapshot["metadata"],
            "validation": snapshot["validation"],
            "move_ids": snapshot["moves"].ids,
            "tag_amounts": {key: self._round_str(value) for key, value in sorted(snapshot["tag_amounts"].items())},
            "kh": {
                "A1": [
                    {
                        "vat": row["vat"],
                        "reference": row["reference"],
                        "date": row["date"],
                        "reverse_charge_code": row["reverse_charge_code"],
                        "base_amount": self._round_str(row["base_amount"]),
                    }
                    for row in snapshot["kh"]["A1"]
                ],
                "A2": [
                    {
                        "country_code": row["country_code"],
                        "vat_number": row["vat_number"],
                        "reference": row["reference"],
                        "date": row["date"],
                        "breakdown": {
                            str(slot): {
                                "base": self._round_str(values["base"]),
                                "tax": self._round_str(values["tax"]),
                            }
                            for slot, values in row["breakdown"].items()
                        },
                    }
                    for row in snapshot["kh"]["A2"]
                ],
                "A4": [
                    {
                        "vat": row["vat"],
                        "reference": row["reference"],
                        "date": row["date"],
                        "breakdown": {
                            str(slot): {
                                "base": self._round_str(values["base"]),
                                "tax": self._round_str(values["tax"]),
                            }
                            for slot, values in row["breakdown"].items()
                        },
                    }
                    for row in snapshot["kh"]["A4"]
                ],
                "A5": {
                    "count": snapshot["kh"]["A5"]["count"],
                    "breakdown": {
                        str(slot): {
                            "base": self._round_str(values["base"]),
                            "tax": self._round_str(values["tax"]),
                        }
                        for slot, values in snapshot["kh"]["A5"]["breakdown"].items()
                    },
                },
                "B1": [
                    {
                        "vat": row["vat"],
                        "reference": row["reference"],
                        "date": row["date"],
                        "reverse_charge_code": row["reverse_charge_code"],
                        "base_amount": self._round_str(row["base_amount"]),
                    }
                    for row in snapshot["kh"]["B1"]
                ],
                "B2": [
                    {
                        "vat": row["vat"],
                        "reference": row["reference"],
                        "date": row["date"],
                        "proportional": row["proportional"],
                        "breakdown": {
                            str(slot): {
                                "base": self._round_str(values["base"]),
                                "tax": self._round_str(values["tax"]),
                            }
                            for slot, values in row["breakdown"].items()
                        },
                    }
                    for row in snapshot["kh"]["B2"]
                ],
                "B3": {
                    "count": snapshot["kh"]["B3"]["count"],
                    "breakdown": {
                        str(slot): {
                            "base": self._round_str(values["base"]),
                            "tax": self._round_str(values["tax"]),
                        }
                        for slot, values in snapshot["kh"]["B3"]["breakdown"].items()
                    },
                },
                "C": {
                    "supply_count": snapshot["kh"]["C"]["supply_count"],
                    "supply_base": self._round_str(snapshot["kh"]["C"]["supply_base"]),
                    "deduction_count": snapshot["kh"]["C"]["deduction_count"],
                    "deduction_base": self._round_str(snapshot["kh"]["C"]["deduction_base"]),
                },
            },
            "sh": snapshot["sh"],
        }

    def build_exports(self, company, date_from, date_to, options=None):
        snapshot = self._build_snapshot(company, date_from, date_to, options or {})
        debug_payload = self._debug_payload(snapshot)
        return {
            "debug": debug_payload,
            "debug_json": json.dumps(debug_payload, ensure_ascii=False, indent=2, sort_keys=True),
            "dphdp3_xml": self._dphdp3_xml(snapshot),
            "dphkh1_xml": self._dphkh1_xml(snapshot),
            "dphshv_xml": self._dphshv_xml(snapshot),
        }
