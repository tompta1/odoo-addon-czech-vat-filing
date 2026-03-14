from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import TransactionCase


class TestL10nCzIsdsSubmission(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.History = cls.env["l10n_cz.vat.filing.history"]
        cls.cz = cls.env.ref("base.cz")
        cls.company.write({"account_fiscal_country_id": cls.cz.id})
        cls.company.partner_id.with_context(no_vat_validation=True).write(
            {
                "vat": "CZ699999999",
                "country_id": cls.cz.id,
                "street": "ISDS Test 1",
                "city": "Praha",
                "zip": "11000",
            }
        )

    def _new_history(self, marker):
        options = {
            "include_dphdp3": True,
            "include_dphkh1": False,
            "include_dphshv": False,
            "submission_date": "2027-04-20",
            "dph_form": "B",
            "kh_form": "B",
            "sh_form": "R",
        }
        exports = {
            "dphdp3_xml": f"<Pisemnost id='{marker}'/>",
            "dphkh1_xml": "",
            "dphshv_xml": "",
            "debug_json": "{}",
            "debug": {
                "metadata": {
                    "submission_date": "2027-04-20",
                    "dph_form": "B",
                    "kh_form": "B",
                    "sh_form": "R",
                },
                "validation": {"warnings": []},
            },
        }
        return self.History.create_export_record(
            self.company,
            "2027-03-01",
            "2027-03-31",
            options,
            exports,
            include_debug_json=False,
        )

    def _patch_http_response(self, body, captured):
        class _FakeResponse:
            def __init__(self, text):
                self._text = text

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return self._text.encode("utf-8")

        def _fake_urlopen(req, timeout=20):
            captured["url"] = req.full_url
            captured["timeout"] = timeout
            captured["method"] = req.get_method()
            captured["auth"] = req.headers.get("Authorization")
            captured["body"] = (req.data or b"").decode("utf-8", errors="replace")
            return _FakeResponse(body)

        return patch(
            "odoo.addons.l10n_cz_vat_filing.models.res_company.request.urlopen",
            side_effect=_fake_urlopen,
        )

    def test_mock_submission_updates_history(self):
        history = self._new_history("MOCK-ISDS")
        self.company.write(
            {
                "l10n_cz_isds_enabled": True,
                "l10n_cz_isds_mode": "mock",
                "l10n_cz_isds_target_box_id": "pndaab6",
            }
        )

        history.action_submit_isds()

        self.assertEqual(history.isds_status, "submitted")
        self.assertTrue((history.isds_message_id or "").startswith("MOCK-"))
        self.assertEqual(history.isds_target_box_id, "pndaab6")
        self.assertIn("mock", (history.isds_response_json or "").lower())

    def test_submission_requires_enabled_company_setting(self):
        history = self._new_history("DISABLED-ISDS")
        self.company.write(
            {
                "l10n_cz_isds_enabled": False,
                "l10n_cz_isds_mode": "mock",
            }
        )

        action = history.action_submit_isds()

        self.assertEqual(history.isds_status, "error")
        self.assertIn("Enable Datova schranka", history.isds_last_error or "")
        self.assertEqual(action.get("tag"), "display_notification")

    def test_http_json_submission_success(self):
        history = self._new_history("HTTP-ISDS-OK")
        self.company.write(
            {
                "l10n_cz_isds_enabled": True,
                "l10n_cz_isds_mode": "http_json",
                "l10n_cz_isds_api_url": "https://isds-bridge.example.test/submit",
                "l10n_cz_isds_username": "api-user",
                "l10n_cz_isds_password": "api-pass",
                "l10n_cz_isds_target_box_id": "pndaab6",
            }
        )
        captured = {}
        with self._patch_http_response(
            '{"status":"ok","message_id":"ISDS-123","delivery_info":"accepted"}',
            captured,
        ):
            history.action_submit_isds()

        self.assertEqual(history.isds_status, "submitted")
        self.assertEqual(history.isds_message_id, "ISDS-123")
        self.assertIn("Basic ", captured.get("auth") or "")
        self.assertIn('"target_box_id": "pndaab6"', captured.get("body") or "")
        self.assertEqual(captured.get("method"), "POST")

    def test_http_json_submission_error_sets_history_error(self):
        history = self._new_history("HTTP-ISDS-ERR")
        self.company.write(
            {
                "l10n_cz_isds_enabled": True,
                "l10n_cz_isds_mode": "http_json",
                "l10n_cz_isds_api_url": "https://isds-bridge.example.test/submit",
                "l10n_cz_isds_username": "api-user",
                "l10n_cz_isds_password": "api-pass",
                "l10n_cz_isds_target_box_id": "pndaab6",
            }
        )
        captured = {}
        with self._patch_http_response('{"status":"error","message":"Rejected"}', captured):
            action = history.action_submit_isds()

        self.assertEqual(history.isds_status, "error")
        self.assertIn("rejected", (history.isds_last_error or "").lower())
        self.assertEqual(action.get("tag"), "display_notification")
