from datetime import date
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import TransactionCase


class TestL10nCzVatFxCnb(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.Account = cls.env["account.account"]
        cls.Journal = cls.env["account.journal"]
        cls.Move = cls.env["account.move"]
        cls.Partner = cls.env["res.partner"]
        cls.Tax = cls.env["account.tax"]
        cls.Currency = cls.env["res.currency"]
        cls.CurrencyRate = cls.env["res.currency.rate"]
        cls.cz = cls.env.ref("base.cz")
        cls.usd = cls.Currency.search([("name", "=", "USD")], limit=1)
        cls.company.write(
            {
                "account_fiscal_country_id": cls.cz.id,
                "l10n_cz_vat_registry_enabled": False,
                "l10n_cz_vat_fx_enforce_cnb": True,
                "l10n_cz_vat_fx_api_url": "https://example.test/vat-fx",
                "l10n_cz_vat_fx_currency_param": "currency",
                "l10n_cz_vat_fx_date_param": "date",
                "l10n_cz_vat_fx_cache_days": 365,
                "l10n_cz_vat_fx_block_on_lookup_error": False,
            }
        )
        cls.company.partner_id.with_context(no_vat_validation=True).write(
            {
                "vat": "CZ699999999",
                "country_id": cls.cz.id,
                "street": "FX Test 1",
                "city": "Praha",
                "zip": "11000",
            }
        )
        cls.purchase_account = cls._find_account(["expense", "expense_direct_cost", "expense_depreciation"])
        cls.purchase_journal = cls._find_journal("purchase")
        cls.tax_purchase_domestic = cls._find_tax("purchase", ["VAT 40 Base", "VAT 40 Total"])
        cls.partner_cz_supplier = cls._ensure_partner("CZ FX Supplier", "CZ30000001", cls.cz)

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
        raise AssertionError(f"Missing {type_tax_use!r} tax with tags {required_tags!r}")

    @classmethod
    def _ensure_partner(cls, name, vat, country):
        partner = cls.Partner.search([("vat", "=", vat)], limit=1)
        if partner:
            return partner
        return cls.Partner.with_context(no_vat_validation=True).create(
            {
                "name": name,
                "vat": vat,
                "country_id": country.id,
                "company_type": "company",
                "street": "FX partner 1",
                "city": "Praha",
                "zip": "11000",
            }
        )

    @classmethod
    def _set_currency_rate(cls, currency, date, rate):
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

    def _create_usd_bill(self, marker, amount, invoice_date, **extra):
        vals = {
            "move_type": "in_invoice",
            "partner_id": self.partner_cz_supplier.id,
            "journal_id": self.purchase_journal.id,
            "currency_id": self.usd.id,
            "invoice_date": invoice_date,
            "date": invoice_date,
            "ref": marker,
            "invoice_line_ids": [
                (
                    0,
                    0,
                    {
                        "name": marker,
                        "quantity": 1,
                        "price_unit": amount,
                        "account_id": self.purchase_account.id,
                        "tax_ids": [(6, 0, [self.tax_purchase_domestic.id])],
                    },
                )
            ],
        }
        vals.update(extra)
        return self.Move.create(vals)

    def _mock_fx_result(self, *, status="ok", rate=25.0, error_message="", network_error=False):
        return {
            "status": status,
            "error_message": error_message,
            "source_url": "https://example.test/vat-fx",
            "payload": {"status": status},
            "rate_to_czk": rate if status == "ok" else 0.0,
            "network_error": network_error,
        }

    def test_export_uses_cnb_rate_not_accounting_rate_for_foreign_currency_move(self):
        self._set_currency_rate(self.usd, "2028-01-15", 0.05)  # accounting rate => 1 USD = 20 CZK
        bill = self._create_usd_bill("FX-CNB-TEST", 100, "2028-01-15")

        with patch.object(
            type(self.company),
            "_l10n_cz_vat_fx_fetch_rate",
            autospec=True,
            return_value=self._mock_fx_result(rate=25.0),
        ):
            bill.action_post()

        exports = self.company.l10n_cz_vat_filing_exports("2028-01-01", "2028-01-31")
        debug = exports["debug"]
        self.assertEqual(bill.l10n_cz_vat_fx_rate, 25.0)
        self.assertEqual(bill.l10n_cz_vat_fx_rate_source, "cnb")
        self.assertEqual(debug["tag_amounts"].get("VAT 40 Base"), "2500.00")
        self.assertEqual(debug["tag_amounts"].get("VAT 40 Total"), "525.00")

    def test_manual_vat_fx_rate_overrides_api_lookup(self):
        self._set_currency_rate(self.usd, "2028-01-16", 0.05)
        bill = self._create_usd_bill(
            "FX-MANUAL-TEST",
            100,
            "2028-01-16",
            l10n_cz_vat_fx_manual_rate=30.0,
        )

        with patch.object(type(self.company), "_l10n_cz_vat_fx_fetch_rate", autospec=True) as mocked_fetch:
            bill.action_post()
            self.assertEqual(mocked_fetch.call_count, 0)

        exports = self.company.l10n_cz_vat_filing_exports("2028-01-01", "2028-01-31")
        debug = exports["debug"]
        self.assertEqual(bill.l10n_cz_vat_fx_rate, 30.0)
        self.assertEqual(bill.l10n_cz_vat_fx_rate_source, "manual")
        self.assertEqual(debug["tag_amounts"].get("VAT 40 Base"), "3000.00")
        self.assertEqual(debug["tag_amounts"].get("VAT 40 Total"), "630.00")

    def test_lookup_error_can_block_posting_when_policy_enabled(self):
        self.company.l10n_cz_vat_fx_block_on_lookup_error = True
        self._set_currency_rate(self.usd, "2028-01-17", 0.05)
        bill = self._create_usd_bill("FX-ERR-BLOCK", 100, "2028-01-17")

        with patch.object(
            type(self.company),
            "_l10n_cz_vat_fx_fetch_rate",
            autospec=True,
            return_value=self._mock_fx_result(status="error", error_message="upstream timeout"),
        ):
            with self.assertRaisesRegex(UserError, "VAT FX lookup failed"):
                bill.action_post()

        self.assertEqual(bill.state, "draft")

    def test_fetch_rate_parses_official_cnb_text_payload(self):
        self.company.l10n_cz_vat_fx_api_url = (
            "https://www.cnb.cz/cs/financni-trhy/devizovy-trh/kurzy-devizoveho-trhu/"
            "kurzy-devizoveho-trhu/denni_kurz.txt"
        )

        body = (
            "15.01.2028 #10\n"
            "země|měna|množství|kód|kurz\n"
            "EMU|euro|1|EUR|25,355\n"
            "USA|dolar|1|USD|23,150\n"
        )
        called = {}

        class _FakeResponse:
            def __init__(self, text):
                self._text = text

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return self._text.encode("utf-8")

        def _fake_urlopen(req, timeout=10):
            called["url"] = req.full_url
            called["timeout"] = timeout
            return _FakeResponse(body)

        with patch(
            "odoo.addons.l10n_cz_vat_filing.models.res_company.request.urlopen",
            side_effect=_fake_urlopen,
        ):
            result = self.company._l10n_cz_vat_fx_fetch_rate(self.usd, "2028-01-15")

        self.assertEqual(result["status"], "ok")
        self.assertAlmostEqual(result["rate_to_czk"], 23.15, places=6)
        self.assertIn("date=15.01.2028", called["url"])
        self.assertNotIn("currency=", called["url"])

    def test_weekend_duzp_falls_back_to_preceding_working_day(self):
        saturday = date(2028, 3, 18)  # Saturday — no ČNB rate
        friday = date(2028, 3, 17)    # Friday — rate available

        def _fake_fetch(company_self, currency, tax_date):
            from odoo import fields as f
            d = f.Date.to_date(tax_date)
            if d >= saturday:
                return self._mock_fx_result(status="error", error_message="HTTP Error 404: Not Found")
            if d == friday:
                return self._mock_fx_result(rate=23.5)
            return self._mock_fx_result(status="error", error_message="unexpected date in test")

        self._set_currency_rate(self.usd, "2028-03-18", 0.04)
        with patch.object(
            type(self.company),
            "_l10n_cz_vat_fx_fetch_rate",
            autospec=True,
            side_effect=_fake_fetch,
        ) as mocked:
            rate_record = self.company._l10n_cz_vat_fx_get_rate_record(
                self.usd, saturday, force_refresh=True
            )

        self.assertEqual(rate_record.status, "ok")
        self.assertAlmostEqual(rate_record.rate_to_czk, 23.5, places=6)
        # Cached under the invoice's DUZP (Saturday), rate sourced from Friday
        self.assertEqual(rate_record.tax_date, saturday)
        self.assertEqual(rate_record.rate_date, friday)
        # Called twice: Saturday fails, Friday succeeds
        self.assertEqual(mocked.call_count, 2)

    def test_network_error_does_not_trigger_fallback(self):
        monday = date(2028, 3, 20)

        with patch.object(
            type(self.company),
            "_l10n_cz_vat_fx_fetch_rate",
            autospec=True,
            return_value=self._mock_fx_result(
                status="error", error_message="connection refused", network_error=True
            ),
        ) as mocked:
            rate_record = self.company._l10n_cz_vat_fx_get_rate_record(
                self.usd, monday, force_refresh=True
            )

        self.assertEqual(rate_record.status, "error")
        # Hard network failure — fallback loop must stop after the first attempt
        self.assertEqual(mocked.call_count, 1)
