# XLSX Configuration Input Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add strict, searchable XLSX configuration input and generation while preserving YAML compatibility and the existing calculation API.

**Architecture:** A central field registry defines every scalar configuration keyword and drives both XLSX parsing and workbook generation. A focused XLSX adapter converts six-sheet workbooks to and from the existing nested dictionary, while `config.py` dispatches by extension so validation and calculation remain format-independent.

**Tech Stack:** Python 3.11+, `openpyxl>=3.1`, PyYAML 6+, `unittest`, existing `argparse` CLI.

## Global Constraints

- Support `.yaml`, `.yml`, and `.xlsx`; reject every other configuration extension.
- Keep the existing nested `dict[str, Any]` calculation interface unchanged.
- Use English sheet names and column headers; `Chinese Notes` is the last column on every data sheet.
- Identify scalar parameters by exact `Config Key`, never by workbook row number.
- Apply scalar precedence `User Value > Default Value > blank-value rule`.
- Reject formulas rather than reading cached formula results.
- Keep existing YAML files and YAML behavior available.
- Add only `openpyxl>=3.1`; do not add pandas.
- Preserve unrelated working-tree changes in `.gitignore` and `readme_zh.md`.

---

## File Structure

New source files:

- `src/obc_adc_designer/config_schema.py`: scalar field definitions, dynamic phase-key matching, blank semantics, and schema lookup.
- `src/obc_adc_designer/xlsx_config.py`: workbook layout constants, XLSX reader/writer, cell conversion, list-sheet conversion, and workbook styling.

New tests:

- `tests/test_config_schema.py`: registry coverage and dynamic-key matching.
- `tests/test_xlsx_config.py`: scalar/list parsing, strict workbook errors, blank semantics, formulas, and workbook presentation.
- `tests/test_config_cli.py`: extension dispatch, mixed standard layers, and `init` conversion.
- `tests/test_xlsx_parity.py`: checked-in YAML/XLSX equivalence and calculation regression.

Modified source and project files:

- `src/obc_adc_designer/config.py`: add generic format dispatch while retaining `load_yaml()` and `save_yaml()`.
- `src/obc_adc_designer/cli.py`: use generic configuration I/O and generate the universal template by default.
- `requirements.txt` and `pyproject.toml`: add `openpyxl>=3.1`.
- `README.md`, `readme_zh.md`, `CHANGELOG.md`, and `MANIFEST.txt`: document XLSX input and updated test inventory.
- `run_windows.bat`, `run_three_phase_windows.bat`, and `run_gbt40432_windows.bat`: exercise XLSX examples.

Generated and checked-in workbooks:

- `config/adc_designer_config_template.xlsx`
- `config/pmp23607_default.xlsx`
- `config/pmp23607_user.xlsx`
- `config/three_phase_22kw_template.xlsx`
- `config/standards/gbt40432_2021.xlsx`

---

### Task 1: Add the Central Scalar Field Registry

**Files:**

- Create: `src/obc_adc_designer/config_schema.py`
- Create: `tests/test_config_schema.py`
- Modify: `requirements.txt:1-2`
- Modify: `pyproject.toml:11-13`

**Interfaces:**

- Produces: `FieldSpec`, `BlankMode`, `FIELD_SPECS`, `field_spec_for_key(key: str) -> FieldSpec | None`, and `template_value_for(spec: FieldSpec) -> Any`.
- Consumes: no feature-specific interfaces.

- [ ] **Step 1: Add the dependency and write failing registry tests**

Add `openpyxl>=3.1` to both dependency files. Create tests that flatten scalar
values from all current YAML fixtures while excluding the four list roots.

```python
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
```

- [ ] **Step 2: Run the registry tests and verify the import failure**

Run:

```powershell
python -m unittest tests.test_config_schema -v
```

Expected: FAIL because `obc_adc_designer.config_schema` does not exist.

- [ ] **Step 3: Implement the registry types and lookups**

Create the public schema types and distinguish required, nullable, and omitted
blank behavior explicitly.

