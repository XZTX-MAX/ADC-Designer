from __future__ import annotations

import math
from typing import Any, Iterable

from .config import deep_merge, get, require
from .models import Diagnostic, Metric, SectionResult, Status


def _num(data: dict[str, Any], path: str, default: float | None = None) -> float:
    value = get(data, path, default)
    if value is None:
        raise ValueError(f"Required numerical parameter is missing: {path}")
    return float(value)


def _optional_num(data: dict[str, Any], path: str) -> float | None:
    value = get(data, path)
    return None if value is None else float(value)


def _status_upper(value: float, limit: float, warn_ratio: float = 0.9) -> Status:
    if value > limit:
        return Status.FAIL
    if value > limit * warn_ratio:
        return Status.WARNING
    return Status.PASS


def _status_lower(value: float, limit: float, warn_ratio: float = 1.1) -> Status:
    if value < limit:
        return Status.FAIL
    if value < limit * warn_ratio:
        return Status.WARNING
    return Status.PASS


def _metric(
    section: SectionResult,
    key: str,
    label: str,
    value: float | int | str | None,
    unit: str = "",
    formula: str = "",
    inputs: str = "",
    source: str = "calculated",
    status: Status = Status.PASS,
    note: str = "",
) -> None:
    section.metrics.append(
        Metric(
            key=key,
            label=label,
            value=value,
            unit=unit,
            formula=formula,
            inputs=inputs,
            source=source,
            status=status,
            note=note,
        )
    )


def _diag(
    section: SectionResult,
    code: str,
    status: Status,
    message: str,
    recommendation: str = "",
) -> None:
    section.diagnostics.append(
        Diagnostic(code=code, scope=section.name, status=status, message=message, recommendation=recommendation)
    )


def calculate_system_rating(cfg: dict[str, Any]) -> SectionResult:
    section = SectionResult("10_System_Rating")
    peak_power = _num(cfg, "system.peak_power_w")
    vac_min = _num(cfg, "system.vac_min_rms_v")
    vdc_min = _num(cfg, "system.vdc_min_v")
    efficiency = _num(cfg, "system.efficiency_min")
    pf = _num(cfg, "system.power_factor_min")
    overload = _num(cfg, "system.overload_factor", 1.0)
    default_margin = _num(cfg, "system.default_range_margin", 1.2)
    iac_margin = _num(cfg, "channels.iac.range_margin", default_margin)
    idc_margin = _num(cfg, "channels.idc.range_margin", default_margin)
    phase_count = int(get(cfg, "system.phase_count", 1))
    voltage_basis = str(get(cfg, "system.ac_voltage_basis", "single_phase" if phase_count == 1 else "line_to_line"))
    unbalance = _num(cfg, "system.phase_unbalance_factor", 1.0) if phase_count == 3 else 1.0

    if phase_count == 1:
        iac_rms = peak_power / (vac_min * efficiency * pf)
        current_formula = "Ppeak/(Vac_min*eta*PF)"
    elif voltage_basis == "line_to_line":
        iac_rms = peak_power / (math.sqrt(3.0) * vac_min * efficiency * pf) * unbalance
        current_formula = "Ppeak/(sqrt(3)*VLL_min*eta*PF)*Kunbalance"
    else:
        iac_rms = peak_power / (3.0 * vac_min * efficiency * pf) * unbalance
        current_formula = "Ppeak/(3*Vphase_min*eta*PF)*Kunbalance"

    iac_peak = math.sqrt(2.0) * iac_rms
    iac_design = iac_peak * overload * iac_margin
    idc_cont = peak_power / (vdc_min * efficiency)
    idc_design = idc_cont * overload * idc_margin

    _metric(section, "phase_count", "AC phase count", phase_count, "phase", source="configuration")
    _metric(section, "ac_voltage_basis", "AC voltage basis", voltage_basis, source="configuration")
    _metric(section, "phase_unbalance_factor", "Phase unbalance design factor", unbalance, "pu", source="configuration")
    _metric(section, "iac_rms_max_a", "Maximum per-line/per-phase AC RMS current", iac_rms, "A", current_formula, f"{peak_power=}, {vac_min=}, {efficiency=}, {pf=}, {unbalance=}")
    _metric(section, "iac_peak_a", "Maximum per-phase AC peak current", iac_peak, "A", "sqrt(2)*Iac_rms")
    _metric(section, "iac_design_peak_a", "Bidirectional per-phase IAC design peak", iac_design, "A", "Iac_peak*Koverload*Kmargin", f"{overload=}, {iac_margin=}")
    _metric(section, "idc_continuous_max_a", "Maximum DC continuous current", idc_cont, "A", "Ppeak/(Vdc_min*eta)")
    _metric(section, "idc_design_peak_a", "Bidirectional IDC design peak", idc_design, "A", "Idc_cont*Koverload*Kmargin", f"{overload=}, {idc_margin=}")

    if phase_count == 3:
        _metric(section, "three_phase_apparent_power_va", "Three-phase apparent power at minimum input", math.sqrt(3.0) * vac_min * iac_rms if voltage_basis == "line_to_line" else 3.0 * vac_min * iac_rms, "VA", "sqrt(3)*VLL*Iline or 3*Vphase*Iphase")
    if not bool(get(cfg, "system.bidirectional", True)):
        _diag(section, "SYS_DIRECTION", Status.WARNING, "The configuration is not marked bidirectional.", "Set system.bidirectional=true for a bidirectional OBC design.")
    return section


