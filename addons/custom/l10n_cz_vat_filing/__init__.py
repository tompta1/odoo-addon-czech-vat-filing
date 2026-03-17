from . import models
from . import wizards


def post_init_hook(env):
    """Backfill default URLs for companies that have none set."""
    _ADIS_URL = "https://adisrws.mfcr.cz/dpr/axis2/services/rozhraniCRPDPH.rozhraniCRPDPHSOAP"
    _CNB_URL = (
        "https://www.cnb.cz/cs/financni-trhy/devizovy-trh/kurzy-devizoveho-trhu/"
        "kurzy-devizoveho-trhu/denni_kurz.txt"
    )
    companies = env["res.company"].search([])
    for company in companies:
        vals = {}
        if not company.l10n_cz_vat_registry_api_url:
            vals["l10n_cz_vat_registry_api_url"] = _ADIS_URL
        if not company.l10n_cz_vat_fx_api_url:
            vals["l10n_cz_vat_fx_api_url"] = _CNB_URL
        if vals:
            company.write(vals)
