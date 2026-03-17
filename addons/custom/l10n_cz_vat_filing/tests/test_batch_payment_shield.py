from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import TransactionCase


class TestL10nCzBatchPaymentShield(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if "account.batch.payment" not in cls.env:
            cls.skipTest(cls, "account_batch_payment (Enterprise) not installed — skipping batch shield tests")

        cls.company = cls.env.company
        cls.Partner = cls.env["res.partner"]
        cls.PartnerBank = cls.env["res.partner.bank"]
        cls.Payment = cls.env["account.payment"]
        cls.BatchPayment = cls.env["account.batch.payment"]
        cls.Journal = cls.env["account.journal"]
        cls.cz = cls.env.ref("base.cz")

        cls.company.write(
            {
                "account_fiscal_country_id": cls.cz.id,
                "l10n_cz_vat_registry_enabled": True,
                "l10n_cz_vat_registry_api_url": "https://example.test/vat-registry",
                "l10n_cz_vat_registry_vat_param": "dic",
                "l10n_cz_vat_registry_cache_hours": 24,
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
        cls.bank_journal = cls.Journal.search(
            [("company_id", "=", cls.company.id), ("type", "=", "bank")],
            limit=1,
            order="id",
        )

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

    def _mock_registry_result(self, *, status="ok", is_unreliable=False, accounts=None, error_message=""):
        return {
            "status": status,
            "error_message": error_message,
            "source_url": "https://example.test/vat-registry",
            "payload": {"status": status},
            "is_unreliable": is_unreliable,
            "published_bank_accounts": accounts or [],
        }

    def _draft_supplier_payment(self, partner, bank_account=None, amount=1000):
        vals = {
            "payment_type": "outbound",
            "partner_type": "supplier",
            "partner_id": partner.id,
            "amount": amount,
            "date": "2027-03-20",
            "journal_id": self.bank_journal.id,
            "payment_method_line_id": self.bank_journal.outbound_payment_method_line_ids[:1].id,
        }
        if bank_account:
            vals["partner_bank_id"] = bank_account.id
        return self.Payment.create(vals)

    def _draft_batch(self, payments):
        return self.BatchPayment.create(
            {
                "batch_type": "outbound",
                "journal_id": self.bank_journal.id,
                "payment_ids": [(6, 0, payments.ids)],
                "payment_method_id": self.bank_journal.outbound_payment_method_line_ids[:1].payment_method_id.id,
            }
        )

    def test_outbound_batch_blocked_for_unreliable_supplier(self):
        supplier = self._new_cz_supplier("BATCHUNREL", "CZ20000001")
        bank = self._new_partner_bank(supplier, "19-9100000001/0800")
        payment = self._draft_supplier_payment(supplier, bank)
        batch = self._draft_batch(payment)

        with patch.object(
            type(self.company),
            "_l10n_cz_vat_registry_fetch",
            autospec=True,
            return_value=self._mock_registry_result(is_unreliable=True, accounts=[bank.acc_number]),
        ):
            with self.assertRaisesRegex(UserError, "unreliable VAT payer"):
                batch.validate()

    def test_outbound_batch_blocked_for_unpublished_bank_account(self):
        supplier = self._new_cz_supplier("BATCHBANK", "CZ20000002")
        bank = self._new_partner_bank(supplier, "19-9200000002/0800")
        payment = self._draft_supplier_payment(supplier, bank)
        batch = self._draft_batch(payment)

        with patch.object(
            type(self.company),
            "_l10n_cz_vat_registry_fetch",
            autospec=True,
            return_value=self._mock_registry_result(accounts=["55-9999999999/0100"]),
        ):
            with self.assertRaisesRegex(UserError, "not published"):
                batch.validate()

    def test_outbound_batch_passes_for_clean_supplier(self):
        supplier = self._new_cz_supplier("BATCHPASS", "CZ20000003")
        bank = self._new_partner_bank(supplier, "19-9300000003/0800")
        payment = self._draft_supplier_payment(supplier, bank)
        batch = self._draft_batch(payment)

        with patch.object(
            type(self.company),
            "_l10n_cz_vat_registry_fetch",
            autospec=True,
            return_value=self._mock_registry_result(accounts=[bank.acc_number]),
        ):
            # Shield must not raise for a clean supplier
            batch._l10n_cz_check_registry_shield()

    def test_inbound_batch_is_never_checked(self):
        batch = self.BatchPayment.new({"batch_type": "inbound"})

        with patch.object(
            type(self.company),
            "_l10n_cz_vat_registry_fetch",
            autospec=True,
            return_value=self._mock_registry_result(),
        ) as mocked_fetch:
            batch._l10n_cz_check_registry_shield()
            self.assertEqual(mocked_fetch.call_count, 0)

    def test_multi_supplier_batch_collects_all_violations(self):
        supplier_a = self._new_cz_supplier("BATCHMULTI_A", "CZ20000005")
        bank_a = self._new_partner_bank(supplier_a, "19-9500000005/0800")
        payment_a = self._draft_supplier_payment(supplier_a, bank_a)

        supplier_b = self._new_cz_supplier("BATCHMULTI_B", "CZ20000006")
        bank_b = self._new_partner_bank(supplier_b, "19-9600000006/0800")
        payment_b = self._draft_supplier_payment(supplier_b, bank_b)

        batch = self._draft_batch(payment_a | payment_b)

        with patch.object(
            type(self.company),
            "_l10n_cz_vat_registry_fetch",
            autospec=True,
            return_value=self._mock_registry_result(is_unreliable=True),
        ):
            with self.assertRaises(UserError) as cm:
                batch._l10n_cz_check_registry_shield()

        error_text = str(cm.exception)
        self.assertIn(supplier_a.display_name, error_text)
        self.assertIn(supplier_b.display_name, error_text)