def analog_filter_metrics(
    *,
    section_name: str,
    resistor_ohm: float,
    capacitor_f: float,
    loop_bw_hz: float,
    switching_hz: float,
    phase_limit_deg: float,
    bandwidth_multiplier: float,
    sensor_bandwidth_hz: float | None = None,
) -> SectionResult:
    section = SectionResult(section_name)
    fc_rc = 1.0 / (2.0 * math.pi * resistor_ohm * capacitor_f)
    fc_effective = min(fc_rc, sensor_bandwidth_hz) if sensor_bandwidth_hz else fc_rc
    phase_deg = math.degrees(math.atan(loop_bw_hz / fc_effective))
    gain = 1.0 / math.sqrt(1.0 + (loop_bw_hz / fc_effective) ** 2)
    attenuation_sw_db = -10.0 * math.log10(1.0 + (switching_hz / fc_effective) ** 2)
    min_fc_by_multiplier = bandwidth_multiplier * loop_bw_hz
    min_fc_by_phase = loop_bw_hz / math.tan(math.radians(phase_limit_deg))
    required_fc = max(min_fc_by_multiplier, min_fc_by_phase)

    phase_status = _status_upper(phase_deg, phase_limit_deg)
    bw_status = _status_lower(fc_effective, required_fc)
    _metric(section, "rc_cutoff_hz", "RC cutoff frequency", fc_rc, "Hz", "1/(2*pi*R*C)")
    _metric(section, "effective_bandwidth_hz", "Effective analog bandwidth", fc_effective, "Hz", "min(RC cutoff, sensor bandwidth)", status=bw_status)
    _metric(section, "required_bandwidth_hz", "Minimum required bandwidth", required_fc, "Hz", "max(Kbw*floop, floop/tan(phi_budget))")
    _metric(section, "loop_gain_ratio", "Magnitude at loop crossover", gain, "pu", "1/sqrt(1+(floop/fc)^2)")
    _metric(section, "loop_phase_loss_deg", "Analog phase loss at crossover", phase_deg, "deg", "atan(floop/fc)", status=phase_status)
    _metric(section, "switching_attenuation_db", "Attenuation at switching frequency", attenuation_sw_db, "dB", "-10*log10(1+(fsw/fc)^2)")

    if phase_status == Status.FAIL:
        _diag(section, "AFE_PHASE", Status.FAIL, f"Analog phase loss {phase_deg:.2f}° exceeds {phase_limit_deg:.2f}°.", "Increase analog bandwidth or lower loop crossover frequency.")
    elif bw_status == Status.FAIL:
        _diag(section, "AFE_BW", Status.FAIL, f"Effective bandwidth {fc_effective:.1f} Hz is below required {required_fc:.1f} Hz.", "Increase sensor/RC bandwidth.")
    elif attenuation_sw_db > -20:
        _diag(section, "AFE_SWITCH_RIPPLE", Status.WARNING, f"Single-pole attenuation at switching frequency is only {attenuation_sw_db:.1f} dB.", "Use PWM-synchronous sampling and/or a higher-order/digital filter; do not reduce bandwidth blindly.")
    return section


def calculate_iac_hall(cfg: dict[str, Any], iac_design_a: float) -> SectionResult:
    section = SectionResult("20_IAC_Hall")
    adc_vref = _num(cfg, "adc.reference_voltage_v")
    adc_codes = 2 ** int(_num(cfg, "adc.resolution_bits"))
    raw_zero_v = _num(cfg, "channels.iac.hall.sensor_zero_output_v")
    raw_sens = _num(cfg, "channels.iac.hall.sensor_sensitivity_v_per_a")
    gain = _num(cfg, "channels.iac.hall.front_end_gain")
    low_headroom = _num(cfg, "channels.iac.adc_headroom_low_v", 0.2)
    high_headroom = _num(cfg, "channels.iac.adc_headroom_high_v", 0.2)
    vmin_allowed = low_headroom
    vmax_allowed = adc_vref - high_headroom
    zero_adc = raw_zero_v * gain
    sens_eff = raw_sens * gain
    span = iac_design_a * sens_eff
    vmin = zero_adc - span
    vmax = zero_adc + span
    vlsb = adc_vref / adc_codes
    a_per_code = vlsb / sens_eff
    code_zero = zero_adc / vlsb
    code_min = vmin / vlsb
    code_max = vmax / vlsb
    utilization = (vmax - vmin) / adc_vref
    maximum_sensitivity = min((zero_adc - vmin_allowed) / iac_design_a, (vmax_allowed - zero_adc) / iac_design_a)
    required_gain_max = maximum_sensitivity / raw_sens

    range_status = Status.PASS if vmin >= vmin_allowed and vmax <= vmax_allowed else Status.FAIL
    util_status = Status.WARNING if utilization < 0.40 else Status.PASS
    _metric(section, "design_current_a", "Required bidirectional peak current", iac_design_a, "A")
    _metric(section, "effective_sensitivity_v_per_a", "Effective ADC sensitivity", sens_eff, "V/A", "Sensor sensitivity*front-end gain")
    _metric(section, "maximum_sensitivity_v_per_a", "Maximum permissible ADC sensitivity", maximum_sensitivity, "V/A", "min((Vzero-Vmin)/Imax,(Vmax-Vzero)/Imax)")
    _metric(section, "maximum_front_end_gain", "Maximum permissible front-end gain", required_gain_max, "V/V", "Seff_max/Ssensor")
    _metric(section, "zero_adc_v", "ADC zero-current voltage", zero_adc, "V")
    _metric(section, "zero_adc_code", "ADC zero-current code", code_zero, "code")
    _metric(section, "adc_min_v", "ADC voltage at negative design current", vmin, "V", status=range_status)
    _metric(section, "adc_max_v", "ADC voltage at positive design current", vmax, "V", status=range_status)
    _metric(section, "adc_min_code", "ADC code at negative design current", code_min, "code")
    _metric(section, "adc_max_code", "ADC code at positive design current", code_max, "code")
    _metric(section, "current_per_code_a", "Current resolution", a_per_code, "A/code", "Vlsb/Seff")
    _metric(section, "adc_utilization", "ADC span utilization", utilization, "pu", "(Vmax-Vmin)/Vref", status=util_status)

    if range_status == Status.FAIL:
        _diag(section, "IAC_RANGE", Status.FAIL, "IAC Hall output exceeds the configured ADC headroom.", "Reduce front-end gain/sensor sensitivity or increase current range.")
    if utilization < 0.40:
        _diag(section, "IAC_UTIL", Status.WARNING, f"Only {utilization*100:.1f}% of ADC full scale is used at the PMP23607 design current.", "This is acceptable for overload headroom but degrades light-load effective resolution; verify zero-offset and noise performance.")
    return section


