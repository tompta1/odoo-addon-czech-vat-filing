{
    "name": "Czech VAT Filing",
    "summary": "Generate Czech DPH, KH, and souhrnne hlaseni exports from Odoo data",
    "version": "19.0.20.0.0",
    "category": "Accounting/Localizations",
    "license": "LGPL-3",
    "author": "OpenAI Codex",
    "depends": ["account", "l10n_cz"],
    "data": [
        "security/ir.model.access.csv",
        "views/account_move_views.xml",
        "views/res_company_views.xml",
        "views/vat_filing_export_wizard_views.xml",
        "views/vat_filing_history_views.xml",
    ],
    "installable": True,
    "application": False,
}
