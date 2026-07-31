from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from obc_adc_designer.config import load_yaml
from obc_adc_designer.config_schema import BlankMode, field_spec_for_key

LIST_ROOTS = {
    "assumptions",
    "sampling.channels",
    "standard_profile.voltage_dip_tests",
    "channels.iac.error_sources",
    "channels.idc.error_sources",
    "channels.vac.error_sources",
    "channels.vdc.error_sources",
}


def scalar_paths(value: Any, prefix: str = "") -> set[str]:
    if prefix in LIST_ROOTS:
        return set()
    if isinstance(value, dict):
        found: set[str] = set()
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else key
            found.update(scalar_paths(child, path))
        return found
    if isinstance(value, list):
        return {prefix}
    return {prefix}


class ConfigSchemaTest(unittest.TestCase):
    def test_every_existing_scalar_has_a_field_spec(self) -> None:
        paths: set[str] = set()
        for relative in (
            "config/pmp23607_default.yaml",
            "config/pmp23607_user.yaml",
            "config/three_phase_22kw_template.yaml",
            "config/standards/gbt40432_2021.yaml",
        ):
            paths.update(scalar_paths(load_yaml(ROOT / relative)))
        missing = sorted(path for path in paths if field_spec_for_key(path) is None)
        self.assertEqual(missing, [])

    def test_phase_override_pattern_is_constrained(self) -> None:
        valid = field_spec_for_key(
            "channels.iac.phase_overrides.B.hall.front_end_gain"
        )
        invalid = field_spec_for_key(
            "channels.iac.phase_overrides.B.hall.front_end_gaim"
        )
        self.assertIsNotNone(valid)
        self.assertIsNone(invalid)

    def test_nullable_and_omitted_blank_modes_are_distinct(self) -> None:
        nullable = field_spec_for_key(
            "adc.acquisition.exact_sample_capacitance_f"
        )
        omitted = field_spec_for_key("system.phase_unbalance_factor")
        self.assertEqual(nullable.blank_mode, BlankMode.NONE)
        self.assertEqual(omitted.blank_mode, BlankMode.OMIT)
