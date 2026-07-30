# XLSX Configuration Input Design

## 1. Goal

Add user-friendly XLSX configuration input without removing the existing YAML
workflow. Users search for stable configuration keywords in Excel, enter their
requirements, and run the existing Python validation and component-selection
calculations.

The implementation must:

- support `.yaml`, `.yml`, and `.xlsx` configuration files;
- preserve the existing nested dictionary passed to validation and calculation;
- provide one universal XLSX template for single- and three-phase designs;
- provide XLSX equivalents of the existing single-phase, three-phase, and
  standard-layer YAML files;
- locate parameters by configuration keyword rather than row number;
- reject malformed XLSX inputs with worksheet, cell, row, and keyword context;
- use English worksheet and column labels, with `Chinese Notes` as the last
  column on each data sheet.

## 2. Architecture

### 2.1 Field schema

Add `src/obc_adc_designer/config_schema.py` as the single source of truth for
scalar configuration fields. Each field specification records:

- configuration key;
- parameter name and section;
- data type;
- unit;
- required or conditionally required status;
- nullability and omission behavior;
- applicability condition;
- allowed values;
- English description;
- Chinese note.

Dynamic phase-override keys use constrained patterns such as
`channels.iac.phase_overrides.<phase>.hall.front_end_gain`. The parsed phase
name must also exist in the configured phase-name list.

The XLSX reader, strict XLSX validation, and template writer all consume this
schema so their supported fields cannot drift independently.

### 2.2 Format-specific I/O

Add `src/obc_adc_designer/xlsx_config.py` for XLSX parsing and generation.
It converts between a workbook and the same nested `dict[str, Any]` structure
currently produced by YAML.

Keep YAML-specific functions in `config.py`, and add format-dispatching
`load_config()` and `save_config()` functions. Dispatch is based only on the
case-insensitive file extension:

- `.yaml` and `.yml`: YAML;
- `.xlsx`: XLSX;
- any other extension: `ConfigError`.

The calculation layer does not import or depend on `openpyxl`.

### 2.3 Data flow

The main path is:

`YAML/XLSX -> format loader -> nested dict -> deep merge -> validate_config -> calculate_design -> report export`

`--standard` remains an optional partial configuration that overrides matching
values in `--config`. A standard layer may use either YAML or XLSX independently
of the main configuration format. Complete business validation runs after the
merge.

## 3. Workbook Format

### 3.1 Worksheets

Every generated workbook contains these English-named worksheets:

1. `Instructions`
2. `Config Parameters`
3. `Sampling Channels`
4. `Error Sources`
5. `Assumptions`
6. `Voltage Dip Tests`

`Instructions` explains the precedence, blank-value, type, list, and formula
rules. The five data sheets use frozen headers, auto filters, readable widths,
highlighted input cells, and data-validation dropdowns where applicable. The
workbook is not password protected.

### 3.2 Scalar parameters

`Config Parameters` has the following columns in this exact order:

1. `Section`
2. `Config Key`
3. `Parameter Name`
4. `Default Value`
5. `User Value`
6. `Data Type`
7. `Unit`
8. `Required`
9. `Applies When`
10. `Allowed Values`
11. `Description`
12. `Chinese Notes`

Rows are identified by the exact `Config Key`; row position is irrelevant.
Duplicate and unknown keys are errors.

Value precedence is:

1. a non-blank `User Value`;
2. otherwise a non-blank `Default Value`;
3. otherwise the field's blank-value rule.

When both value cells are blank:

- a required, non-nullable field fails validation;
- a nullable field is represented as Python `None`;
- an optional field with program-default behavior is omitted from the nested
  dictionary so existing defaults remain effective.

String lists such as phase names use comma-separated text, for example
`A,B,C`. Values are trimmed, and empty or duplicate members are rejected where
the field requires uniqueness.

The universal template leaves project-specific required values blank. It may
prepopulate only generic enum choices and non-project-specific defaults. The
separate example workbooks remain directly runnable.

### 3.3 List sheets

A completely blank list row is ignored. If any input cell in a row is filled,
all fields required for that row type must be valid; partially completed rows
are errors.

