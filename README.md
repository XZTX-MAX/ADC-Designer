# F29H85x OBC ADC Sensing Designer MVP v0.2

A deterministic Python calculator for first-stage current/voltage sensing design on single-phase and three-phase bidirectional one-stage OBC platforms.

## v0.2 scope

### Preserved single-phase support

- PMP23607/F29H85x regression profile.
- Bidirectional IAC/IDC range calculation.
- Hall, shunt/isolation-amplifier, VAC and VDC calculations.
- Analog filter, ADC acquisition, delay and WC/RSS error calculations.

### Added three-phase support

- Three-phase line-current equations:
  - line-to-line input: `P/(sqrt(3)*VLL*eta*PF)`;
  - phase-to-neutral input: `P/(3*Vphase*eta*PF)`.
- Configurable phase-unbalance design factor.
- Per-phase current and voltage channel instances with independent overrides.
- Two-current-sensor mode with explicit KCL reconstruction warning.
- Phase-channel gain/zero/divider-ratio matching calculations.
- Synchronous sampling model:
  - common ePWM trigger consistency;
  - ADC-module allocation check for directly measured phase currents;
  - sample-aperture skew;
  - line-frequency and switching-frequency angle skew;
  - `di/dt * skew` and `dv/dt * skew` error estimates.
- Three-phase Excel and JSON report output.

## Quick start

Single-phase PMP23607 regression:

```bash
python run_mvp.py validate --config config/pmp23607_default.yaml
python run_mvp.py calculate \
  --config config/pmp23607_default.yaml \
  --output results/PMP23607_ADC_Sensing_Design_v0p2.xlsx \
  --json results/PMP23607_ADC_Sensing_Design_v0p2.json
```

Three-phase template:

```bash
python run_mvp.py validate --config config/three_phase_22kw_template.yaml
python run_mvp.py calculate \
  --config config/three_phase_22kw_template.yaml \
  --output results/Three_Phase_22kW_ADC_Sensing_Design.xlsx \
  --json results/Three_Phase_22kW_ADC_Sensing_Design.json
```

The three-phase 22 kW YAML is a **provisional architecture template**, not a released PMP41186 specification. Replace voltage ranges, sensor parameters, ADC assignments, delay bounds and error sources before design release.

## Three-phase configuration blocks

```yaml
system:
  phase_count: 3
  ac_voltage_basis: line_to_line
  phase_unbalance_factor: 1.05

channels:
  iac:
    phase_names: [A, B, C]
    phase_overrides: {}
  vac:
    measurement_basis: phase_to_neutral
    phase_names: [A, B, C]
    phase_overrides: {}

sampling:
  trigger_source: EPWM1_SOCA
  trigger_position: PWM_CENTER
  simultaneous_required: true
  maximum_channel_skew_s: 1.0e-7
  channels:
    - name: IAC_A
      quantity: current
      adc_module: ADCA
      soc: 0
      aperture_delay_s: 0.0
```

## Fail-closed behavior

- Missing exact F29H85x internal ADC parameters remain `NOT_EVALUATED`.
- Missing delay/error inputs are not replaced with zero.
- Direct phase currents sharing an ADC module fail the simultaneous-sampling requirement.
- Missing per-phase sampling assignments fail validation/report checks.
- Two-current-sensor reconstruction is allowed only when explicitly configured.

## Tests

```bash
python -m unittest discover -s tests -v
```

The regression suite covers both the original PMP23607 calculations and the new three-phase formulas, per-phase channel generation, line/phase voltage conversion, matching and sampling-skew model.