def calculate_idc_shunt(cfg: dict[str, Any], idc_design_a: float, idc_cont_a: float) -> SectionResult:
    section = SectionResult("30_IDC_Shunt")
    adc_vref = _num(cfg, "adc.reference_voltage_v")
    adc_codes = 2 ** int(_num(cfg, "adc.resolution_bits"))
    shunt = _num(cfg, "channels.idc.shunt.resistance_ohm")
    clip = _num(cfg, "channels.idc.amplifier.input_clip_v")
    ref = _num(cfg, "channels.idc.amplifier.reference_voltage_v")
    input_use = _num(cfg, "channels.idc.amplifier.input_range_utilization", 0.8)
    low_headroom = _num(cfg, "channels.idc.adc_headroom_low_v", 0.2)
    high_headroom = _num(cfg, "channels.idc.adc_headroom_high_v", 0.2)
    amplifier_offset_v = _optional_num(cfg, "channels.idc.amplifier.input_offset_v")

    amp_gain_per_input = ref / (2.0 * clip)
    zero = ref / 2.0
    effective_sens = shunt * amp_gain_per_input
    vspan = idc_design_a * effective_sens
    vmin = zero - vspan
    vmax = zero + vspan
    allowable_span = min(zero - low_headroom, adc_vref - high_headroom - zero)
    max_shunt_by_adc = allowable_span / (idc_design_a * amp_gain_per_input)
    max_shunt_by_input = clip * input_use / idc_design_a
    recommended_max = min(max_shunt_by_adc, max_shunt_by_input)
    continuous_power = idc_cont_a**2 * shunt
    peak_power = idc_design_a**2 * shunt
    vlsb = adc_vref / adc_codes
    a_per_code = vlsb / effective_sens
    utilization = (vmax - vmin) / adc_vref
    range_status = Status.PASS if shunt <= recommended_max and vmin >= low_headroom and vmax <= adc_vref - high_headroom else Status.FAIL

    _metric(section, "actual_shunt_ohm", "Configured shunt resistance", shunt, "ohm")
    _metric(section, "max_shunt_adc_ohm", "Maximum shunt from ADC swing", max_shunt_by_adc, "ohm")
    _metric(section, "max_shunt_input_ohm", "Maximum shunt from amplifier input", max_shunt_by_input, "ohm")
    _metric(section, "recommended_shunt_max_ohm", "Recommended maximum shunt", recommended_max, "ohm", "min(R_adc,R_input)", status=range_status)
    _metric(section, "effective_sensitivity_v_per_a", "Effective ADC sensitivity", effective_sens, "V/A", "Rshunt*Vref/(2*Vclip)")
    _metric(section, "zero_adc_v", "Zero-current ADC voltage", zero, "V")
    _metric(section, "adc_min_v", "ADC voltage at negative design current", vmin, "V", status=range_status)
    _metric(section, "adc_max_v", "ADC voltage at positive design current", vmax, "V", status=range_status)
    _metric(section, "current_per_code_a", "Current resolution", a_per_code, "A/code", "Vlsb/Seff")
    _metric(section, "adc_utilization", "ADC span utilization", utilization, "pu")
    _metric(section, "continuous_shunt_power_w", "Continuous shunt loss", continuous_power, "W", "Irms^2*R")
    _metric(section, "peak_shunt_power_w", "Peak shunt loss", peak_power, "W", "Ipeak^2*R")

    if amplifier_offset_v is None:
        _metric(section, "equivalent_offset_current_a", "Equivalent input offset current", None, "A", "Vos/Rshunt", source="missing input", status=Status.NOT_EVALUATED, note="Enter channels.idc.amplifier.input_offset_v.")
        _diag(section, "IDC_OFFSET_UNKNOWN", Status.NOT_EVALUATED, "IDC amplifier input offset is not configured.", "Enter the exact device maximum offset before design release.")
    else:
        i_offset = amplifier_offset_v / shunt
        _metric(section, "equivalent_offset_current_a", "Equivalent input offset current", i_offset, "A", "Vos/Rshunt")

    if range_status == Status.FAIL:
        _diag(section, "IDC_RANGE", Status.FAIL, "Configured shunt or amplifier output violates the design range/headroom.", "Reduce shunt value or change amplifier input range/output scaling.")
    if utilization < 0.25:
        _diag(section, "IDC_UTIL", Status.WARNING, f"IDC uses only {utilization*100:.1f}% of ADC full scale at calculated rated power.", "Confirm whether the channel is intentionally sized for a higher DCDC current or fault range.")
    return section