```python
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
from typing import Any, Literal, Pattern

DataType = Literal["str", "int", "float", "bool", "list[str]"]


class BlankMode(str, Enum):
    ERROR = "error"
    NONE = "none"
    OMIT = "omit"


@dataclass(frozen=True)
class FieldSpec:
    key: str
    section: str
    name: str
    data_type: DataType
    unit: str = ""
    blank_mode: BlankMode = BlankMode.OMIT
    required_when: str = ""
    allowed_values: tuple[str, ...] = ()
    description: str = ""
    chinese_notes: str = ""
    template_default: Any = None
    pattern: Pattern[str] | None = None

    @property
    def required(self) -> bool:
        return self.blank_mode == BlankMode.ERROR

    def matches(self, key: str) -> bool:
        return key == self.key or (
            self.pattern is not None and self.pattern.fullmatch(key) is not None
        )
```

Populate `FIELD_SPECS` with every scalar and string-list key present in the four
existing YAML files, plus optional keys read by `calculators.py`,
`application.py`, and `compliance.py`. Use exact dynamic patterns for supported
IAC/VAC phase overrides. Required base fields match `validate_config()`; fields
that intentionally carry unknown engineering values use `BlankMode.NONE`;
fields with calculation defaults use `BlankMode.OMIT`.

Implement exact-key lookup first and pattern lookup second:

```python
EXACT_FIELD_SPECS = {spec.key: spec for spec in FIELD_SPECS if spec.pattern is None}
PATTERN_FIELD_SPECS = tuple(spec for spec in FIELD_SPECS if spec.pattern is not None)


def field_spec_for_key(key: str) -> FieldSpec | None:
    exact = EXACT_FIELD_SPECS.get(key)
    if exact is not None:
        return exact
    return next((spec for spec in PATTERN_FIELD_SPECS if spec.matches(key)), None)


def template_value_for(spec: FieldSpec) -> Any:
    return spec.template_default
```

- [ ] **Step 4: Run schema and existing tests**

Run:

```powershell
python -m unittest tests.test_config_schema -v
python -m unittest discover -s tests -v
```

Expected: registry coverage passes and all existing YAML tests remain green.

- [ ] **Step 5: Commit the registry**

```powershell
git add requirements.txt pyproject.toml src/obc_adc_designer/config_schema.py tests/test_config_schema.py
git commit -m "feat: define xlsx configuration schema"
```

---

### Task 2: Implement Scalar XLSX Reading and Workbook Generation

**Files:**

- Create: `src/obc_adc_designer/xlsx_config.py`
- Create: `tests/test_xlsx_config.py`

**Interfaces:**

- Consumes: `FIELD_SPECS`, `BlankMode`, `FieldSpec`, and `field_spec_for_key()` from Task 1.
- Produces: `load_xlsx(path: str | Path, *, allow_partial: bool = False) -> dict[str, Any]`, `save_xlsx(data: dict[str, Any], path: str | Path, *, template: bool = False) -> Path`, and `create_xlsx_template(path: str | Path) -> Path`.

- [ ] **Step 1: Write failing scalar round-trip and presentation tests**

Create a temporary workbook from a compact valid dictionary. Assert scalar
types, value precedence, workbook layout, and row-order independence.

