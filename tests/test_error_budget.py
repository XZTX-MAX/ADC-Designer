from __future__ import annotations

import copy
import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from obc_adc_designer.application import calculate_design
from obc_adc_designer.config import load_yaml


class ErrorBudgetTest(unittest.TestCase):
    def test_wc_and_rss(self) -> None:
        cfg = load_yaml(ROOT / "config" / "pmp23607_default.yaml")
        cfg = copy.deepcopy(cfg)
        cfg["channels"]["iac"]["error_sources"] = [
            {"name": "A", "percent_fs": 0.1, "drift_ppm_per_c": 0},
            {"name": "B", "percent_fs": 0.2, "drift_ppm_per_c": 0},
        ]
        result = calculate_design(cfg)
        section = result.sections["60_IAC_Error"]
        self.assertAlmostEqual(section.metric_value("wc_percent_fs"), 0.3, places=12)
        self.assertAlmostEqual(section.metric_value("rss_percent_fs"), math.sqrt(0.05), places=12)


if __name__ == "__main__":
    unittest.main(verbosity=2)
