from unittest.mock import patch
import xml.etree.ElementTree as ET

from odoo.exceptions import UserError
from odoo.tests import TransactionCase


class TestL10nCzVatFilingExport(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.Account = cls.env["account.account"]
        cls.Journal = cls.env["account.journal"]
        cls.Move = cls.env["account.move"]
        cls.Partner = cls.env["res.partner"]
        cls.Tax = cls.env["account.tax"]
        cls.Tag = cls.env["account.account.tag"]
        cls.Currency = cls.env["res.currency"]
        cls.CurrencyRate = cls.env["res.currency.rate"]
        cls.cz = cls.env.ref("base.cz")
        cls.de = cls.env.ref("base.de")
        cls.sk = cls.env.ref("base.sk")
        cls.usd = cls.Currency.search([("name", "=", "USD")], limit=1)
        cls._setup_company()
        cls.sale_account = cls._find_account(["income", "income_other"])
        cls.purchase_account = cls._find_account(["expense", "expense_direct_cost", "expense_depreciation"])
        cls.sale_journal = cls._find_journal("sale")
        cls.purchase_journal = cls._find_journal("purchase")
        cls._ensure_tag("VAT 45 Full")
        cls._ensure_tag("VAT 45 Reduced")
        cls._ensure_tag("VAT 40 Coefficient")
        cls._ensure_tag("VAT 41 Coefficient")
        cls._ensure_tag("VAT 42 Coefficient")
        cls.tax_sale_domestic = cls._find_tax("sale", ["VAT 1 Base", "VAT 1 Tax"])
        cls.tax_sale_rc = cls._find_tax("sale", ["VAT 25"])
        cls.tax_sale_ioss_placeholder = cls._find_or_copy_tax(
            "sale",
            [],
            cls.tax_sale_domestic,
            "21% IOSS Placeholder Test",
            base_tags=[],
            invoice_tax_tags=[],
            refund_tax_tags=[],
        )
        cls.tax_purchase_a2 = cls._find_tax("purchase", ["VAT 3 Base", "VAT 3 Tax"])
        cls.tax_purchase_b1 = cls._find_tax("purchase", ["VAT 10 Base", "VAT 10 Tax"])
        cls.tax_purchase_import = cls._find_tax("purchase", ["VAT 7 Base", "VAT 7 Tax"])
        cls.tax_purchase_domestic = cls._find_tax("purchase", ["VAT 40 Base", "VAT 40 Total"])
        cls.tax_purchase_customs = cls._find_or_copy_tax(
            "purchase",
            ["VAT 42 Base", "VAT 42 Total"],
            cls.tax_purchase_domestic,
            "21% Customs Deduction Test",
            base_tags=["VAT 42 Base"],
            invoice_tax_tags=["VAT 42 Total"],
            refund_tax_tags=["VAT 42 Total"],
        )
        cls.tax_import_with_kh = cls._find_or_copy_tax(
            "purchase",
            ["VAT 7 Base", "VAT 7 Tax", "VAT 3 Base", "VAT 3 Tax"],
            cls.tax_purchase_import,
            "21% Import Mixed KH Test",
            base_tags=["VAT 7 Base", "VAT 3 Base"],
            invoice_tax_tags=["VAT 7 Tax", "VAT 3 Tax"],
            refund_tax_tags=["VAT 7 Tax", "VAT 3 Tax"],
        )
        cls.tax_import_correction_full = cls._find_or_copy_tax(
            "purchase",
            ["VAT 7 Base", "VAT 7 Tax", "VAT 45 Full"],
            cls.tax_purchase_import,
            "21% Import Correction Full Test",
            base_tags=["VAT 7 Base"],
            invoice_tax_tags=["VAT 7 Tax", "VAT 45 Full"],
            refund_tax_tags=["VAT 7 Tax", "VAT 45 Full"],
        )
        cls.tax_purchase_domestic_coefficient = cls._find_or_copy_tax(
            "purchase",
            ["VAT 40 Base", "VAT 40 Total", "VAT 40 Coefficient"],
            cls.tax_purchase_domestic,
            "21% Domestic Purchase Coefficient Test",
            base_tags=["VAT 40 Base"],
            invoice_tax_tags=["VAT 40 Total", "VAT 40 Coefficient"],
            refund_tax_tags=["VAT 40 Total", "VAT 40 Coefficient"],
        )
        cls.partner_cz_customer = cls._ensure_partner("CZ Customer Test", "CZ12345678", cls.cz)
        cls.partner_cz_supplier = cls._ensure_partner("CZ Supplier Test", "CZ22345678", cls.cz)
        cls.partner_cz_private = cls._ensure_partner("CZ Private Buyer Test", "", cls.cz, company_type="person")
        cls.partner_sk_supplier = cls._ensure_partner("SK Supplier Test", "SK1234567891", cls.sk)
        cls.partner_de_supplier = cls._ensure_partner("DE Supplier Test", "DE123456789", cls.de)
        cls.partner_de_private = cls._ensure_partner("DE Private Buyer Test", "", cls.de, company_type="person")

    @classmethod
    def _setup_company(cls):
        cls.company.write({"account_fiscal_country_id": cls.cz.id})
        cls.company.partner_id.with_context(no_vat_validation=True).write(
            {
                "name": cls.company.name or "CZ Filing Test Company",
                "vat": "CZ699999999",
                "country_id": cls.cz.id,
                "street": "Testovaci 1",
                "city": "Praha",
                "zip": "11000",
                "company_type": "company",
            }
        )

    @classmethod
    def _find_account(cls, account_types):
        account = cls.Account.search([("account_type", "in", account_types)], limit=1, order="id")
        if not account:
            raise AssertionError(f"Missing account for {account_types!r}")
        return account

    @classmethod
    def _find_journal(cls, journal_type):
        journal = cls.Journal.search(
            [("company_id", "=", cls.company.id), ("type", "=", journal_type)],
            limit=1,
            order="id",
        )
        if not journal:
            raise AssertionError(f"Missing {journal_type!r} journal")
        return journal

    @classmethod
    def _ensure_tag(cls, name):
        tag = cls.Tag.search([("name", "=", name)], limit=1)
        if tag:
            return tag
        return cls.Tag.create(
            {
                "name": name,
                "applicability": "taxes",
                "country_id": cls.cz.id,
            }
        )

    @classmethod
    def _tag_ids(cls, names):
        tags = cls.Tag.search([("name", "in", names)])
        missing = sorted(set(names) - set(tags.mapped("name")))
        if missing:
            raise AssertionError(f"Missing account tags: {missing!r}")
        return [tag.id for tag in tags.sorted(key=lambda record: record.name)]

    @classmethod
    def _find_tax(cls, type_tax_use, required_tags):
        required = set(required_tags)
        for tax in cls.Tax.search([("type_tax_use", "=", type_tax_use)]):
            tags = {
                tag.name
                for rep in tax.invoice_repartition_line_ids
                for tag in rep.tag_ids
            }
            if required.issubset(tags):
                return tax
        return False

    @classmethod
    def _find_or_copy_tax(
        cls,
        type_tax_use,
        required_tags,
        source_tax,
        new_name,
        *,
        base_tags=None,
        invoice_tax_tags=None,
        refund_tax_tags=None,
    ):
        if required_tags:
            tax = cls._find_tax(type_tax_use, required_tags)
            if tax:
                return tax
        else:
            tax = cls.Tax.search([("type_tax_use", "=", type_tax_use), ("name", "=", new_name)], limit=1)
            if tax:
                return tax
        tax = source_tax.copy(
            {
                "name": new_name,
                "description": new_name,
                "invoice_label": new_name,
            }
        )
        if base_tags is not None:
            tag_ids = cls._tag_ids(base_tags)
            for line in tax.invoice_repartition_line_ids.filtered(lambda record: record.repartition_type == "base"):
                line.tag_ids = [(6, 0, tag_ids)]
            for line in tax.refund_repartition_line_ids.filtered(lambda record: record.repartition_type == "base"):
                line.tag_ids = [(6, 0, tag_ids)]
        if invoice_tax_tags is not None:
            tag_ids = cls._tag_ids(invoice_tax_tags)
            for line in tax.invoice_repartition_line_ids.filtered(
                lambda record: record.repartition_type == "tax" and record.tag_ids
            ):
                line.tag_ids = [(6, 0, tag_ids)]
        if refund_tax_tags is not None:
            tag_ids = cls._tag_ids(refund_tax_tags)
            for line in tax.refund_repartition_line_ids.filtered(
                lambda record: record.repartition_type == "tax" and record.tag_ids
            ):
                line.tag_ids = [(6, 0, tag_ids)]
        return tax

    @classmethod
    def _ensure_partner(cls, name, vat, country, company_type="company"):
        domain = [("vat", "=", vat)] if vat else [("name", "=", name), ("country_id", "=", country.id)]
        partner = cls.Partner.search(domain, limit=1)
        if partner:
            return partner
        return cls.Partner.with_context(no_vat_validation=True).create(
            {
                "name": name,
                "vat": vat,
                "country_id": country.id,
                "company_type": company_type,
                "street": "Testovaci 1",
                "city": "Praha",
                "zip": "11000",
            }
        )

    @classmethod
    def _set_currency_rate(cls, currency, date, rate):
        if not currency:
            raise AssertionError("Missing currency for exchange-rate test")
        rate_record = cls.CurrencyRate.search(
            [
                ("currency_id", "=", currency.id),
                ("company_id", "=", cls.company.id),
                ("name", "=", date),
            ],
            limit=1,
        )
        if rate_record:
            rate_record.write({"rate": rate})
            return rate_record
        return cls.CurrencyRate.create(
            {
                "currency_id": currency.id,
                "company_id": cls.company.id,
                "name": date,
                "rate": rate,
            }
        )

    def _create_move(self, marker, move_type, partner, account, tax, amount, invoice_date, **extra):
        journal = self.sale_journal if move_type in {"out_invoice", "out_refund"} else self.purchase_journal
        line_extra = dict(extra.pop("line_extra", {}))
        line_vals = {
            "name": marker,
            "quantity": 1,
            "price_unit": amount,
            "account_id": account.id,
            "tax_ids": [(6, 0, [tax.id])] if tax else [],
        }
        line_vals.update(line_extra)
        vals = {
            "move_type": move_type,
            "partner_id": partner.id,
            "journal_id": journal.id,
            "invoice_date": invoice_date,
            "date": extra.pop("date", invoice_date),
            "invoice_line_ids": [
                (
                    0,
                    0,
                    line_vals,
                )
            ],
            **extra,
        }
        if move_type in {"out_invoice", "out_refund"}:
            vals["invoice_origin"] = marker
        else:
            vals["ref"] = marker
        move = self.Move.create(vals)
        move.action_post()
        return move

    def test_move_has_any_tag_uses_tag_presence_not_amount(self):
        exporter = self.env["l10n_cz.vat.filing.export"]
        with patch.object(type(exporter), "_move_tag_names", autospec=True, return_value={"VAT 33"}):
            self.assertTrue(exporter._move_has_any_tag(self.Move.browse(), {"VAT 33"}))

    def test_duzp_period_selection_uses_czech_tax_date(self):
        move = self._create_move(
            "TEST-DUZP-A2",
            "in_invoice",
            self.partner_sk_supplier,
            self.purchase_account,
            self.tax_purchase_a2,
            1000,
            "2027-04-05",
            date="2027-04-05",
            l10n_cz_dph_tax_date="2027-03-11",
            l10n_cz_kh_document_reference="TEST-DUZP-A2",
            l10n_cz_kh_tax_point_date="2027-03-11",
        )

        march = self.company.l10n_cz_vat_filing_exports("2027-03-01", "2027-03-31")
        april = self.company.l10n_cz_vat_filing_exports("2027-04-01", "2027-04-30")

        self.assertIn(move.id, march["debug"]["move_ids"])
        self.assertNotIn(move.id, april["debug"]["move_ids"])
        self.assertIn(
            "TEST-DUZP-A2",
            [row["reference"] for row in march["debug"]["kh"]["A2"]],
        )

    def test_ioss_moves_are_excluded_from_standard_czech_exports(self):
        move = self._create_move(
            "TEST-IOSS-SKIP",
            "out_invoice",
            self.partner_de_private,
            self.sale_account,
            self.tax_sale_ioss_placeholder,
            2400,
            "2027-03-31",
            l10n_cz_vat_regime="ioss",
            l10n_cz_kh_document_reference="TEST-IOSS-SKIP",
        )

        exports = self.company.l10n_cz_vat_filing_exports("2027-03-01", "2027-03-31")
        debug = exports["debug"]

        self.assertNotIn(move.id, debug["move_ids"])
        self.assertIn(
            {
                "id": move.id,
                "reference": "TEST-IOSS-SKIP",
                "vat_regime": "ioss",
                "customs_mrn": "",
                "customs_decision_number": "",
                "customs_release_date": "",
                "accounting_date": "2027-03-31",
                "invoice_date": "2027-03-31",
            },
            debug["excluded_regime_moves"],
        )

    def test_ioss_moves_with_czech_tags_fail_validation(self):
        self._create_move(
            "TEST-IOSS-BAD-TAGS",
            "out_invoice",
            self.partner_de_private,
            self.sale_account,
            self.tax_sale_domestic,
            2400,
            "2027-03-30",
            l10n_cz_vat_regime="ioss",
            l10n_cz_kh_document_reference="TEST-IOSS-BAD-TAGS",
        )

        with self.assertRaisesRegex(UserError, "still carries Czech filing tags"):
            self.company.l10n_cz_vat_filing_exports("2027-03-01", "2027-03-31")

    def test_third_country_import_tags_stay_out_of_kh(self):
        import_move = self._create_move(
            "TEST-IMPORT-ROW7",
            "in_invoice",
            self.partner_de_supplier,
            self.purchase_account,
            self.tax_purchase_import,
            14000,
            "2027-03-13",
            l10n_cz_vat_regime="third_country_import",
            l10n_cz_customs_mrn="27CZMRN0000001",
            l10n_cz_customs_release_date="2027-03-13",
            l10n_cz_kh_document_reference="TEST-IMPORT-ROW7",
        )
        customs_move = self._create_move(
            "TEST-IMPORT-ROW43",
            "in_invoice",
            self.partner_de_supplier,
            self.purchase_account,
            self.tax_purchase_customs,
            2500,
            "2027-03-14",
            l10n_cz_vat_regime="third_country_import",
            l10n_cz_customs_decision_number="JSD-2027-0001",
            l10n_cz_customs_release_date="2027-03-14",
            l10n_cz_kh_document_reference="TEST-IMPORT-ROW43",
            l10n_cz_kh_proportional_deduction=True,
        )

        exports = self.company.l10n_cz_vat_filing_exports("2027-03-01", "2027-03-31")
        debug = exports["debug"]
        a2_refs = [row["reference"] for row in debug["kh"]["A2"]]
        b2_refs = [row["reference"] for row in debug["kh"]["B2"]]

        self.assertIn("VAT 7 Base", debug["tag_amounts"])
        self.assertIn("VAT 7 Tax", debug["tag_amounts"])
        self.assertIn("VAT 42 Base", debug["tag_amounts"])
        self.assertIn("VAT 42 Total", debug["tag_amounts"])
        self.assertNotIn(import_move.l10n_cz_kh_document_reference, a2_refs)
        self.assertNotIn(import_move.l10n_cz_kh_document_reference, b2_refs)
        self.assertNotIn(customs_move.l10n_cz_kh_document_reference, a2_refs)
        self.assertNotIn(customs_move.l10n_cz_kh_document_reference, b2_refs)
        import_debug = next(
            row
            for row in debug["move_period_dates"]
            if row["reference"] == "TEST-IMPORT-ROW7"
        )
        self.assertEqual(import_debug["customs_mrn"], "27CZMRN0000001")
        self.assertEqual(import_debug["customs_release_date"], "2027-03-13")

    def test_import_move_cannot_mix_import_and_kh_tags(self):
        self._create_move(
            "TEST-IMPORT-KH-MIX",
            "in_invoice",
            self.partner_de_supplier,
            self.purchase_account,
            self.tax_import_with_kh,
            1000,
            "2027-03-15",
            l10n_cz_vat_regime="third_country_import",
            l10n_cz_customs_mrn="27CZMRN0000002",
            l10n_cz_customs_release_date="2027-03-15",
            l10n_cz_kh_document_reference="TEST-IMPORT-KH-MIX",
        )

        with self.assertRaisesRegex(UserError, "must not leak into KH detail"):
            self.company.l10n_cz_vat_filing_exports("2027-03-01", "2027-03-31")

    def test_third_country_import_requires_customs_evidence(self):
        self._create_move(
            "TEST-IMPORT-MISSING-JSD",
            "in_invoice",
            self.partner_de_supplier,
            self.purchase_account,
            self.tax_purchase_import,
            1000,
            "2027-03-16",
            l10n_cz_vat_regime="third_country_import",
            l10n_cz_kh_document_reference="TEST-IMPORT-MISSING-JSD",
        )

        with self.assertRaisesRegex(UserError, "requires CZ Customs MRN or Customs Decision Number"):
            self.company.l10n_cz_vat_filing_exports("2027-03-01", "2027-03-31")

    def test_import_correction_row45_routes_to_dph_and_not_kh(self):
        origin = self._create_move(
            "TEST-IMPORT-CORR-ORIG",
            "in_invoice",
            self.partner_de_supplier,
            self.purchase_account,
            self.tax_purchase_import,
            5000,
            "2027-03-10",
            l10n_cz_vat_regime="third_country_import",
            l10n_cz_customs_mrn="27CZMRN0000045",
            l10n_cz_customs_release_date="2027-03-10",
            l10n_cz_kh_document_reference="TEST-IMPORT-CORR-ORIG",
        )
        correction = self._create_move(
            "TEST-IMPORT-CORR-REFUND",
            "in_refund",
            self.partner_de_supplier,
            self.purchase_account,
            self.tax_import_correction_full,
            1000,
            "2027-03-20",
            l10n_cz_vat_regime="third_country_import",
            l10n_cz_import_correction_origin_id=origin.id,
            l10n_cz_import_correction_reason="Customs value reduced after JSD revision",
            l10n_cz_kh_document_reference="TEST-IMPORT-CORR-REFUND",
        )

        exports = self.company.l10n_cz_vat_filing_exports("2027-03-01", "2027-03-31")
        debug = exports["debug"]

        self.assertEqual(debug["tag_amounts"].get("VAT 45 Full"), "-210.00")
        self.assertEqual(debug["dph_section_values"]["Veta4"].get("odp_rez_nar"), "-210.00")
        self.assertEqual(debug["dph_section_values"]["Veta1"].get("dan_dzb23"), "840.00")

        a2_refs = {row["reference"] for row in debug["kh"]["A2"]}
        b2_refs = {row["reference"] for row in debug["kh"]["B2"]}
        self.assertNotIn("TEST-IMPORT-CORR-ORIG", a2_refs)
        self.assertNotIn("TEST-IMPORT-CORR-ORIG", b2_refs)
        self.assertNotIn(correction.l10n_cz_kh_document_reference, a2_refs)
        self.assertNotIn(correction.l10n_cz_kh_document_reference, b2_refs)

        correction_debug = next(
            row for row in debug["move_period_dates"] if row["reference"] == "TEST-IMPORT-CORR-REFUND"
        )
        self.assertEqual(correction_debug["effective_customs_mrn"], "27CZMRN0000045")
        self.assertEqual(correction_debug["effective_customs_release_date"], "2027-03-10")
        self.assertEqual(correction_debug["import_correction_origin_id"], origin.id)

    def test_import_correction_row45_requires_origin_link(self):
        self._create_move(
            "TEST-IMPORT-CORR-NO-ORIGIN",
            "in_refund",
            self.partner_de_supplier,
            self.purchase_account,
            self.tax_import_correction_full,
            1000,
            "2027-03-22",
            l10n_cz_vat_regime="third_country_import",
            l10n_cz_customs_decision_number="JSD-2027-0045",
            l10n_cz_customs_release_date="2027-03-22",
            l10n_cz_kh_document_reference="TEST-IMPORT-CORR-NO-ORIGIN",
        )

        with self.assertRaisesRegex(UserError, "missing Import Correction Origin"):
            self.company.l10n_cz_vat_filing_exports("2027-03-01", "2027-03-31")

    def test_coefficient_tax_tag_routes_dph_to_reduced_fields_and_keeps_kh_full(self):
        self._create_move(
            "TEST-COEF70-ASSET",
            "in_invoice",
            self.partner_cz_supplier,
            self.purchase_account,
            self.tax_purchase_domestic_coefficient,
            100000,
            "2027-03-24",
            l10n_cz_kh_document_reference="TEST-COEF70-ASSET",
        )

        exports = self.company.l10n_cz_vat_filing_exports(
            "2027-03-01",
            "2027-03-31",
            options={"line_52a_coefficient": 70},
        )
        debug = exports["debug"]
        veta4 = debug["dph_section_values"]["Veta4"]
        veta5 = debug["dph_section_values"]["Veta5"]

        self.assertEqual(debug["tag_amounts"].get("VAT 40 Base"), "100000.00")
        self.assertEqual(debug["tag_amounts"].get("VAT 40 Total"), "21000.00")
        self.assertEqual(veta4.get("pln23"), "100000.00")
        self.assertEqual(veta4.get("odp_tuz23"), "21000.00")
        self.assertNotIn("odp_tuz23_nar", veta4)
        self.assertEqual(veta5.get("koef_p20_nov"), "70.00")
        self.assertEqual(veta5.get("odp_uprav_kf"), "14700.00")

        b2_row = next(row for row in debug["kh"]["B2"] if row["reference"] == "TEST-COEF70-ASSET")
        self.assertEqual(b2_row["breakdown"]["1"]["base"], "100000.00")
        self.assertEqual(b2_row["breakdown"]["1"]["tax"], "21000.00")

    def test_kh_b2b_under_10k_routes_to_b3(self):
        self._create_move(
            "TEST-B2B-UNDER-10K",
            "in_invoice",
            self.partner_cz_supplier,
            self.purchase_account,
            self.tax_purchase_domestic,
            5000,
            "2027-03-20",
            l10n_cz_kh_document_reference="TEST-B2B-UNDER-10K",
        )

        exports = self.company.l10n_cz_vat_filing_exports("2027-03-01", "2027-03-31")
        kh = exports["debug"]["kh"]
        self.assertFalse([row for row in kh["B2"] if row["reference"] == "TEST-B2B-UNDER-10K"])
        self.assertEqual(kh["B3"]["count"], 1)
        self.assertEqual(kh["B3"]["breakdown"]["1"]["base"], "5000.00")
        self.assertEqual(kh["B3"]["breakdown"]["1"]["tax"], "1050.00")

    def test_kh_b2b_over_10k_routes_to_b2(self):
        self._create_move(
            "TEST-B2B-OVER-10K",
            "in_invoice",
            self.partner_cz_supplier,
            self.purchase_account,
            self.tax_purchase_domestic,
            15000,
            "2027-03-21",
            l10n_cz_kh_document_reference="TEST-B2B-OVER-10K",
        )

        exports = self.company.l10n_cz_vat_filing_exports("2027-03-01", "2027-03-31")
        kh = exports["debug"]["kh"]
        b2_row = next(row for row in kh["B2"] if row["reference"] == "TEST-B2B-OVER-10K")
        self.assertEqual(b2_row["breakdown"]["1"]["base"], "15000.00")
        self.assertEqual(b2_row["breakdown"]["1"]["tax"], "3150.00")
        self.assertEqual(kh["B3"]["count"], 0)

    def test_kh_threshold_uses_czk_amount_for_foreign_currency_invoice(self):
        self._set_currency_rate(self.usd, "2027-03-21", 0.04)
        self._create_move(
            "TEST-USD-B2B-CZK-THRESHOLD",
            "in_invoice",
            self.partner_cz_supplier,
            self.purchase_account,
            self.tax_purchase_domestic,
            500,
            "2027-03-21",
            currency_id=self.usd.id,
            l10n_cz_kh_document_reference="TEST-USD-B2B-CZK-THRESHOLD",
        )

        exports = self.company.l10n_cz_vat_filing_exports("2027-03-01", "2027-03-31")
        kh = exports["debug"]["kh"]
        b2_row = next(row for row in kh["B2"] if row["reference"] == "TEST-USD-B2B-CZK-THRESHOLD")
        self.assertEqual(b2_row["breakdown"]["1"]["base"], "12500.00")
        self.assertEqual(b2_row["breakdown"]["1"]["tax"], "2625.00")
        self.assertEqual(kh["B3"]["count"], 0)

    def test_kh_b2c_over_10k_routes_to_a5(self):
        self._create_move(
            "TEST-B2C-OVER-10K",
            "out_invoice",
            self.partner_cz_private,
            self.sale_account,
            self.tax_sale_domestic,
            20000,
            "2027-03-22",
            l10n_cz_kh_document_reference="TEST-B2C-OVER-10K",
        )

        exports = self.company.l10n_cz_vat_filing_exports("2027-03-01", "2027-03-31")
        kh = exports["debug"]["kh"]
        self.assertFalse([row for row in kh["A4"] if row["reference"] == "TEST-B2C-OVER-10K"])
        self.assertEqual(kh["A5"]["count"], 1)
        self.assertEqual(kh["A5"]["breakdown"]["1"]["base"], "20000.00")
        self.assertEqual(kh["A5"]["breakdown"]["1"]["tax"], "4200.00")

    def test_kh_threshold_routing_is_reflected_in_xml(self):
        self._create_move(
            "TEST-KH-XML-B2B-UNDER-10K",
            "in_invoice",
            self.partner_cz_supplier,
            self.purchase_account,
            self.tax_purchase_domestic,
            5000,
            "2027-03-20",
            l10n_cz_kh_document_reference="TEST-KH-XML-B2B-UNDER-10K",
        )
        self._create_move(
            "TEST-KH-XML-B2B-OVER-10K",
            "in_invoice",
            self.partner_cz_supplier,
            self.purchase_account,
            self.tax_purchase_domestic,
            15000,
            "2027-03-21",
            l10n_cz_kh_document_reference="TEST-KH-XML-B2B-OVER-10K",
        )
        self._create_move(
            "TEST-KH-XML-B2C-OVER-10K",
            "out_invoice",
            self.partner_cz_private,
            self.sale_account,
            self.tax_sale_domestic,
            20000,
            "2027-03-22",
            l10n_cz_kh_document_reference="TEST-KH-XML-B2C-OVER-10K",
        )

        exports = self.company.l10n_cz_vat_filing_exports("2027-03-01", "2027-03-31")
        root = ET.fromstring(exports["dphkh1_xml"])

        veta_a4 = root.findall(".//VetaA4")
        veta_a5 = root.findall(".//VetaA5")
        veta_b2 = root.findall(".//VetaB2")
        veta_b3 = root.findall(".//VetaB3")

        self.assertEqual(len(veta_a4), 0)
        self.assertEqual(len(veta_a5), 1)
        self.assertEqual(veta_a5[0].attrib.get("zakl_dane1"), "20000.00")
        self.assertEqual(veta_a5[0].attrib.get("dan1"), "4200.00")

        self.assertEqual(len(veta_b2), 1)
        self.assertEqual(veta_b2[0].attrib.get("c_evid_dd"), "TEST-KH-XML-B2B-OVER-10K")
        self.assertEqual(veta_b2[0].attrib.get("zakl_dane1"), "15000.00")
        self.assertEqual(veta_b2[0].attrib.get("dan1"), "3150.00")

        self.assertEqual(len(veta_b3), 1)
        self.assertEqual(veta_b3[0].attrib.get("zakl_dane1"), "5000.00")
        self.assertEqual(veta_b3[0].attrib.get("dan1"), "1050.00")

    def test_kh_b2b_refunds_under_10k_aggregate_without_origin(self):
        sale_refund = self._create_move(
            "TEST-SALE-REFUND-UNDER-10K",
            "out_refund",
            self.partner_cz_customer,
            self.sale_account,
            self.tax_sale_domestic,
            2000,
            "2027-03-23",
            l10n_cz_kh_document_reference="TEST-SALE-REFUND-UNDER-10K",
        )
        purchase_refund = self._create_move(
            "TEST-PURCHASE-REFUND-UNDER-10K",
            "in_refund",
            self.partner_cz_supplier,
            self.purchase_account,
            self.tax_purchase_domestic,
            3000,
            "2027-03-24",
            l10n_cz_kh_document_reference="TEST-PURCHASE-REFUND-UNDER-10K",
        )

        exports = self.company.l10n_cz_vat_filing_exports("2027-03-01", "2027-03-31")
        kh = exports["debug"]["kh"]
        self.assertFalse([row for row in kh["A4"] if row["reference"] == sale_refund.l10n_cz_kh_document_reference])
        self.assertFalse([row for row in kh["B2"] if row["reference"] == purchase_refund.l10n_cz_kh_document_reference])
        self.assertEqual(kh["A5"]["count"], 1)
        self.assertEqual(kh["A5"]["breakdown"]["1"]["base"], "-2000.00")
        self.assertEqual(kh["A5"]["breakdown"]["1"]["tax"], "-420.00")
        self.assertEqual(kh["B3"]["count"], 1)
        self.assertEqual(kh["B3"]["breakdown"]["1"]["base"], "-3000.00")
        self.assertEqual(kh["B3"]["breakdown"]["1"]["tax"], "-630.00")

    def test_kh_b2b_refunds_under_10k_stay_detailed_with_over_10k_origin(self):
        sale_origin = self._create_move(
            "TEST-SALE-ORIGIN-OVER-10K",
            "out_invoice",
            self.partner_cz_customer,
            self.sale_account,
            self.tax_sale_domestic,
            20000,
            "2027-03-22",
            l10n_cz_kh_document_reference="TEST-SALE-ORIGIN-OVER-10K",
        )
        purchase_origin = self._create_move(
            "TEST-PURCHASE-ORIGIN-OVER-10K",
            "in_invoice",
            self.partner_cz_supplier,
            self.purchase_account,
            self.tax_purchase_domestic,
            30000,
            "2027-03-22",
            l10n_cz_kh_document_reference="TEST-PURCHASE-ORIGIN-OVER-10K",
        )
        sale_refund = self._create_move(
            "TEST-SALE-REFUND-LINKED-UNDER-10K",
            "out_refund",
            self.partner_cz_customer,
            self.sale_account,
            self.tax_sale_domestic,
            2000,
            "2027-03-23",
            reversed_entry_id=sale_origin.id,
            l10n_cz_kh_document_reference="TEST-SALE-REFUND-LINKED-UNDER-10K",
        )
        purchase_refund = self._create_move(
            "TEST-PURCHASE-REFUND-LINKED-UNDER-10K",
            "in_refund",
            self.partner_cz_supplier,
            self.purchase_account,
            self.tax_purchase_domestic,
            3000,
            "2027-03-23",
            reversed_entry_id=purchase_origin.id,
            l10n_cz_kh_document_reference="TEST-PURCHASE-REFUND-LINKED-UNDER-10K",
        )

        exports = self.company.l10n_cz_vat_filing_exports("2027-03-01", "2027-03-31")
        kh = exports["debug"]["kh"]
        a4_row = next(row for row in kh["A4"] if row["reference"] == sale_refund.l10n_cz_kh_document_reference)
        b2_row = next(row for row in kh["B2"] if row["reference"] == purchase_refund.l10n_cz_kh_document_reference)
        self.assertEqual(a4_row["breakdown"]["1"]["base"], "-2000.00")
        self.assertEqual(a4_row["breakdown"]["1"]["tax"], "-420.00")
        self.assertEqual(b2_row["breakdown"]["1"]["base"], "-3000.00")
        self.assertEqual(b2_row["breakdown"]["1"]["tax"], "-630.00")

    def test_rpdp_line_subject_code_is_used_for_kh_a1(self):
        self._create_move(
            "TEST-A1-LINE-CODE",
            "out_invoice",
            self.partner_cz_customer,
            self.sale_account,
            self.tax_sale_rc,
            15000,
            "2027-03-26",
            l10n_cz_kh_document_reference="TEST-A1-LINE-CODE",
            line_extra={"l10n_cz_kh_subject_code": "4"},
        )

        exports = self.company.l10n_cz_vat_filing_exports("2027-03-01", "2027-03-31")
        a1_row = next(row for row in exports["debug"]["kh"]["A1"] if row["reference"] == "TEST-A1-LINE-CODE")
        self.assertEqual(a1_row["reverse_charge_code"], "4")
        self.assertEqual(exports["debug"]["dph_section_values"]["Veta2"].get("pln_rez_pren"), "15000.00")

    def test_rpdp_line_subject_code_is_used_for_kh_b1(self):
        self._create_move(
            "TEST-B1-LINE-CODE",
            "in_invoice",
            self.partner_cz_supplier,
            self.purchase_account,
            self.tax_purchase_b1,
            18000,
            "2027-03-27",
            l10n_cz_kh_document_reference="TEST-B1-LINE-CODE",
            line_extra={"l10n_cz_kh_subject_code": "4"},
        )

        exports = self.company.l10n_cz_vat_filing_exports("2027-03-01", "2027-03-31")
        b1_row = next(row for row in exports["debug"]["kh"]["B1"] if row["reference"] == "TEST-B1-LINE-CODE")
        self.assertEqual(b1_row["reverse_charge_code"], "4")
        veta1 = exports["debug"]["dph_section_values"]["Veta1"]
        veta4 = exports["debug"]["dph_section_values"]["Veta4"]
        self.assertEqual(veta1.get("rez_pren23"), "18000.00")
        self.assertEqual(veta1.get("dan_rpren23"), "3780.00")
        self.assertEqual(veta4.get("nar_zdp23"), "18000.00")
        self.assertEqual(veta4.get("od_zdp23"), "3780.00")

    def test_rpdp_temporary_code_a1_requires_100k_base(self):
        self._create_move(
            "TEST-A1-CODE11-UNDER-100K",
            "out_invoice",
            self.partner_cz_customer,
            self.sale_account,
            self.tax_sale_rc,
            90000,
            "2027-03-26",
            l10n_cz_kh_document_reference="TEST-A1-CODE11-UNDER-100K",
            line_extra={"l10n_cz_kh_subject_code": "11"},
        )

        with self.assertRaisesRegex(UserError, "below 100.000 CZK"):
            self.company.l10n_cz_vat_filing_exports("2027-03-01", "2027-03-31")

    def test_rpdp_temporary_code_b1_requires_100k_base(self):
        self._create_move(
            "TEST-B1-CODE14-UNDER-100K",
            "in_invoice",
            self.partner_cz_supplier,
            self.purchase_account,
            self.tax_purchase_b1,
            90000,
            "2027-03-27",
            l10n_cz_kh_document_reference="TEST-B1-CODE14-UNDER-100K",
            line_extra={"l10n_cz_kh_subject_code": "14"},
        )

        with self.assertRaisesRegex(UserError, "below 100.000 CZK"):
            self.company.l10n_cz_vat_filing_exports("2027-03-01", "2027-03-31")

    def test_year_end_row53_settlement_is_computed_and_kh_untouched(self):
        self._create_move(
            "TEST-ROW53-YE",
            "in_invoice",
            self.partner_cz_supplier,
            self.purchase_account,
            self.tax_purchase_domestic_coefficient,
            100000,
            "2027-12-15",
            l10n_cz_kh_document_reference="TEST-ROW53-YE",
        )

        exports = self.company.l10n_cz_vat_filing_exports(
            "2027-12-01",
            "2027-12-31",
            options={
                "line_52a_coefficient": 60,
                "line_53a_settlement_coefficient": 70,
            },
        )
        debug = exports["debug"]
        veta5 = debug["dph_section_values"]["Veta5"]
        self.assertEqual(veta5.get("koef_p20_nov"), "60.00")
        self.assertEqual(veta5.get("odp_uprav_kf"), "12600.00")
        self.assertEqual(veta5.get("koef_p20_vypor"), "70.00")
        self.assertEqual(veta5.get("vypor_odp"), "2100.00")

        b2_row = next(row for row in debug["kh"]["B2"] if row["reference"] == "TEST-ROW53-YE")
        self.assertEqual(b2_row["breakdown"]["1"]["base"], "100000.00")
        self.assertEqual(b2_row["breakdown"]["1"]["tax"], "21000.00")

    def test_quarterly_legal_entity_export_requires_disabling_kh(self):
        with self.assertRaisesRegex(UserError, "quarterly exports must disable include_dphkh1"):
            self.company.l10n_cz_vat_filing_exports("2026-01-01", "2026-03-31")

    def test_dodatecne_dph_requires_explicit_tax_statement_date(self):
        self._create_move(
            "TEST-DODATECNE-SALE",
            "out_invoice",
            self.partner_cz_customer,
            self.sale_account,
            self.tax_sale_domestic,
            1000,
            "2026-03-10",
            l10n_cz_kh_document_reference="TEST-DODATECNE-SALE",
        )

        with self.assertRaisesRegex(UserError, "require an explicit tax_statement_date"):
            self.company.l10n_cz_vat_filing_exports(
                "2026-03-01",
                "2026-03-31",
                options={"dph_form": "D"},
            )
