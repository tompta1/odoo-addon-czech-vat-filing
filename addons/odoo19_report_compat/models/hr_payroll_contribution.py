from datetime import datetime

from dateutil.relativedelta import relativedelta as relativedelta_delta

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class PayslipLinesContributionRegister(models.TransientModel):
    _inherit = "payslip.lines.contribution.register"

    def print_report(self):
        active_ids = self.env.context.get("active_ids", [])
        datas = {
            "ids": active_ids,
            "model": "hr.contribution.register",
            "form": self.read()[0],
        }
        return self.env.ref("om_hr_payroll.action_contribution_register").report_action([], data=datas)


class ContributionRegisterReport(models.AbstractModel):
    _name = "report.om_hr_payroll.report_contribution_register"
    _description = "Payroll Contribution Register Report"

    def _get_payslip_lines(self, register_ids, date_from, date_to):
        if not register_ids:
            return {}
        result = {}
        self.env.cr.execute(
            """
            SELECT pl.id from hr_payslip_line as pl
            LEFT JOIN hr_payslip AS hp on (pl.slip_id = hp.id)
            WHERE (hp.date_from >= %s) AND (hp.date_to <= %s)
            AND pl.register_id in %s
            AND hp.state = 'done'
            ORDER BY pl.slip_id, pl.sequence
            """,
            (date_from, date_to, tuple(register_ids)),
        )
        line_ids = [row[0] for row in self.env.cr.fetchall()]
        for line in self.env["hr.payslip.line"].browse(line_ids):
            result.setdefault(line.register_id.id, self.env["hr.payslip.line"])
            result[line.register_id.id] += line
        return result

    @api.model
    def _get_report_values(self, docids, data=None):
        if not data or not data.get("form"):
            raise UserError(_("Form content is missing, this report cannot be printed."))

        register_ids = self.env.context.get("active_ids", [])
        contrib_registers = self.env["hr.contribution.register"].browse(register_ids)
        date_from = data["form"].get("date_from", fields.Date.today())
        date_to = data["form"].get(
            "date_to",
            str(datetime.now() + relativedelta_delta(months=+1, day=1, days=-1))[:10],
        )
        lines_data = self._get_payslip_lines(register_ids, date_from, date_to)
        lines_total = {}
        for register in contrib_registers:
            lines = lines_data.get(register.id)
            lines_total[register.id] = lines and sum(lines.mapped("total")) or 0.0
        return {
            "doc_ids": register_ids,
            "doc_model": "hr.contribution.register",
            "docs": contrib_registers,
            "data": data,
            "lines_data": lines_data,
            "lines_total": lines_total,
        }
