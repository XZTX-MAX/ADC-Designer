from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from obc_adc_designer.application import calculate_design
from obc_adc_designer.config import load_yaml, validate_config
from obc_adc_designer.models import Status


class ThreePhaseRegressionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cfg = load_yaml(ROOT / "config" / "three_phase_22kw_template.yaml")
        validate_config(cls.cfg)
        cls.result = calculate_design(cls.cfg)

    def test_three_phase_line_current_formula(self) -> None:
        actual = self.result.sections["10_System_Rating"].metric_value("iac_rms_max_a")
        expected = 22000.0 / (math.sqrt(3.0) * 304.0 * 0.95 * 0.99) * 1.05
        self.assertAlmostEqual(actual, expected, places=10)

    def test_per_phase_sections_exist(self) -> None:
        for name in ("20_IAC_A", "20_IAC_B", "20_IAC_C", "40_VAC_A", "40_VAC_B", "40_VAC_C"):
            self.assertIn(name, self.result.sections)

    def test_line_to_phase_voltage_conversion(self) -> None:
        design_peak = self.result.sections["40_VAC_A"].metric_value("vac_design_peak_v")
        expected = (480.0 / math.sqrt(3.0)) * math.sqrt(2.0) * 1.15
        self.assertAlmostEqual(design_peak, expected, places=10)

    def test_phase_matching_is_calculated(self) -> None:
        mismatch = self.result.sections["16_Phase_Matching"].metric_value("phase_current_gain_mismatch_percent")
        self.assertGreater(mismatch, 0.0)
        self.assertLess(mismatch, 0.2)

    def test_synchronous_current_modules_are_parallel(self) -> None:
        section = self.result.sections["52_Sampling_Sync"]
        self.assertEqual(section.metric_value("current_adc_module_count"), 3)
        self.assertFalse(any(d.code == "SAMPLING_ADC_REUSE" and d.status == Status.FAIL for d in section.diagnostics))

    def test_sampling_skew_model(self) -> None:
        section = self.result.sections["52_Sampling_Sync"]
        self.assertAlmostEqual(section.metric_value("maximum_channel_skew_s"), 60e-9, places=15)
        self.assertAlmostEqual(section.metric_value("current_skew_error_a"), 0.12, places=12)


if __name__ == "__main__":
    unittest.main(verbosity=2)