def calculate_vac(cfg: dict[str, Any]) -> SectionResult:
    section = SectionResult("40_VAC")
    vac_max_rms = _num(cfg, "system.vac_max_rms_v")
    margin = _num(cfg, "channels.vac.range_margin", _num(cfg, "system.default_range_margin", 1.2))
    rtop = _num(cfg, "channels.vac.divider.high_side_total_ohm")
    rbottom = _num(cfg, "channels.vac.divider.low_side_ohm")
    iso_gain = _num(cfg, "channels.vac.isolation.gain_v_per_v", 1.0)
    ref = _num(cfg, "channels.vac.isolation.reference_voltage_v")
    linear_input = _num(cfg, "channels.vac.isolation.linear_input_abs_max_v")
    target_use = _num(cfg, "channels.vac.isolation.input_range_utilization", 0.9)
    adc_vref = _num(cfg, "adc.reference_voltage_v")
    adc_codes = 2 ** int(_num(cfg, "adc.resolution_bits"))
    vdesign = vac_max_rms * math.sqrt(2.0) * margin
    ratio = rbottom / (rtop + rbottom)
    input_peak = vdesign * ratio
    output_min = ref - input_peak * iso_gain
    output_max = ref + input_peak * iso_gain
    target_input = linear_input * target_use
    recommended_rtop = rbottom * (vdesign / target_input - 1.0)
    vlsb = adc_vref / adc_codes
    vac_per_code = vlsb / (ratio * iso_gain)
    linear_status = _status_upper(input_peak, linear_input)
    adc_status = Status.PASS if output_min >= 0 and output_max <= adc_vref else Status.FAIL
    total_status = Status.FAIL if Status.FAIL in (linear_status, adc_status) else Status.PASS

    _metric(section, "vac_design_peak_v", "VAC design peak including margin", vdesign, "V", "Vac_rms_max*sqrt(2)*Kmargin")
    _metric(section, "divider_ratio", "Configured divider ratio", ratio, "V/V", "Rbottom/(Rtop+Rbottom)")
    _metric(section, "isolation_input_peak_v", "Isolation amplifier input peak", input_peak, "V", "Vdesign*Kdivider", status=linear_status)
    _metric(section, "isolation_linear_limit_v", "Isolation amplifier linear input limit", linear_input, "V")
    _metric(section, "recommended_high_side_ohm", "Required high-side resistance", recommended_rtop, "ohm", "Rbottom*(Vdesign/Vtarget-1)", status=total_status)
    _metric(section, "adc_output_min_v", "ADC minimum voltage", output_min, "V", status=adc_status)
    _metric(section, "adc_output_max_v", "ADC maximum voltage", output_max, "V", status=adc_status)
    _metric(section, "vac_per_code_v", "VAC resolution", vac_per_code, "V/code", "Vlsb/(Kdivider*Gain)")

    if linear_status == Status.FAIL:
        _diag(section, "VAC_LINEAR_RANGE", Status.FAIL, f"VAC divider drives the isolation input to {input_peak:.3f} V, beyond the ±{linear_input:.3f} V linear range.", "Increase high-side resistance/reduce divider ratio. Hardware redesign is required; software calibration cannot restore clipped data.")
    if adc_status == Status.FAIL:
        _diag(section, "VAC_ADC_RANGE", Status.FAIL, "VAC isolation output exceeds ADC range.", "Adjust divider ratio, reference voltage or output gain.")
    return section


def calculate_vdc(cfg: dict[str, Any]) -> SectionResult:
    section = SectionResult("41_VDC")
    architecture = str(get(cfg, "channels.vdc.architecture", "direct_hv"))
    vdc_max = _num(cfg, "system.vdc_max_v")
    margin = _num(cfg, "channels.vdc.range_margin", _num(cfg, "system.default_range_margin", 1.2))
    vdesign = vdc_max * margin
    adc_vref = _num(cfg, "adc.reference_voltage_v")
    adc_codes = 2 ** int(_num(cfg, "adc.resolution_bits"))
    vlsb = adc_vref / adc_codes

    _metric(section, "vdc_design_max_v", "VDC design maximum including margin", vdesign, "V", "Vdc_max*Kmargin")
    _metric(section, "architecture", "Sensing architecture", architecture)

    if architecture == "direct_hv":
        clip = _num(cfg, "channels.vdc.direct_hv.high_voltage_clip_v")
        reference = _num(cfg, "channels.vdc.direct_hv.reference_voltage_v")
        ratio = reference / clip
        output = vdesign * ratio
        maximum_measurable = adc_vref / ratio
        per_code = vlsb / ratio
        utilization = output / adc_vref
        status = _status_upper(output, adc_vref)
        _metric(section, "sensor_transfer_ratio", "Direct-HV sensor transfer ratio", ratio, "V/V", "Vref/Vclip")
        _metric(section, "adc_voltage_at_design_max", "ADC voltage at VDC design maximum", output, "V", status=status)
        _metric(section, "maximum_measurable_vdc_v", "Maximum measurable VDC before ADC full scale", maximum_measurable, "V", "Vadc_fs/Ksensor")
        _metric(section, "vdc_per_code_v", "VDC resolution", per_code, "V/code", "Vlsb/Ksensor")
        _metric(section, "adc_utilization", "ADC utilization at VDC design maximum", utilization, "pu")
        if status == Status.FAIL:
            _diag(section, "VDC_RANGE", Status.FAIL, "Direct-HV sensor output exceeds ADC full scale.", "Use a higher-range sensor variant or add attenuation.")
        elif utilization < 0.40:
            _diag(section, "VDC_UTIL", Status.WARNING, f"VDC uses only {utilization*100:.1f}% of ADC full scale.", "Confirm whether the high-voltage range is required for DCDC/fault operation; otherwise select a lower clip-voltage variant.")
    elif architecture == "divider":
        rbottom = _num(cfg, "channels.vdc.divider.low_side_ohm")
        target = _num(cfg, "channels.vdc.divider.target_sense_v")
        rtop = rbottom * (vdesign / target - 1.0)
        ratio = rbottom / (rtop + rbottom)
        _metric(section, "required_high_side_ohm", "Required high-side resistance", rtop, "ohm")
        _metric(section, "divider_ratio", "Required divider ratio", ratio, "V/V")
        _metric(section, "vdc_per_code_v", "VDC resolution", vlsb / ratio, "V/code")
    else:
        _diag(section, "VDC_ARCH", Status.FAIL, f"Unsupported VDC architecture: {architecture}", "Use direct_hv or divider.")
    return section


