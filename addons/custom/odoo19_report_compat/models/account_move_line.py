from odoo import models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    def odoo19_report_compat_analytic_names(self):
        self.ensure_one()
        distribution = self.analytic_distribution or {}
        account_ids = []
        seen = set()
        for raw_key in distribution:
            for token in str(raw_key).split(","):
                token = token.strip()
                if not token.isdigit():
                    continue
                account_id = int(token)
                if account_id in seen:
                    continue
                seen.add(account_id)
                account_ids.append(account_id)
        if not account_ids:
            return ""
        accounts = {
            account.id: account.display_name
            for account in self.env["account.analytic.account"].browse(account_ids).exists()
        }
        return ", ".join(accounts[account_id] for account_id in account_ids if account_id in accounts)
