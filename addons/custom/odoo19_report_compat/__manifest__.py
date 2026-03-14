{
    "name": "Odoo 19 Report Compatibility",
    "summary": "Compatibility fixes for third-party reports on Odoo 19",
    "version": "19.0.1.0.0",
    "category": "Accounting",
    "license": "LGPL-3",
    "author": "OpenAI Codex",
    "depends": ["accounting_pdf_reports", "om_account_followup", "om_hr_payroll"],
    "data": [
        "views/report_journal_entries.xml",
    ],
    "installable": True,
    "application": False,
}
