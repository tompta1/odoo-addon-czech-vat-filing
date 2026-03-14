import calendar
import json
import re
import xml.etree.ElementTree as ET
from datetime import timedelta
from urllib import error, parse, request
from xml.sax.saxutils import escape

from odoo import _, fields, models
from odoo.exceptions import UserError

CNB_DAILY_RATE_URL = (
    "https://www.cnb.cz/cs/financni-trhy/devizovy-trh/kurzy-devizoveho-trhu/"
    "kurzy-devizoveho-trhu/denni_kurz.txt"
)


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
    l10n_cz_vat_fx_enforce_cnb = fields.Boolean(
        string="Enable CZ VAT FX Decoupling",
        help=(
            "If enabled, Czech VAT export calculations for foreign-currency documents use CZ VAT FX rates "
            "resolved for DUZP instead of accounting conversion rates."
        ),
    )
    l10n_cz_vat_fx_api_url = fields.Char(
        string="CZ VAT FX API URL",
        default=CNB_DAILY_RATE_URL,
        help=(
            "HTTP endpoint used for VAT FX rates (default: official CNB daily rate feed). "
            "Use `{date}` and `{currency}` placeholders or set query-parameter names below."
        ),
    )
    l10n_cz_vat_fx_currency_param = fields.Char(
        string="CZ VAT FX Currency Parameter",
        default="currency",
        help="Query-parameter name for currency code when the FX API URL does not include `{currency}`.",
    )
    l10n_cz_vat_fx_date_param = fields.Char(
        string="CZ VAT FX Date Parameter",
        default="date",
        help="Query-parameter name for tax date when the FX API URL does not include `{date}`.",
    )
    l10n_cz_vat_fx_timeout_seconds = fields.Integer(
        string="CZ VAT FX Timeout (s)",
        default=10,
        help="HTTP timeout for VAT FX lookups.",
    )
    l10n_cz_vat_fx_cache_days = fields.Integer(
        string="CZ VAT FX Cache (days)",
        default=365,
        help="How long successful CZ VAT FX lookups are cached for DUZP-based reuse.",
    )
    l10n_cz_vat_fx_block_on_lookup_error = fields.Boolean(
        string="Block On VAT FX Lookup Errors",
        help="If enabled, foreign-currency invoice posting fails when VAT FX lookup for DUZP fails.",
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
        return self._l10n_cz_dedupe_bank_accounts(accounts)

    def _l10n_cz_dedupe_bank_accounts(self, accounts):
        deduped = []
        seen = set()
        for account in accounts:
            normalized = self._l10n_cz_normalize_bank_account(account)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(account.strip())
        return deduped

    def _l10n_cz_registry_is_unreliable(self, value):
        signature = self._l10n_cz_key_signature(value if isinstance(value, str) else str(value or ""))
        if not signature:
            return False
        if signature in {
            "jenespolehlivyplatce",
            "nespolehlivyplatce",
            "jenespolehlivysubjekt",
            "nespolehlivysubjekt",
        }:
            return True
        if signature in {
            "neninespolehlivyplatce",
            "neninespolehlivysubjekt",
        }:
            return False
        return self._l10n_cz_truthy(value)

    def _l10n_cz_xml_local_name(self, tag):
        if "}" in tag:
            return tag.rsplit("}", 1)[-1]
        return tag

    def _l10n_cz_xml_text_values(self, root, candidates):
        signatures = {self._l10n_cz_key_signature(candidate) for candidate in candidates}
        values = []
        for node in root.iter():
            if self._l10n_cz_key_signature(self._l10n_cz_xml_local_name(node.tag)) not in signatures:
                continue
            text = (node.text or "").strip()
            if text:
                values.append(text)
        return values

    def _l10n_cz_extract_bank_accounts_from_xml(self, root):
        values = self._l10n_cz_xml_text_values(
            root,
            [
                "published_bank_accounts",
                "publishedAccounts",
                "bank_accounts",
                "bankAccounts",
                "accounts",
                "zverejnene_ucty",
                "zverejneneUcty",
                "zverejnenyUcet",
                "ucet",
                "ucty",
                "bankovniUcet",
                "accountNumber",
                "iban",
                "cislo_uctu",
                "cisloUctu",
            ],
        )
        account_pattern = re.compile(r"\b(?:\d{1,6}-)?\d{2,10}/\d{4}\b")
        iban_pattern = re.compile(r"\bCZ\d{22}\b")
        accounts = []
        for value in values:
            account_matches = account_pattern.findall(value)
            iban_matches = iban_pattern.findall(value)
            if account_matches or iban_matches:
                accounts.extend(account_matches)
                accounts.extend(iban_matches)
                continue
            if "/" in value or value.upper().startswith("CZ"):
                accounts.append(value)
        return self._l10n_cz_dedupe_bank_accounts(accounts)

    def _l10n_cz_vat_registry_parse_json_payload(self, payload):
        vies_valid = self._l10n_cz_payload_first_value(payload, ["valid", "isValid"])
        vies_error = self._l10n_cz_payload_first_value(
            payload,
            [
                "userError",
                "errorCode",
                "faultCode",
                "faultString",
                "error",
                "message",
            ],
        )
        if vies_valid is not None or vies_error is not None:
            if self._l10n_cz_truthy(vies_valid):
                return {
                    "status": "ok",
                    "error_message": "",
                    "payload": payload,
                    "is_unreliable": False,
                    "published_bank_accounts": [],
                }
            if vies_error:
                error_message = str(vies_error)
            else:
                error_message = _("VAT number is invalid according to VIES.")
            return {
                "status": "error",
                "error_message": error_message,
                "payload": payload,
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
        return {
            "status": "ok",
            "error_message": "",
            "payload": payload,
            "is_unreliable": self._l10n_cz_registry_is_unreliable(unreliable_raw),
            "published_bank_accounts": self._l10n_cz_extract_bank_accounts(payload),
        }

    def _l10n_cz_vat_registry_parse_xml_payload(self, body):
        try:
            root = ET.fromstring(body)
        except ET.ParseError:
            return {
                "status": "error",
                "error_message": _("VAT registry API response is not valid XML."),
                "payload": {"raw": body},
                "is_unreliable": False,
                "published_bank_accounts": [],
            }

        has_fault = any(
            self._l10n_cz_key_signature(self._l10n_cz_xml_local_name(node.tag)) == "fault"
            for node in root.iter()
        )
        if has_fault:
            fault_strings = self._l10n_cz_xml_text_values(root, ["faultString", "reason", "text", "message"])
            fault_codes = self._l10n_cz_xml_text_values(root, ["faultCode"])
            if fault_strings:
                fault_message = fault_strings[0]
            elif fault_codes:
                fault_message = fault_codes[0]
            else:
                fault_message = _("VAT registry API returned a SOAP fault.")
            return {
                "status": "error",
                "error_message": fault_message,
                "payload": {"raw": body},
                "is_unreliable": False,
                "published_bank_accounts": [],
            }

        status_values = self._l10n_cz_xml_text_values(
            root,
            [
                "isUnreliable",
                "unreliable",
                "nespolehlivy_platce",
                "nespolehlivyPlatce",
                "nespolehlivySubjekt",
                "statusNespolehlivySubjekt",
                "statusNespolehlivehoPlatce",
                "status",
            ],
        )
        is_unreliable = any(self._l10n_cz_registry_is_unreliable(value) for value in status_values)
        return {
            "status": "ok",
            "error_message": "",
            "payload": {"raw": body},
            "is_unreliable": is_unreliable,
            "published_bank_accounts": self._l10n_cz_extract_bank_accounts_from_xml(root),
        }

    def _l10n_cz_vat_registry_parse_response_body(self, body):
        stripped = (body or "").lstrip()
        if stripped.startswith("<"):
            return self._l10n_cz_vat_registry_parse_xml_payload(body)
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            return {
                "status": "error",
                "error_message": _("VAT registry API response is not valid JSON or XML."),
                "payload": {"raw": body},
                "is_unreliable": False,
                "published_bank_accounts": [],
            }
        return self._l10n_cz_vat_registry_parse_json_payload(payload)

    def _l10n_cz_registry_is_soap_endpoint(self, base_url):
        parsed = parse.urlsplit(base_url or "")
        path = (parsed.path or "").lower()
        return "rozhranicrpdph" in path and "soap" in path

    def _l10n_cz_vat_registry_soap_body(self, vat):
        vat_xml = escape(vat or "")
        return (
            "<?xml version='1.0' encoding='utf-8'?>"
            "<soapenv:Envelope xmlns:soapenv='http://schemas.xmlsoap.org/soap/envelope/' "
            "xmlns:dph='http://adis.mfcr.cz/rozhraniCRPDPH/'>"
            "<soapenv:Header/>"
            "<soapenv:Body>"
            "<dph:getStatusNespolehlivySubjektRozsireny>"
            f"<dph:dic>{vat_xml}</dph:dic>"
            "</dph:getStatusNespolehlivySubjektRozsireny>"
            "</soapenv:Body>"
            "</soapenv:Envelope>"
        ).encode("utf-8")

    def _l10n_cz_build_registry_url(self, vat):
        self.ensure_one()
        base_url = (self.l10n_cz_vat_registry_api_url or "").strip()
        if not base_url:
            return ""
        if self._l10n_cz_registry_is_soap_endpoint(base_url):
            return base_url
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
        is_soap = self._l10n_cz_registry_is_soap_endpoint(url)
        if is_soap:
            req = request.Request(
                url,
                data=self._l10n_cz_vat_registry_soap_body(vat),
                method="POST",
                headers={
                    "Content-Type": "text/xml; charset=utf-8",
                    "SOAPAction": "getStatusNespolehlivySubjektRozsireny",
                    "Accept": "text/xml,application/xml",
                    "User-Agent": "Odoo-CZ-VAT-Filing/19",
                },
            )
        else:
            req = request.Request(
                url,
                headers={
                    "Accept": "application/json,application/xml,text/xml",
                    "User-Agent": "Odoo-CZ-VAT-Filing/19",
                },
            )
        try:
            with request.urlopen(req, timeout=timeout) as response:
                body = response.read().decode("utf-8", errors="replace")
        except (error.HTTPError, error.URLError, TimeoutError, ValueError) as exc:
            return {
                "status": "error",
                "error_message": str(exc),
                "source_url": url,
                "payload": {},
                "is_unreliable": False,
                "published_bank_accounts": [],
            }
        parsed_result = self._l10n_cz_vat_registry_parse_response_body(body)
        parsed_result["source_url"] = url
        return parsed_result

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

    def _l10n_cz_parse_float(self, value):
        if value in (None, "", False):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value).strip().replace(" ", "").replace(",", ".")
        try:
            return float(text)
        except ValueError:
            return None

    def _l10n_cz_vat_fx_tax_date(self, move):
        return move.l10n_cz_dph_tax_date or move.invoice_date or move.date or fields.Date.today()

    def _l10n_cz_vat_fx_move_enabled(self, move):
        self.ensure_one()
        if not self.l10n_cz_vat_fx_enforce_cnb:
            return False
        company_currency = self.currency_id
        if not company_currency or company_currency.name != "CZK":
            return False
        move_currency = move.currency_id or company_currency
        return bool(move_currency and move_currency != company_currency)

    def _l10n_cz_extract_rate_to_czk(self, payload, currency_code):
        direct_rate = self._l10n_cz_parse_float(
            self._l10n_cz_payload_first_value(payload, ["rate_to_czk", "rateToCzk"])
        )
        if direct_rate and direct_rate > 0:
            direct_amount = self._l10n_cz_parse_float(
                self._l10n_cz_payload_first_value(payload, ["amount", "mnozstvi"])
            ) or 1.0
            if direct_amount > 0:
                return direct_rate / direct_amount
            return direct_rate

        for mapping in self._l10n_cz_iter_payload_dicts(payload):
            code = (
                mapping.get("currency")
                or mapping.get("code")
                or mapping.get("mena")
                or mapping.get("kod")
            )
            if not (isinstance(code, str) and code.upper() == currency_code):
                continue
            rate = self._l10n_cz_parse_float(
                mapping.get("rate_to_czk")
                or mapping.get("rate")
                or mapping.get("kurz")
                or mapping.get("value")
            )
            if not rate or rate <= 0:
                continue
            amount = self._l10n_cz_parse_float(mapping.get("amount") or mapping.get("mnozstvi")) or 1.0
            if amount > 0:
                return rate / amount
            return rate

        for mapping in self._l10n_cz_iter_payload_dicts(payload):
            if currency_code not in mapping:
                continue
            candidate = mapping[currency_code]
            if isinstance(candidate, dict):
                rate = self._l10n_cz_parse_float(
                    candidate.get("rate_to_czk")
                    or candidate.get("rate")
                    or candidate.get("kurz")
                    or candidate.get("value")
                )
                if not rate or rate <= 0:
                    continue
                amount = self._l10n_cz_parse_float(candidate.get("amount") or candidate.get("mnozstvi")) or 1.0
                if amount > 0:
                    return rate / amount
                return rate
            rate = self._l10n_cz_parse_float(candidate)
            if rate and rate > 0:
                return rate
        return None

    def _l10n_cz_vat_fx_is_cnb_url(self, base_url):
        parsed = parse.urlsplit(base_url or "")
        host = (parsed.netloc or "").lower()
        path = (parsed.path or "").lower()
        return host.endswith("cnb.cz") and "denni_kurz.txt" in path

    def _l10n_cz_vat_fx_extract_rate_from_cnb_text(self, body, currency_code):
        lines = [line.strip() for line in (body or "").splitlines() if line.strip()]
        if len(lines) < 3:
            return None, {"provider": "cnb_txt", "raw": body or ""}
        for line in lines[2:]:
            parts = [part.strip() for part in line.split("|")]
            if len(parts) != 5:
                continue
            if parts[3].upper() != currency_code:
                continue
            amount = self._l10n_cz_parse_float(parts[2])
            rate = self._l10n_cz_parse_float(parts[4])
            if not amount or amount <= 0 or not rate or rate <= 0:
                continue
            return (rate / amount), {"provider": "cnb_txt", "header": lines[0], "line": line}
        return None, {"provider": "cnb_txt", "header": lines[0]}

    def _l10n_cz_vat_fx_build_url(self, currency, tax_date):
        self.ensure_one()
        base_url = (self.l10n_cz_vat_fx_api_url or "").strip()
        if not base_url:
            return ""
        is_cnb_url = self._l10n_cz_vat_fx_is_cnb_url(base_url)
        currency_code = (currency.name or "").upper()
        tax_date_value = fields.Date.to_date(tax_date)
        tax_date_text = tax_date_value.strftime("%d.%m.%Y") if is_cnb_url else tax_date_value.isoformat()
        if "{currency}" in base_url or "{date}" in base_url:
            return (
                base_url.replace("{currency}", parse.quote(currency_code, safe=""))
                .replace("{date}", parse.quote(tax_date_text, safe=""))
            )
        parsed = parse.urlsplit(base_url)
        query = dict(parse.parse_qsl(parsed.query, keep_blank_values=True))
        if is_cnb_url:
            query["date"] = tax_date_text
        else:
            currency_param = (self.l10n_cz_vat_fx_currency_param or "").strip()
            date_param = (self.l10n_cz_vat_fx_date_param or "date").strip() or "date"
            if currency_param:
                query[currency_param] = currency_code
            query[date_param] = tax_date_text
        return parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parse.urlencode(query), parsed.fragment))

    def _l10n_cz_vat_fx_fetch_rate(self, currency, tax_date):
        self.ensure_one()
        url = self._l10n_cz_vat_fx_build_url(currency, tax_date)
        if not url:
            return {
                "status": "error",
                "error_message": _("CZ VAT FX API URL is not configured."),
                "source_url": "",
                "payload": {},
                "rate_to_czk": 0.0,
            }
        timeout = max(1, int(self.l10n_cz_vat_fx_timeout_seconds or 10))
        req = request.Request(url, headers={"Accept": "*/*", "User-Agent": "Odoo-CZ-VAT-Filing/19"})
        try:
            with request.urlopen(req, timeout=timeout) as response:
                body = response.read().decode("utf-8", errors="replace")
        except (error.HTTPError, error.URLError, TimeoutError, ValueError) as exc:
            return {
                "status": "error",
                "error_message": str(exc),
                "source_url": url,
                "payload": {},
                "rate_to_czk": 0.0,
            }
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            rate, text_payload = self._l10n_cz_vat_fx_extract_rate_from_cnb_text(body, (currency.name or "").upper())
            if rate and rate > 0:
                return {
                    "status": "ok",
                    "error_message": "",
                    "source_url": url,
                    "payload": text_payload,
                    "rate_to_czk": rate,
                }
            return {
                "status": "error",
                "error_message": _("CZ VAT FX API response is neither valid JSON nor parseable CNB text."),
                "source_url": url,
                "payload": text_payload,
                "rate_to_czk": 0.0,
            }

        rate = self._l10n_cz_extract_rate_to_czk(payload, (currency.name or "").upper())
        if not rate or rate <= 0:
            return {
                "status": "error",
                "error_message": _("CZ VAT FX API did not provide a positive rate for %s.") % (currency.name,),
                "source_url": url,
                "payload": payload,
                "rate_to_czk": 0.0,
            }
        return {
            "status": "ok",
            "error_message": "",
            "source_url": url,
            "payload": payload,
            "rate_to_czk": rate,
        }

    def _l10n_cz_vat_fx_cached_rate(self, currency, tax_date):
        self.ensure_one()
        rate_record = self.env["l10n_cz.vat.fx.rate"].search(
            [
                ("company_id", "=", self.id),
                ("currency_id", "=", currency.id),
                ("tax_date", "=", tax_date),
            ],
            limit=1,
        )
        if not rate_record or rate_record.status != "ok":
            return self.env["l10n_cz.vat.fx.rate"]
        cache_days = max(0, int(self.l10n_cz_vat_fx_cache_days or 0))
        if not cache_days:
            return self.env["l10n_cz.vat.fx.rate"]
        threshold = fields.Datetime.now() - timedelta(days=cache_days)
        return rate_record if rate_record.checked_at and rate_record.checked_at >= threshold else self.env["l10n_cz.vat.fx.rate"]

    def _l10n_cz_vat_fx_get_rate_record(self, currency, tax_date, force_refresh=False):
        self.ensure_one()
        tax_date = fields.Date.to_date(tax_date)
        rate_record = self.env["l10n_cz.vat.fx.rate"].search(
            [
                ("company_id", "=", self.id),
                ("currency_id", "=", currency.id),
                ("tax_date", "=", tax_date),
            ],
            limit=1,
        )
        if not force_refresh:
            cached = self._l10n_cz_vat_fx_cached_rate(currency, tax_date)
            if cached:
                return cached

        fetched = self._l10n_cz_vat_fx_fetch_rate(currency, tax_date)
        values = {
            "company_id": self.id,
            "currency_id": currency.id,
            "tax_date": tax_date,
            "checked_at": fields.Datetime.now(),
            "status": fetched["status"],
            "rate_to_czk": fetched["rate_to_czk"],
            "source_url": fetched["source_url"],
            "response_payload": fetched["payload"],
            "error_message": fetched["error_message"],
        }
        if rate_record:
            rate_record.sudo().write(values)
            return rate_record
        return self.env["l10n_cz.vat.fx.rate"].sudo().create(values)

    def l10n_cz_vat_fx_rate_for_move(self, move, force_refresh=False):
        self.ensure_one()
        if not self._l10n_cz_vat_fx_move_enabled(move):
            return None, self.env["l10n_cz.vat.fx.rate"]
        currency = move.currency_id or self.currency_id
        tax_date = self._l10n_cz_vat_fx_tax_date(move)
        rate_record = self._l10n_cz_vat_fx_get_rate_record(currency, tax_date, force_refresh=force_refresh)
        if rate_record.status == "ok" and rate_record.rate_to_czk > 0:
            return rate_record.rate_to_czk, rate_record
        message = _(
            "CZ VAT FX lookup failed for %(currency)s on %(tax_date)s: %(error)s"
        ) % {
            "currency": currency.name,
            "tax_date": fields.Date.to_date(tax_date).isoformat(),
            "error": rate_record.error_message or _("Unknown API error"),
        }
        if self.l10n_cz_vat_fx_block_on_lookup_error:
            raise UserError(message)
        return None, rate_record

    def cron_l10n_cz_refresh_vat_fx_rates(self):
        companies = self.search(
            [
                ("l10n_cz_vat_fx_enforce_cnb", "=", True),
                ("l10n_cz_vat_fx_api_url", "!=", False),
            ]
        )
        if not companies:
            return True
        today = fields.Date.today()
        recent_since = today - timedelta(days=90)
        Move = self.env["account.move"]
        for company in companies:
            recent_moves = Move.search(
                [
                    ("company_id", "=", company.id),
                    ("state", "=", "posted"),
                    ("move_type", "in", ["out_invoice", "out_refund", "in_invoice", "in_refund"]),
                    ("date", ">=", recent_since),
                ]
            )
            currencies = recent_moves.mapped("currency_id")
            for currency in currencies:
                if not currency or currency == company.currency_id:
                    continue
                try:
                    company._l10n_cz_vat_fx_get_rate_record(currency, today, force_refresh=False)
                except Exception:
                    continue
        return True

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
