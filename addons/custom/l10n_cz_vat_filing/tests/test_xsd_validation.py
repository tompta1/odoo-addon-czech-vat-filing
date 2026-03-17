"""
Unit tests for _validate_xml_against_xsd().

These tests use unittest.TestCase (no Odoo database required) because
_validate_xml_against_xsd() is a self-contained helper with no ORM access.
"""
import textwrap
import unittest
from unittest.mock import patch

from odoo.exceptions import UserError


# ---------------------------------------------------------------------------
# Minimal stand-in: attach the method to a plain object so we can call it
# without setting up a full Odoo model instance.
# ---------------------------------------------------------------------------
class _FakeModel:
    """Duck-typed stand-in for L10nCzVatFilingExport used only in these tests."""


def _load_method():
    from odoo.addons.l10n_cz_vat_filing.models.vat_filing_export import (
        L10nCzVatFilingExport,
    )
    _FakeModel._validate_xml_against_xsd = L10nCzVatFilingExport._validate_xml_against_xsd


_load_method()


# ---------------------------------------------------------------------------
# Minimal XML fixtures
# ---------------------------------------------------------------------------

# A structurally valid DPHDP3 document (all required attributes present)
_VALID_DPHDP3 = textwrap.dedent("""\
    <?xml version="1.0" encoding="UTF-8"?>
    <Pisemnost nazevSW="Odoo" verzeSW="1.0">
      <DPHDP3>
        <VetaD dokument="DP3" k_uladis="DPH" d_poddp="20.03.2026"
               dapdph_forma="B" rok="2026" mesic="3"
               typ_platce="P" dic_puv="CZ12345678"/>
        <VetaP dic="12345678" c_ufo="451" c_pracufo="2001"
               typ_ds="P" zkrobchjm="Test s.r.o."/>
      </DPHDP3>
    </Pisemnost>
""")

# Missing required attribute d_poddp — should fail validation
_INVALID_DPHDP3 = textwrap.dedent("""\
    <?xml version="1.0" encoding="UTF-8"?>
    <Pisemnost nazevSW="Odoo" verzeSW="1.0">
      <DPHDP3>
        <VetaD dokument="DP3" k_uladis="DPH"
               dapdph_forma="B" rok="2026" mesic="3"/>
        <VetaP dic="12345678" c_ufo="451" c_pracufo="2001"/>
      </DPHDP3>
    </Pisemnost>
""")


class TestXsdValidation(unittest.TestCase):

    def setUp(self):
        self.model = _FakeModel()

    # ------------------------------------------------------------------
    # 1. Happy path: valid XML passes without raising
    # ------------------------------------------------------------------
    def test_valid_dphdp3_passes(self):
        # Should return None and not raise any exception
        result = self.model._validate_xml_against_xsd(_VALID_DPHDP3, "DPHDP3")
        self.assertIsNone(result)

    # ------------------------------------------------------------------
    # 2. Invalid XML raises UserError mentioning the form name
    # ------------------------------------------------------------------
    def test_invalid_dphdp3_raises(self):
        with self.assertRaises(UserError) as ctx:
            self.model._validate_xml_against_xsd(_INVALID_DPHDP3, "DPHDP3")
        self.assertIn("DPHDP3", str(ctx.exception))

    # ------------------------------------------------------------------
    # 3. Missing XSD file → warning only, no exception
    # ------------------------------------------------------------------
    def test_missing_xsd_file_skips(self):
        with patch("os.path.isfile", return_value=False):
            # Even clearly broken XML must not raise when the schema is absent
            self.model._validate_xml_against_xsd(_INVALID_DPHDP3, "DPHDP3")

    # ------------------------------------------------------------------
    # 4. lxml not installed → warning only, no exception
    # ------------------------------------------------------------------
    def test_missing_lxml_skips(self):
        with patch.dict("sys.modules", {"lxml": None, "lxml.etree": None}):
            self.model._validate_xml_against_xsd(_INVALID_DPHDP3, "DPHDP3")