def calculate_adc_timing(cfg: dict[str, Any]) -> SectionResult:
    section = SectionResult("50_ADC_Timing")
    nbits = int(_num(cfg, "adc.resolution_bits"))
    vref = _num(cfg, "adc.reference_voltage_v")
    sysclk = _num(cfg, "adc.sysclk_hz")
    configured_cycles = int(_num(cfg, "adc.existing_sample_window_cycles", 20))
    current_window_s = configured_cycles / sysclk
    target_lsb = _num(cfg, "adc.acquisition.target_error_lsb", 0.5)
    safety = _num(cfg, "adc.acquisition.safety_factor", 1.5)
    vlsb = vref / (2**nbits)

    _metric(section, "adc_lsb_v", "ADC voltage LSB", vlsb, "V/code", "Vref/2^N")
    _metric(section, "configured_sample_cycles", "Configured sample window", configured_cycles, "SYSCLK")
    _metric(section, "configured_sample_time_s", "Configured sample time", current_window_s, "s", "cycles/fsysclk")

    total_c = _optional_num(cfg, "adc.acquisition.simplified_total_capacitance_f")
    source_r = _optional_num(cfg, "adc.acquisition.simplified_source_resistance_ohm")
    if total_c is None or source_r is None:
        _metric(section, "simplified_required_time_s", "Simplified required acquisition time", None, "s", source="missing input", status=Status.NOT_EVALUATED)
        _diag(section, "ADC_SIMPLE_MISSING", Status.NOT_EVALUATED, "Simplified ADC acquisition inputs are incomplete.", "Set simplified source resistance and total capacitance.")
    else:
        epsilon = target_lsb / (2**nbits)
        tau = source_r * total_c
        required = -tau * math.log(epsilon)
        recommended = required * safety
        cycles = math.ceil(recommended * sysclk)
        status = _status_lower(current_window_s, recommended)
        _metric(section, "simplified_tau_s", "Simplified RC time constant", tau, "s", "Rsource*Ctotal")
        _metric(section, "simplified_required_time_s", "Simplified required acquisition time", required, "s", "-tau*ln(target_lsb/2^N)")
        _metric(section, "simplified_recommended_time_s", "Simplified recommended acquisition time", recommended, "s", "treq*Ksafety")
        _metric(section, "simplified_recommended_cycles", "Simplified recommended sample window", cycles, "SYSCLK", "ceil(trec*fsysclk)", status=status)
        if status == Status.FAIL:
            _diag(section, "ADC_WINDOW_SIMPLE", Status.FAIL, f"Configured {configured_cycles} cycles are below simplified recommendation {cycles} cycles.", "Increase sampleWindow or reduce source impedance.")

    ch = _optional_num(cfg, "adc.acquisition.exact_sample_capacitance_f")
    ron = _optional_num(cfg, "adc.acquisition.exact_switch_resistance_ohm")
    exact_source = _optional_num(cfg, "adc.acquisition.exact_source_resistance_ohm")
    if ch is None or ron is None or exact_source is None:
        _metric(section, "exact_recommended_cycles", "Exact-model recommended sample window", None, "SYSCLK", source="missing device parameters", status=Status.NOT_EVALUATED, note="Enter F29H85x sample capacitor and switch resistance from the applicable data sheet/model.")
        _diag(section, "ADC_EXACT_MISSING", Status.NOT_EVALUATED, "Exact ADC acquisition model is not evaluated because MCU internal parameters are not provided.", "Populate exact_sample_capacitance_f, exact_switch_resistance_ohm and exact_source_resistance_ohm.")
    else:
        epsilon = target_lsb / (2**nbits)
        tau = (ron + exact_source) * ch
        required = -tau * math.log(epsilon)
        recommended = max(required * safety, _num(cfg, "adc.minimum_sample_window_s", 0.0))
        cycles = math.ceil(recommended * sysclk)
        status = _status_lower(current_window_s, recommended)
        _metric(section, "exact_tau_s", "Exact-model ADC time constant", tau, "s", "(Rsource+Ron)*Ch")
        _metric(section, "exact_required_time_s", "Exact-model required acquisition time", required, "s")
        _metric(section, "exact_recommended_cycles", "Exact-model recommended sample window", cycles, "SYSCLK", status=status)
    return section


def calculate_delay_budget(cfg: dict[str, Any], channel: str, loop_bw_hz: float, phase_limit_deg: float) -> SectionResult:
    section = SectionResult(f"55_{channel.upper()}_Delay")
    delays = {
        "sensor": _optional_num(cfg, f"channels.{channel}.delay.sensor_s"),
        "isolation": _optional_num(cfg, f"channels.{channel}.delay.isolation_s"),
        "adc": _optional_num(cfg, f"channels.{channel}.delay.adc_s"),
        "isr": _optional_num(cfg, f"channels.{channel}.delay.isr_s"),
        "pwm": _optional_num(cfg, f"channels.{channel}.delay.pwm_s"),
    }
    missing = [key for key, value in delays.items() if value is None]
    known_total = sum(value for value in delays.values() if value is not None)
    phase = 360.0 * loop_bw_hz * known_total
    status = _status_upper(phase, phase_limit_deg) if not missing else Status.NOT_EVALUATED
    for key, value in delays.items():
        _metric(section, f"{key}_delay_s", f"{key.title()} delay", value, "s", status=Status.NOT_EVALUATED if value is None else Status.PASS)
    _metric(section, "known_delay_total_s", "Known pure-delay total", known_total, "s", "sum(known delays)")
    _metric(section, "known_delay_phase_deg", "Known pure-delay phase loss", phase, "deg", "360*floop*Tdelay", status=status)
    if missing:
        _diag(section, f"{channel.upper()}_DELAY_MISSING", Status.NOT_EVALUATED, f"Delay budget is incomplete; missing: {', '.join(missing)}.", "Enter worst-case propagation/compute/PWM update delays before closing loop stability analysis.")
    elif phase > phase_limit_deg:
        _diag(section, f"{channel.upper()}_DELAY", Status.FAIL, f"Pure-delay phase loss {phase:.2f}° exceeds budget {phase_limit_deg:.2f}°.", "Reduce delay or loop bandwidth.")
    return section


