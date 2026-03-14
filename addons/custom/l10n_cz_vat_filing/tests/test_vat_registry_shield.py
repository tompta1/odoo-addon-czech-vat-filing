from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import TransactionCase


class TestL10nCzVatRegistryShield(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.Account = cls.env["account.account"]
        cls.Journal = cls.env["account.journal"]
        cls.Move = cls.env["account.move"]
        cls.Partner = cls.env["res.partner"]
        cls.PartnerBank = cls.env["res.partner.bank"]
        cls.Tax = cls.env["account.tax"]
        cls.cz = cls.env.ref("base.cz")
        cls.company.write(
            {
                "account_fiscal_country_id": cls.cz.id,
                "l10n_cz_vat_registry_enabled": True,
                "l10n_cz_vat_registry_api_url": "https://example.test/vat-registry",
                "l10n_cz_vat_registry_vat_param": "dic",
                "l10n_cz_vat_registry_cache_hours": 24,
                "l10n_cz_vat_registry_block_on_post": True,
                "l10n_cz_vat_registry_block_on_payment": True,
                "l10n_cz_vat_registry_block_unreliable": True,
                "l10n_cz_vat_registry_block_unpublished_bank": True,
                "l10n_cz_vat_registry_block_on_lookup_error": False,
            }
        )
        cls.company.partner_id.with_context(no_vat_validation=True).write(
            {
                "vat": "CZ699999999",
                "country_id": cls.cz.id,
                "street": "Shield Test 1",
                "city": "Praha",
                "zip": "11000",
            }
        )
        cls.purchase_account = cls._find_account(["expense", "expense_direct_cost", "expense_depreciation"])
        cls.purchase_journal = cls._find_journal("purchase")
        cls.tax_purchase_domestic = cls._find_tax("purchase", ["VAT 40 Base", "VAT 40 Total"])

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

    def _new_cz_supplier(self, marker, vat):
        return self.Partner.with_context(no_vat_validation=True).create(
            {
                "name": f"CZ Supplier {marker}",
                "vat": vat,
                "country_id": self.cz.id,
                "company_type": "company",
                "street": "Shieldovaci 1",
                "city": "Praha",
                "zip": "11000",
            }
        )

    def _new_partner_bank(self, partner, account_number):
        return self.PartnerBank.create(
            {
                "partner_id": partner.id,
                "acc_number": account_number,
            }
        )

    def _draft_vendor_bill(self, marker, partner, bank_account):
        return self.Move.create(
            {
                "move_type": "in_invoice",
                "partner_id": partner.id,
                "partner_bank_id": bank_account.id,
                "journal_id": self.purchase_journal.id,
                "invoice_date": "2027-03-20",
                "date": "2027-03-20",
                "ref": marker,
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "name": marker,
                            "quantity": 1,
                            "price_unit": 1000,
                            "account_id": self.purchase_account.id,
                            "tax_ids": [(6, 0, [self.tax_purchase_domestic.id])],
                        },
                    )
                ],
            }
        )

    def _mock_registry_result(self, *, status="ok", is_unreliable=False, accounts=None, error_message=""):
        return {
            "status": status,
            "error_message": error_message,
            "source_url": "https://example.test/vat-registry",
            "payload": {"status": status},
            "is_unreliable": is_unreliable,
            "published_bank_accounts": accounts or [],
        }

    def test_vendor_bill_post_is_blocked_for_unreliable_supplier(self):
        supplier = self._new_cz_supplier("UNREL", "CZ10000001")
        bank = self._new_partner_bank(supplier, "19-1234567890/0800")
        bill = self._draft_vendor_bill("TEST-UNREL-BLOCK", supplier, bank)

        with patch.object(
            type(self.company),
            "_l10n_cz_vat_registry_fetch",
            autospec=True,
            return_value=self._mock_registry_result(is_unreliable=True, accounts=[bank.acc_number]),
        ) as mocked_fetch:
            with self.assertRaisesRegex(UserError, "unreliable VAT payer"):
                bill.action_post()
            self.assertEqual(mocked_fetch.call_count, 1)

        self.assertEqual(bill.state, "draft")
        self.assertTrue(bill.l10n_cz_vat_registry_check_id)
        self.assertIn("unreliable VAT payer", bill.l10n_cz_vat_registry_note or "")

    def test_vendor_bill_post_is_blocked_for_unpublished_bank_account(self):
        supplier = self._new_cz_supplier("BANK", "CZ10000002")
        bank = self._new_partner_bank(supplier, "19-1111111111/0800")
        bill = self._draft_vendor_bill("TEST-BANK-BLOCK", supplier, bank)

        with patch.object(
            type(self.company),
            "_l10n_cz_vat_registry_fetch",
            autospec=True,
            return_value=self._mock_registry_result(accounts=["55-9999999999/0100"]),
        ):
            with self.assertRaisesRegex(UserError, "not published"):
                bill.action_post()

        self.assertEqual(bill.state, "draft")
        self.assertTrue(bill.l10n_cz_vat_registry_check_id)
        self.assertIn("not published", bill.l10n_cz_vat_registry_note or "")

    def test_vendor_bill_post_passes_for_published_bank_account(self):
        supplier = self._new_cz_supplier("PASS", "CZ10000003")
        bank = self._new_partner_bank(supplier, "19-2222222222/0800")
        bill = self._draft_vendor_bill("TEST-BANK-PASS", supplier, bank)

        with patch.object(
            type(self.company),
            "_l10n_cz_vat_registry_fetch",
            autospec=True,
            return_value=self._mock_registry_result(accounts=[bank.acc_number]),
        ):
            bill.action_post()

        self.assertEqual(bill.state, "posted")
        self.assertTrue(bill.l10n_cz_vat_registry_check_id)
        self.assertIn("shield check passed", (bill.l10n_cz_vat_registry_note or "").lower())

    def test_registry_result_is_reused_from_cache(self):
        supplier = self._new_cz_supplier("CACHE", "CZ10000004")
        bank = self._new_partner_bank(supplier, "19-3333333333/0800")

        with patch.object(
            type(self.company),
            "_l10n_cz_vat_registry_fetch",
            autospec=True,
            return_value=self._mock_registry_result(accounts=[bank.acc_number]),
        ) as mocked_fetch:
            first = self.company.l10n_cz_vat_registry_evaluate_partner(supplier, bank_account=bank.acc_number)
            second = self.company.l10n_cz_vat_registry_evaluate_partner(supplier, bank_account=bank.acc_number)

        self.assertEqual(mocked_fetch.call_count, 1)
        self.assertTrue(first["check"])
        self.assertEqual(first["check"], second["check"])

    def test_lookup_error_can_warn_without_blocking(self):
        supplier = self._new_cz_supplier("LOOKUPERR", "CZ10000005")
        bank = self._new_partner_bank(supplier, "19-4444444444/0800")
        bill = self._draft_vendor_bill("TEST-LOOKUP-NONBLOCK", supplier, bank)
        self.company.l10n_cz_vat_registry_block_on_lookup_error = False

        with patch.object(
            type(self.company),
            "_l10n_cz_vat_registry_fetch",
            autospec=True,
            return_value=self._mock_registry_result(status="error", error_message="temporary upstream outage"),
        ):
            bill.action_post()

        self.assertEqual(bill.state, "posted")
        self.assertTrue(bill.l10n_cz_vat_registry_check_id)
        self.assertIn("lookup failed", (bill.l10n_cz_vat_registry_note or "").lower())

