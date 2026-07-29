from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from obc_adc_designer.application import calculate_design
from obc_adc_designer.config import load_yaml
from obc_adc_designer.models import Status


class Pmp23607RegressionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cfg = load_yaml(ROOT / "config" / "pmp23607_default.yaml")
        cls.result = calculate_design(cls.cfg)

    def test_adc_lsb(self) -> None:
        value = self.result.sections["50_ADC_Timing"].metric_value("adc_lsb_v")
        self.assertAlmostEqual(value, 3.0 / 4096.0, places=12)

    def test_iac_hardware_scaling(self) -> None:
        value = self.result.sections["20_IAC_Hall"].metric_value("current_per_code_a")
        expected = (3.0 / 4096.0) / (0.025 * 0.584268)
        self.assertAlmostEqual(value, expected, places=8)

    def test_idc_hardware_scaling(self) -> None:
        value = self.result.sections["30_IDC_Shunt"].metric_value("current_per_code_a")
        expected = (3.0 / 4096.0) / (0.001 * 3.3 / (2 * 0.064))
        self.assertAlmostEqual(value, expected, places=8)

    def test_vac_range_is_flagged(self) -> None:
        diagnostics = self.result.sections["40_VAC"].diagnostics
        self.assertTrue(any(d.code == "VAC_LINEAR_RANGE" and d.status == Status.FAIL for d in diagnostics))

    def test_vdc_transfer_ratio(self) -> None:
        value = self.result.sections["41_VDC"].metric_value("sensor_transfer_ratio")
        self.assertAlmostEqual(value, 3.3 / 1281.0, places=12)

    def test_ppb_not_claimed(self) -> None:
        # This tool calculates hardware design parameters only; it must not infer that PPB is used by control code.
        self.assertNotIn("PPB", " ".join(self.result.sections.keys()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