def calculate_error_budget(cfg: dict[str, Any], channel: str) -> SectionResult:
    section = SectionResult(f"60_{channel.upper()}_Error")
    sources = get(cfg, f"channels.{channel}.error_sources", [])
    if not sources:
        _metric(section, "wc_percent_fs", "Worst-case total error", None, "%FS", status=Status.NOT_EVALUATED, source="missing error sources")
        _metric(section, "rss_percent_fs", "RSS total error", None, "%FS", status=Status.NOT_EVALUATED, source="missing error sources")
        _diag(section, f"{channel.upper()}_ERROR_MISSING", Status.NOT_EVALUATED, "No channel error-source data are configured.", "Enter exact device maximum gain/offset/drift/ADC/VREF errors before design release.")
        return section

    delta_t = _num(cfg, "environment.temperature_span_c", 165.0)
    contributions: list[tuple[str, float]] = []
    for source in sources:
        if not bool(source.get("enabled", True)):
            continue
        base = abs(float(source.get("percent_fs", 0.0)))
        drift = abs(float(source.get("drift_ppm_per_c", 0.0))) * delta_t / 10000.0
        total = base + drift
        contributions.append((str(source.get("name", "unnamed")), total))
        _metric(section, f"source_{len(contributions)}", str(source.get("name", "unnamed")), total, "%FS", "base + drift_ppm*DeltaT/10000")
    wc = sum(value for _, value in contributions)
    rss = math.sqrt(sum(value * value for _, value in contributions))
    target = _num(cfg, f"channels.{channel}.accuracy_target_percent_fs", 0.5)
    wc_status = _status_upper(wc, target)
    rss_status = _status_upper(rss, target)
    _metric(section, "wc_percent_fs", "Worst-case total error", wc, "%FS", "sum(abs(Ei))", status=wc_status)
    _metric(section, "rss_percent_fs", "RSS total error", rss, "%FS", "sqrt(sum(Ei^2))", status=rss_status)
    if wc_status == Status.FAIL:
        _diag(section, f"{channel.upper()}_ERROR_WC", Status.FAIL, f"Worst-case error {wc:.3f}%FS exceeds target {target:.3f}%FS.", "Reduce dominant error sources or add calibration/temperature compensation.")
    dominant = sorted(contributions, key=lambda item: item[1], reverse=True)[:3]
    _metric(section, "dominant_sources", "Dominant error sources", "; ".join(f"{name}: {value:.3f}%" for name, value in dominant))
    return section


def _phase_channel_config(cfg: dict[str, Any], channel: str, label: str) -> dict[str, Any]:
    base = get(cfg, f"channels.{channel}", {})
    overrides = get(cfg, f"channels.{channel}.phase_overrides.{label}", {})
    if not isinstance(base, dict):
        raise ValueError(f"channels.{channel} must be a mapping")
    if not isinstance(overrides, dict):
        raise ValueError(f"channels.{channel}.phase_overrides.{label} must be a mapping")
    return deep_merge(base, overrides)


def _cfg_with_channel_override(cfg: dict[str, Any], channel: str, channel_cfg: dict[str, Any]) -> dict[str, Any]:
    merged = deep_merge(cfg, {})
    merged.setdefault("channels", {})[channel] = channel_cfg
    return merged


def calculate_iac_hall_phase(cfg: dict[str, Any], phase: str, iac_design_a: float) -> SectionResult:
    phase_cfg = _phase_channel_config(cfg, "iac", phase)
    local_cfg = _cfg_with_channel_override(cfg, "iac", phase_cfg)
    section = calculate_iac_hall(local_cfg, iac_design_a)
    section.name = f"20_IAC_{phase}"
    for diagnostic in section.diagnostics:
        object.__setattr__(diagnostic, "scope", section.name)
    return section


def _vac_measurement_rms(cfg: dict[str, Any]) -> float:
    system_basis = str(get(cfg, "system.ac_voltage_basis", "line_to_line"))
    measurement_basis = str(get(cfg, "channels.vac.measurement_basis", "phase_to_neutral"))
    vac_max = _num(cfg, "system.vac_max_rms_v")
    if int(get(cfg, "system.phase_count", 1)) == 1:
        return vac_max
    if system_basis == measurement_basis:
        return vac_max
    if system_basis == "line_to_line" and measurement_basis == "phase_to_neutral":
        return vac_max / math.sqrt(3.0)
    if system_basis == "phase_to_neutral" and measurement_basis == "line_to_line":
        return vac_max * math.sqrt(3.0)
    raise ValueError(f"Unsupported AC voltage-basis conversion: {system_basis} -> {measurement_basis}")


def calculate_vac_phase(cfg: dict[str, Any], phase: str) -> SectionResult:
    phase_cfg = _phase_channel_config(cfg, "vac", phase)
    local_cfg = _cfg_with_channel_override(cfg, "vac", phase_cfg)
    local_cfg = deep_merge(local_cfg, {})
    local_cfg["system"]["vac_max_rms_v"] = _vac_measurement_rms(cfg)
    section = calculate_vac(local_cfg)
    section.name = f"40_VAC_{phase}"
    for diagnostic in section.diagnostics:
        object.__setattr__(diagnostic, "scope", section.name)
    _metric(section, "measurement_basis", "Voltage measurement basis", str(get(cfg, "channels.vac.measurement_basis", "phase_to_neutral")), source="configuration")
    return section