```python
from __future__ import annotations

import copy
import sys
import tempfile
import unittest
from pathlib import Path

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from obc_adc_designer.config import ConfigError, load_yaml
from obc_adc_designer.xlsx_config import (
    DATA_SHEETS,
    create_xlsx_template,
    load_xlsx,
    save_xlsx,
)


class XlsxScalarConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name)
        self.cfg = load_yaml(ROOT / "config" / "pmp23607_default.yaml")

    def test_scalar_round_trip_and_layout(self) -> None:
        path = save_xlsx(self.cfg, self.root / "config.xlsx")
        loaded = load_xlsx(path)
        self.assertEqual(loaded["metadata"]["profile"], self.cfg["metadata"]["profile"])
        self.assertEqual(loaded["system"]["rated_power_w"], 2500.0)
        workbook = load_workbook(path, data_only=False)
        self.assertEqual(workbook.sheetnames, list(DATA_SHEETS))
        sheet = workbook["Config Parameters"]
        headers = [cell.value for cell in sheet[1]]
        self.assertEqual(headers[-1], "Chinese Notes")
        self.assertEqual(sheet.freeze_panes, "A2")
        self.assertIsNotNone(sheet.auto_filter.ref)

    def test_user_value_overrides_default_value(self) -> None:
        path = save_xlsx(self.cfg, self.root / "override.xlsx")
        workbook = load_workbook(path)
        sheet = workbook["Config Parameters"]
        for row in range(2, sheet.max_row + 1):
            if sheet.cell(row, 2).value == "system.rated_power_w":
                sheet.cell(row, 5).value = 3300
                break
        workbook.save(path)
        self.assertEqual(load_xlsx(path)["system"]["rated_power_w"], 3300.0)

    def test_scalar_rows_may_be_reordered(self) -> None:
        path = save_xlsx(self.cfg, self.root / "reordered.xlsx")
        workbook = load_workbook(path)
        sheet = workbook["Config Parameters"]
        first = [cell.value for cell in sheet[2]]
        last = [cell.value for cell in sheet[sheet.max_row]]
        for column, value in enumerate(last, start=1):
            sheet.cell(2, column).value = value
        for column, value in enumerate(first, start=1):
            sheet.cell(sheet.max_row, column).value = value
        workbook.save(path)
        self.assertEqual(
            load_xlsx(path)["metadata"]["profile"],
            self.cfg["metadata"]["profile"],
        )
```

- [ ] **Step 2: Run tests and verify the missing module failure**

Run:

```powershell
python -m unittest tests.test_xlsx_config.XlsxScalarConfigTest -v
```

Expected: FAIL because `xlsx_config.py` does not exist.

- [ ] **Step 3: Implement workbook constants, dotted-path helpers, and cell parsing**

Define the exact sheet and header contracts:

```python
DATA_SHEETS = (
    "Instructions",
    "Config Parameters",
    "Sampling Channels",
    "Error Sources",
    "Assumptions",
    "Voltage Dip Tests",
)

CONFIG_HEADERS = (
    "Section",
    "Config Key",
    "Parameter Name",
    "Default Value",
    "User Value",
    "Data Type",
    "Unit",
    "Required",
    "Applies When",
    "Allowed Values",
    "Description",
    "Chinese Notes",
)
```

Implement `_set_dotted()`, `_get_dotted()`, `_is_blank()`,
`_reject_formula()`, and `_parse_scalar()`. Parse `list[str]` from comma-separated
text. Enforce `allowed_values`. Raise `ConfigError` messages beginning with a
location such as `[Config Parameters!E27]`.

- [ ] **Step 4: Implement scalar workbook writing**

Use `Workbook()` and build all six sheets in the required order. For each scalar
row:

- write field metadata from `FieldSpec`;
- place values from `data` into `Default Value`;
- leave `User Value` blank;
- when `template=True`, leave project-specific required values blank and use
  only `template_default`;
- add auto filters, `freeze_panes = "A2"`, readable column widths, header
  styling, input-cell fills, and enum/boolean data validations;
- keep `Chinese Notes` last.

`create_xlsx_template(path)` calls `save_xlsx({}, path, template=True)`.

- [ ] **Step 5: Implement scalar workbook reading**

Load with `data_only=False`. Require the exact six-sheet set and exact header
tuples. For each `Config Parameters` row:

- reject a missing, duplicate, or unknown `Config Key`;
- validate that metadata columns match the registry;
- select `User Value`, then `Default Value`;
- apply `BlankMode.ERROR`, `BlankMode.NONE`, or `BlankMode.OMIT`;
- write parsed values using `_set_dotted()`;
- after all rows, validate dynamic phase names against configured
  `channels.iac.phase_names` or `channels.vac.phase_names`.

When `allow_partial=True`, absent registry rows are permitted, but rows that are
present must still pass all strict checks.

- [ ] **Step 6: Run scalar tests**

