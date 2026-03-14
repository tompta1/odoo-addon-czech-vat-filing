import calendar
import json
import re
from datetime import timedelta
from urllib import error, parse, request

from odoo import _, fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    l10n_cz_dph_use_manual_advance_coefficient = fields.Boolean(
        string="Use Manual CZ DPH Advance Coefficient",
        help="Use the manual Czech DPH advance coefficient below instead of deriving row 52 from the previous calendar year.",
    )
    l10n_cz_dph_advance_coefficient = fields.Float(
        string="CZ DPH Advance Coefficient",
        digits=(16, 2),
        help="Advance coefficient percentage for Czech DPH row 52 when the company is not deriving it from the previous calendar year.",
    )
    l10n_cz_vat_filing_history_count = fields.Integer(
        string="Czech VAT Filing Exports",
        compute="_compute_l10n_cz_vat_filing_history_count",
    )
    l10n_cz_vat_registry_enabled = fields.Boolean(
        string="Enable CZ VAT Registry Shield",
        help=(
            "If enabled, Odoo checks Czech suppliers against the VAT registry before vendor-bill posting "
            "and supplier-payment posting."
        ),
    )
    l10n_cz_vat_registry_api_url = fields.Char(
        string="CZ VAT Registry API URL",
        help=(
            "HTTP endpoint used for supplier VAT status checks. "
            "Use `{vat}` placeholder in the URL or set a query-parameter name below."
        ),
    )
    l10n_cz_vat_registry_vat_param = fields.Char(
        string="CZ VAT Registry VAT Parameter",
        default="dic",
        help="Query-parameter name for VAT when the API URL does not include `{vat}`.",
    )
    l10n_cz_vat_registry_timeout_seconds = fields.Integer(
        string="CZ VAT Registry Timeout (s)",
        default=10,
        help="HTTP timeout for VAT registry checks.",
    )
    l10n_cz_vat_registry_cache_hours = fields.Integer(
        string="CZ VAT Registry Cache (h)",
        default=24,
        help="How long previous successful checks are reused.",
    )
    l10n_cz_vat_registry_block_on_post = fields.Boolean(
        string="Block Vendor Bills On Registry Risk",
        default=True,
        help="Blocks vendor bill/refund posting when a configured VAT registry risk is detected.",
    )
    l10n_cz_vat_registry_block_on_payment = fields.Boolean(
        string="Block Supplier Payments On Registry Risk",
        default=True,
        help="Blocks supplier-payment posting when a configured VAT registry risk is detected.",
    )
    l10n_cz_vat_registry_block_unreliable = fields.Boolean(
        string="Block Unreliable VAT Payers",
        default=True,
        help="Treats unreliable VAT-payer status as blocking.",
    )
    l10n_cz_vat_registry_block_unpublished_bank = fields.Boolean(
        string="Block Unpublished Supplier Bank Accounts",
        default=True,
        help="Treats supplier bank-account mismatch against registry-published accounts as blocking.",
    )
    l10n_cz_vat_registry_block_on_lookup_error = fields.Boolean(
        string="Block On VAT Registry Lookup Errors",
        help="If enabled, temporary registry/API errors block posting as a safety policy.",
    )

    def _compute_l10n_cz_vat_filing_history_count(self):
        History = self.env["l10n_cz.vat.filing.history"]
        for company in self:
            company.l10n_cz_vat_filing_history_count = History.search_count([("company_id", "=", company.id)])

    def _l10n_cz_normalize_vat(self, vat):
        normalized = re.sub(r"[^A-Z0-9]", "", (vat or "").upper())
        if not normalized:
            return ""
        if not normalized.startswith("CZ"):
            normalized = f"CZ{normalized}"
        return normalized

    def _l10n_cz_normalize_bank_account(self, account_number):
        return re.sub(r"[^A-Z0-9]", "", (account_number or "").upper())

    def _l10n_cz_truthy(self, value):
        if isinstance(value, bool):
            return value
        if value in (None, "", 0, 0.0):
            return False
        return str(value).strip().lower() in {"1", "true", "yes", "y", "on", "ano"}

    def _l10n_cz_iter_payload_dicts(self, payload):
        stack = [payload]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                yield node
                for value in node.values():
                    if isinstance(value, (dict, list)):
                        stack.append(value)
            elif isinstance(node, list):
                for value in node:
                    if isinstance(value, (dict, list)):
                        stack.append(value)

    def _l10n_cz_key_signature(self, key):
        return re.sub(r"[^a-z0-9]", "", (key or "").lower())

    def _l10n_cz_payload_first_value(self, payload, candidates):
        signatures = {self._l10n_cz_key_signature(key) for key in candidates}
        for mapping in self._l10n_cz_iter_payload_dicts(payload):
            for key, value in mapping.items():
                if self._l10n_cz_key_signature(key) in signatures:
                    return value
        return None

    def _l10n_cz_payload_all_values(self, payload, candidates):
        signatures = {self._l10n_cz_key_signature(key) for key in candidates}
        collected = []
        for mapping in self._l10n_cz_iter_payload_dicts(payload):
            for key, value in mapping.items():
                if self._l10n_cz_key_signature(key) in signatures:
                    collected.append(value)
        return collected

    def _l10n_cz_extract_bank_accounts(self, payload):
        values = self._l10n_cz_payload_all_values(
            payload,
            [
                "published_bank_accounts",
                "publishedAccounts",
                "bank_accounts",
                "bankAccounts",
                "accounts",
                "zverejnene_ucty",
                "ucty",
            ],
        )
        accounts = []
        for value in values:
            if isinstance(value, str):
                accounts.append(value)
            elif isinstance(value, dict):
                for key in ["account_number", "acc_number", "number", "iban", "cislo_uctu"]:
                    if value.get(key):
                        accounts.append(str(value[key]))
                        break
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        accounts.append(item)
                    elif isinstance(item, dict):
                        for key in ["account_number", "acc_number", "number", "iban", "cislo_uctu"]:
                            if item.get(key):
                                accounts.append(str(item[key]))
                                break
        deduped = []
        seen = set()
        for account in accounts:
            normalized = self._l10n_cz_normalize_bank_account(account)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(account.strip())
        return deduped

    def _l10n_cz_build_registry_url(self, vat):
        self.ensure_one()
        base_url = (self.l10n_cz_vat_registry_api_url or "").strip()
        if not base_url:
            return ""
        if "{vat}" in base_url:
            return base_url.replace("{vat}", parse.quote(vat, safe=""))
        parsed = parse.urlsplit(base_url)
        query = dict(parse.parse_qsl(parsed.query, keep_blank_values=True))
        query[(self.l10n_cz_vat_registry_vat_param or "dic").strip() or "dic"] = vat
        return parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parse.urlencode(query), parsed.fragment))

    def _l10n_cz_vat_registry_fetch(self, vat):
        self.ensure_one()
        url = self._l10n_cz_build_registry_url(vat)
        if not url:
            return {
                "status": "error",
                "error_message": _("VAT registry API URL is not configured."),
                "source_url": "",
                "payload": {},
                "is_unreliable": False,
                "published_bank_accounts": [],
            }
        timeout = max(1, int(self.l10n_cz_vat_registry_timeout_seconds or 10))
        req = request.Request(url, headers={"Accept": "application/json", "User-Agent": "Odoo-CZ-VAT-Filing/19"})
        try:
            with request.urlopen(req, timeout=timeout) as response:
                body = response.read().decode("utf-8")
        except (error.HTTPError, error.URLError, TimeoutError, ValueError) as exc:
            return {
                "status": "error",
                "error_message": str(exc),
                "source_url": url,
                "payload": {},
                "is_unreliable": False,
                "published_bank_accounts": [],
            }
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            return {
                "status": "error",
                "error_message": _("VAT registry API response is not valid JSON."),
                "source_url": url,
                "payload": {"raw": body},
                "is_unreliable": False,
                "published_bank_accounts": [],
            }

        unreliable_raw = self._l10n_cz_payload_first_value(
            payload,
            [
                "is_unreliable",
                "unreliable",
                "nespolehlivy_platce",
                "nespolehlivy",
                "nespolehlivyPlatce",
            ],
        )
        is_unreliable = self._l10n_cz_truthy(unreliable_raw)
        return {
            "status": "ok",
            "error_message": "",
            "source_url": url,
            "payload": payload,
            "is_unreliable": is_unreliable,
            "published_bank_accounts": self._l10n_cz_extract_bank_accounts(payload),
        }

    def _l10n_cz_vat_registry_cached_check(self, vat):
        self.ensure_one()
        cache_hours = max(0, int(self.l10n_cz_vat_registry_cache_hours or 0))
        if not cache_hours:
            return self.env["l10n_cz.vat.registry.check"]
        threshold = fields.Datetime.now() - timedelta(hours=cache_hours)
        return self.env["l10n_cz.vat.registry.check"].search(
            [
                ("company_id", "=", self.id),
                ("vat_number", "=", vat),
                ("checked_at", ">=", threshold),
                ("status", "=", "ok"),
            ],
            order="checked_at desc,id desc",
            limit=1,
        )

    def l10n_cz_vat_registry_evaluate_partner(self, partner, bank_account=None, force_refresh=False):
        self.ensure_one()
        result = {
            "enabled": bool(self.l10n_cz_vat_registry_enabled),
            "skipped": False,
            "check": self.env["l10n_cz.vat.registry.check"],
            "violations": [],
            "messages": [],
            "status": "skipped",
            "is_unreliable": False,
            "bank_account_published": None,
            "published_bank_accounts": [],
        }
        if not self.l10n_cz_vat_registry_enabled:
            result["skipped"] = True
            return result

        supplier = partner.commercial_partner_id
        vat = self._l10n_cz_normalize_vat(supplier.vat)
        if not vat.startswith("CZ"):
            result["skipped"] = True
            result["messages"].append(_("Supplier has no Czech VAT number; VAT registry check skipped."))
            return result

        check = self.env["l10n_cz.vat.registry.check"]
        if not force_refresh:
            check = self._l10n_cz_vat_registry_cached_check(vat)
        if not check:
            fetched = self._l10n_cz_vat_registry_fetch(vat)
            check_values = {
                "company_id": self.id,
                "partner_id": supplier.id,
                "vat_number": vat,
                "checked_at": fields.Datetime.now(),
                "status": fetched["status"],
                "is_unreliable": fetched["is_unreliable"],
                "bank_account_checked": bank_account or "",
                "published_bank_accounts": fetched["published_bank_accounts"],
                "response_payload": fetched["payload"],
                "error_message": fetched["error_message"],
                "source_url": fetched["source_url"],
            }
            check = self.env["l10n_cz.vat.registry.check"].sudo().create(check_values)
        elif bank_account and not check.bank_account_checked:
            check.sudo().write({"bank_account_checked": bank_account})

        result["check"] = check
        result["status"] = check.status
        result["is_unreliable"] = bool(check.is_unreliable)
        result["published_bank_accounts"] = check.published_bank_accounts

        if check.status == "error":
            message = _(
                "CZ VAT registry lookup failed for supplier %(supplier)s (%(vat)s): %(error)s"
            ) % {
                "supplier": supplier.display_name,
                "vat": vat,
                "error": check.error_message or _("Unknown API error"),
            }
            result["messages"].append(message)
            if self.l10n_cz_vat_registry_block_on_lookup_error:
                result["violations"].append(message)
            return result

        if self.l10n_cz_vat_registry_block_unreliable and check.is_unreliable:
            result["violations"].append(
                _(
                    "Supplier %(supplier)s (%(vat)s) is marked as an unreliable VAT payer in the Czech VAT registry."
                )
                % {
                    "supplier": supplier.display_name,
                    "vat": vat,
                }
            )

        normalized_checked_bank = self._l10n_cz_normalize_bank_account(bank_account)
        normalized_published = {
            self._l10n_cz_normalize_bank_account(account)
            for account in check.published_bank_accounts
            if account
        }
        bank_published = None
        if normalized_checked_bank:
            bank_published = normalized_checked_bank in normalized_published if normalized_published else False
            result["bank_account_published"] = bank_published
            if self.l10n_cz_vat_registry_block_unpublished_bank and bank_published is False:
                result["violations"].append(
                    _(
                        "Supplier bank account %(account)s is not published in the Czech VAT registry for %(vat)s."
                    )
                    % {
                        "account": bank_account,
                        "vat": vat,
                    }
                )

        if not result["violations"]:
            result["messages"].append(_("CZ VAT registry shield check passed."))
        return result

    def l10n_cz_vat_filing_exports(self, date_from, date_to, options=None):
        self.ensure_one()
        return self.env["l10n_cz.vat.filing.export"].build_exports(
            self,
            date_from,
            date_to,
            options=options or {},
        )

    def action_open_l10n_cz_vat_filing_export_wizard(self):
        self.ensure_one()
        today = fields.Date.context_today(self)
        period_start = today.replace(day=1)
        period_end = today.replace(day=calendar.monthrange(today.year, today.month)[1])
        return {
            "type": "ir.actions.act_window",
            "name": _("Czech VAT Filing Export"),
            "res_model": "l10n_cz.vat.filing.export.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_company_id": self.id,
                "default_date_from": period_start,
                "default_date_to": period_end,
            },
        }

    def action_open_l10n_cz_vat_filing_history(self):
        self.ensure_one()
        action = self.env.ref("l10n_cz_vat_filing.action_l10n_cz_vat_filing_history").read()[0]
        action["domain"] = [("company_id", "=", self.id)]
        action["context"] = {"default_company_id": self.id}
        return action