def calculate_phase_channel_plan(cfg: dict[str, Any]) -> SectionResult:
    section = SectionResult("15_Phase_Channels")
    phase_count = int(get(cfg, "system.phase_count", 1))
    if phase_count == 1:
        _metric(section, "phase_mode", "Phase-channel model", "single_phase")
        return section

    current_names = [str(x) for x in get(cfg, "channels.iac.phase_names", ["A", "B", "C"])]
    voltage_basis = str(get(cfg, "channels.vac.measurement_basis", "phase_to_neutral"))
    voltage_default = ["A", "B", "C"] if voltage_basis == "phase_to_neutral" else ["AB", "BC", "CA"]
    voltage_names = [str(x) for x in get(cfg, "channels.vac.phase_names", voltage_default)]
    reconstruction = str(get(cfg, "channels.iac.reconstruction", "none"))

    _metric(section, "current_phase_channels", "Configured phase-current channels", ", ".join(current_names), source="configuration")
    _metric(section, "voltage_phase_channels", "Configured phase-voltage channels", ", ".join(voltage_names), source="configuration")
    _metric(section, "voltage_measurement_basis", "Phase-voltage measurement basis", voltage_basis, source="configuration")
    _metric(section, "current_reconstruction", "Current reconstruction mode", reconstruction, source="configuration")
    _metric(section, "physical_current_sensor_count", "Physical current-sensor count", len(current_names), "channel")
    _metric(section, "physical_voltage_sensor_count", "Physical voltage-sensor count", len(voltage_names), "channel")

    if len(current_names) == 2:
        if reconstruction not in ("third_phase_from_kcl", "ic_equals_minus_ia_minus_ib"):
            _diag(section, "PHASE_CURRENT_RECONSTRUCTION", Status.FAIL, "Only two phase-current channels are configured without an explicit third-phase reconstruction rule.", "Set channels.iac.reconstruction=third_phase_from_kcl or add the third current sensor.")
        else:
            _metric(section, "reconstructed_current_formula", "Third-phase reconstruction", "i_missing = -(i_phase1 + i_phase2)", "A", source="algorithm")
            _diag(section, "PHASE_CURRENT_RECONSTRUCTION", Status.WARNING, "The third phase current is reconstructed from two measured currents.", "Include gain/offset mismatch and fault-mode loss of observability in the safety analysis.")
    elif len(current_names) != 3:
        _diag(section, "PHASE_CURRENT_COUNT", Status.FAIL, f"Unsupported phase-current channel count: {len(current_names)}.", "Use two channels with KCL reconstruction or three direct phase-current channels.")
    return section


def calculate_phase_matching(
    cfg: dict[str, Any],
    iac_sections: dict[str, SectionResult],
    vac_sections: dict[str, SectionResult],
) -> SectionResult:
    section = SectionResult("16_Phase_Matching")
    current_values = [float(s.metric_value("effective_sensitivity_v_per_a")) for s in iac_sections.values()]
    current_zero_codes = [float(s.metric_value("zero_adc_code")) for s in iac_sections.values()]
    voltage_values = [float(s.metric_value("divider_ratio")) for s in vac_sections.values()]

    def mismatch_percent(values: list[float]) -> float:
        mean = sum(values) / len(values)
        return 0.0 if mean == 0 else (max(values) - min(values)) / abs(mean) * 100.0

    current_gain_mismatch = mismatch_percent(current_values)
    current_zero_mismatch = max(current_zero_codes) - min(current_zero_codes)
    voltage_gain_mismatch = mismatch_percent(voltage_values)
    current_limit = _num(cfg, "targets.phase_current_gain_mismatch_percent", 0.2)
    voltage_limit = _num(cfg, "targets.phase_voltage_gain_mismatch_percent", 0.2)
    zero_limit = _num(cfg, "targets.phase_zero_code_mismatch", 5.0)

    current_status = _status_upper(current_gain_mismatch, current_limit)
    voltage_status = _status_upper(voltage_gain_mismatch, voltage_limit)
    zero_status = _status_upper(current_zero_mismatch, zero_limit)
    _metric(section, "phase_current_gain_mismatch_percent", "Phase-current gain mismatch", current_gain_mismatch, "%", "(max(Seff)-min(Seff))/mean(Seff)*100", status=current_status)
    _metric(section, "phase_current_zero_mismatch_code", "Phase-current zero-code mismatch", current_zero_mismatch, "code", "max(Nzero)-min(Nzero)", status=zero_status)
    _metric(section, "phase_voltage_gain_mismatch_percent", "Phase-voltage divider-ratio mismatch", voltage_gain_mismatch, "%", "(max(Kdiv)-min(Kdiv))/mean(Kdiv)*100", status=voltage_status)
    _metric(section, "phase_current_gain_mismatch_limit_percent", "Allowed current-channel gain mismatch", current_limit, "%", source="configuration")
    _metric(section, "phase_voltage_gain_mismatch_limit_percent", "Allowed voltage-channel gain mismatch", voltage_limit, "%", source="configuration")

    if current_status == Status.FAIL:
        _diag(section, "PHASE_I_GAIN_MATCH", Status.FAIL, "Phase-current channel gain mismatch exceeds the configured limit.", "Use matched components or independent per-phase gain calibration.")
    if zero_status == Status.FAIL:
        _diag(section, "PHASE_I_OFFSET_MATCH", Status.FAIL, "Phase-current zero-code mismatch exceeds the configured limit.", "Perform per-phase zero-current calibration and temperature compensation.")
    if voltage_status == Status.FAIL:
        _diag(section, "PHASE_V_GAIN_MATCH", Status.FAIL, "Phase-voltage channel ratio mismatch exceeds the configured limit.", "Use matched divider networks and per-channel calibration.")
    return section