`Sampling Channels` represents `sampling.channels` with fields for channel
name, measured quantity, ADC module, SOC number, trigger source, and aperture
delay. Channel names must be unique.

`Error Sources` represents each channel's `error_sources` list with fields for
channel, source name, enabled state, base error in percent full scale, and
temperature drift in ppm per degree Celsius. The channel must be one of
`iac`, `idc`, `vac`, or `vdc`.

`Assumptions` represents the existing assumption entries with topic, value,
source type, and qualification fields.

`Voltage Dip Tests` represents
`standard_profile.voltage_dip_tests` with voltage percentage, 50 Hz duration
cycles, 60 Hz duration cycles, and functional status.

Every list sheet ends with a `Chinese Notes` column.

### 3.4 Cell rules

Input values may be text, numbers, booleans, or blank as permitted by the field
schema. Boolean parsing accepts native Excel booleans and the documented
case-insensitive text values `true` and `false`.

Formula cells are not supported. A formula in either scalar value column or a
list input column is rejected rather than relying on a possibly stale cached
Excel result.

## 4. CLI Behavior

`validate` and `calculate` accept YAML or XLSX for both `--config` and
`--standard`. Help text describes generic configuration files rather than YAML
only.

`init` defaults to:

```text
config/adc_designer_user.xlsx
```

Without `--preset`, it generates the universal template from the field schema.
With `--preset`, the preset may be YAML or XLSX. The `--output` extension
selects YAML or XLSX output, allowing YAML-to-XLSX and XLSX-to-YAML conversion.

The generated XLSX deliverables are:

- `config/adc_designer_config_template.xlsx`;
- `config/pmp23607_default.xlsx`;
- `config/pmp23607_user.xlsx`;
- `config/three_phase_22kw_template.xlsx`;
- `config/standards/gbt40432_2021.xlsx`.

Existing YAML files remain available. Windows example scripts prefer the XLSX
examples so the new path is exercised in normal use.

## 5. Error Handling

XLSX errors must identify the relevant worksheet and, when applicable, the cell
or row and configuration keyword. Example:

```text
ConfigError: [Config Parameters!E27] system.rated_power_w:
expected float, got "22kW"
```

Strict checks cover:

- missing, extra, or incorrectly named required worksheets and columns;
- duplicate, unknown, or inapplicable configuration keywords;
- formula cells;
- invalid data types, booleans, enums, and string-list syntax;
- phase overrides that do not match configured phase names;
- partially filled list rows;
- duplicate sampling channels and unknown error-source channels;
- conditional requirements and all existing business range checks.

YAML retains its existing parsing behavior and shares the final business
validation with XLSX.

## 6. Dependencies and Documentation

Add `openpyxl>=3.1` to both `requirements.txt` and `pyproject.toml`.

Update the CLI documentation, `README.md`, the existing `readme_zh.md`,
`MANIFEST.txt`, and `CHANGELOG.md` only where needed to describe XLSX input,
template usage, blank-value behavior, conversion, and backward compatibility.
Existing unrelated working-tree changes must be preserved.

The project version remains unchanged unless an existing release rule requires
otherwise.

## 7. Testing and Acceptance

Automated tests cover:

- all existing YAML regressions;
- dictionary equivalence between each existing YAML file and its XLSX
  counterpart;
- equivalent core calculation results from YAML and XLSX;
- row-order independence;
- user-value precedence and all three blank-value behaviors;
- parsing and round-tripping of all four list types;
- mixed YAML/XLSX main and standard configurations;
- `init` default generation and YAML/XLSX conversion;
- failures for duplicate or unknown keys, formulas, wrong types, wrong headers,
  invalid phase overrides, and partially filled list rows;
- generated workbook sheet names, column order, filters, frozen panes, data
  validations, and last-column `Chinese Notes`.

Acceptance requires:

1. the complete existing and new automated test suite passes;
2. CLI `validate` succeeds for the single-phase XLSX example;
3. CLI `validate` succeeds for the three-phase XLSX example;
4. CLI `validate` succeeds with an XLSX standard layer;
5. an end-to-end `calculate` run succeeds when the report-export runtime is
   available.

