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
    "VAT 23": [("Veta2", "dod_dop_nrg", None)],
    "VAT 24": [("Veta2", "pln_zaslani", None)],
    "VAT 25": [("Veta2", "pln_rez_pren", None)],
    "VAT 26": [("Veta2", "pln_ost", None)],
    "VAT 30": [("Veta3", "tri_pozb", None)],
    "VAT 31": [("Veta3", "tri_dozb", None)],
    "VAT 32": [("Veta3", "dov_osv", None)],
    "VAT 33": [("Veta1", "opr_dane_dan", None), ("Veta3", "opr_verit", None)],
    "VAT 34": [("Veta3", "opr_dluz", None)],
    "VAT 40 Base": [("Veta4", "pln23", None)],
    "VAT 40 Total": [("Veta4", "odp_tuz23_nar", "odp_tuz23")],
    "VAT 41 Base": [("Veta4", "pln5", None)],
    "VAT 41 Total": [("Veta4", "odp_tuz5_nar", "odp_tuz5")],
    "VAT 42 Base": [("Veta4", "dov_cu", None)],
    "VAT 42 Total": [("Veta4", "odp_cu_nar", "odp_cu")],
    "VAT 45 Full": [("Veta4", "odp_rez_nar", None)],
    "VAT 45 Reduced": [("Veta4", "odp_rezim", None)],
    "VAT 47 Base": [("Veta4", "nar_maj", None)],
    "VAT 47 Total": [("Veta4", "od_maj", "odkr_maj")],
    "VAT 50": [("Veta5", "plnosv_kf", None)],
    "VAT 51 with deduction": [("Veta5", "pln_nkf", None)],
    "VAT 51 without deduction": [("Veta5", "plnosv_nkf", None)],
    "VAT 61": [("Veta6", "dan_vrac", None)],
}

DPH_COEFFICIENT_TRIGGER_BY_TAG = {
    "VAT 40 Total": "VAT 40 Coefficient",
    "VAT 41 Total": "VAT 41 Coefficient",
    "VAT 42 Total": "VAT 42 Coefficient",
}

# Temporary domestic reverse-charge regimes (e.g. selected goods) require a
# minimum taxable base of 100.000 CZK without VAT.
RPDP_TEMPORARY_THRESHOLD_CODES = {"11", "14"}
RPDP_TEMPORARY_THRESHOLD_BASE = Decimal("100000.00")

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
DPH_BAD_DEBT_SALE_EXCLUDED_TAGS = {"VAT 1 Base", "VAT 1 Tax", "VAT 2 Base", "VAT 2 Tax"}
SH_LINE_TAGS = {"VAT 20": "0", "VAT 21": "3", "VAT 31": "2"}
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
IMPORT_OUTPUT_TAGS = {"VAT 7 Base", "VAT 7 Tax", "VAT 8 Base", "VAT 8 Tax"}
IMPORT_DEDUCTION_TAGS = {"VAT 42 Base", "VAT 42 Total"}
IMPORT_CORRECTION_TAGS = {"VAT 45 Full", "VAT 45 Reduced"}
IMPORT_TAGS = IMPORT_OUTPUT_TAGS | IMPORT_DEDUCTION_TAGS | IMPORT_CORRECTION_TAGS
KH_DRIVING_TAGS = (
    set(KH_BASE_TAGS)
    | set(KH_TAX_TAGS)
    | A1_TAGS
    | set(A2_BASE_TAGS)
    | set(A2_TAX_TAGS)
    | set(B1_BASE_TAGS)
    | set(B1_TAX_TAGS)
    | {"VAT 33", "VAT 34"}
)
STANDARD_CZ_EXCLUDED_REGIMES = {"oss", "ioss"}
STANDARD_CZ_FILING_TAGS = set(DPH_FIELD_SPECS_BY_TAG) | KH_DRIVING_TAGS | set(SH_LINE_TAGS)
SUPPORTED_VAT_TAGS = set(DPH_FIELD_SPECS_BY_TAG)
UNSUPPORTED_VAT_TAGS = set()

DPH_OPTION_FIELD_SPECS = {
    "line_45_full_deduction": ("Veta4", "odp_rez_nar"),
    "line_45_reduced_deduction": ("Veta4", "odp_rezim"),
    "line_48_base_amount": ("Veta4", "kor_odp_zd"),
    "line_48_full_deduction": ("Veta4", "kor_odp_plne"),
    "line_48_reduced_deduction": ("Veta4", "kor_odp_krac"),
    "line_52a_coefficient": ("Veta5", "koef_p20_nov"),
    "line_52b_deduction": ("Veta5", "odp_uprav_kf"),
    "line_53a_settlement_coefficient": ("Veta5", "koef_p20_vypor"),
    "line_53b_change_deduction": ("Veta5", "vypor_odp"),
    "line_60_adjustment": ("Veta6", "uprav_odp"),
}

DPH_LEGACY_OPTION_ALIASES = {
    "line_45_in_full_amount": "line_48_full_deduction",
    "line_45_reduced_claim": "line_48_reduced_deduction",
}

DPH_ROW46_FULL_FIELDS = {
    "odp_tuz23_nar",
    "odp_tuz5_nar",
    "odp_cu_nar",
    "od_zdp23",
    "od_zdp5",
    "odp_rez_nar",
}

DPH_ROW46_REDUCED_FIELDS = {
    "odp_tuz23",
    "odp_tuz5",
    "odp_cu",
    "odkr_zdp23",
    "odkr_zdp5",
    "odp_rezim",
}

DPH_COEFFICIENT_NUMERATOR_FIELDS = [
    ("Veta1", "obrat23"),
    ("Veta1", "obrat5"),
    ("Veta2", "dod_zb"),
    ("Veta2", "pln_sluzby"),
    ("Veta2", "pln_vyvoz"),
    ("Veta2", "dod_dop_nrg"),
    ("Veta2", "pln_zaslani"),
    ("Veta2", "pln_rez_pren"),
    ("Veta2", "pln_ost"),
    ("Veta3", "tri_dozb"),
    ("Veta5", "pln_nkf"),
]