def calculate_synchronous_sampling(cfg: dict[str, Any], iac_design_a: float) -> SectionResult:
    section = SectionResult("52_Sampling_Sync")
    phase_count = int(get(cfg, "system.phase_count", 1))
    if phase_count == 1:
        _metric(section, "sampling_model", "Sampling synchronization model", "single_phase")
        return section

    assignments = get(cfg, "sampling.channels", [])
    trigger_default = str(get(cfg, "sampling.trigger_source", "EPWM1_SOCA"))
    trigger_position = str(get(cfg, "sampling.trigger_position", "PWM_CENTER"))
    simultaneous_required = bool(get(cfg, "sampling.simultaneous_required", True))
    max_skew_limit = _num(cfg, "sampling.maximum_channel_skew_s", 1.0e-7)
    max_skew_error_pct = _num(cfg, "sampling.max_skew_error_percent_fs", 0.1)
    current_slew = _optional_num(cfg, "sampling.max_current_slew_rate_a_per_s")
    voltage_slew = _optional_num(cfg, "sampling.max_voltage_slew_rate_v_per_s")
    line_frequency = _num(cfg, "control.line_frequency_hz", 50.0)
    switching_frequency = _num(cfg, "system.switching_frequency_hz")

    expected_i = {f"IAC_{name}" for name in get(cfg, "channels.iac.phase_names", ["A", "B", "C"])}
    vac_names = get(cfg, "channels.vac.phase_names", ["A", "B", "C"])
    expected_v = {f"VAC_{name}" for name in vac_names}
    actual_names = {str(item.get("name")) for item in assignments}
    missing = sorted((expected_i | expected_v) - actual_names)
    if missing:
        _diag(section, "SAMPLING_CHANNEL_MISSING", Status.FAIL, f"Sampling assignments are missing: {', '.join(missing)}.", "Add each per-phase current and voltage channel to sampling.channels.")

    _metric(section, "trigger_source", "Common sampling trigger source", trigger_default, source="configuration")
    _metric(section, "trigger_position", "PWM trigger position", trigger_position, source="configuration")
    _metric(section, "simultaneous_required", "Simultaneous sampling required", simultaneous_required, source="configuration")
    _metric(section, "configured_channel_count", "Configured synchronous channels", len(assignments), "channel")

    trigger_sources = {str(item.get("trigger_source", trigger_default)) for item in assignments}
    trigger_status = Status.PASS if len(trigger_sources) == 1 else Status.FAIL
    _metric(section, "trigger_source_count", "Distinct trigger-source count", len(trigger_sources), "source", status=trigger_status)
    if trigger_status == Status.FAIL:
        _diag(section, "SAMPLING_TRIGGER_MISMATCH", Status.FAIL, "Per-phase channels do not share one hardware trigger source.", "Route all control-critical phase channels from the same ePWM SOCA/SOCB event.")

    current_items = [item for item in assignments if str(item.get("quantity", "")).lower() == "current"]
    voltage_items = [item for item in assignments if str(item.get("quantity", "")).lower() == "voltage"]
    current_modules = [str(item.get("adc_module")) for item in current_items]
    voltage_modules = [str(item.get("adc_module")) for item in voltage_items]
    unique_current_modules = len(set(current_modules))
    _metric(section, "current_adc_module_count", "Distinct ADC modules for phase currents", unique_current_modules, "module")
    if simultaneous_required and len(current_items) >= 3 and unique_current_modules < len(current_items):
        _diag(section, "SAMPLING_ADC_REUSE", Status.FAIL, "Multiple directly measured phase currents share an ADC module, so their sample apertures are sequential rather than simultaneous.", "Place direct phase currents on independent ADC modules or provide an explicitly bounded skew model.")

    delays: list[float] = []
    missing_delays: list[str] = []
    for item in assignments:
        delay = item.get("aperture_delay_s")
        name = str(item.get("name"))
        if delay is None:
            missing_delays.append(name)
        else:
            delays.append(float(delay))
        _metric(section, f"assignment_{name}", f"{name} assignment", f"{item.get('adc_module')}/SOC{item.get('soc')}", source="configuration", note=f"aperture_delay_s={delay}")

    if missing_delays:
        _metric(section, "maximum_channel_skew_s", "Maximum sample-aperture skew", None, "s", status=Status.NOT_EVALUATED, source="missing aperture delays")
        _diag(section, "SAMPLING_SKEW_MISSING", Status.NOT_EVALUATED, f"Sample-aperture delays are missing for: {', '.join(missing_delays)}.", "Enter worst-case aperture_delay_s for each assigned channel.")
        return section

    max_skew = max(delays) - min(delays) if delays else 0.0
    skew_status = _status_upper(max_skew, max_skew_limit)
    line_angle = 360.0 * line_frequency * max_skew
    switching_angle = 360.0 * switching_frequency * max_skew
    _metric(section, "maximum_channel_skew_s", "Maximum sample-aperture skew", max_skew, "s", "max(t_aperture)-min(t_aperture)", status=skew_status)
    _metric(section, "maximum_channel_skew_limit_s", "Allowed sample-aperture skew", max_skew_limit, "s", source="configuration")
    _metric(section, "line_frequency_angle_skew_deg", "Equivalent electrical-angle skew at line frequency", line_angle, "deg", "360*fline*DeltaT")
    _metric(section, "switching_frequency_angle_skew_deg", "Equivalent angle skew at switching frequency", switching_angle, "deg", "360*fsw*DeltaT")
    if skew_status == Status.FAIL:
        _diag(section, "SAMPLING_SKEW", Status.FAIL, f"Maximum sample skew {max_skew*1e9:.1f} ns exceeds the {max_skew_limit*1e9:.1f} ns limit.", "Use parallel ADC modules, a common trigger and matched acquisition windows.")

    if current_slew is None:
        _metric(section, "current_skew_error_a", "Current error caused by channel skew", None, "A", status=Status.NOT_EVALUATED, source="missing current slew rate")
        _diag(section, "SAMPLING_DI_DT_MISSING", Status.NOT_EVALUATED, "Current slew-rate bound is not configured.", "Enter sampling.max_current_slew_rate_a_per_s from the worst-case inductor/ripple model.")
    else:
        current_error = current_slew * max_skew
        current_error_pct = current_error / iac_design_a * 100.0 if iac_design_a else 0.0
        current_status = _status_upper(current_error_pct, max_skew_error_pct)
        _metric(section, "current_skew_error_a", "Worst-case current mismatch caused by skew", current_error, "A", "max(di/dt)*DeltaT")
        _metric(section, "current_skew_error_percent_fs", "Current skew error relative to phase design peak", current_error_pct, "%FS", "DeltaI/Iphase_design*100", status=current_status)
        if current_status == Status.FAIL:
            _diag(section, "SAMPLING_CURRENT_ERROR", Status.FAIL, "Sampling skew produces excessive phase-current mismatch.", "Reduce aperture skew or revise the worst-case slew-rate/current-range design.")

    if voltage_slew is None:
        _metric(section, "voltage_skew_error_v", "Voltage error caused by channel skew", None, "V", status=Status.NOT_EVALUATED, source="missing voltage slew rate")
    else:
        voltage_error = voltage_slew * max_skew
        _metric(section, "voltage_skew_error_v", "Worst-case voltage mismatch caused by skew", voltage_error, "V", "max(dv/dt)*DeltaT")

    return section
