# Changelog

## 0.2.0

- Added single-/three-phase system selection.
- Added three-phase line-to-line and phase-to-neutral current equations.
- Added phase-unbalance factor.
- Added per-phase IAC and VAC channel instances and per-phase overrides.
- Added two-sensor KCL reconstruction model and diagnostic.
- Added phase matching calculations for current gain, current zero code and voltage divider ratio.
- Added synchronous sampling assignments, common-trigger check, ADC-module parallelism check, aperture-skew calculation, angle-skew calculation and slew-rate error calculation.
- Added provisional 22 kW three-phase template.
- Expanded regression suite from 7 to 13 tests.
- Preserved PMP23607 single-phase regression behavior.

## 0.3.0

- Embedded a reusable GB/T 40432—2021 whole-product compliance layer.
- Added separate compliance-test voltage/frequency ranges without overwriting wider hardware design ranges.
- Added startup inrush-range, VDC/IDC error-allocation, range-margin, PF and efficiency checks.
- Added GB/T test matrix, test-instrument selection, environment, dielectric, contact-current and EMC requirement sections.
- Added bidirectional/inverter Appendix A requirements.
- Added `config/standards/gbt40432_2021.yaml` and optional CLI `--standard` merge support.
- Added standard clauses/sources to Excel metric rows.
- Expanded regression tests for standard voltage windows, dielectric-voltage rules, instrument selection and layer enable/disable behavior.