DPH_COEFFICIENT_DENOMINATOR_EXTRA_FIELDS = [
    ("Veta5", "plnosv_kf"),
]


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

    def _first_day_of_year(self, value):
        return value.replace(month=1, day=1)

    def _last_day_of_year(self, value):
        return value.replace(month=12, day=31)

    def _first_day_of_quarter(self, value):
        quarter_month = (((value.month - 1) // 3) * 3) + 1
        return value.replace(month=quarter_month, day=1)

    def _last_day_of_quarter(self, value):
        quarter_start = self._first_day_of_quarter(value)
        quarter_end_month = quarter_start.month + 2
        return value.replace(
            month=quarter_end_month,
            day=calendar.monthrange(value.year, quarter_end_month)[1],
        )

    def _normalize_date(self, value):
        if isinstance(value, str):
            return fields.Date.from_string(value)
        return value

    def _truthy(self, value):
        if isinstance(value, bool):
            return value
        if value in (None, "", 0, 0.0):
            return False
        return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}

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

    def _move_dph_tax_date(self, move):
        return (
            move.l10n_cz_dph_tax_date
            or move.invoice_date
            or move.date
            or fields.Date.today()
        )

    def _czk_currency(self, company):
        if company.currency_id and company.currency_id.name == "CZK":
            return company.currency_id
        currency = self.env["res.currency"].search([("name", "=", "CZK")], limit=1)
        return currency or company.currency_id

    def _move_amount_total_czk(self, move):
        amount = self._decimal(abs(move.amount_total))
        company = move.company_id
        source_currency = move.currency_id or company.currency_id
        target_currency = self._czk_currency(company)
        if not source_currency or source_currency == target_currency:
            return amount
        vat_fx_rate = self._move_vat_fx_rate(move)
        if vat_fx_rate:
            return self._decimal(amount * vat_fx_rate)
        converted = source_currency._convert(
            float(amount),
            target_currency,
            company,
            self._move_dph_tax_date(move),
            round=False,
        )
        return self._decimal(converted)

    def _move_vat_fx_rate(self, move):
        company = move.company_id
        if not company.l10n_cz_vat_fx_enforce_cnb:
            return None
        source_currency = move.currency_id or company.currency_id
        target_currency = self._czk_currency(company)
        if not source_currency or source_currency == target_currency:
            return None
        if move.l10n_cz_vat_fx_manual_rate and move.l10n_cz_vat_fx_manual_rate > 0:
            return self._decimal(move.l10n_cz_vat_fx_manual_rate)
        if move.l10n_cz_vat_fx_rate and move.l10n_cz_vat_fx_rate > 0:
            return self._decimal(move.l10n_cz_vat_fx_rate)
        resolved_rate, _rate_record = company.l10n_cz_vat_fx_rate_for_move(move)
        if resolved_rate:
            return self._decimal(resolved_rate)
        return None

    def _refund_origin_requires_detail(self, move):
        if move.move_type not in {"out_refund", "in_refund"}:
            return False
        origin = move.reversed_entry_id
        if not origin:
            return False
        expected_origin_type = "out_invoice" if move.move_type == "out_refund" else "in_invoice"
        if origin.move_type != expected_origin_type:
            return False
        return self._move_amount_total_czk(origin) > Decimal("10000.00")

    def _period_move_domain(self, company, date_from, date_to):
        return [
            ("company_id", "=", company.id),
            ("state", "=", "posted"),
            ("move_type", "in", ["out_invoice", "out_refund", "in_invoice", "in_refund"]),
            "|",
            "|",
            "&",
            "&",
            ("l10n_cz_dph_tax_date", "!=", False),
            ("l10n_cz_dph_tax_date", ">=", date_from),
            ("l10n_cz_dph_tax_date", "<=", date_to),
            "&",
            "&",
            "&",
            ("l10n_cz_dph_tax_date", "=", False),
            ("invoice_date", "!=", False),
            ("invoice_date", ">=", date_from),
            ("invoice_date", "<=", date_to),
            "&",
            "&",
            "&",
            ("l10n_cz_dph_tax_date", "=", False),
            ("invoice_date", "=", False),
            ("date", ">=", date_from),
            ("date", "<=", date_to),
        ]

    def _period_moves(self, company, date_from, date_to):
        domain = self._period_move_domain(company, date_from, date_to)
        return self.env["account.move"].search(domain, order="date,id")

    def _posted_moves(self, company, date_from, date_to):
        moves = self._period_moves(company, date_from, date_to)
        return moves.filtered(
            lambda move: (move.l10n_cz_vat_regime or "standard") not in STANDARD_CZ_EXCLUDED_REGIMES
        )

    def _requested_forms(self, options):
        return {
            "dphdp3": self._truthy(options.get("include_dphdp3", True)),
            "dphkh1": self._truthy(options.get("include_dphkh1", True)),
            "dphshv": self._truthy(options.get("include_dphshv", True)),
        }

    def _period_bounds(self, reference_date, period):
        if period["kind"] == "month":
            return self._first_day_of_month(reference_date), self._last_day_of_month(reference_date)
        return self._first_day_of_quarter(reference_date), self._last_day_of_quarter(reference_date)

    def _period_range_override(self, date_from, date_to, period, options):
        explicit_from = options.get("period_from")
        explicit_to = options.get("period_to")
        if explicit_from or explicit_to:
            if not explicit_from or not explicit_to:
                raise UserError(_("Czech filing period overrides require both period_from and period_to."))
            return {
                "from": self._normalize_date(explicit_from),
                "to": self._normalize_date(explicit_to),
            }

        period_start, period_end = self._period_bounds(date_from, period)
        if date_from == period_start and date_to == period_end:
            return None
        return {
            "from": date_from,
            "to": date_to,
        }

    def _normalize_options(self, options):
        normalized = dict(options)
        warnings = []
        conflicts = []
        for legacy_name, canonical_name in DPH_LEGACY_OPTION_ALIASES.items():
            if legacy_name not in normalized:
                continue
            if canonical_name in normalized:
                if self._decimal(normalized[legacy_name]) != self._decimal(normalized[canonical_name]):
                    conflicts.append((legacy_name, canonical_name))
                continue
            normalized[canonical_name] = normalized[legacy_name]
            warnings.append(
                _("DPH export option %s is deprecated; use %s instead.")
                % (legacy_name, canonical_name)
            )
        return normalized, warnings, conflicts

    def _merge_section_values(self, target, source):
        for section_name, values in source.items():
            for field_name, amount in values.items():
                target[section_name][field_name] += amount

    def _move_manual_dph_values(self, move):
        values = defaultdict(lambda: defaultdict(Decimal))
        if move.l10n_cz_dph_line_45_full_deduction:
            values["Veta4"]["odp_rez_nar"] += self._decimal(move.l10n_cz_dph_line_45_full_deduction)
        if move.l10n_cz_dph_line_45_reduced_deduction:
            values["Veta4"]["odp_rezim"] += self._decimal(move.l10n_cz_dph_line_45_reduced_deduction)
        if move.l10n_cz_dph_line_48_base_amount:
            values["Veta4"]["kor_odp_zd"] += self._decimal(move.l10n_cz_dph_line_48_base_amount)
        if move.l10n_cz_dph_line_48_full_deduction:
            values["Veta4"]["kor_odp_plne"] += self._decimal(move.l10n_cz_dph_line_48_full_deduction)
        if move.l10n_cz_dph_line_48_reduced_deduction:
            values["Veta4"]["kor_odp_krac"] += self._decimal(move.l10n_cz_dph_line_48_reduced_deduction)
        if move.l10n_cz_dph_line_60_adjustment:
            values["Veta6"]["uprav_odp"] += self._decimal(move.l10n_cz_dph_line_60_adjustment)
        if self._move_has_any_tag(move, {"VAT 33"}):
            base_amount = self._move_tag_amount(move, {"VAT 1 Base", "VAT 2 Base"})
            if base_amount:
                values["Veta1"]["opr_dane_zd"] += base_amount
        return values

    def _raw_dph_section_values(self, moves):
        section_values = defaultdict(lambda: defaultdict(Decimal))
        for move in moves:
            excluded_tags = self._dph_move_excluded_tags(move)
            for line in move.line_ids.filtered(lambda aml: aml.tax_tag_ids):
                amount = self._line_amount_from_balance(line)
                line_tags = {tag.name for tag in line.tax_tag_ids}
                for tag_name in line_tags:
                    if tag_name in excluded_tags:
                        continue
                    use_reduced_field = move.l10n_cz_kh_proportional_deduction or (
                        DPH_COEFFICIENT_TRIGGER_BY_TAG.get(tag_name) in line_tags
                    )
                    for section_name, field_name, proportional_field in DPH_FIELD_SPECS_BY_TAG.get(tag_name, []):
                        target_field = proportional_field if use_reduced_field and proportional_field else field_name
                        section_values[section_name][target_field] += amount
            self._merge_section_values(section_values, self._move_manual_dph_values(move))
        return section_values

    def _section_total(self, section_values, field_refs):
        total = Decimal("0.00")
        for section_name, field_name in field_refs:
            total += section_values.get(section_name, {}).get(field_name, Decimal("0.00"))
        return total

    def _proportional_source_total(self, section_values):
        return sum(
            section_values["Veta4"].get(field_name, Decimal("0.00"))
            for field_name in DPH_ROW46_REDUCED_FIELDS
        )

    def _year_end_period(self, snapshot):
        if self._truthy(snapshot["options"].get("force_settlement_coefficient")):
            return True
        period = snapshot["period"]
        return (period["kind"] == "month" and period["mesic"] == "12") or (
            period["kind"] == "quarter" and period["ctvrt"] == "4"
        )

    def _coefficient_from_section_values(self, section_values):
        numerator = self._section_total(section_values, DPH_COEFFICIENT_NUMERATOR_FIELDS)
        denominator = numerator + self._section_total(section_values, DPH_COEFFICIENT_DENOMINATOR_EXTRA_FIELDS)
        if not denominator:
            return None
        return (numerator * Decimal("100.00") / denominator).quantize(TWOPLACES, rounding=ROUND_HALF_UP)

    def _annual_raw_dph_section_values(self, company, year):
        date_from = fields.Date.from_string(f"{year}-01-01")
        date_to = fields.Date.from_string(f"{year}-12-31")
        return self._raw_dph_section_values(self._posted_moves(company, date_from, date_to))

    def _advance_coefficient(self, snapshot):
        explicit = snapshot["options"].get("line_52a_coefficient")
        if explicit not in (None, "", False):
            return self._decimal(explicit)
        company = snapshot["company"]
        if company.l10n_cz_dph_use_manual_advance_coefficient:
            return self._decimal(company.l10n_cz_dph_advance_coefficient)
        previous_year = int(snapshot["period"]["year"]) - 1
        return self._coefficient_from_section_values(
            self._annual_raw_dph_section_values(company, previous_year)
        )

    def _settlement_coefficient(self, snapshot):
        explicit = snapshot["options"].get("line_53a_settlement_coefficient")
        if explicit not in (None, "", False):
            return self._decimal(explicit)
        if not self._year_end_period(snapshot):
            return None
        year = int(snapshot["period"]["year"])
        return self._coefficient_from_section_values(
            self._annual_raw_dph_section_values(snapshot["company"], year)
        )

    def _line_amount_from_balance(self, line):
        vat_fx_amount = self._line_amount_from_vat_fx(line)
        if vat_fx_amount is not None:
            return vat_fx_amount
        return self._decimal(abs(line.balance) * self._move_sign(line.move_id))

    def _line_amount_from_vat_fx(self, line):
        move = line.move_id
        vat_fx_rate = self._move_vat_fx_rate(move)
        if not vat_fx_rate:
            return None
        if not line.amount_currency:
            return None
        amount_currency = self._decimal(abs(line.amount_currency))
        return self._decimal(amount_currency * self._move_sign(move) * vat_fx_rate)

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

    def _import_customs_field_value(self, move, field_name):
        value = getattr(move, field_name)
        if value:
            return value
        origin = move.l10n_cz_import_correction_origin_id
        if origin:
            return getattr(origin, field_name)
        return False

    def _has_import_customs_reference(self, move):
        return bool(
            self._import_customs_field_value(move, "l10n_cz_customs_mrn")
            or self._import_customs_field_value(move, "l10n_cz_customs_decision_number")
        )

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
            or move.l10n_cz_dph_tax_date
            or move.invoice_date
            or move.date
            or fields.Date.today()
        )

    def _move_deduction_date(self, move):
        return self._xml_date(
            move.l10n_cz_kh_deduction_date
            or move.l10n_cz_dph_tax_date
            or move.date
            or move.invoice_date
            or fields.Date.today()
        )

    def _move_proportional_flag(self, move):
        return "A" if move.l10n_cz_kh_proportional_deduction else "N"

    def _move_line_subject_codes(self, move, tag_names):
        tag_names = set(tag_names)
        codes = set()
        for line in move.line_ids.filtered(lambda aml: aml.tax_tag_ids and aml.l10n_cz_kh_subject_code):
            line_tags = {tag.name for tag in line.tax_tag_ids}
            if line_tags & tag_names:
                codes.add(line.l10n_cz_kh_subject_code)
        return sorted(codes)

    def _move_reverse_charge_code_for_tags(self, move, tag_names):
        line_codes = self._move_line_subject_codes(move, tag_names)
        if len(line_codes) > 1:
            return "", line_codes
        if line_codes:
            return line_codes[0], line_codes
        return move.l10n_cz_kh_reverse_charge_code or "", []

    def _move_reverse_charge_code(self, move):
        return move.l10n_cz_kh_reverse_charge_code or ""

    def _partner_vat_identifier(self, partner):
        country_code = partner.country_id.code or ""
        vat_country, vat_number = self._eu_vat_parts(partner.vat)
        return vat_country or country_code, vat_number or self._vat_core(partner.vat)

    def _move_has_any_tag(self, move, tag_names):
        return bool(self._move_tag_names(move).intersection(set(tag_names)))

    def _dph_move_excluded_tags(self, move):
        excluded = set()
        if self._move_has_any_tag(move, {"VAT 33"}):
            excluded |= DPH_BAD_DEBT_SALE_EXCLUDED_TAGS
        return excluded

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
        reverse_charge_code, _line_codes = self._move_reverse_charge_code_for_tags(move, A1_TAGS)
        return {
            "vat": self._vat_core(partner.vat),
            "reference": self._move_document_reference(move),
            "date": self._move_tax_point_date(move),
            "reverse_charge_code": reverse_charge_code,
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
        amount_total = self._move_amount_total_czk(move)
        vat = self._vat_core(partner.vat)
        bad_debt_adjustment = self._move_has_any_tag(move, {"VAT 33"})
        detailed_refund = bool(vat) and self._refund_origin_requires_detail(move)
        category = (
            "A4"
            if bad_debt_adjustment or detailed_refund or (vat and amount_total > Decimal("10000.00"))
            else "A5"
        )
        return {
            "category": category,
            "vat": vat,
            "reference": self._move_document_reference(move),
            "date": self._move_tax_point_date(move),
            "breakdown": breakdown,
            "total_base": total_base,
            "zdph_44": "P" if bad_debt_adjustment else "N",
        }

    def _kh_b1_row(self, move):
        partner = move.commercial_partner_id
        if move.move_type not in {"in_invoice", "in_refund"} or (partner.country_id.code or "") != "CZ":
            return None
        breakdown = self._move_breakdown_from_tags(move, B1_BASE_TAGS, B1_TAX_TAGS)
        if not self._breakdown_has_values(breakdown):
            return None
        base_amount = self._move_tag_amount(move, B1_BASE_TAGS)
        reverse_charge_code, _line_codes = self._move_reverse_charge_code_for_tags(
            move, set(B1_BASE_TAGS) | set(B1_TAX_TAGS)
        )
        return {
            "vat": self._vat_core(partner.vat),
            "reference": self._move_document_reference(move),
            "date": self._move_tax_point_date(move),
            "reverse_charge_code": reverse_charge_code,
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
        amount_total = self._move_amount_total_czk(move)
        vat = self._vat_core(partner.vat)
        bad_debt_adjustment = self._move_has_any_tag(move, {"VAT 34"})
        detailed_refund = bool(vat) and self._refund_origin_requires_detail(move)
        category = (
            "B2"
            if bad_debt_adjustment or detailed_refund or (vat and amount_total > Decimal("10000.00"))
            else "B3"
        )
        return {
            "category": category,
            "vat": vat,
            "reference": self._move_document_reference(move),
            "date": self._move_tax_point_date(move),
            "proportional": self._move_proportional_flag(move),
            "breakdown": breakdown,
            "total_base": total_base,
            "zdph_44": "P" if bad_debt_adjustment else "N",
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
        options = snapshot["options"]
        requested_forms = snapshot["requested_forms"]
        errors = []
        warnings = list(snapshot.get("option_warnings", []))
        company_partner = snapshot["company"].partner_id.commercial_partner_id
        explicit_tax_statement_date = bool(snapshot.get("raw_options", {}).get("tax_statement_date"))
        submission_date = self._normalize_date(metadata["submission_date"]) if metadata["submission_date"] else None
        tax_statement_date = (
            self._normalize_date(metadata["tax_statement_date"]) if metadata["tax_statement_date"] else None
        )

        for legacy_name, canonical_name in snapshot.get("option_alias_conflicts", []):
            errors.append(
                _("DPH export options %s and %s conflict; keep only the canonical name.")
                % (legacy_name, canonical_name)
            )

        if submission_date and tax_statement_date and tax_statement_date > submission_date:
            errors.append(
                _("tax_statement_date (d_zjist) cannot be later than submission_date (d_poddp).")
            )

        if not metadata["ulice"] or not metadata["obec"] or not metadata["psc"]:
            errors.append(_("Company address must include street, city, and ZIP/PSC for Czech filing XML."))

        if not self._vat_core(metadata["dic"]):
            errors.append(_("Company VAT number must contain a usable core DIČ for Czech filing XML."))

        if not any(requested_forms.values()):
            errors.append(_("Enable at least one Czech filing export form."))

        if requested_forms["dphdp3"] and metadata["dph_form"] in {"D", "E"} and not explicit_tax_statement_date:
            errors.append(
                _("Dodatecne or opravne DPH exports require an explicit tax_statement_date for VetaD d_zjist.")
            )

        if requested_forms["dphkh1"] and metadata["kh_form"] in {"N", "E"} and not (
            explicit_tax_statement_date or metadata["kh_challenge_reference"]
        ):
            errors.append(
                _("Nasledne or opravne KH exports require tax_statement_date or kh_challenge_reference.")
            )

        if requested_forms["dphkh1"] and snapshot["period"]["kind"] == "quarter" and company_partner.company_type == "company":
            errors.append(
                _("Czech KH for legal entities is monthly, so quarterly exports must disable include_dphkh1.")
            )

        if requested_forms["dphkh1"] and snapshot["period_range_override"] and company_partner.company_type == "company":
            errors.append(
                _("Partial-period KH exports are not valid for Czech legal entities; disable include_dphkh1 or use a natural-person taxpayer.")
            )

        if requested_forms["dphshv"] and snapshot["period"]["kind"] == "quarter":
            invalid_quarter_codes = {
                row["k_pln_eu"]
                for row in snapshot["sh"]
                if row["k_pln_eu"] in {"0", "2"}
            }
            if invalid_quarter_codes:
                errors.append(
                    _(
                        "Quarterly souhrnne hlaseni is only valid for service rows. "
                        "Current data includes non-service line codes: %s. Disable include_dphshv or export monthly."
                    )
                    % ", ".join(sorted(invalid_quarter_codes))
                )

        if metadata["kh_challenge_response"] and not metadata["kh_challenge_reference"]:
            errors.append(_("kh_challenge_response requires kh_challenge_reference."))

        if metadata["kh_challenge_response"] and (
            snapshot["kh"]["A1"]
            or snapshot["kh"]["A2"]
            or snapshot["kh"]["A4"]
            or snapshot["kh"]["A5"]["count"]
            or snapshot["kh"]["B1"]
            or snapshot["kh"]["B2"]
            or snapshot["kh"]["B3"]["count"]
        ):
            errors.append(
                _(
                    "KH challenge-response mode cannot include A/B detail rows. "
                    "Disable kh_challenge_response for a normal nasledne KH export."
                )
            )

        for move in snapshot.get("excluded_regime_moves", []):
            filing_tags = sorted(self._move_tag_names(move) & STANDARD_CZ_FILING_TAGS)
            if filing_tags:
                errors.append(
                    _(
                        "Document %s is marked as %s but still carries Czech filing tags: %s. "
                        "Use non-Czech taxes for OSS/IOSS moves so they stay outside the standard CZ exports."
                    )
                    % (
                        self._move_document_reference(move),
                        (move.l10n_cz_vat_regime or "standard").upper(),
                        ", ".join(filing_tags),
                    )
                )

        for move in snapshot["moves"]:
            partner = move.commercial_partner_id
            tag_names = self._move_tag_names(move)
            correction_origin = move.l10n_cz_import_correction_origin_id

            if (tag_names & IMPORT_TAGS) and (tag_names & KH_DRIVING_TAGS):
                errors.append(
                    _(
                        "Document %s mixes 3rd-country import tags with KH-driving tags. "
                        "Imports from third countries must not leak into KH detail."
                    )
                    % self._move_document_reference(move)
                )

            if move.l10n_cz_vat_regime == "third_country_import" and tag_names & KH_DRIVING_TAGS:
                errors.append(
                    _(
                        "Document %s is marked as a 3rd-country import but still carries KH-driving tags."
                    )
                    % self._move_document_reference(move)
                )

            if correction_origin:
                if correction_origin == move:
                    errors.append(
                        _("Document %s cannot reference itself as import correction origin.")
                        % self._move_document_reference(move)
                    )
                if correction_origin.company_id != move.company_id:
                    errors.append(
                        _("Document %s references an import correction origin from another company.")
                        % self._move_document_reference(move)
                    )
                if correction_origin.state != "posted":
                    errors.append(
                        _("Document %s references an import correction origin that is not posted.")
                        % self._move_document_reference(move)
                    )

            if tag_names & IMPORT_CORRECTION_TAGS:
                if move.move_type not in {"in_invoice", "in_refund"}:
                    errors.append(
                        _("Document %s uses VAT 45 correction tags but is not a vendor bill/refund.")
                        % self._move_document_reference(move)
                    )
                if move.l10n_cz_vat_regime != "third_country_import":
                    errors.append(
                        _("Document %s uses VAT 45 correction tags but is not marked as 3rd-country import.")
                        % self._move_document_reference(move)
                    )
                if not correction_origin:
                    errors.append(
                        _("Document %s uses VAT 45 correction tags but is missing Import Correction Origin.")
                        % self._move_document_reference(move)
                    )
                elif correction_origin.l10n_cz_vat_regime != "third_country_import":
                    errors.append(
                        _("Document %s must reference a 3rd-country import document as correction origin.")
                        % self._move_document_reference(move)
                    )

            if move.l10n_cz_vat_regime == "third_country_import":
                if not self._has_import_customs_reference(move):
                    errors.append(
                        _(
                            "Document %s is marked as a 3rd-country import and requires CZ Customs MRN or Customs Decision Number (or a linked correction origin with that evidence)."
                        )
                        % self._move_document_reference(move)
                    )
                if not self._import_customs_field_value(move, "l10n_cz_customs_release_date"):
                    errors.append(
                        _(
                            "Document %s is marked as a 3rd-country import and requires Customs Release Date (or a linked correction origin with that evidence)."
                        )
                        % self._move_document_reference(move)
                    )

            if tag_names & A1_TAGS:
                a1_code, a1_line_codes = self._move_reverse_charge_code_for_tags(move, A1_TAGS)
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
                if len(a1_line_codes) > 1:
                    errors.append(
                        _(
                            "Document %s has multiple CZ KH subject codes on VAT 25 lines. "
                            "Split the document by subject code for KH A1."
                        )
                        % self._move_document_reference(move)
                    )
                if not a1_code:
                    errors.append(
                        _("Document %s requires CZ KH reverse charge code for KH A1.")
                        % self._move_document_reference(move)
                    )
                if a1_code in RPDP_TEMPORARY_THRESHOLD_CODES:
                    temporary_base = abs(self._move_tag_amount(move, A1_TAGS))
                    if temporary_base < RPDP_TEMPORARY_THRESHOLD_BASE:
                        errors.append(
                            _(
                                "Document %s uses temporary RPDP subject code %s but taxable base is below 100.000 CZK."
                            )
                            % (self._move_document_reference(move), a1_code)
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
                b1_code, b1_line_codes = self._move_reverse_charge_code_for_tags(
                    move, set(B1_BASE_TAGS) | set(B1_TAX_TAGS)
                )
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
                if len(b1_line_codes) > 1:
                    errors.append(
                        _(
                            "Document %s has multiple CZ KH subject codes on VAT 10/11 lines. "
                            "Split the document by subject code for KH B1."
                        )
                        % self._move_document_reference(move)
                    )
                if not b1_code:
                    errors.append(
                        _("Document %s requires CZ KH reverse charge code for KH B1.")
                        % self._move_document_reference(move)
                    )
                if b1_code in RPDP_TEMPORARY_THRESHOLD_CODES:
                    temporary_base = abs(self._move_tag_amount(move, set(B1_BASE_TAGS)))
                    if temporary_base < RPDP_TEMPORARY_THRESHOLD_BASE:
                        errors.append(
                            _(
                                "Document %s uses temporary RPDP subject code %s but taxable base is below 100.000 CZK."
                            )
                            % (self._move_document_reference(move), b1_code)
                        )

            if "VAT 30" in tag_names:
                if move.move_type not in {"in_invoice", "in_refund"}:
                    errors.append(
                        _("Document %s uses VAT 30 but is not a vendor bill/refund.")
                        % self._move_document_reference(move)
                    )
                country_code, vat_number = self._partner_vat_identifier(partner)
                if country_code in {"", "CZ"} or not vat_number:
                    errors.append(
                        _("Document %s requires a non-Czech EU partner VAT identifier for VAT 30 triangular acquisition.")
                        % self._move_document_reference(move)
                    )

            if "VAT 31" in tag_names:
                if move.move_type not in {"out_invoice", "out_refund"}:
                    errors.append(
                        _("Document %s uses VAT 31 but is not a customer invoice/refund.")
                        % self._move_document_reference(move)
                    )
                country_code, vat_number = self._partner_vat_identifier(partner)
                if country_code in {"", "CZ"} or not vat_number:
                    errors.append(
                        _("Document %s requires a non-Czech EU customer VAT identifier for VAT 31 triangular supply.")
                        % self._move_document_reference(move)
                    )

            if "VAT 32" in tag_names and move.move_type not in {"in_invoice", "in_refund"}:
                errors.append(
                    _("Document %s uses VAT 32 but is not a vendor bill/refund.")
                    % self._move_document_reference(move)
                )

            if "VAT 33" in tag_names:
                if move.move_type not in {"out_invoice", "out_refund"}:
                    errors.append(
                        _("Document %s uses VAT 33 but is not a customer invoice/refund.")
                        % self._move_document_reference(move)
                    )
                if (partner.country_id.code or "") != "CZ" or not self._vat_core(partner.vat):
                    errors.append(
                        _("Document %s requires a Czech customer VAT identifier for VAT 33 bad-debt correction.")
                        % self._move_document_reference(move)
                    )
                if not self._breakdown_has_values(self._move_base_tax_breakdown(move)):
                    errors.append(
                        _("Document %s uses VAT 33 but is missing domestic sale base/tax tags required for KH A4 detail.")
                        % self._move_document_reference(move)
                    )

            if "VAT 34" in tag_names:
                if move.move_type not in {"in_invoice", "in_refund"}:
                    errors.append(
                        _("Document %s uses VAT 34 but is not a vendor bill/refund.")
                        % self._move_document_reference(move)
                    )
                if (partner.country_id.code or "") != "CZ" or not self._vat_core(partner.vat):
                    errors.append(
                        _("Document %s requires a Czech supplier VAT identifier for VAT 34 bad-debt correction.")
                        % self._move_document_reference(move)
                    )
                if not self._breakdown_has_values(self._move_base_tax_breakdown(move)):
                    errors.append(
                        _("Document %s uses VAT 34 but is missing purchase deduction tags required for KH B2 detail.")
                        % self._move_document_reference(move)
                    )

            if "VAT 23" in tag_names:
                if move.move_type not in {"out_invoice", "out_refund"}:
                    errors.append(
                        _("Document %s uses VAT 23 but is not a customer invoice/refund.")
                        % self._move_document_reference(move)
                    )
                if (partner.country_id.code or "") in {"", "CZ"}:
                    errors.append(
                        _("Document %s requires a non-Czech customer country for VAT 23.")
                        % self._move_document_reference(move)
                    )
                if partner.vat:
                    warnings.append(
                        _("Document %s uses VAT 23 but the customer has a VAT number; verify that line 23 is legally correct.")
                        % self._move_document_reference(move)
                    )

            if "VAT 24" in tag_names:
                if move.move_type not in {"out_invoice", "out_refund"}:
                    errors.append(
                        _("Document %s uses VAT 24 but is not a customer invoice/refund.")
                        % self._move_document_reference(move)
                    )
                if (partner.country_id.code or "") in {"", "CZ"}:
                    errors.append(
                        _("Document %s requires a non-Czech customer country for VAT 24.")
                        % self._move_document_reference(move)
                    )

            if {"VAT 47 Base", "VAT 47 Total"} & tag_names:
                if move.move_type not in {"in_invoice", "in_refund"}:
                    errors.append(
                        _("Document %s uses VAT 47 tags but is not a vendor bill/refund.")
                        % self._move_document_reference(move)
                    )
                if not {"VAT 47 Base", "VAT 47 Total"} <= tag_names:
                    errors.append(
                        _("Document %s must include both VAT 47 Base and VAT 47 Total tags.")
                        % self._move_document_reference(move)
                    )

            if "VAT 50" in tag_names and move.move_type not in {"out_invoice", "out_refund"}:
                errors.append(
                    _("Document %s uses VAT 50 but is not a customer invoice/refund.")
                    % self._move_document_reference(move)
                )

            if {"VAT 51 with deduction", "VAT 51 without deduction"} & tag_names:
                if move.move_type not in {"out_invoice", "out_refund"}:
                    errors.append(
                        _("Document %s uses VAT 51 tags but is not a customer invoice/refund.")
                        % self._move_document_reference(move)
                    )

            if "VAT 61" in tag_names and move.move_type not in {"out_invoice", "out_refund"}:
                errors.append(
                    _("Document %s uses VAT 61 but is not a customer invoice/refund.")
                    % self._move_document_reference(move)
                )

            unsupported_tags = sorted(tag_names & UNSUPPORTED_VAT_TAGS)
            if unsupported_tags:
                errors.append(
                    _("Document %s uses Czech VAT tags that are not implemented in this exporter: %s.")
                    % (self._move_document_reference(move), ", ".join(unsupported_tags))
                )

            if move.move_type in {"out_invoice", "out_refund"} and (partner.country_id.code or "") == "CZ":
                if self._move_amount_total_czk(move) > Decimal("10000.00") and not self._vat_core(partner.vat):
                    warnings.append(
                        _("Domestic document %s exceeds 10.000 CZK but partner VAT is missing; it will not qualify for A4 detail.")
                        % self._move_document_reference(move)
                    )

            if move.move_type in {"in_invoice", "in_refund"} and (partner.country_id.code or "") == "CZ":
                has_b2_breakdown = self._breakdown_has_values(self._move_base_tax_breakdown(move))
                has_b1_breakdown = self._breakdown_has_values(self._move_breakdown_from_tags(move, B1_BASE_TAGS, B1_TAX_TAGS))
                if (
                    has_b2_breakdown
                    and not has_b1_breakdown
                    and self._move_amount_total_czk(move) > Decimal("10000.00")
                    and not self._vat_core(partner.vat)
                ):
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

        for option_name in ["line_52a_coefficient", "line_53a_settlement_coefficient"]:
            option_value = options.get(option_name)
            if option_value in (None, "", False):
                continue
            numeric_value = self._decimal(option_value)
            if numeric_value < 0 or numeric_value > Decimal("100.00"):
                errors.append(
                    _("DPH export option %s must be between 0 and 100.")
                    % option_name
                )

        if (
            snapshot["dph_derivations"]["current_period_proportional_source"]
            and snapshot["dph_derivations"]["advance_coefficient"] is None
            and options.get("line_52b_deduction") in (None, "", False)
        ):
            errors.append(
                _(
                    "Czech DPH row 52 cannot be derived because no advance coefficient is available. "
                    "Set a manual company coefficient, provide line_52a_coefficient, or load the previous calendar year data."
                )
            )

        if (
            snapshot["dph_derivations"]["year_end_period"]
            and snapshot["dph_derivations"]["annual_proportional_source"]
            and snapshot["dph_derivations"]["settlement_coefficient"] is None
            and options.get("line_53b_change_deduction") in (None, "", False)
        ):
            errors.append(
                _(
                    "Czech DPH row 53 cannot be derived for the year-end period because the settlement coefficient is unavailable."
                )
            )

        return {"errors": errors, "warnings": warnings}

    def _period_options(self, company, date_from, date_to, options):
        partner = self._validate_company(company)
        period = self._infer_period(date_from, date_to, options.get("period_kind"))
        address = self._address_parts(partner)
        metadata = {
            "submission_date": options.get("submission_date", self._today_str()),
            "tax_statement_date": options.get("tax_statement_date", ""),
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
            "kh_challenge_reference": options.get("kh_challenge_reference", ""),
            "kh_challenge_response": options.get("kh_challenge_response", ""),
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

        normalized_options, option_warnings, option_alias_conflicts = self._normalize_options(options)
        metadata, period = self._period_options(company, date_from, date_to, normalized_options)
        requested_forms = self._requested_forms(normalized_options)
        period_moves = self._period_moves(company, date_from, date_to)
        moves = period_moves.filtered(
            lambda move: (move.l10n_cz_vat_regime or "standard") not in STANDARD_CZ_EXCLUDED_REGIMES
        )
        snapshot = {
            "company": company,
            "date_from": date_from,
            "date_to": date_to,
            "metadata": metadata,
            "raw_options": dict(options),
            "options": normalized_options,
            "option_warnings": option_warnings,
            "option_alias_conflicts": option_alias_conflicts,
            "period": period,
            "requested_forms": requested_forms,
            "period_range_override": self._period_range_override(date_from, date_to, period, normalized_options),
            "excluded_regime_moves": period_moves - moves,
            "moves": moves,
            "tag_names": sorted(self._tax_tag_names(moves)),
            "tag_amounts": self._tag_amounts(moves),
            "kh": self._kh_payload(moves),
            "sh": self._sh_payload(moves),
        }
        snapshot["dph_raw_section_values"] = self._raw_dph_section_values(moves)
        snapshot["dph_section_values"], snapshot["dph_derivations"] = self._dph_section_values(snapshot)
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

    def _period_override_attrs(self, snapshot):
        override = snapshot.get("period_range_override")
        if not override:
            return {}
        return {
            "zdobd_od": self._xml_date(override["from"]),
            "zdobd_do": self._xml_date(override["to"]),
        }

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

    def _option_dph_section_values(self, snapshot):
        option_values = defaultdict(lambda: defaultdict(Decimal))
        for option_name, (section_name, field_name) in DPH_OPTION_FIELD_SPECS.items():
            option_value = snapshot["options"].get(option_name)
            if option_value in (None, "", False):
                continue
            option_values[section_name][field_name] += self._decimal(option_value)
        return option_values

    def _dph_section_values(self, snapshot):
        section_values = defaultdict(lambda: defaultdict(Decimal))
        self._merge_section_values(section_values, snapshot["dph_raw_section_values"])
        self._merge_section_values(section_values, self._option_dph_section_values(snapshot))

        advance_coefficient = self._advance_coefficient(snapshot)
        settlement_coefficient = self._settlement_coefficient(snapshot)
        proportional_source = self._proportional_source_total(section_values)

        if (
            proportional_source
            and advance_coefficient is not None
            and snapshot["options"].get("line_52b_deduction") in (None, "", False)
        ):
            section_values["Veta5"]["koef_p20_nov"] = advance_coefficient
            section_values["Veta5"]["odp_uprav_kf"] = (
                proportional_source * advance_coefficient / Decimal("100.00")
            ).quantize(TWOPLACES, rounding=ROUND_HALF_UP)

        if (
            self._year_end_period(snapshot)
            and settlement_coefficient is not None
            and snapshot["options"].get("line_53b_change_deduction") in (None, "", False)
        ):
            annual_raw_values = self._annual_raw_dph_section_values(
                snapshot["company"], int(snapshot["period"]["year"])
            )
            annual_proportional_source = self._proportional_source_total(annual_raw_values)
            section_values["Veta5"]["koef_p20_vypor"] = settlement_coefficient
            if annual_proportional_source:
                advance_total = Decimal("0.00")
                if advance_coefficient is not None:
                    advance_total = (
                        annual_proportional_source * advance_coefficient / Decimal("100.00")
                    ).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
                settlement_total = (
                    annual_proportional_source * settlement_coefficient / Decimal("100.00")
                ).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
                section_values["Veta5"]["vypor_odp"] = settlement_total - advance_total
        else:
            annual_proportional_source = Decimal("0.00")

        section_values["Veta4"]["odp_sum_nar"] = sum(
            section_values["Veta4"].get(field_name, Decimal("0.00"))
            for field_name in DPH_ROW46_FULL_FIELDS
        )
        section_values["Veta4"]["odp_sum_kr"] = sum(
            section_values["Veta4"].get(field_name, Decimal("0.00"))
            for field_name in DPH_ROW46_REDUCED_FIELDS
        )

        return section_values, {
            "advance_coefficient": advance_coefficient,
            "settlement_coefficient": settlement_coefficient,
            "current_period_proportional_source": proportional_source,
            "annual_proportional_source": annual_proportional_source,
            "year_end_period": self._year_end_period(snapshot),
        }

    def _dph_totals_attrs(self, section_values):
        output_tax = sum(
            value
            for key, value in section_values["Veta1"].items()
            if key.startswith("dan") or key == "opr_dane_dan"
        )
        output_tax -= section_values["Veta6"].get("dan_vrac", Decimal("0.00"))
        deduction_tax = section_values["Veta4"].get("odp_sum_nar", Decimal("0.00"))
        deduction_tax += section_values["Veta5"].get("odp_uprav_kf", Decimal("0.00"))
        deduction_tax += section_values["Veta5"].get("vypor_odp", Decimal("0.00"))
        deduction_tax += section_values["Veta6"].get("uprav_odp", Decimal("0.00"))
        attrs = {
            "dan_zocelk": self._whole_str(output_tax),
            "odp_zocelk": self._whole_str(deduction_tax),
        }
        if section_values["Veta6"].get("uprav_odp"):
            attrs["uprav_odp"] = self._whole_str(section_values["Veta6"]["uprav_odp"])
        if section_values["Veta6"].get("dan_vrac"):
            attrs["dan_vrac"] = self._whole_str(section_values["Veta6"]["dan_vrac"])
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
                **self._period_override_attrs(snapshot),
                "typ_platce": metadata["dph_taxpayer_type"],
                "dic_puv": metadata["dic_puv"],
            },
        )
        if metadata["dph_form"] in {"D", "E"} and metadata["tax_statement_date"]:
            d_record.set("d_zjist", self._xml_date(metadata["tax_statement_date"]))
        self._add_p_record(form, snapshot, "DPHDP3")

        section_values = snapshot["dph_section_values"]

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
                **self._period_override_attrs(snapshot),
                "c_jed_vyzvy": metadata["kh_challenge_reference"],
                "vyzva_odp": metadata["kh_challenge_response"],
            },
        )
        if metadata["kh_form"] in {"N", "E"} and metadata["tax_statement_date"]:
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
                "zdph_44": row["zdph_44"],
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
                "zdph_44": row["zdph_44"],
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
            "raw_options": snapshot.get("raw_options", {}),
            "options": snapshot["options"],
            "requested_forms": snapshot["requested_forms"],
            "period_range_override": {
                "from": str(snapshot["period_range_override"]["from"]),
                "to": str(snapshot["period_range_override"]["to"]),
            } if snapshot.get("period_range_override") else None,
            "validation": snapshot["validation"],
            "move_ids": snapshot["moves"].ids,
            "move_period_dates": [
                {
                    "id": move.id,
                    "reference": self._move_document_reference(move),
                    "vat_regime": move.l10n_cz_vat_regime or "standard",
                    "customs_mrn": move.l10n_cz_customs_mrn or "",
                    "customs_decision_number": move.l10n_cz_customs_decision_number or "",
                    "customs_release_date": str(move.l10n_cz_customs_release_date or ""),
                    "effective_customs_mrn": self._import_customs_field_value(move, "l10n_cz_customs_mrn") or "",
                    "effective_customs_decision_number": self._import_customs_field_value(move, "l10n_cz_customs_decision_number") or "",
                    "effective_customs_release_date": str(
                        self._import_customs_field_value(move, "l10n_cz_customs_release_date") or ""
                    ),
                    "customs_office": move.l10n_cz_customs_office or "",
                    "customs_value_amount": self._round_str(move.l10n_cz_customs_value_amount or 0.0),
                    "customs_vat_amount": self._round_str(move.l10n_cz_customs_vat_amount or 0.0),
                    "import_correction_origin_id": move.l10n_cz_import_correction_origin_id.id or False,
                    "import_correction_origin_reference": (
                        self._move_document_reference(move.l10n_cz_import_correction_origin_id)
                        if move.l10n_cz_import_correction_origin_id
                        else ""
                    ),
                    "import_correction_reason": move.l10n_cz_import_correction_reason or "",
                    "accounting_date": str(move.date or ""),
                    "invoice_date": str(move.invoice_date or ""),
                    "dph_tax_date": str(move.l10n_cz_dph_tax_date or ""),
                    "effective_dph_tax_date": str(self._move_dph_tax_date(move)),
                }
                for move in snapshot["moves"]
            ],
            "excluded_regime_moves": [
                {
                    "id": move.id,
                    "reference": self._move_document_reference(move),
                    "vat_regime": move.l10n_cz_vat_regime or "standard",
                    "customs_mrn": move.l10n_cz_customs_mrn or "",
                    "customs_decision_number": move.l10n_cz_customs_decision_number or "",
                    "customs_release_date": str(move.l10n_cz_customs_release_date or ""),
                    "accounting_date": str(move.date or ""),
                    "invoice_date": str(move.invoice_date or ""),
                }
                for move in snapshot.get("excluded_regime_moves", [])
            ],
            "tag_amounts": {key: self._round_str(value) for key, value in sorted(snapshot["tag_amounts"].items())},
            "dph_derivations": {
                key: self._round_str(value) if isinstance(value, Decimal) else value
                for key, value in snapshot["dph_derivations"].items()
            },
            "dph_section_values": {
                section_name: {
                    field_name: self._round_str(amount)
                    for field_name, amount in sorted(values.items())
                    if amount
                }
                for section_name, values in snapshot["dph_section_values"].items()
                if any(values.values())
            },
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
                        "zdph_44": row["zdph_44"],
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
                        "zdph_44": row["zdph_44"],
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
        requested_forms = snapshot["requested_forms"]
        return {
            "debug": debug_payload,
            "debug_json": json.dumps(debug_payload, ensure_ascii=False, indent=2, sort_keys=True),
            "dphdp3_xml": self._dphdp3_xml(snapshot) if requested_forms["dphdp3"] else None,
            "dphkh1_xml": self._dphkh1_xml(snapshot) if requested_forms["dphkh1"] else None,
            "dphshv_xml": self._dphshv_xml(snapshot) if requested_forms["dphshv"] else None,
        }
