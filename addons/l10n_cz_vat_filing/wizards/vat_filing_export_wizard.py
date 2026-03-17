import calendar

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class L10nCzVatFilingExportWizard(models.TransientModel):
    _name = "l10n_cz.vat.filing.export.wizard"
    _description = "Czech VAT Filing Export Wizard"

    def _default_date_from(self):
        today = fields.Date.context_today(self)
        return today.replace(day=1)

    def _default_date_to(self):
        today = fields.Date.context_today(self)
        return today.replace(day=calendar.monthrange(today.year, today.month)[1])

    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
    )
    date_from = fields.Date(
        string="From",
        required=True,
        default=_default_date_from,
    )
    date_to = fields.Date(
        string="To",
        required=True,
        default=_default_date_to,
    )
    period_kind = fields.Selection(
        [
            ("auto", "Auto"),
            ("month", "Month"),
            ("quarter", "Quarter"),
        ],
        string="Period Kind",
        required=True,
        default="auto",
        help="Auto infers the period type from dates. Set explicitly when the selected range is not a full month/quarter.",
    )
    period_from = fields.Date(
        string="VetaD Period From",
        help="Optional explicit VetaD period start (period_from). Requires VetaD Period To.",
    )
    period_to = fields.Date(
        string="VetaD Period To",
        help="Optional explicit VetaD period end (period_to). Requires VetaD Period From.",
    )

    include_dphdp3 = fields.Boolean(string="Export DPHDP3", default=True)
    include_dphkh1 = fields.Boolean(string="Export DPHKH1", default=True)
    include_dphshv = fields.Boolean(string="Export DPHSHV", default=True)
    include_debug_json = fields.Boolean(
        string="Include Debug JSON",
        default=True,
    )

    submission_date = fields.Date(
        string="Submission Date (d_poddp)",
        required=True,
        default=fields.Date.context_today,
    )
    tax_statement_date = fields.Date(
        string="Tax Statement Date (d_zjist)",
        help="Required for dodatecne/opravne DPH and nasledne/opravne KH when no challenge reference is provided.",
    )
    dph_form = fields.Selection(
        [
            ("B", "B - Radne"),
            ("O", "O - Opravne"),
            ("D", "D - Dodatecne"),
            ("E", "E - Dodatecne/Opravne"),
        ],
        string="DPH Form",
        required=True,
        default="B",
    )
    kh_form = fields.Selection(
        [
            ("B", "B - Radne"),
            ("O", "O - Opravne"),
            ("N", "N - Nasledne"),
            ("E", "E - Nasledne/Opravne"),
        ],
        string="KH Form",
        required=True,
        default="B",
    )
    sh_form = fields.Selection(
        [
            ("R", "R - Radne"),
            ("O", "O - Opravne"),
        ],
        string="SH Form",
        required=True,
        default="R",
    )
    kh_challenge_reference = fields.Char(
        string="KH Challenge Reference",
        help="c_jed_vyzvy for KH challenge-response flow.",
    )
    kh_challenge_response = fields.Char(
        string="KH Challenge Response",
        help="vyzva_odp for KH challenge-response flow.",
    )
    row_53_available = fields.Boolean(
        string="Row 53 Available",
        compute="_compute_row_53_available",
    )
    calculate_row_53 = fields.Boolean(
        string="Calculate Row 53 Settlement",
        default=False,
        help="For the last tax period of the year only (December or Q4): derive row 53 settlement from the actual coefficient.",
    )
    actual_year_coefficient = fields.Integer(
        string="Actual Year Coefficient (%)",
        help="Settlement coefficient for row 53 (1-100) used in the year-end period.",
    )

    @api.depends("date_from", "date_to", "period_kind")
    def _compute_row_53_available(self):
        for wizard in self:
            wizard.row_53_available = wizard._is_year_end_period()

    def _infer_period_kind_for_row_53(self):
        self.ensure_one()
        if not self.date_from or not self.date_to:
            return None
        if self.period_kind in {"month", "quarter"}:
            return self.period_kind

        # `auto` mode mirrors exporter period inference for full natural month/quarter.
        if (
            self.date_from.day == 1
            and self.date_to.day == calendar.monthrange(self.date_to.year, self.date_to.month)[1]
            and self.date_from.year == self.date_to.year
            and self.date_from.month == self.date_to.month
        ):
            return "month"

        if (
            self.date_from.month in {1, 4, 7, 10}
            and self.date_from.day == 1
            and self.date_to.month == self.date_from.month + 2
            and self.date_to.year == self.date_from.year
            and self.date_to.day == calendar.monthrange(self.date_to.year, self.date_to.month)[1]
        ):
            return "quarter"
        return None

    def _is_year_end_period(self):
        self.ensure_one()
        period_kind = self._infer_period_kind_for_row_53()
        if period_kind == "month":
            return self.date_from and self.date_from.month == 12
        if period_kind == "quarter":
            return self.date_from and self.date_from.month == 10
        return False

    @api.constrains("date_from", "date_to")
    def _check_date_range(self):
        for wizard in self:
            if wizard.date_from and wizard.date_to and wizard.date_from > wizard.date_to:
                raise ValidationError(_("Date From must be on or before Date To."))

    @api.constrains("period_from", "period_to")
    def _check_period_override_pair(self):
        for wizard in self:
            if bool(wizard.period_from) ^ bool(wizard.period_to):
                raise ValidationError(
                    _("VetaD period override requires both Period From and Period To.")
                )
            if wizard.period_from and wizard.period_to and wizard.period_from > wizard.period_to:
                raise ValidationError(_("VetaD Period From must be on or before VetaD Period To."))

    @api.constrains("include_dphdp3", "include_dphkh1", "include_dphshv")
    def _check_selected_forms(self):
        for wizard in self:
            if not (wizard.include_dphdp3 or wizard.include_dphkh1 or wizard.include_dphshv):
                raise ValidationError(_("Enable at least one export form (DPHDP3, DPHKH1, or DPHSHV)."))

    @api.constrains("calculate_row_53", "actual_year_coefficient", "date_from", "date_to", "period_kind")
    def _check_row_53_inputs(self):
        for wizard in self:
            if not wizard.calculate_row_53:
                continue
            if not wizard._is_year_end_period():
                raise ValidationError(
                    _("Row 53 settlement can be calculated only for the year-end period (December or Q4).")
                )
            if not wizard.actual_year_coefficient:
                raise ValidationError(_("Set Actual Year Coefficient when Row 53 settlement is enabled."))
            if wizard.actual_year_coefficient < 1 or wizard.actual_year_coefficient > 100:
                raise ValidationError(_("Actual Year Coefficient must be between 1 and 100."))

    def _build_options(self):
        self.ensure_one()
        options = {
            "include_dphdp3": self.include_dphdp3,
            "include_dphkh1": self.include_dphkh1,
            "include_dphshv": self.include_dphshv,
            "submission_date": str(self.submission_date),
            "dph_form": self.dph_form,
            "kh_form": self.kh_form,
            "sh_form": self.sh_form,
        }
        if self.period_kind != "auto":
            options["period_kind"] = self.period_kind
        if self.period_from and self.period_to:
            options["period_from"] = str(self.period_from)
            options["period_to"] = str(self.period_to)
        if self.tax_statement_date:
            options["tax_statement_date"] = str(self.tax_statement_date)
        if self.kh_challenge_reference:
            options["kh_challenge_reference"] = self.kh_challenge_reference.strip()
        if self.kh_challenge_response:
            options["kh_challenge_response"] = self.kh_challenge_response.strip()
        if self.calculate_row_53:
            options["line_53a_settlement_coefficient"] = int(self.actual_year_coefficient)
        return options

    def action_export_zip(self):
        self.ensure_one()
        if not self.company_id:
            raise UserError(_("Choose a company before exporting Czech filing XML."))

        options = self._build_options()
        exports = self.company_id.l10n_cz_vat_filing_exports(self.date_from, self.date_to, options=options)
        history = self.env["l10n_cz.vat.filing.history"].create_export_record(
            self.company_id,
            self.date_from,
            self.date_to,
            options,
            exports,
            include_debug_json=self.include_debug_json,
        )
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/{history.zip_attachment_id.id}?download=true",
            "target": "self",
        }
