from odoo.tests import TransactionCase


class TestL10nCzVatOssBridge(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.Account = cls.env["account.account"]
        cls.Journal = cls.env["account.journal"]
        cls.Move = cls.env["account.move"]
        cls.Tax = cls.env["account.tax"]
        cls.Tag = cls.env["account.account.tag"]
        cls.ProductTemplate = cls.env["product.template"]
        cls.Partner = cls.env["res.partner"]
        cls.cz = cls.env.ref("base.cz")
        cls.de = cls.env.ref("base.de")
        cls.company.write({"account_fiscal_country_id": cls.cz.id})
        cls.company.partner_id.with_context(no_vat_validation=True).write(
            {
                "vat": "CZ699999999",
                "country_id": cls.cz.id,
                "street": "OSS Test 1",
                "city": "Praha",
                "zip": "11000",
            }
        )
        cls.sale_account = cls._find_account(["income", "income_other"])
        cls.sale_journal = cls._find_journal("sale")
        cls.oss_tag = cls.env.ref("l10n_eu_oss.tag_oss")
        cls.non_eu_origin_tag = cls.env.ref("l10n_eu_oss.tag_eu_import")
        cls.tax_sale_domestic = cls._find_tax("sale", ["VAT 1 Base", "VAT 1 Tax"])
        cls.tax_sale_oss = cls._find_or_copy_tax_with_oss_tag(
            cls.tax_sale_domestic,
            "21% OSS Bridge Test",
        )
        cls.partner_de_private = cls._ensure_partner(
            "DE OSS Buyer Test",
            "",
            cls.de,
            company_type="person",
        )
        cls.non_eu_product = cls.ProductTemplate.create(
            {
                "name": "IOSS Bridge Product",
                "type": "consu",
                "list_price": 100.0,
                "account_tag_ids": [(6, 0, [cls.non_eu_origin_tag.id])],
            }
        ).product_variant_id

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
                for line in tax.invoice_repartition_line_ids
                for tag in line.tag_ids
            }
            if required.issubset(tags):
                return tax
        raise AssertionError(f"Missing tax for {required_tags!r}")

    @classmethod
    def _find_or_copy_tax_with_oss_tag(cls, source_tax, new_name):
        tax = cls.Tax.search(
            [("name", "=", new_name), ("type_tax_use", "=", source_tax.type_tax_use)],
            limit=1,
        )
        if not tax:
            tax = source_tax.copy(
                {
                    "name": new_name,
                    "description": new_name,
                    "invoice_label": new_name,
                }
            )

        for repartition_line in tax.invoice_repartition_line_ids.filtered(lambda l: l.tag_ids):
            repartition_line.tag_ids = [(6, 0, (repartition_line.tag_ids | cls.oss_tag).ids)]
        for repartition_line in tax.refund_repartition_line_ids.filtered(lambda l: l.tag_ids):
            repartition_line.tag_ids = [(6, 0, (repartition_line.tag_ids | cls.oss_tag).ids)]
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
                "street": "OSS Test Street 1",
                "city": "Praha",
                "zip": "11000",
            }
        )

    def _create_out_invoice(self, marker, price, invoice_date, product=None):
        line_vals = {
            "name": marker,
            "quantity": 1,
            "price_unit": price,
            "account_id": self.sale_account.id,
            "tax_ids": [(6, 0, [self.tax_sale_oss.id])],
        }
        if product:
            line_vals["product_id"] = product.id
        move = self.Move.create(
            {
                "move_type": "out_invoice",
                "partner_id": self.partner_de_private.id,
                "journal_id": self.sale_journal.id,
                "invoice_date": invoice_date,
                "date": invoice_date,
                "invoice_origin": marker,
                "invoice_line_ids": [(0, 0, line_vals)],
            }
        )
        move.action_post()
        return move

    def _create_out_invoice_draft(self, marker, price, invoice_date, product=None):
        line_vals = {
            "name": marker,
            "quantity": 1,
            "price_unit": price,
            "account_id": self.sale_account.id,
            "tax_ids": [(6, 0, [self.tax_sale_oss.id])],
        }
        if product:
            line_vals["product_id"] = product.id
        return self.Move.create(
            {
                "move_type": "out_invoice",
                "partner_id": self.partner_de_private.id,
                "journal_id": self.sale_journal.id,
                "invoice_date": invoice_date,
                "date": invoice_date,
                "invoice_origin": marker,
                "invoice_line_ids": [(0, 0, line_vals)],
            }
        )

    def test_detects_oss_regime_from_oss_tax_tag(self):
        move = self._create_out_invoice("OSS-BRIDGE-OSS", 1000, "2030-03-10")
        self.assertEqual(move.l10n_cz_vat_regime, "oss")

    def test_detects_ioss_regime_from_non_eu_origin_product_tag(self):
        move = self._create_out_invoice(
            "OSS-BRIDGE-IOSS",
            1500,
            "2030-03-11",
            product=self.non_eu_product,
        )
        self.assertEqual(move.l10n_cz_vat_regime, "ioss")

    def test_exports_exclude_detected_oss_moves(self):
        move = self._create_out_invoice("OSS-BRIDGE-EXPORT", 1200, "2030-03-12")
        exports = self.company.l10n_cz_vat_filing_exports("2030-03-01", "2030-03-31")
        debug = exports["debug"]
        self.assertNotIn(move.id, debug["move_ids"])
        excluded = {
            row["id"]: row["vat_regime"]
            for row in debug["excluded_regime_moves"]
        }
        self.assertEqual(excluded.get(move.id), "oss")

    def test_backfill_action_updates_historical_moves(self):
        move = self._create_out_invoice("OSS-BRIDGE-BACKFILL", 1300, "2030-03-13")
        move.with_context(skip_l10n_cz_oss_bridge=True).write({"l10n_cz_vat_regime": "standard"})
        self.assertEqual(move.l10n_cz_vat_regime, "standard")

        action = self.company.action_l10n_cz_oss_bridge_backfill()
        move.invalidate_recordset(["l10n_cz_vat_regime"])

        self.assertEqual(move.l10n_cz_vat_regime, "oss")
        self.assertEqual(action["type"], "ir.actions.client")
        self.assertEqual(action["tag"], "display_notification")

    def test_sync_clears_regime_when_oss_markers_are_removed(self):
        move = self._create_out_invoice_draft("OSS-BRIDGE-RESET", 900, "2030-03-14")
        self.assertEqual(move.l10n_cz_vat_regime, "oss")

        move.write(
            {
                "invoice_line_ids": [
                    (
                        1,
                        move.invoice_line_ids[0].id,
                        {"tax_ids": [(6, 0, [self.tax_sale_domestic.id])]},
                    )
                ]
            }
        )
        move.invalidate_recordset(["l10n_cz_vat_regime"])

        self.assertEqual(move.l10n_cz_vat_regime, "standard")
