from odoo import _, models


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    def refund_sheet(self):
        copied_payslips = self.env["hr.payslip"]
        for payslip in self:
            refund = payslip.copy({"credit_note": True, "name": _("Refund: ") + payslip.name})
            refund.compute_sheet()
            refund.action_payslip_done()
            copied_payslips |= refund
        form_view_ref = self.env.ref("om_hr_payroll.view_hr_payslip_form", False)
        list_view_ref = self.env.ref("om_hr_payroll.view_hr_payslip_tree", False)
        return {
            "name": _("Refund Payslip"),
            "view_mode": "list, form",
            "view_id": False,
            "view_type": "form",
            "res_model": "hr.payslip",
            "type": "ir.actions.act_window",
            "target": "current",
            "domain": "[('id', 'in', %s)]" % copied_payslips.ids,
            "views": [
                (list_view_ref.id if list_view_ref else False, "list"),
                (form_view_ref.id if form_view_ref else False, "form"),
            ],
            "context": {},
        }
