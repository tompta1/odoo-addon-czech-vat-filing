import base64
import io
import json
import zipfile

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class L10nCzVatFilingHistory(models.Model):
    _name = "l10n_cz.vat.filing.history"
    _description = "Czech VAT Filing Export History"
    _order = "create_date desc, id desc"

    name = fields.Char(string="Name", required=True, readonly=True, default="/")
    company_id = fields.Many2one("res.company", string="Company", required=True, index=True)
    date_from = fields.Date(string="From", required=True)
    date_to = fields.Date(string="To", required=True)
    include_dphdp3 = fields.Boolean(string="DPHDP3", default=True)
    include_dphkh1 = fields.Boolean(string="DPHKH1", default=True)
    include_dphshv = fields.Boolean(string="DPHSHV", default=True)
    include_debug_json = fields.Boolean(string="Debug JSON", default=True)
    submission_date = fields.Date(string="Submission Date (d_poddp)")
    tax_statement_date = fields.Date(string="Tax Statement Date (d_zjist)")
    dph_form = fields.Char(string="DPH Form")
    kh_form = fields.Char(string="KH Form")
    sh_form = fields.Char(string="SH Form")
    options_json = fields.Text(string="Options JSON", readonly=True)
    warning_messages = fields.Text(string="Warnings", readonly=True)

    zip_attachment_id = fields.Many2one("ir.attachment", string="ZIP Attachment", readonly=True, ondelete="set null")
    dphdp3_attachment_id = fields.Many2one("ir.attachment", string="DPHDP3 XML", readonly=True, ondelete="set null")
    dphkh1_attachment_id = fields.Many2one("ir.attachment", string="DPHKH1 XML", readonly=True, ondelete="set null")
    dphshv_attachment_id = fields.Many2one("ir.attachment", string="DPHSHV XML", readonly=True, ondelete="set null")
    debug_attachment_id = fields.Many2one(
        "ir.attachment",
        string="Debug JSON Attachment",
        readonly=True,
        ondelete="set null",
    )

    def _set_default_name(self):
        for record in self.filtered(lambda rec: rec.name == "/"):
            record.name = f"CZ VAT Filing {record.date_from} - {record.date_to} #{record.id}"

    @staticmethod
    def _zip_bytes(files):
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
            for file_name, content in files:
                archive.writestr(file_name, content or "")
        return zip_buffer.getvalue()

    def _create_text_attachment(self, file_name, content, mimetype):
        self.ensure_one()
        payload = (content or "").encode("utf-8")
        return self.env["ir.attachment"].create(
            {
                "name": file_name,
                "type": "binary",
                "datas": base64.b64encode(payload),
                "mimetype": mimetype,
                "res_model": self._name,
                "res_id": self.id,
            }
        )

    def _create_zip_attachment(self, archive_name, files):
        self.ensure_one()
        return self.env["ir.attachment"].create(
            {
                "name": archive_name,
                "type": "binary",
                "datas": base64.b64encode(self._zip_bytes(files)),
                "mimetype": "application/zip",
                "res_model": self._name,
                "res_id": self.id,
            }
        )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._set_default_name()
        return records

    @api.model
    def create_export_record(self, company, date_from, date_to, options, exports, include_debug_json=True):
        debug_payload = exports.get("debug", {})
        metadata = debug_payload.get("metadata", {})
        warnings = debug_payload.get("validation", {}).get("warnings", []) or []
        record = self.create(
            {
                "company_id": company.id,
                "date_from": date_from,
                "date_to": date_to,
                "include_dphdp3": bool(options.get("include_dphdp3", True)),
                "include_dphkh1": bool(options.get("include_dphkh1", True)),
                "include_dphshv": bool(options.get("include_dphshv", True)),
                "include_debug_json": bool(include_debug_json),
                "submission_date": metadata.get("submission_date"),
                "tax_statement_date": metadata.get("tax_statement_date") or False,
                "dph_form": metadata.get("dph_form") or "",
                "kh_form": metadata.get("kh_form") or "",
                "sh_form": metadata.get("sh_form") or "",
                "options_json": json.dumps(options or {}, ensure_ascii=False, sort_keys=True, indent=2),
                "warning_messages": "\n".join(warnings),
            }
        )

        files = []
        attachment_ids = {}
        file_specs = [
            ("dphdp3.xml", exports.get("dphdp3_xml"), "application/xml", "dphdp3_attachment_id"),
            ("dphkh1.xml", exports.get("dphkh1_xml"), "application/xml", "dphkh1_attachment_id"),
            ("dphshv.xml", exports.get("dphshv_xml"), "application/xml", "dphshv_attachment_id"),
        ]
        for file_name, content, mimetype, field_name in file_specs:
            if not content:
                continue
            files.append((file_name, content))
            attachment_ids[field_name] = record._create_text_attachment(file_name, content, mimetype).id

        if include_debug_json:
            debug_json = exports.get("debug_json") or "{}"
            files.append(("debug.json", debug_json))
            attachment_ids["debug_attachment_id"] = record._create_text_attachment(
                "debug.json",
                debug_json,
                "application/json",
            ).id

        if not files:
            raise UserError(_("No export files were generated."))

        period_token = f"{date_from}_{date_to}"
        archive_name = f"cz_vat_filing_{period_token}.zip"
        attachment_ids["zip_attachment_id"] = record._create_zip_attachment(archive_name, files).id
        record.write(attachment_ids)
        return record
