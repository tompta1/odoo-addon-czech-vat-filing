from types import SimpleNamespace
from unittest.mock import Mock

from odoo.tests import TransactionCase

from odoo.addons.odoo19_report_compat.models.account_move_line import AccountMoveLine
from odoo.addons.odoo19_report_compat.models.hr_payroll_contribution import ContributionRegisterReport
from odoo.addons.odoo19_report_compat.models.hr_payslip import HrPayslip


class _FakeRecordset(list):
    def __init__(self, records=None, env=None):
        super().__init__(records or [])
        self.env = env

    @property
    def ids(self):
        return [record.id for record in self]

    def __ior__(self, other):
        self.extend(list(other))
        return self

    def compute_sheet(self):
        for record in self:
            record.compute_sheet()

    def action_payslip_done(self):
        for record in self:
            record.action_payslip_done()


class _FakeRefund:
    def __init__(self, record_id):
        self.id = record_id
        self.compute_calls = 0
        self.done_calls = 0

    def compute_sheet(self):
        self.compute_calls += 1

    def action_payslip_done(self):
        self.done_calls += 1


class _FakePayslip:
    def __init__(self, name, refund_recordset):
        self.name = name
        self._refund_recordset = refund_recordset

    def copy(self, values):
        assert values["credit_note"] is True
        assert values["name"].startswith("Refund: ")
        return self._refund_recordset


class _FakeEnv(dict):
    def __init__(self, cr, uid):
        super().__init__()
        self.cr = cr
        self.uid = uid

    def __getitem__(self, key):
        if key == "hr.payslip":
            return _FakeRecordset(env=self)
        raise KeyError(key)

    def ref(self, xmlid, default=False):
        return SimpleNamespace(id=99)


class TestOdoo19ReportCompat(TransactionCase):
    def test_refund_sheet_returns_all_copied_payslips(self):
        refund_one = _FakeRefund(101)
        refund_two = _FakeRefund(102)
        fake_env = _FakeEnv(self.env.cr, self.env.uid)
        payslips = _FakeRecordset(
            [
                _FakePayslip("Slip A", _FakeRecordset([refund_one], env=fake_env)),
                _FakePayslip("Slip B", _FakeRecordset([refund_two], env=fake_env)),
            ],
            env=fake_env,
        )

        action = HrPayslip.refund_sheet(payslips)

        self.assertEqual(action["domain"], "[('id', 'in', [101, 102])]")
        self.assertEqual(refund_one.compute_calls, 1)
        self.assertEqual(refund_one.done_calls, 1)
        self.assertEqual(refund_two.compute_calls, 1)
        self.assertEqual(refund_two.done_calls, 1)

    def test_get_payslip_lines_skips_sql_for_empty_register_selection(self):
        fake_cr = SimpleNamespace(execute=Mock())
        fake_env = SimpleNamespace(cr=fake_cr)
        fake_self = SimpleNamespace(env=fake_env)

        result = ContributionRegisterReport._get_payslip_lines(fake_self, [], "2027-01-01", "2027-01-31")

        self.assertEqual(result, {})
        fake_cr.execute.assert_not_called()

    def test_analytic_distribution_helper_resolves_display_names(self):
        plan = self.env["account.analytic.plan"].search([], limit=1)
        if not plan:
            plan = self.env["account.analytic.plan"].create({"name": "Compat Test Plan"})
        account_one = self.env["account.analytic.account"].create(
            {"name": "Compat Alpha", "plan_id": plan.id}
        )
        account_two = self.env["account.analytic.account"].create(
            {"name": "Compat Beta", "plan_id": plan.id}
        )
        line = self.env["account.move.line"].new(
            {
                "analytic_distribution": {
                    str(account_one.id): 60.0,
                    str(account_two.id): 40.0,
                }
            }
        )

        labels = AccountMoveLine.odoo19_report_compat_analytic_names(line)

        self.assertEqual(labels, f"{account_one.display_name}, {account_two.display_name}")
