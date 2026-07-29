from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from obc_adc_designer.application import calculate_design
from obc_adc_designer.config import load_yaml
from obc_adc_designer.models import Status


class Gbt40432ComplianceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.single_cfg = load_yaml(ROOT / "config" / "pmp23607_default.yaml")
        cls.single = calculate_design(cls.single_cfg)
        cls.three_cfg = load_yaml(ROOT / "config" / "three_phase_22kw_template.yaml")
        cls.three = calculate_design(cls.three_cfg)

    def test_single_phase_standard_voltage_window(self) -> None:
        section = self.single.sections["02_GBT_Compliance"]
        self.assertAlmostEqual(section.metric_value("gbt_ac_test_min_v"), 187.0, places=12)
        self.assertAlmostEqual(section.metric_value("gbt_ac_test_max_v"), 253.0, places=12)
        self.assertFalse(any(d.code == "GBT_AC_RANGE" and d.status == Status.FAIL for d in section.diagnostics))

    def test_three_phase_standard_voltage_window(self) -> None:
        section = self.three.sections["02_GBT_Compliance"]
        self.assertAlmostEqual(section.metric_value("gbt_ac_test_min_v"), 323.0, places=12)
        self.assertAlmostEqual(section.metric_value("gbt_ac_test_max_v"), 437.0, places=12)

    def test_startup_inrush_range_floor(self) -> None:
        section = self.single.sections["02_GBT_Compliance"]
        required = section.metric_value("gbt_required_iac_linear_peak_a")
        steady_peak = self.single.sections["10_System_Rating"].metric_value("iac_peak_a")
        self.assertAlmostEqual(required, steady_peak * 1.20, places=12)

    def test_vdc_error_allocation(self) -> None:
        section = self.single.sections["02_GBT_Compliance"]
        self.assertAlmostEqual(section.metric_value("allocated_vdc_sensing_error_percent"), 0.5, places=12)
        self.assertAlmostEqual(section.metric_value("configured_vdc_sensing_target_percent"), 0.5, places=12)

    def test_dielectric_voltage_table(self) -> None:
        single = self.single.sections["08_GBT_Safety_EMC"]
        three = self.three.sections["08_GBT_Safety_EMC"]
        self.assertAlmostEqual(single.metric_value("dielectric_test_voltage_rms_v"), 2000.0, places=12)
        self.assertAlmostEqual(three.metric_value("dielectric_test_voltage_rms_v"), 2700.0, places=12)

    def test_instrument_selection_table(self) -> None:
        section = self.single.sections["07_GBT_Test_Equipment"]
        self.assertEqual(section.metric_value("sensor_validation_instrument_class"), "0.1 class")
        self.assertEqual(section.metric_value("voltage_error_test_instrument_class"), "0.2 class")
        self.assertEqual(section.metric_value("current_error_test_instrument_class"), "0.5 class")

    def test_bidirectional_inverter_layer_exists(self) -> None:
        self.assertIn("09_GBT_Inverter", self.single.sections)

    def test_standard_layer_can_be_disabled(self) -> None:
        cfg = copy.deepcopy(self.single_cfg)
        cfg["standard_profile"]["enabled"] = False
        result = calculate_design(cfg)
        self.assertNotIn("02_GBT_Compliance", result.sections)


if __name__ == "__main__":
    unittest.main(verbosity=2)
