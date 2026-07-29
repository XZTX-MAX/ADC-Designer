# MVP v0.2 implementation notes

## Backward compatibility

The PMP23607 single-phase profile retains the original section names and numerical regression tests. `system.phase_count` defaults to 1 when omitted.

## Three-phase model boundary

The three-phase implementation calculates requirements and timing consistency. It does not generate SysConfig, pinmux or ADC SOC code. The ADC assignment in the example YAML is an architecture model and must be checked against the selected F29H85x package and ADC operating mode.

## Synchronous sampling interpretation

- Directly measured phase currents are expected on independent ADC modules when `simultaneous_required=true`.
- Per-channel `aperture_delay_s` is the worst-case aperture timestamp relative to the common trigger.
- Maximum skew is `max(aperture_delay)-min(aperture_delay)`.
- The tool reports fundamental-angle skew, switching-angle skew and slew-rate-induced current/voltage mismatch.
- The slew-rate bounds must come from the actual inductor, switching state and voltage model. Template values are provisional.

## Per-phase overrides

The common IAC/VAC circuit is inherited by each phase. `phase_overrides` can change Hall gain, zero level, divider values, filter values or device bandwidth per phase. The phase-matching section compares the resulting effective gains and zero codes.

## Known intentionally unresolved items

- Exact F29H85x ADC acquisition model remains fail-closed until authoritative internal capacitance/switch resistance data are entered.
- Component WC/RSS errors remain `NOT_EVALUATED` in both example profiles.
- The 22 kW three-phase profile is an engineering template, not a released product specification.

## v0.3 GB/T compliance architecture

The standard layer is deterministic and isolated from the sensing-design equations. `standard_profile` is evaluated by `compliance.py`; it neither mutates nor silently narrows `system.vac_min_rms_v`, `system.vac_max_rms_v`, channel range margins, ADC timing or control bandwidths. Compliance metrics include the applicable GB/T clause in the source field. System-level EMC, isolation and inverter requirements remain `NOT_EVALUATED` when component/system evidence is not provided.