Run:

```powershell
python -m unittest tests.test_xlsx_config.XlsxScalarConfigTest -v
```

Expected: all scalar and presentation tests pass.

- [ ] **Step 7: Commit scalar XLSX support**

```powershell
git add src/obc_adc_designer/xlsx_config.py tests/test_xlsx_config.py
git commit -m "feat: read and write scalar xlsx configuration"
```

---

### Task 3: Add List Sheets and Strict Workbook Diagnostics

**Files:**

- Modify: `src/obc_adc_designer/xlsx_config.py`
- Modify: `tests/test_xlsx_config.py`

**Interfaces:**

- Consumes: `load_xlsx()` and `save_xlsx()` from Task 2.
- Produces: complete conversion for `sampling.channels`, channel
  `error_sources`, `assumptions`, and
  `standard_profile.voltage_dip_tests`.

- [ ] **Step 1: Add failing list round-trip tests**

Add a complete error source and verify all list types survive a round trip.

```python
class XlsxListConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name)

    def test_all_list_sheets_round_trip(self) -> None:
        cfg = load_yaml(ROOT / "config" / "three_phase_22kw_template.yaml")
        cfg = copy.deepcopy(cfg)
        cfg["channels"]["iac"]["error_sources"] = [
            {
                "name": "Hall gain",
                "enabled": True,
                "percent_fs": 0.1,
                "drift_ppm_per_c": 12.0,
            }
        ]
        path = save_xlsx(cfg, self.root / "lists.xlsx")
        loaded = load_xlsx(path)
        self.assertEqual(loaded["sampling"]["channels"], cfg["sampling"]["channels"])
        self.assertEqual(
            loaded["channels"]["iac"]["error_sources"],
            cfg["channels"]["iac"]["error_sources"],
        )
        self.assertEqual(loaded["assumptions"], cfg["assumptions"])
        self.assertEqual(
            loaded["standard_profile"]["voltage_dip_tests"],
            cfg["standard_profile"]["voltage_dip_tests"],
        )
```

- [ ] **Step 2: Add failing strict-error tests**

Programmatically alter generated workbooks and assert errors include sheet,
cell/row, and keyword context.

```python
    def test_duplicate_config_key_reports_location(self) -> None:
        cfg = load_yaml(ROOT / "config" / "pmp23607_default.yaml")
        path = save_xlsx(cfg, self.root / "duplicate.xlsx")
        workbook = load_workbook(path)
        sheet = workbook["Config Parameters"]
        sheet.cell(3, 2).value = sheet.cell(2, 2).value
        workbook.save(path)
        with self.assertRaisesRegex(
            ConfigError, r"Config Parameters!B3.*duplicate"
        ):
            load_xlsx(path)

    def test_formula_is_rejected(self) -> None:
        cfg = load_yaml(ROOT / "config" / "pmp23607_default.yaml")
        path = save_xlsx(cfg, self.root / "formula.xlsx")
        workbook = load_workbook(path)
        sheet = workbook["Config Parameters"]
        sheet["E2"] = "=1+1"
        workbook.save(path)
        with self.assertRaisesRegex(ConfigError, r"Config Parameters!E2.*formula"):
            load_xlsx(path)

    def test_partial_sampling_row_is_rejected(self) -> None:
        cfg = load_yaml(ROOT / "config" / "three_phase_22kw_template.yaml")
        path = save_xlsx(cfg, self.root / "partial.xlsx")
        workbook = load_workbook(path)
        sheet = workbook["Sampling Channels"]
        sheet.append(["IAC_D", "", "", "", "", "", ""])
        workbook.save(path)
        with self.assertRaisesRegex(
            ConfigError, r"Sampling Channels.*IAC_D.*required"
        ):
            load_xlsx(path)
```

Also test an unknown key, wrong data type, wrong header, unknown error channel,
duplicate sampling name, invalid enum, and a dynamic phase override for an
unconfigured phase.

- [ ] **Step 3: Run list/error tests and verify failures**

Run:

