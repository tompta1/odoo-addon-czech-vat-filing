import base64
import binascii
import calendar
import hashlib
import json
import logging
import os
import re
import xml.etree.ElementTree as ET
from datetime import timedelta

# ADIS EPO ZjistiStatus response status signatures
_EPO_ACCEPTED_SIGS = frozenset({"zpracovano", "akceptovano", "prijatoapzpracovano", "zpracovanobezchyb"})
_EPO_REJECTED_SIGS = frozenset({"odmitnut", "zamitnuto", "chyba", "neplatne", "neprijato", "odmitnutobiychybou"})
from urllib import error, parse, request
from xml.sax.saxutils import escape

_logger = logging.getLogger(__name__)

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
        default="https://adisrws.mfcr.cz/dpr/axis2/services/rozhraniCRPDPH.rozhraniCRPDPHSOAP",
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
    l10n_cz_isds_enabled = fields.Boolean(
        string="Enable Datova Schranka Submission",
        help=(
            "Enables Datova schranka submission actions from Czech VAT filing history records."
        ),
    )
    l10n_cz_isds_mode = fields.Selection(
        [
            ("mock", "Mock (No External Delivery)"),
            ("http_json", "HTTP JSON Bridge"),
            ("soap_owner_info", "SOAP Credential Check (GetOwnerInfoFromLogin)"),
            ("soap_create_message", "SOAP Submit (CreateMessage)"),
        ],
        string="ISDS Submission Mode",
        default="mock",
        help=(
            "Mock mode stores a deterministic local submission receipt for testing. "
            "HTTP JSON Bridge mode posts filing payloads to an external gateway service. "
            "SOAP Credential Check validates direct ISDS SOAP credentials (test/prod endpoints). "
            "SOAP Submit directly sends filing attachments via CreateMessage."
        ),
    )
    l10n_cz_isds_api_url = fields.Char(
        string="ISDS Endpoint URL",
        help=(
            "Endpoint URL used by non-mock ISDS modes. "
            "Examples: https://ws1.czebox.cz/DS/DsManage (credential check), "
            "https://ws1.czebox.cz/DS/dz (CreateMessage submit)."
        ),
    )
    l10n_cz_isds_username = fields.Char(
        string="ISDS Username",
        groups="base.group_system",
    )
    l10n_cz_isds_password = fields.Char(
        string="ISDS Password",
        groups="base.group_system",
    )
    l10n_cz_isds_sender_box_id = fields.Char(
        string="ISDS Sender Databox ID",
        help="Optional sender databox identifier included in submission payload metadata.",
    )
    l10n_cz_isds_target_box_id = fields.Char(
        string="ISDS Target Databox ID",
        default="pndaab6",
        help="Target databox ID for delivery routing metadata.",
    )
    l10n_cz_isds_timeout_seconds = fields.Integer(
        string="ISDS Timeout (s)",
        default=20,
        help="HTTP timeout used for ISDS bridge requests.",
    )
    l10n_cz_isds_epo_poll_enabled = fields.Boolean(
        string="Enable EPO Status Polling",
        help=(
            "If enabled, a cron job periodically calls the ADIS ZjistiStatus endpoint "
            "to check whether submitted filings have been accepted or rejected by the Tax Administration."
        ),
    )
    l10n_cz_isds_adis_epo_url = fields.Char(
        string="ADIS EPO Status URL",
        default="https://adisepo.mfcr.cz/adistc/adis/idpr/epo/zpracovaniRPDP/ws.asmx",
        help=(
            "SOAP endpoint for the ADIS ZjistiStatus operation (EPO filing status). "
            "Only used when EPO status polling is enabled. "
            "No ISDS credentials are sent to this endpoint — it is a separate ADIS service."
        ),
    )

    # XSD schema refresh
    l10n_cz_xsd_dphdp3_url = fields.Char(
        string="DPHDP3 XSD URL",
        help=(
            "URL of the authoritative DPHDP3 XSD schema published by MFČR. "
            "When set, the 'Refresh XSD Schemas' button will download and replace "
            "the bundled data/xsd/dphdp3.xsd file."
        ),
    )
    l10n_cz_xsd_dphkh1_url = fields.Char(
        string="DPHKH1 XSD URL",
        help=(
            "URL of the authoritative DPHKH1 XSD schema published by MFČR. "
            "When set, the 'Refresh XSD Schemas' button will download and replace "
            "the bundled data/xsd/dphkh1.xsd file."
        ),
    )
    l10n_cz_xsd_dphshv_url = fields.Char(
        string="DPHSHV XSD URL",
        help=(
            "URL of the authoritative DPHSHV XSD schema published by MFČR. "
            "When set, the 'Refresh XSD Schemas' button will download and replace "
            "the bundled data/xsd/dphshv.xsd file."
        ),
    )
    l10n_cz_xsd_refresh_log = fields.Text(
        string="Last XSD Refresh Log",
        readonly=True,
        help="Result of the most recent 'Refresh XSD Schemas' run.",
    )
    # Internal: JSON dict mapping form name → ETag/Last-Modified for conditional GETs
    l10n_cz_xsd_etags = fields.Text(default="{}")

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

    def l10n_cz_vat_registry_evaluate_partner(
        self,
        partner,
        bank_account=None,
        force_refresh=False,
        require_bank_account=False,
    ):
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
        if (
            require_bank_account
            and self.l10n_cz_vat_registry_block_unpublished_bank
            and not normalized_checked_bank
        ):
            result["violations"].append(
                _(
                    "Select a supplier bank account before posting the payment so the Czech VAT registry shield can verify it."
                )
            )
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

    def _l10n_cz_isds_collect_history_attachments(self, history):
        self.ensure_one()
        attachments = []
        specs = [
            ("dphdp3.xml", history.dphdp3_attachment_id),
            ("dphkh1.xml", history.dphkh1_attachment_id),
            ("dphshv.xml", history.dphshv_attachment_id),
        ]
        for file_name, attachment in specs:
            if not attachment:
                continue
            datas = attachment.datas
            if isinstance(datas, bytes):
                datas = datas.decode("ascii")
            attachments.append(
                {
                    "filename": file_name,
                    "mimetype": attachment.mimetype or "application/xml",
                    "content_base64": datas or "",
                }
            )
        if attachments:
            return attachments
        if history.zip_attachment_id:
            datas = history.zip_attachment_id.datas
            if isinstance(datas, bytes):
                datas = datas.decode("ascii")
            return [
                {
                    "filename": history.zip_attachment_id.name or "cz_vat_filing.zip",
                    "mimetype": history.zip_attachment_id.mimetype or "application/zip",
                    "content_base64": datas or "",
                }
            ]
        raise UserError(_("No filing attachment is available for Datova schranka submission."))

    def _l10n_cz_isds_prepare_payload(self, history):
        self.ensure_one()
        target_box = (self.l10n_cz_isds_target_box_id or "").strip()
        if not target_box:
            raise UserError(_("Set ISDS Target Databox ID on company settings before submission."))
        company_vat = self._l10n_cz_normalize_vat(self.partner_id.vat)
        return {
            "target_box_id": target_box,
            "sender_box_id": (self.l10n_cz_isds_sender_box_id or "").strip(),
            "subject": f"Czech VAT Filing {history.date_from} - {history.date_to}",
            "company_vat": company_vat,
            "period_from": str(history.date_from),
            "period_to": str(history.date_to),
            "forms": {
                "dphdp3": bool(history.dphdp3_attachment_id),
                "dphkh1": bool(history.dphkh1_attachment_id),
                "dphshv": bool(history.dphshv_attachment_id),
            },
            "attachments": self._l10n_cz_isds_collect_history_attachments(history),
        }

    def _l10n_cz_isds_extract_delivery_receipt(self, response_payload):
        self.ensure_one()
        if not isinstance(response_payload, dict):
            return None

        nested_payload = (
            response_payload.get("delivery_receipt")
            or response_payload.get("deliveryReceipt")
            or response_payload.get("receipt")
        )
        source = nested_payload if isinstance(nested_payload, dict) else response_payload

        content_base64 = (
            source.get("content_base64")
            or source.get("contentBase64")
            or source.get("delivery_receipt_base64")
            or source.get("deliveryReceiptBase64")
            or source.get("receipt_base64")
            or source.get("receiptBase64")
            or source.get("dorucenka_base64")
        )
        if not content_base64:
            return None

        if isinstance(content_base64, bytes):
            content_base64 = content_base64.decode("ascii", errors="ignore")
        content_base64 = str(content_base64).strip()
        if not content_base64:
            return None

        try:
            base64.b64decode(content_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise UserError(
                _("ISDS bridge returned a delivery receipt with invalid base64 content.")
            ) from exc

        filename = (
            source.get("filename")
            or source.get("file_name")
            or source.get("delivery_receipt_filename")
            or source.get("deliveryReceiptFilename")
            or source.get("receipt_filename")
            or "isds_delivery_receipt.pdf"
        )
        filename = str(filename or "isds_delivery_receipt.pdf").strip().replace("/", "_").replace("\\", "_")
        if not filename:
            filename = "isds_delivery_receipt.pdf"
        mimetype = (
            source.get("mimetype")
            or source.get("mime_type")
            or source.get("delivery_receipt_mimetype")
            or source.get("deliveryReceiptMimetype")
            or source.get("receipt_mimetype")
            or "application/pdf"
        )
        return {
            "filename": str(filename or "isds_delivery_receipt.pdf"),
            "mimetype": str(mimetype or "application/pdf"),
            "content_base64": content_base64,
        }

    def _l10n_cz_isds_submit_mock(self, payload):
        self.ensure_one()
        digest_seed = "|".join(
            [
                payload.get("target_box_id") or "",
                payload.get("period_from") or "",
                payload.get("period_to") or "",
                str(len(payload.get("attachments") or [])),
            ]
        )
        message_id = "MOCK-" + hashlib.sha1(digest_seed.encode("utf-8")).hexdigest()[:16].upper()
        return {
            "message_id": message_id,
            "delivery_info": _("Mock submission stored locally (no external Datova schranka delivery)."),
            "raw_response": {"provider": "mock", "message_id": message_id},
        }

    def _l10n_cz_isds_submit_http_json(self, payload):
        self.ensure_one()
        url = (self.l10n_cz_isds_api_url or "").strip()
        if not url:
            raise UserError(_("Set ISDS Bridge API URL before using HTTP JSON Bridge mode."))
        timeout = max(1, int(self.l10n_cz_isds_timeout_seconds or 20))
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Odoo-CZ-VAT-Filing/19",
        }
        username = (self.l10n_cz_isds_username or "").strip()
        password = self.l10n_cz_isds_password or ""
        if username:
            token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
            headers["Authorization"] = f"Basic {token}"
        req = request.Request(url, data=body, method="POST", headers=headers)
        try:
            with request.urlopen(req, timeout=timeout) as response:
                response_body = response.read().decode("utf-8", errors="replace")
        except (error.HTTPError, error.URLError, TimeoutError, ValueError) as exc:
            raise UserError(_("ISDS bridge submission failed: %s") % (exc,)) from exc

        try:
            response_payload = json.loads(response_body or "{}")
        except json.JSONDecodeError as exc:
            raise UserError(_("ISDS bridge response is not valid JSON.")) from exc

        status_raw = response_payload.get("status")
        if status_raw is None:
            status_raw = response_payload.get("result")
        if status_raw is None:
            status_raw = response_payload.get("success")
        status_text = str(status_raw or "").strip().lower()
        is_success = status_raw is True or status_text in {"ok", "success", "submitted", "true", "1"}
        if not is_success:
            detail = (
                response_payload.get("error")
                or response_payload.get("message")
                or response_payload.get("detail")
                or _("unknown error")
            )
            raise UserError(_("ISDS bridge rejected the submission: %s") % (detail,))

        message_id = (
            response_payload.get("message_id")
            or response_payload.get("messageId")
            or response_payload.get("id")
        )
        if not message_id:
            raise UserError(_("ISDS bridge did not return a message identifier."))
        delivery_receipt = self._l10n_cz_isds_extract_delivery_receipt(response_payload)
        return {
            "message_id": str(message_id),
            "delivery_info": (
                response_payload.get("delivery_info")
                or response_payload.get("deliveryInfo")
                or response_payload.get("message")
                or ""
            ),
            "delivery_receipt": delivery_receipt,
            "raw_response": response_payload,
        }

    def _l10n_cz_xml_local_name(self, tag):
        return str(tag or "").split("}", 1)[-1]

    def _l10n_cz_isds_normalize_soap_endpoint(self, raw_url, default_path):
        self.ensure_one()
        candidate = (raw_url or "").strip()
        if not candidate:
            candidate = f"https://ws1.czebox.cz{default_path}"
        elif "://" not in candidate:
            candidate = f"https://{candidate.lstrip('/')}"

        parsed_url = parse.urlsplit(candidate)
        netloc = parsed_url.netloc or "ws1.czebox.cz"
        path = parsed_url.path or default_path
        if path == "/":
            path = default_path
        else:
            path = path.rstrip("/") or default_path

        # Allow users to keep one URL in config; remap DsManage for CreateMessage mode.
        normalized_path = path.lower().rstrip("/")
        if default_path == "/DS/dz" and normalized_path == "/ds/dsmanage":
            path = "/DS/dz"

        return parse.urlunsplit(
            (
                parsed_url.scheme or "https",
                netloc,
                path,
                parsed_url.query or "",
                parsed_url.fragment or "",
            )
        )

    def _l10n_cz_isds_soap_fault_message(self, root):
        self.ensure_one()
        fault_node = None
        for node in root.iter():
            if self._l10n_cz_xml_local_name(node.tag) == "Fault":
                fault_node = node
                break
        if fault_node is None:
            return ""

        for preferred in ("faultstring", "Text", "Reason", "faultcode", "Code"):
            for node in fault_node.iter():
                if self._l10n_cz_xml_local_name(node.tag) != preferred:
                    continue
                text = (node.text or "").strip()
                if text:
                    return text
        return _("unknown SOAP fault")

    def _l10n_cz_isds_parse_soap_owner_info(self, response_body):
        self.ensure_one()
        try:
            root = ET.fromstring(response_body or "")
        except ET.ParseError as exc:
            raise UserError(_("ISDS SOAP response is not valid XML.")) from exc

        fault_text = self._l10n_cz_isds_soap_fault_message(root)
        if fault_text:
            raise UserError(_("ISDS SOAP call failed: %s") % (fault_text,))

        owner_info = {}
        accepted_fields = {
            "dbID",
            "dbIDOVM",
            "firmName",
            "ic",
            "pnFirstName",
            "pnLastName",
            "adresaTextem",
            "dbType",
            "userType",
        }
        for node in root.iter():
            local_name = self._l10n_cz_xml_local_name(node.tag)
            if local_name not in accepted_fields or local_name in owner_info:
                continue
            text = (node.text or "").strip()
            if text:
                owner_info[local_name] = text
        return owner_info

    def _l10n_cz_isds_build_soap_create_message(self, payload):
        self.ensure_one()
        target_box = escape(payload.get("target_box_id") or "")
        if not target_box:
            raise UserError(_("Set ISDS Target Databox ID on company settings before submission."))

        subject = (payload.get("subject") or _("Czech VAT Filing")).strip()
        subject = subject[:255]
        subject_xml = escape(subject)

        attachments = payload.get("attachments") or []
        if not attachments:
            raise UserError(_("No filing attachment is available for Datova schranka submission."))

        file_nodes = []
        for index, attachment in enumerate(attachments):
            filename = str(attachment.get("filename") or f"attachment_{index + 1}.xml").strip()
            filename = filename.replace("/", "_").replace("\\", "_")
            if not filename:
                filename = f"attachment_{index + 1}.xml"
            content_base64 = str(attachment.get("content_base64") or "").strip()
            if not content_base64:
                raise UserError(_("Attachment %s has no base64 content for ISDS SOAP submit.") % (filename,))
            mime_type = str(attachment.get("mimetype") or "application/octet-stream").strip()
            if not mime_type:
                mime_type = "application/octet-stream"
            file_meta = "main" if index == 0 else "enclosure"
            file_nodes.append(
                (
                    "<db:dmFile "
                    f"dmFileDescr='{escape(filename)}' "
                    f"dmMimeType='{escape(mime_type)}' "
                    f"dmFileMetaType='{file_meta}'>"
                    f"<db:dmEncodedContent>{content_base64}</db:dmEncodedContent>"
                    "</db:dmFile>"
                )
            )

        return (
            "<?xml version='1.0' encoding='utf-8'?>"
            "<soapenv:Envelope xmlns:soapenv='http://schemas.xmlsoap.org/soap/envelope/' "
            "xmlns:db='http://isds.czechpoint.cz/v20'>"
            "<soapenv:Body>"
            "<db:CreateMessage>"
            "<db:dmEnvelope>"
            f"<db:dbIDRecipient>{target_box}</db:dbIDRecipient>"
            f"<db:dmAnnotation>{subject_xml}</db:dmAnnotation>"
            "<db:dmPersonalDelivery>false</db:dmPersonalDelivery>"
            "<db:dmAllowSubstDelivery>true</db:dmAllowSubstDelivery>"
            "</db:dmEnvelope>"
            "<db:dmFiles>"
            f"{''.join(file_nodes)}"
            "</db:dmFiles>"
            "</db:CreateMessage>"
            "</soapenv:Body>"
            "</soapenv:Envelope>"
        )

    def _l10n_cz_isds_parse_soap_create_message(self, response_body):
        self.ensure_one()
        try:
            root = ET.fromstring(response_body or "")
        except ET.ParseError as exc:
            raise UserError(_("ISDS SOAP response is not valid XML.")) from exc

        fault_text = self._l10n_cz_isds_soap_fault_message(root)
        if fault_text:
            raise UserError(_("ISDS SOAP call failed: %s") % (fault_text,))

        status_code = ""
        status_message = ""
        message_id = ""
        for node in root.iter():
            local_name = self._l10n_cz_xml_local_name(node.tag)
            text = (node.text or "").strip()
            if not text:
                continue
            if local_name in {"dmStatusCode", "StatusCode"} and not status_code:
                status_code = text
            elif local_name in {"dmStatusMessage", "StatusMessage"} and not status_message:
                status_message = text
            elif local_name in {"dmID", "dmId", "MessageId", "MessageID"} and not message_id:
                message_id = text

        if not status_code:
            raise UserError(_("ISDS SOAP CreateMessage response did not contain dmStatusCode."))
        if status_code not in {"0000", "0"}:
            detail = status_message or _("unknown status")
            raise UserError(_("ISDS SOAP CreateMessage rejected submission (%s): %s") % (status_code, detail))
        if not message_id:
            raise UserError(_("ISDS SOAP CreateMessage response did not contain dmID."))

        return {
            "status_code": status_code,
            "status_message": status_message,
            "message_id": message_id,
        }

    def _l10n_cz_isds_submit_soap_owner_info(self, payload):
        self.ensure_one()
        url = self._l10n_cz_isds_normalize_soap_endpoint(self.l10n_cz_isds_api_url, "/DS/DsManage")
        username = (self.l10n_cz_isds_username or "").strip()
        password = self.l10n_cz_isds_password or ""
        if not username or not password:
            raise UserError(
                _(
                    "Set ISDS username and password before using SOAP credential-check mode."
                )
            )
        timeout = max(1, int(self.l10n_cz_isds_timeout_seconds or 20))
        envelope = (
            "<?xml version='1.0' encoding='utf-8'?>"
            "<soapenv:Envelope xmlns:soapenv='http://schemas.xmlsoap.org/soap/envelope/' "
            "xmlns:db='http://isds.czechpoint.cz/v20'>"
            "<soapenv:Body><db:GetOwnerInfoFromLogin/></soapenv:Body>"
            "</soapenv:Envelope>"
        )
        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "Accept": "text/xml",
            "SOAPAction": "GetOwnerInfoFromLogin",
            "User-Agent": "Odoo-CZ-VAT-Filing/19",
        }
        token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
        headers["Authorization"] = f"Basic {token}"
        req = request.Request(url, data=envelope.encode("utf-8"), method="POST", headers=headers)
        try:
            with request.urlopen(req, timeout=timeout) as response:
                response_body = response.read().decode("utf-8", errors="replace")
        except (error.HTTPError, error.URLError, TimeoutError, ValueError) as exc:
            raise UserError(_("ISDS SOAP call failed: %s") % (exc,)) from exc

        owner_info = self._l10n_cz_isds_parse_soap_owner_info(response_body)
        owner_token = (
            owner_info.get("dbID")
            or owner_info.get("ic")
            or owner_info.get("firmName")
            or _("unknown")
        )
        digest_seed = "|".join(
            [
                url,
                owner_token,
                payload.get("period_from") or "",
                payload.get("period_to") or "",
            ]
        )
        message_id = "SOAP-OWNER-" + hashlib.sha1(digest_seed.encode("utf-8")).hexdigest()[:16].upper()
        return {
            "message_id": message_id,
            "delivery_info": _(
                "SOAP credential check passed (GetOwnerInfoFromLogin). Filing XML was not submitted in this mode."
            ),
            "raw_response": {
                "provider": "soap_owner_info",
                "endpoint": url,
                "owner_info": owner_info,
            },
        }

    def _l10n_cz_isds_submit_soap_create_message(self, payload):
        self.ensure_one()
        url = self._l10n_cz_isds_normalize_soap_endpoint(self.l10n_cz_isds_api_url, "/DS/dz")
        username = (self.l10n_cz_isds_username or "").strip()
        password = self.l10n_cz_isds_password or ""
        if not username or not password:
            raise UserError(
                _(
                    "Set ISDS username and password before using SOAP CreateMessage mode."
                )
            )

        timeout = max(1, int(self.l10n_cz_isds_timeout_seconds or 20))
        envelope = self._l10n_cz_isds_build_soap_create_message(payload)
        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "Accept": "text/xml",
            "SOAPAction": "CreateMessage",
            "User-Agent": "Odoo-CZ-VAT-Filing/19",
        }
        token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
        headers["Authorization"] = f"Basic {token}"
        req = request.Request(url, data=envelope.encode("utf-8"), method="POST", headers=headers)
        try:
            with request.urlopen(req, timeout=timeout) as response:
                response_body = response.read().decode("utf-8", errors="replace")
        except (error.HTTPError, error.URLError, TimeoutError, ValueError) as exc:
            raise UserError(_("ISDS SOAP CreateMessage call failed: %s") % (exc,)) from exc

        parsed = self._l10n_cz_isds_parse_soap_create_message(response_body)
        return {
            "message_id": parsed["message_id"],
            "delivery_info": _(
                "SOAP CreateMessage status %(code)s %(message)s"
            )
            % {
                "code": parsed["status_code"],
                "message": parsed["status_message"] or "",
            },
            "raw_response": {
                "provider": "soap_create_message",
                "endpoint": url,
                "status_code": parsed["status_code"],
                "status_message": parsed["status_message"],
                "message_id": parsed["message_id"],
            },
        }

    def l10n_cz_isds_submit_history(self, history):
        self.ensure_one()
        history.ensure_one()
        if history.company_id != self:
            raise UserError(_("Submission history company does not match the selected company."))
        if not self.l10n_cz_isds_enabled:
            raise UserError(_("Enable Datova schranka submission on company settings first."))

        payload = self._l10n_cz_isds_prepare_payload(history)
        mode = self.l10n_cz_isds_mode or "mock"
        if mode == "mock":
            result = self._l10n_cz_isds_submit_mock(payload)
        elif mode == "http_json":
            result = self._l10n_cz_isds_submit_http_json(payload)
        elif mode == "soap_owner_info":
            result = self._l10n_cz_isds_submit_soap_owner_info(payload)
        elif mode == "soap_create_message":
            result = self._l10n_cz_isds_submit_soap_create_message(payload)
        else:
            raise UserError(_("Unsupported ISDS submission mode: %s") % (mode,))
        result["payload"] = payload
        result["mode"] = mode
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
        """Fetch the ČNB rate for a single specific date.

        Returns a dict with keys: status, error_message, source_url, payload,
        rate_to_czk, network_error.

        ``network_error=True`` signals a hard connectivity failure (DNS, timeout,
        connection refused).  The fallback wrapper uses this flag to stop retrying
        when the problem is the network, not a missing rate for the requested date.
        """
        self.ensure_one()
        url = self._l10n_cz_vat_fx_build_url(currency, tax_date)
        if not url:
            return {
                "status": "error",
                "error_message": _("CZ VAT FX API URL is not configured."),
                "source_url": "",
                "payload": {},
                "rate_to_czk": 0.0,
                "network_error": False,
            }
        timeout = max(1, int(self.l10n_cz_vat_fx_timeout_seconds or 10))
        req = request.Request(url, headers={"Accept": "*/*", "User-Agent": "Odoo-CZ-VAT-Filing/19"})
        try:
            with request.urlopen(req, timeout=timeout) as response:
                body = response.read().decode("utf-8", errors="replace")
        except error.HTTPError as exc:
            # Server responded with an HTTP error (e.g. 404 for a weekend date).
            # This is a date-specific failure — the fallback may succeed on the
            # preceding working day.
            return {
                "status": "error",
                "error_message": str(exc),
                "source_url": url,
                "payload": {},
                "rate_to_czk": 0.0,
                "network_error": False,
            }
        except (error.URLError, TimeoutError, ValueError) as exc:
            # Hard connectivity failure — retrying other dates won't help.
            return {
                "status": "error",
                "error_message": str(exc),
                "source_url": url,
                "payload": {},
                "rate_to_czk": 0.0,
                "network_error": True,
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
                    "network_error": False,
                }
            return {
                "status": "error",
                "error_message": _("CZ VAT FX API response is neither valid JSON nor parseable CNB text."),
                "source_url": url,
                "payload": text_payload,
                "rate_to_czk": 0.0,
                "network_error": False,
            }

        rate = self._l10n_cz_extract_rate_to_czk(payload, (currency.name or "").upper())
        if not rate or rate <= 0:
            return {
                "status": "error",
                "error_message": _("CZ VAT FX API did not provide a positive rate for %s.") % (currency.name,),
                "source_url": url,
                "payload": payload,
                "rate_to_czk": 0.0,
                "network_error": False,
            }
        return {
            "status": "ok",
            "error_message": "",
            "source_url": url,
            "payload": payload,
            "rate_to_czk": rate,
            "network_error": False,
        }

    def _l10n_cz_vat_fx_fetch_rate_with_fallback(self, currency, tax_date, max_fallback_days=5):
        """Fetch the ČNB rate for tax_date, falling back to preceding working days.

        The ČNB publishes rates on working days only.  Per § 38 of the Czech VAT
        Act, invoices dated on a weekend or public holiday must use the rate of
        the immediately preceding working day.  This method retries up to
        max_fallback_days earlier dates until a positive rate is found.

        Hard network failures (URLError, TimeoutError) stop the loop immediately —
        there is no point querying alternate dates when the server is unreachable.

        Returns the same dict as _l10n_cz_vat_fx_fetch_rate, plus a 'rate_date'
        key: the actual ČNB date the rate was sourced from (may be earlier than
        tax_date when a fallback was applied, or None on total failure).
        """
        self.ensure_one()
        base_date = fields.Date.to_date(tax_date)
        last_result = None
        for days_back in range(max_fallback_days + 1):
            attempt_date = base_date - timedelta(days=days_back)
            result = self._l10n_cz_vat_fx_fetch_rate(currency, attempt_date)
            if result["status"] == "ok" and result.get("rate_to_czk", 0) > 0:
                result["rate_date"] = attempt_date
                return result
            last_result = result
            if result.get("network_error"):
                break  # Hard connectivity failure — don't try other dates
        last_result = last_result or {
            "status": "error",
            "error_message": _("No ČNB rate found within %d days before the tax date.") % (max_fallback_days,),
            "source_url": "",
            "payload": {},
            "rate_to_czk": 0.0,
            "network_error": False,
        }
        last_result["rate_date"] = None
        return last_result

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

        fetched = self._l10n_cz_vat_fx_fetch_rate_with_fallback(currency, tax_date)
        values = {
            "company_id": self.id,
            "currency_id": currency.id,
            "tax_date": tax_date,
            "rate_date": fetched.get("rate_date") or tax_date,
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

    def _l10n_cz_adis_epo_soap_body(self, dic):
        """Build the ZjistiStatus SOAP request for ADIS EPO.

        ``dic`` should be the company's Czech VAT number (with or without CZ prefix);
        the CZ prefix is stripped because ADIS EPO expects the pure numeric DIC.
        """
        self.ensure_one()
        numeric_dic = re.sub(r"^CZ", "", (dic or "").strip().upper())
        dic_xml = escape(numeric_dic)
        return (
            "<?xml version='1.0' encoding='utf-8'?>"
            "<soapenv:Envelope xmlns:soapenv='http://schemas.xmlsoap.org/soap/envelope/' "
            "xmlns:adis='http://adis.mfcr.cz/WS_IDPR_EPO_ZPRACOVANI/'>"
            "<soapenv:Header/>"
            "<soapenv:Body>"
            "<adis:ZjistiStatus>"
            f"<adis:Dic>{dic_xml}</adis:Dic>"
            "</adis:ZjistiStatus>"
            "</soapenv:Body>"
            "</soapenv:Envelope>"
        ).encode("utf-8")

    def _l10n_cz_adis_epo_parse_zjisti_status(self, response_body):
        """Parse a ZjistiStatus SOAP response from ADIS EPO.

        Returns a dict:
          status       – 'accepted' | 'rejected' | 'pending' | 'error'
          raw_status   – verbatim status text from the XML (empty on parse error)
          description  – human-readable description element if present
          id_podani    – EPO-assigned submission ID if present in the response
          error_message – non-empty only when status == 'error'
        """
        self.ensure_one()
        try:
            root = ET.fromstring(response_body or "")
        except ET.ParseError:
            return {
                "status": "error",
                "raw_status": "",
                "description": "",
                "id_podani": "",
                "error_message": _("ADIS EPO response is not valid XML."),
            }

        fault_text = self._l10n_cz_isds_soap_fault_message(root)
        if fault_text:
            return {
                "status": "error",
                "raw_status": "",
                "description": "",
                "id_podani": "",
                "error_message": _("ADIS EPO SOAP fault: %s") % (fault_text,),
            }

        raw_status_values = self._l10n_cz_xml_text_values(
            root,
            ["StavZpracovani", "Stav", "Status", "VysledekZpracovani", "StatusZpracovani", "VysledekPodani"],
        )
        description_values = self._l10n_cz_xml_text_values(
            root,
            ["PopisStavu", "PopisChyby", "Popis", "Description", "StatusMessage", "zprava"],
        )
        id_podani_values = self._l10n_cz_xml_text_values(
            root,
            ["IdPodani", "IdZpracovani", "idPodani"],
        )

        raw_status = raw_status_values[0] if raw_status_values else ""
        description = description_values[0] if description_values else ""
        id_podani = id_podani_values[0] if id_podani_values else ""

        if not raw_status:
            return {
                "status": "error",
                "raw_status": "",
                "description": description,
                "id_podani": id_podani,
                "error_message": _("ADIS EPO response did not contain a recognisable status field."),
            }

        sig = self._l10n_cz_key_signature(raw_status)
        if sig in _EPO_ACCEPTED_SIGS:
            epo_status = "accepted"
        elif sig in _EPO_REJECTED_SIGS:
            epo_status = "rejected"
        else:
            # Unknown or intermediate status (e.g. PRIJATO, CEKA) — leave as pending
            epo_status = "pending"

        return {
            "status": epo_status,
            "raw_status": raw_status,
            "description": description,
            "id_podani": id_podani,
            "error_message": "",
        }

    def _l10n_cz_adis_epo_poll_history(self, history):
        """Call ADIS ZjistiStatus for one filing history record and update its fields.

        Returns the parsed result dict (same shape as _l10n_cz_adis_epo_parse_zjisti_status).
        Never raises — network/parse errors are stored on the record and returned as
        status=='error' so the cron can continue with the next record.
        """
        self.ensure_one()
        history.ensure_one()

        url = (self.l10n_cz_isds_adis_epo_url or "").strip()
        if not url:
            return {"status": "error", "raw_status": "", "description": "", "id_podani": "",
                    "error_message": _("ADIS EPO URL is not configured.")}

        company_vat = self._l10n_cz_normalize_vat(self.partner_id.vat)
        if not company_vat.startswith("CZ"):
            return {"status": "error", "raw_status": "", "description": "", "id_podani": "",
                    "error_message": _("Company has no Czech VAT number for EPO status check.")}

        body = self._l10n_cz_adis_epo_soap_body(company_vat)
        timeout = max(1, int(self.l10n_cz_isds_timeout_seconds or 20))
        req = request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "text/xml; charset=utf-8",
                "SOAPAction": "ZjistiStatus",
                "Accept": "text/xml,application/xml",
                "User-Agent": "Odoo-CZ-VAT-Filing/19",
            },
        )
        try:
            with request.urlopen(req, timeout=timeout) as response:
                response_body = response.read().decode("utf-8", errors="replace")
        except (error.HTTPError, error.URLError, TimeoutError, ValueError) as exc:
            err_text = str(exc)
            history.write({"isds_epo_checked_at": fields.Datetime.now(), "isds_epo_status_raw": err_text})
            return {"status": "error", "raw_status": "", "description": "", "id_podani": "",
                    "error_message": err_text}

        parsed = self._l10n_cz_adis_epo_parse_zjisti_status(response_body)

        write_vals = {
            "isds_epo_checked_at": fields.Datetime.now(),
            "isds_epo_status_raw": parsed.get("raw_status") or parsed.get("error_message") or "",
        }
        if parsed.get("id_podani"):
            write_vals["isds_epo_submission_id"] = parsed["id_podani"]

        if parsed["status"] in ("accepted", "rejected"):
            write_vals["isds_status"] = "accepted_by_epo" if parsed["status"] == "accepted" else "rejected_by_epo"
            filename = "epo_response.xml" if parsed["status"] == "accepted" else "epo_rejection.xml"
            attachment = history._create_text_attachment(filename, response_body, "application/xml")
            write_vals["epo_response_attachment_id"] = attachment.id

        history.write(write_vals)
        return parsed

    def cron_l10n_cz_poll_epo_status(self):
        """Cron: poll ADIS ZjistiStatus for all companies with EPO polling enabled."""
        companies = self.search(
            [
                ("l10n_cz_isds_epo_poll_enabled", "=", True),
                ("l10n_cz_isds_adis_epo_url", "!=", False),
            ]
        )
        if not companies:
            return True
        History = self.env["l10n_cz.vat.filing.history"]
        poll_threshold = fields.Datetime.now() - timedelta(hours=1)
        for company in companies:
            pending = History.search(
                [
                    ("company_id", "=", company.id),
                    ("isds_status", "=", "submitted"),
                    "|",
                    ("isds_epo_checked_at", "=", False),
                    ("isds_epo_checked_at", "<=", poll_threshold),
                ]
            )
            for history in pending:
                try:
                    company._l10n_cz_adis_epo_poll_history(history)
                except Exception:
                    _logger.exception(
                        "EPO status poll failed for filing history %s (company %s)",
                        history.id,
                        company.name,
                    )
        return True

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

    def action_l10n_cz_refresh_xsd_schemas(self):
        """Fetch XSD schemas from the configured URLs and overwrite the bundled files.

        Uses conditional GET (If-None-Match / ETag) so unchanged schemas produce
        a 304 and incur no disk write.  Results are written to l10n_cz_xsd_refresh_log
        and to the server log.  Gracefully skips any schema whose URL is blank.
        """
        self.ensure_one()

        xsd_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "xsd")
        schemas = [
            ("DPHDP3", self.l10n_cz_xsd_dphdp3_url),
            ("DPHKH1", self.l10n_cz_xsd_dphkh1_url),
            ("DPHSHV", self.l10n_cz_xsd_dphshv_url),
        ]

        try:
            etags = json.loads(self.l10n_cz_xsd_etags or "{}")
        except (ValueError, TypeError):
            etags = {}

        log_lines = []
        updated = 0
        unchanged = 0
        errored = 0

        for form_name, url in schemas:
            if not url:
                log_lines.append(f"{form_name}: no URL configured — skipped")
                continue

            req = request.Request(url, headers={"User-Agent": "Odoo/l10n_cz_vat_filing"})
            stored_etag = etags.get(form_name)
            if stored_etag:
                req.add_header("If-None-Match", stored_etag)

            try:
                with request.urlopen(req, timeout=30) as resp:
                    content = resp.read()
                    new_etag = resp.headers.get("ETag") or resp.headers.get("Last-Modified", "")
                    etags[form_name] = new_etag
                    dest = os.path.join(xsd_dir, f"{form_name.lower()}.xsd")
                    with open(dest, "wb") as fh:
                        fh.write(content)
                    log_lines.append(
                        f"{form_name}: updated — {len(content):,} bytes"
                        + (f", ETag: {new_etag}" if new_etag else "")
                    )
                    updated += 1
            except error.HTTPError as exc:
                if exc.code == 304:
                    log_lines.append(f"{form_name}: unchanged (304 Not Modified)")
                    unchanged += 1
                else:
                    log_lines.append(f"{form_name}: HTTP {exc.code} {exc.reason}")
                    errored += 1
            except Exception as exc:
                log_lines.append(f"{form_name}: error — {exc}")
                errored += 1

        timestamp = fields.Datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
        log = f"[{timestamp}]\n" + "\n".join(log_lines)
        self.write({"l10n_cz_xsd_refresh_log": log, "l10n_cz_xsd_etags": json.dumps(etags)})
        _logger.info("CZ XSD schema refresh for company %s:\n%s", self.name, log)

        summary = _("Updated: %(u)d  Unchanged: %(s)d  Errors: %(e)d") % {
            "u": updated, "s": unchanged, "e": errored,
        }
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("XSD Schema Refresh"),
                "message": summary,
                "type": "success" if not errored else "warning",
                "sticky": False,
            },
        }
