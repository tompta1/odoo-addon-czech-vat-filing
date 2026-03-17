import json

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase


class TestL10nCzVatFilingExportWizard(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Wizard = cls.env["l10n_cz.vat.filing.export.wizard"]
        cls.History = cls.env["l10n_cz.vat.filing.history"]
        cls.company = cls.env.company
        cls.cz = cls.env.ref("base.cz")
        cls.company.write({"account_fiscal_country_id": cls.cz.id})
        cls.company.partner_id.with_context(no_vat_validation=True).write(
            {
                "vat": "CZ699999999",
                "country_id": cls.cz.id,
                "street": "Wizard Test 1",
                "city": "Praha",
                "zip": "11000",
            }
        )

    def test_period_override_requires_pair(self):
        with self.assertRaises(ValidationError):
            self.Wizard.create(
                {
                    "company_id": self.company.id,
                    "date_from": "2027-03-01",
                    "date_to": "2027-03-31",
                    "period_from": "2027-03-05",
                }
            )

    def test_row_53_requires_year_end_period(self):
        with self.assertRaises(ValidationError):
            self.Wizard.create(
                {
                    "company_id": self.company.id,
                    "date_from": "2027-03-01",
                    "date_to": "2027-03-31",
                    "calculate_row_53": True,
                    "actual_year_coefficient": 80,
                }
            )

    def test_row_53_requires_actual_coefficient(self):
        with self.assertRaises(ValidationError):
            self.Wizard.create(
                {
                    "company_id": self.company.id,
                    "date_from": "2027-12-01",
                    "date_to": "2027-12-31",
                    "period_kind": "month",
                    "calculate_row_53": True,
                }
            )

    def test_build_options_adds_row_53_settlement_coefficient(self):
        wizard = self.Wizard.create(
            {
                "company_id": self.company.id,
                "date_from": "2027-12-01",
                "date_to": "2027-12-31",
                "period_kind": "month",
                "calculate_row_53": True,
                "actual_year_coefficient": 81,
            }
        )
        options = wizard._build_options()
        self.assertEqual(options.get("line_53a_settlement_coefficient"), 81)

    def test_action_export_zip_returns_download_url(self):
        before_count = self.History.search_count([("company_id", "=", self.company.id)])
        wizard = self.Wizard.create(
            {
                "company_id": self.company.id,
                "date_from": "2027-03-01",
                "date_to": "2027-03-31",
                "include_dphdp3": True,
                "include_dphkh1": False,
                "include_dphshv": False,
                "include_debug_json": True,
                "submission_date": "2027-04-20",
                "period_kind": "month",
            }
        )
        action = wizard.action_export_zip()
        self.assertEqual(action["type"], "ir.actions.act_url")
        self.assertIn("/web/content/", action["url"])
        history = self.History.search([("company_id", "=", self.company.id)], order="id desc", limit=1)
        self.assertTrue(history)
        self.assertEqual(self.History.search_count([("company_id", "=", self.company.id)]), before_count + 1)
        self.assertTrue(history.zip_attachment_id)
        self.assertTrue(history.dphdp3_attachment_id)
        self.assertFalse(history.dphkh1_attachment_id)
        self.assertFalse(history.dphshv_attachment_id)
        self.assertTrue(history.debug_attachment_id)
        self.assertEqual(history.include_dphdp3, True)
        self.assertEqual(history.include_dphkh1, False)
        self.assertEqual(history.include_dphshv, False)
        self.assertEqual(history.include_debug_json, True)
        options_payload = json.loads(history.options_json or "{}")
        self.assertEqual(options_payload.get("dph_form"), "B")
        self.assertEqual(options_payload.get("kh_form"), "B")
        self.assertEqual(options_payload.get("sh_form"), "R")