```powershell
python -m unittest tests.test_xlsx_config.XlsxListConfigTest -v
python -m unittest tests.test_xlsx_config.XlsxStrictValidationTest -v
```

Expected: FAIL because list data is not yet written/read and strict cases are
not all implemented.

- [ ] **Step 4: Implement exact list-sheet contracts**

Use these exact headers:

```python
SAMPLING_HEADERS = (
    "Name",
    "Quantity",
    "ADC Module",
    "SOC",
    "Trigger Source",
    "Aperture Delay (s)",
    "Chinese Notes",
)
ERROR_HEADERS = (
    "Channel",
    "Name",
    "Enabled",
    "Percent FS",
    "Drift (ppm/degC)",
    "Chinese Notes",
)
ASSUMPTION_HEADERS = (
    "Topic",
    "Value",
    "Source Type",
    "Qualification",
    "Chinese Notes",
)
DIP_HEADERS = (
    "Voltage Percent",
    "Duration Cycles 50Hz",
    "Duration Cycles 60Hz",
    "Functional Status",
    "Chinese Notes",
)
```

Write list entries to their corresponding sheets. Add boolean validation for
`Enabled`, channel validation for `iac,idc,vac,vdc`, and quantity validation
for `current,voltage`.

- [ ] **Step 5: Implement strict list parsing**

Ignore rows whose input columns are all blank; `Chinese Notes` does not activate
a row. Enforce:

- sampling requires `Name`, `Quantity`, `ADC Module`, and integer `SOC`;
- sampling names are unique; trigger source is optional; aperture delay is
  nullable and non-negative;
- error sources require `Channel` and `Name`; `Enabled` defaults to true,
  `Percent FS` and drift default to zero;
- error-source channel is exactly one of `iac`, `idc`, `vac`, `vdc`;
- assumptions require all four input fields;
- voltage dip rows require voltage percent, 50 Hz duration, and functional
  status; 60 Hz duration is optional;
- every formula in an input column is rejected.

Assemble the parsed rows under their current nested dictionary paths.

- [ ] **Step 6: Run all XLSX tests and existing regressions**

Run:

```powershell
python -m unittest tests.test_xlsx_config -v
python -m unittest discover -s tests -v
```

Expected: all XLSX tests and all pre-existing tests pass.

- [ ] **Step 7: Commit list parsing and diagnostics**

```powershell
git add src/obc_adc_designer/xlsx_config.py tests/test_xlsx_config.py
git commit -m "feat: validate xlsx configuration tables"
```

---

### Task 4: Add Generic Config Dispatch and CLI Conversion

**Files:**

- Modify: `src/obc_adc_designer/config.py:12-31`
- Modify: `src/obc_adc_designer/cli.py:10-97`
- Create: `tests/test_config_cli.py`

**Interfaces:**

- Consumes: `load_xlsx()`, `save_xlsx()`, and `create_xlsx_template()` from Tasks 2–3.
- Produces: `load_config(path: str | Path, *, allow_partial: bool = False) -> dict[str, Any]` and `save_config(data: dict[str, Any], path: str | Path) -> Path`.

- [ ] **Step 1: Write failing dispatch and CLI tests**

Test extension dispatch, mixed format merging, unsupported extensions, default
`init`, and YAML/XLSX conversion.

```python
from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from obc_adc_designer.cli import main
from obc_adc_designer.config import ConfigError, load_config, load_yaml


class ConfigDispatchTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name)

    def test_unsupported_extension_is_rejected(self) -> None:
        with self.assertRaisesRegex(ConfigError, "Unsupported configuration"):
            load_config(self.root / "config.csv")

    def test_init_generates_xlsx_template(self) -> None:
        output = self.root / "adc_designer_user.xlsx"
        self.assertEqual(main(["init", "--output", str(output)]), 0)
        self.assertTrue(output.exists())

    def test_yaml_to_xlsx_to_yaml_conversion(self) -> None:
        source = ROOT / "config" / "pmp23607_default.yaml"
        xlsx = self.root / "converted.xlsx"
        yaml = self.root / "converted.yaml"
        self.assertEqual(
            main(["init", "--preset", str(source), "--output", str(xlsx)]),
            0,
        )
        self.assertEqual(
            main(["init", "--preset", str(xlsx), "--output", str(yaml)]),
            0,
        )
        self.assertEqual(load_yaml(source), load_yaml(yaml))
```

Add a CLI `validate` case with an XLSX main file and YAML standard, plus the
inverse combination.

- [ ] **Step 2: Run CLI tests and verify failures**

Run:

```powershell
python -m unittest tests.test_config_cli -v
```

Expected: FAIL because `load_config()` and generic `init` do not exist.

- [ ] **Step 3: Implement format dispatch**

Keep `load_yaml()` and `save_yaml()` behavior intact. Add:

```python
def load_config(
    path: str | Path, *, allow_partial: bool = False
) -> dict[str, Any]:
    suffix = Path(path).suffix.lower()
    if suffix in {".yaml", ".yml"}:
        return load_yaml(path)
    if suffix == ".xlsx":
        from .xlsx_config import load_xlsx
        return load_xlsx(path, allow_partial=allow_partial)
    raise ConfigError(
        f"Unsupported configuration file extension: {suffix or '<none>'}. "
        "Expected .yaml, .yml, or .xlsx."
    )


def save_config(data: dict[str, Any], path: str | Path) -> Path:
    suffix = Path(path).suffix.lower()
    if suffix in {".yaml", ".yml"}:
        save_yaml(data, path)
        return Path(path)
    if suffix == ".xlsx":
        from .xlsx_config import save_xlsx
        return save_xlsx(data, path)
    raise ConfigError(
        f"Unsupported configuration file extension: {suffix or '<none>'}. "
        "Expected .yaml, .yml, or .xlsx."
    )
```

- [ ] **Step 4: Update CLI parsing and execution**

Change `init` defaults and help:

```python
init_cmd = sub.add_parser(
    "init", help="Create a user-editable configuration or convert a preset"
)
init_cmd.add_argument("--output", default="config/adc_designer_user.xlsx")
init_cmd.add_argument(
    "--preset", default=None, help="Optional YAML or XLSX preset path"
)
```

For `init` without a preset, generate a schema template. With a preset, call
`load_config(..., allow_partial=True)` and `save_config()`. For `validate` and
`calculate`, load the main file with `load_config()`, load the standard with
`allow_partial=True`, deep-merge, then call `validate_config()`.

- [ ] **Step 5: Run CLI and full tests**

Run:

```powershell
python -m unittest tests.test_config_cli -v
python -m unittest discover -s tests -v
```

Expected: dispatch/conversion tests and all existing tests pass.

- [ ] **Step 6: Commit generic configuration I/O**

```powershell
git add src/obc_adc_designer/config.py src/obc_adc_designer/cli.py tests/test_config_cli.py
git commit -m "feat: accept xlsx configuration in cli"
```

---

### Task 5: Generate Checked-In Workbooks and Prove YAML/XLSX Parity

**Files:**

- Create: `config/adc_designer_config_template.xlsx`
- Create: `config/pmp23607_default.xlsx`
- Create: `config/pmp23607_user.xlsx`
- Create: `config/three_phase_22kw_template.xlsx`
- Create: `config/standards/gbt40432_2021.xlsx`
- Create: `tests/test_xlsx_parity.py`

**Interfaces:**

- Consumes: generic `init`, `load_config()`, and existing `calculate_design()`.
- Produces: distributable template/preset workbooks and regression proof that they match YAML.

- [ ] **Step 1: Generate the universal template and four equivalents**

Run:

```powershell
python run_mvp.py init --output config/adc_designer_config_template.xlsx
python run_mvp.py init --preset config/pmp23607_default.yaml --output config/pmp23607_default.xlsx
python run_mvp.py init --preset config/pmp23607_user.yaml --output config/pmp23607_user.xlsx
python run_mvp.py init --preset config/three_phase_22kw_template.yaml --output config/three_phase_22kw_template.xlsx
python run_mvp.py init --preset config/standards/gbt40432_2021.yaml --output config/standards/gbt40432_2021.xlsx
```

Expected: five six-sheet XLSX files are created.

- [ ] **Step 2: Write failing parity and calculation tests**

```python
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from obc_adc_designer.application import calculate_design
from obc_adc_designer.config import load_config


class XlsxParityTest(unittest.TestCase):
    def test_yaml_xlsx_pairs_are_equal(self) -> None:
        pairs = (
            ("config/pmp23607_default.yaml", "config/pmp23607_default.xlsx", False),
            ("config/pmp23607_user.yaml", "config/pmp23607_user.xlsx", False),
            (
                "config/three_phase_22kw_template.yaml",
                "config/three_phase_22kw_template.xlsx",
                False,
            ),
            (
                "config/standards/gbt40432_2021.yaml",
                "config/standards/gbt40432_2021.xlsx",
                True,
            ),
        )
        for yaml_path, xlsx_path, partial in pairs:
            with self.subTest(xlsx=xlsx_path):
                self.assertEqual(
                    load_config(ROOT / yaml_path, allow_partial=partial),
                    load_config(ROOT / xlsx_path, allow_partial=partial),
                )

    def test_xlsx_calculation_matches_yaml(self) -> None:
        yaml_result = calculate_design(
            load_config(ROOT / "config/pmp23607_default.yaml")
        )
        xlsx_result = calculate_design(
            load_config(ROOT / "config/pmp23607_default.xlsx")
        )
        self.assertEqual(yaml_result.profile_name, xlsx_result.profile_name)
        self.assertEqual(
            yaml_result.sections["10_System_Rating"].metric_value("iac_rms_max_a"),
            xlsx_result.sections["10_System_Rating"].metric_value("iac_rms_max_a"),
        )
        self.assertEqual(
            yaml_result.sections["41_VDC"].metric_value("sensor_transfer_ratio"),
            xlsx_result.sections["41_VDC"].metric_value("sensor_transfer_ratio"),
        )
```

- [ ] **Step 3: Run parity tests and correct serialization differences**

Run:

```powershell
python -m unittest tests.test_xlsx_parity -v
```

Expected: all YAML/XLSX dictionaries and core calculations are equal. If Excel
normalizes an integer/float representation, correct the registry data type so
the Python values match the YAML fixture.

- [ ] **Step 4: Validate the generated XLSX configurations through the CLI**

Run:

```powershell
python run_mvp.py validate --config config/pmp23607_default.xlsx
python run_mvp.py validate --config config/three_phase_22kw_template.xlsx
python run_mvp.py validate --config config/pmp23607_user.xlsx --standard config/standards/gbt40432_2021.xlsx
```

Expected: each command prints `Configuration is valid.` and exits 0.

- [ ] **Step 5: Commit generated artifacts and parity tests**

```powershell
git add config/adc_designer_config_template.xlsx config/pmp23607_default.xlsx config/pmp23607_user.xlsx config/three_phase_22kw_template.xlsx config/standards/gbt40432_2021.xlsx tests/test_xlsx_parity.py
git commit -m "feat: add xlsx configuration templates"
```

---

### Task 6: Update User Documentation and Windows Examples

**Files:**

- Modify: `README.md:28-53`
- Modify: `README.md:114-130`
- Modify: `readme_zh.md:28-53`
- Modify: `readme_zh.md:114-130`
- Modify: `CHANGELOG.md`
- Modify: `MANIFEST.txt`
- Modify: `run_windows.bat:2`
- Modify: `run_three_phase_windows.bat:2`
- Modify: `run_gbt40432_windows.bat:2`

**Interfaces:**

- Consumes: final CLI names, workbook names, and blank semantics from Tasks 1–5.
- Produces: user-facing instructions that run exactly against the checked-in files.

- [ ] **Step 1: Write the English XLSX workflow**

Document:

- `python run_mvp.py init --output config/adc_designer_user.xlsx`;
- the six worksheets and searchable `Config Key` column;
- `User Value > Default Value`;
- required blank, nullable blank, and omitted/program-default behavior;
- no formula support;
- `validate` and `calculate` examples using XLSX;
- YAML compatibility and YAML/XLSX `--standard` mixing;
- YAML-to-XLSX and XLSX-to-YAML `init --preset` conversion.

- [ ] **Step 2: Update the Chinese README without replacing existing content**

Patch only the matching usage and standard-layer sections in `readme_zh.md`.
Explain the same behavior in Chinese while retaining the actual English sheet
and column names. Keep `Chinese Notes` as the documented final column.

- [ ] **Step 3: Update examples and release inventory**

Change the three batch files to:

```bat
python run_mvp.py calculate --config config\pmp23607_user.xlsx ...
python run_mvp.py calculate --config config\three_phase_22kw_template.xlsx ...
python run_mvp.py calculate --config config\pmp23607_user.xlsx --standard config\standards\gbt40432_2021.xlsx ...
```

Add an unreleased XLSX configuration section to `CHANGELOG.md`. Update
`MANIFEST.txt` with the five workbooks, XLSX/YAML compatibility, and the actual
test count reported by the final test run.

- [ ] **Step 4: Verify every documented command and filename**

Run:

```powershell
rg -n "pmp23607_.*\\.xlsx|three_phase_.*\\.xlsx|gbt40432_2021\\.xlsx|adc_designer_user\\.xlsx" README.md readme_zh.md run_windows.bat run_three_phase_windows.bat run_gbt40432_windows.bat MANIFEST.txt
Get-ChildItem config -Recurse -Filter *.xlsx | Select-Object FullName
```

Expected: every documented workbook exists and all three batch files use XLSX.

- [ ] **Step 5: Commit documentation and examples**

Stage only the listed documentation and batch files, including the existing
untracked `readme_zh.md` after its focused update:

```powershell
git add README.md readme_zh.md CHANGELOG.md MANIFEST.txt run_windows.bat run_three_phase_windows.bat run_gbt40432_windows.bat
git commit -m "docs: explain xlsx configuration workflow"
```

---

### Task 7: Final Verification and Handoff

**Files:**

- Verify only; modify a feature file only if a failing check identifies a defect.

**Interfaces:**

- Consumes: all interfaces and artifacts from Tasks 1–6.
- Produces: evidence that the approved design is complete.

- [ ] **Step 1: Run the complete automated suite**

Run:

```powershell
python -m unittest discover -s tests -v
```

Expected: every test passes with no errors or failures.

- [ ] **Step 2: Run all required XLSX validation paths**

Run:

```powershell
python run_mvp.py validate --config config/pmp23607_default.xlsx
python run_mvp.py validate --config config/three_phase_22kw_template.xlsx
python run_mvp.py validate --config config/pmp23607_user.yaml --standard config/standards/gbt40432_2021.xlsx
python run_mvp.py validate --config config/pmp23607_user.xlsx --standard config/standards/gbt40432_2021.yaml
```

Expected: all four commands print `Configuration is valid.` and exit 0.

- [ ] **Step 3: Attempt the end-to-end calculation path**

Run:

```powershell
python run_mvp.py calculate --config config/pmp23607_default.xlsx --output "$env:TEMP\ADC_Designer_XLSX_Verification.xlsx"
```

Expected when the report runtime is available: report creation succeeds.
Expected when it is unavailable: the command reaches report export and returns
the existing explicit `artifact_tool` runtime error; this limitation is recorded
in the handoff without weakening input-validation acceptance.

- [ ] **Step 4: Check repository scope and whitespace**

Run:

```powershell
git diff --check
git status --short
git log --oneline -8
```

Expected: no whitespace errors; only intentional feature files and the user's
pre-existing unrelated `.gitignore` change remain; task commits are visible.

- [ ] **Step 5: Report completion**

Report:

- generic YAML/XLSX input and conversion behavior;
- paths to the universal template and examples;
- complete test count and CLI validation results;
- end-to-end export result or the exact unavailable-runtime limitation;
- the preserved unrelated `.gitignore` change.
