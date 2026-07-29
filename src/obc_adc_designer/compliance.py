from __future__ import annotations

import math
from typing import Any

from .config import get
from .models import Diagnostic, Metric, SectionResult, Status


def _num(cfg: dict[str, Any], path: str, default: float | None = None) -> float:
    value = get(cfg, path, default)
    if value is None:
        raise ValueError(f"Required numerical parameter is missing: {path}")
    return float(value)


def _metric(
    section: SectionResult,
    key: str,
    label: str,
    value: float | int | str | bool | None,
    unit: str = "",
    formula: str = "",
    inputs: str = "",
    source: str = "GB/T 40432—2021",
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


def _diag(section: SectionResult, code: str, status: Status, message: str, recommendation: str = "") -> None:
    section.diagnostics.append(
        Diagnostic(code=code, scope=section.name, status=status, message=message, recommendation=recommendation)
    )


def _upper_status(value: float, limit: float, warning_ratio: float = 0.9) -> Status:
    if value > limit:
        return Status.FAIL
    if value > limit * warning_ratio:
        return Status.WARNING
    return Status.PASS


def _lower_status(value: float, limit: float, warning_ratio: float = 1.05) -> Status:
    if value < limit:
        return Status.FAIL
    if value < limit * warning_ratio:
        return Status.WARNING
    return Status.PASS


def _dielectric_test_voltage_rms(udmax_v: float) -> float:
    if udmax_v <= 60.0:
        return 500.0
    if udmax_v <= 125.0:
        return 1000.0
    if udmax_v <= 250.0:
        return 1500.0
    if udmax_v <= 500.0:
        return 2000.0
    return 1000.0 + 2.0 * udmax_v


def _instrument_requirement(error_percent: float) -> tuple[str, str]:
    if error_percent <= 0.5:
        return "0.1 class", "6.5 digit"
    if error_percent <= 1.5:
        return "0.2 class", "5.5 digit"
    if error_percent <= 5.0:
        return "0.5 class", "4.5 digit"
    return "1.0 class", "4.5 digit"


def standard_enabled(cfg: dict[str, Any]) -> bool:
    return bool(get(cfg, "standard_profile.enabled", False))


def calculate_gbt_compliance(cfg: dict[str, Any], system: SectionResult) -> list[SectionResult]:
    """Build a GB/T 40432—2021 compliance layer without overwriting design inputs.

    The standard limits are treated as whole-product compliance/test requirements. The
    calculator separately checks whether the product hardware range and allocated sensing
    targets are adequate. It does not equate whole-product error limits with sensor error.
    """

    if not standard_enabled(cfg):
        return []

    sections: list[SectionResult] = []
    sections.append(_calculate_profile_and_checks(cfg, system))
    sections.append(_calculate_test_matrix(cfg, system))
    sections.append(_calculate_design_allocation(cfg, system))
    sections.append(_calculate_test_equipment(cfg))
    sections.append(_calculate_safety_environment_emc(cfg))
    if bool(get(cfg, "system.bidirectional", False)):
        sections.append(_calculate_inverter_requirements(cfg, system))
    return sections


def _standard_ac_values(cfg: dict[str, Any]) -> tuple[float, float, float, str]:
    phase_count = int(get(cfg, "system.phase_count", 1))
    basis = str(get(cfg, "system.ac_voltage_basis", "single_phase" if phase_count == 1 else "line_to_line"))
    tolerance = _num(cfg, "standard_profile.ac_input.voltage_tolerance_percent", 15.0) / 100.0
    if phase_count == 1:
        nominal = _num(cfg, "standard_profile.ac_input.single_phase_nominal_v", 220.0)
        label = "single-phase RMS"
    else:
        nominal_ll = _num(cfg, "standard_profile.ac_input.three_phase_line_nominal_v", 380.0)
        if basis == "phase_to_neutral":
            nominal = nominal_ll / math.sqrt(3.0)
            label = "phase-to-neutral RMS derived from 380 V line-to-line"
        else:
            nominal = nominal_ll
            label = "three-phase line-to-line RMS"
    return nominal, nominal * (1.0 - tolerance), nominal * (1.0 + tolerance), label


def _calculate_profile_and_checks(cfg: dict[str, Any], system: SectionResult) -> SectionResult:
    section = SectionResult("02_GBT_Compliance")
    standard_name = str(get(cfg, "standard_profile.name", "GB/T 40432—2021"))
    phase_count = int(get(cfg, "system.phase_count", 1))
    nominal, test_min, test_max, basis_label = _standard_ac_values(cfg)
    hardware_min = _num(cfg, "system.vac_min_rms_v")
    hardware_nom = _num(cfg, "system.vac_nom_rms_v", nominal)
    hardware_max = _num(cfg, "system.vac_max_rms_v")
    vdc_max = _num(cfg, "system.vdc_max_v")
    line_freq = _num(cfg, "control.line_frequency_hz", 50.0)
    standard_freq = _num(cfg, "standard_profile.ac_input.nominal_frequency_hz", 50.0)
    freq_tol = _num(cfg, "standard_profile.ac_input.frequency_tolerance_hz", 1.0)

    _metric(section, "standard_name", "Enabled standard profile", standard_name, source="configuration")
    _metric(section, "standard_scope_phase", "Applicable phase configuration", phase_count, "phase", source="configuration")
    _metric(section, "standard_ac_basis", "Standard AC test voltage basis", basis_label, source="calculated from GB/T 40432—2021 §4.2.1")

    max_dc_scope = _num(cfg, "standard_profile.scope.max_dc_output_v", 1500.0)
    scope_status = _upper_status(vdc_max, max_dc_scope, 1.0)
    _metric(section, "standard_max_dc_output_v", "Standard scope maximum DC output", max_dc_scope, "V", source="GB/T 40432—2021 §1")
    _metric(section, "configured_vdc_max_v", "Configured maximum DC voltage", vdc_max, "V", source="system configuration", status=scope_status)
    if scope_status == Status.FAIL:
        _diag(section, "GBT_SCOPE_DC", Status.FAIL, f"Configured DC maximum {vdc_max:.1f} V exceeds the {max_dc_scope:.1f} V scope of GB/T 40432—2021.", "Use a different/extended compliance profile for this product.")

    nominal_mismatch_pct = abs(hardware_nom - nominal) / nominal * 100.0
    nominal_status = Status.PASS if nominal_mismatch_pct <= 1.0 else Status.WARNING
    _metric(section, "standard_ac_nominal_v", "Standard AC nominal test voltage", nominal, "V RMS", source="GB/T 40432—2021 Table 1")
    _metric(section, "configured_ac_nominal_v", "Configured product nominal AC voltage", hardware_nom, "V RMS", source="system configuration", status=nominal_status)
    _metric(section, "nominal_voltage_difference_percent", "Product/standard nominal-voltage difference", nominal_mismatch_pct, "%", "abs(Vproduct-Vstd)/Vstd*100", status=nominal_status)
    if nominal_status == Status.WARNING:
        _diag(section, "GBT_NOMINAL_VOLTAGE", Status.WARNING, f"Product nominal voltage {hardware_nom:.1f} V differs from the GB/T test nominal {nominal:.1f} V.", "Keep the hardware rating, but use the separate GB/T nominal voltage for compliance testing.")

    range_status = Status.PASS if hardware_min <= test_min and hardware_max >= test_max else Status.FAIL
    _metric(section, "gbt_ac_test_min_v", "GB/T AC lower test voltage", test_min, "V RMS", "Vnom*(1-15%)", source="GB/T 40432—2021 §4.2.1.2/§5.3.2.1", status=range_status)
    _metric(section, "gbt_ac_test_max_v", "GB/T AC upper test voltage", test_max, "V RMS", "Vnom*(1+15%)", source="GB/T 40432—2021 §4.2.1.2/§5.3.2.1", status=range_status)
    _metric(section, "hardware_ac_min_v", "Configured hardware minimum AC voltage", hardware_min, "V RMS", source="system configuration")
    _metric(section, "hardware_ac_max_v", "Configured hardware maximum AC voltage", hardware_max, "V RMS", source="system configuration")
    if range_status == Status.FAIL:
        _diag(section, "GBT_AC_RANGE", Status.FAIL, f"Hardware AC range {hardware_min:.1f}–{hardware_max:.1f} V does not cover the GB/T test range {test_min:.1f}–{test_max:.1f} V.", "Expand the hardware/sensing range or revise the product applicability statement.")

    freq_status = Status.PASS if abs(line_freq - standard_freq) < 1e-9 else Status.WARNING
    _metric(section, "gbt_frequency_nominal_hz", "GB/T nominal frequency", standard_freq, "Hz", source="GB/T 40432—2021 Table 1")
    _metric(section, "gbt_frequency_min_hz", "GB/T lower frequency test", standard_freq - freq_tol, "Hz", source="GB/T 40432—2021 §4.2.1.3/§5.3.2.2")
    _metric(section, "gbt_frequency_max_hz", "GB/T upper frequency test", standard_freq + freq_tol, "Hz", source="GB/T 40432—2021 §4.2.1.3/§5.3.2.2")
    _metric(section, "configured_line_frequency_hz", "Configured line frequency", line_freq, "Hz", source="control configuration", status=freq_status)
    if freq_status == Status.WARNING:
        _diag(section, "GBT_LINE_FREQ", Status.WARNING, "Configured line frequency is not the GB/T 50 Hz nominal condition.", "Create a 50 Hz compliance test configuration while retaining other regional product profiles separately.")

    if phase_count == 3:
        phase_dev = _num(cfg, "standard_profile.ac_input.three_phase_phase_deviation_deg", 3.0)
        _metric(section, "gbt_phase_deviation_deg", "Three-phase phase-deviation test", phase_dev, "±deg", source="GB/T 40432—2021 §4.2.1.4/§5.3.2.3")

    iac_peak = float(system.metric_value("iac_peak_a"))
    iac_design = float(system.metric_value("iac_design_peak_a"))
    inrush_ratio = _num(cfg, "standard_profile.current.startup_inrush_peak_ratio_max", 1.20)
    required_inrush_range = iac_peak * inrush_ratio
    inrush_status = _lower_status(iac_design, required_inrush_range, 1.0)
    _metric(section, "gbt_startup_inrush_ratio", "Maximum startup input-current peak ratio", inrush_ratio, "pu", source="GB/T 40432—2021 §4.2.2")
    _metric(section, "gbt_required_iac_linear_peak_a", "Minimum IAC linear range for GB/T startup test", required_inrush_range, "A peak", "Isteady_peak*1.20", status=inrush_status)
    _metric(section, "configured_iac_design_peak_a", "Configured IAC design peak", iac_design, "A peak", source="system-rating calculation", status=inrush_status)
    if inrush_status == Status.FAIL:
        _diag(section, "GBT_IAC_INRUSH_RANGE", Status.FAIL, "Configured IAC design range does not cover the GB/T startup-current limit.", "Increase IAC range margin or reduce sensing gain/sensitivity.")

    allocation_fraction = _num(cfg, "standard_profile.design_allocation.sensing_error_budget_fraction", 0.50)
    vdc_system_limit = _num(cfg, "standard_profile.dc_output.voltage_error_percent_max", 1.0)
    vdc_sensor_alloc = vdc_system_limit * allocation_fraction
    vdc_sensor_target = _num(cfg, "channels.vdc.accuracy_target_percent_fs", 0.5)
    vdc_accuracy_status = _upper_status(vdc_sensor_target, vdc_sensor_alloc, 1.0)
    _metric(section, "gbt_output_voltage_error_percent", "Whole-product DC output-voltage error limit", vdc_system_limit, "%", source="GB/T 40432—2021 §4.2.6")
    _metric(section, "allocated_vdc_sensing_error_percent", "Allocated VDC sensing-chain error", vdc_sensor_alloc, "%FS", "GBT limit*allocation fraction", status=vdc_accuracy_status)
    _metric(section, "configured_vdc_sensing_target_percent", "Configured VDC sensing target", vdc_sensor_target, "%FS", source="channel configuration", status=vdc_accuracy_status)
    if vdc_accuracy_status == Status.FAIL:
        _diag(section, "GBT_VDC_ERROR_ALLOCATION", Status.FAIL, "VDC sensing target consumes more than the allocated share of the GB/T whole-product voltage-error limit.", "Tighten the sensing target or revise the documented error budget with justified allocations.")

    idc_threshold = _num(cfg, "standard_profile.dc_output.current_error_threshold_a", 10.0)
    idc_rel_limit = _num(cfg, "standard_profile.dc_output.current_error_above_threshold_percent", 5.0)
    idc_abs_limit = _num(cfg, "standard_profile.dc_output.current_error_at_or_below_threshold_a", 0.5)
    idc_target_pct_fs = _num(cfg, "channels.idc.accuracy_target_percent_fs", 0.5)
    idc_design = float(system.metric_value("idc_design_peak_a"))
    idc_target_abs = idc_design * idc_target_pct_fs / 100.0
    idc_rel_alloc = idc_rel_limit * allocation_fraction
    idc_abs_alloc = idc_abs_limit * allocation_fraction
    idc_rel_status = _upper_status(idc_target_pct_fs, idc_rel_alloc, 1.0)
    idc_abs_status = _upper_status(idc_target_abs, idc_abs_alloc, 1.0)
    _metric(section, "gbt_output_current_threshold_a", "Output-current error threshold", idc_threshold, "A", source="GB/T 40432—2021 §4.2.7")
    _metric(section, "gbt_output_current_error_above_threshold_percent", "Whole-product current-error limit above threshold", idc_rel_limit, "%", source="GB/T 40432—2021 §4.2.7")
    _metric(section, "gbt_output_current_error_below_threshold_a", "Whole-product current deviation at/below threshold", idc_abs_limit, "A", source="GB/T 40432—2021 §4.2.7")
    _metric(section, "allocated_idc_sensing_error_percent", "Allocated IDC sensing error above 10 A", idc_rel_alloc, "%FS", status=idc_rel_status)
    _metric(section, "configured_idc_sensing_target_percent", "Configured IDC sensing target", idc_target_pct_fs, "%FS", source="channel configuration", status=idc_rel_status)
    _metric(section, "configured_idc_sensing_target_absolute_a", "Configured IDC target converted to design-full-scale amperes", idc_target_abs, "A", "IDC_design*target_%FS/100", status=idc_abs_status, note="Conservative screening; %FS and low-current absolute error are not identical definitions.")
    _metric(section, "allocated_idc_low_current_error_a", "Allocated IDC low-current absolute error", idc_abs_alloc, "A", status=idc_abs_status)
    if idc_rel_status == Status.FAIL or idc_abs_status == Status.FAIL:
        _diag(section, "GBT_IDC_ERROR_ALLOCATION", Status.FAIL, "IDC sensing target does not meet the provisional allocation of the GB/T current-control error limits.", "Tighten offset/gain targets or document a different whole-product error allocation.")

    ripple_limit = _num(cfg, "standard_profile.dc_output.voltage_ripple_factor_percent_max", 5.0)
    _metric(section, "gbt_voltage_ripple_factor_percent", "Whole-product DC voltage-ripple factor limit", ripple_limit, "%", "Vpp/(2*Vdc)*100", source="GB/T 40432—2021 §4.2.8/§5.3.9")
    _metric(section, "gbt_voltage_ripple_vpp_ratio", "Equivalent maximum ripple peak-to-peak ratio", 2.0 * ripple_limit, "% of Vdc", "Vpp/Vdc=2*Vripple_factor", source="derived from GB/T 40432—2021 §4.2.8")

    vdc_margin = _num(cfg, "channels.vdc.range_margin", _num(cfg, "system.default_range_margin", 1.2))
    idc_margin = _num(cfg, "channels.idc.range_margin", _num(cfg, "system.default_range_margin", 1.2))
    v_overshoot = _num(cfg, "standard_profile.dc_output.startup_voltage_overshoot_percent_max", 10.0)
    i_overshoot = _num(cfg, "standard_profile.dc_output.startup_current_overshoot_percent_max", 5.0)
    v_margin_req = 1.0 + v_overshoot / 100.0
    i_margin_req = 1.0 + i_overshoot / 100.0
    v_margin_status = _lower_status(vdc_margin, v_margin_req, 1.0)
    i_margin_status = _lower_status(idc_margin, i_margin_req, 1.0)
    _metric(section, "gbt_vdc_startup_range_factor", "Minimum VDC range factor from startup overvoltage", v_margin_req, "pu", source="GB/T 40432—2021 §4.2.9.1", status=v_margin_status)
    _metric(section, "configured_vdc_range_margin", "Configured VDC range margin", vdc_margin, "pu", source="channel configuration", status=v_margin_status)
    _metric(section, "gbt_idc_startup_range_factor", "Minimum IDC range factor from startup overcurrent", i_margin_req, "pu", source="GB/T 40432—2021 §4.2.9.2", status=i_margin_status)
    _metric(section, "configured_idc_range_margin", "Configured IDC range margin", idc_margin, "pu", source="channel configuration", status=i_margin_status)
    if v_margin_status == Status.FAIL or i_margin_status == Status.FAIL:
        _diag(section, "GBT_STARTUP_MARGIN", Status.FAIL, "Configured voltage/current range margin is below the GB/T startup-overshoot boundary.", "Increase the affected channel range margin.")

    pf_rated_min = _num(cfg, "standard_profile.power_quality.pf_rated_min", 0.98)
    pf_half_min = _num(cfg, "standard_profile.power_quality.pf_half_load_min", 0.95)
    configured_pf = _num(cfg, "system.power_factor_min")
    pf_status = _lower_status(configured_pf, pf_rated_min, 1.0)
    _metric(section, "gbt_pf_rated_min", "Minimum PF at rated output", pf_rated_min, "pu", source="GB/T 40432—2021 Table 2")
    _metric(section, "gbt_pf_half_load_min", "Minimum PF at 50% output", pf_half_min, "pu", source="GB/T 40432—2021 Table 2")
    _metric(section, "configured_pf_design", "Configured design PF", configured_pf, "pu", source="system configuration", status=pf_status)
    if pf_status == Status.FAIL:
        _diag(section, "GBT_POWER_FACTOR", Status.FAIL, "Configured power factor is below the GB/T rated-output minimum.", "Revise the PFC target or compliance applicability.")

    rated_power = _num(cfg, "system.rated_power_w")
    efficiency = _num(cfg, "system.efficiency_min")
    if phase_count == 1:
        rated_input_current = rated_power / (nominal * efficiency * configured_pf)
    elif str(get(cfg, "system.ac_voltage_basis", "line_to_line")) == "line_to_line":
        rated_input_current = rated_power / (math.sqrt(3.0) * nominal * efficiency * configured_pf)
    else:
        rated_input_current = rated_power / (3.0 * nominal * efficiency * configured_pf)
    harmonic_standard = "GB 17625.1" if rated_input_current <= 16.0 else "GB/T 17625.8"
    flicker_standard = "GB/T 17625.2" if rated_input_current <= 16.0 else "GB/T 17625.7"
    _metric(section, "estimated_rated_input_current_a", "Estimated rated per-line input current for standard branch", rated_input_current, "A RMS", "Prated/(Vnom*eta*PF), with phase factor", source="calculated for GB/T 40432—2021 §4.5.3.5/§4.5.3.6")
    _metric(section, "harmonic_current_standard", "Applicable harmonic-current standard", harmonic_standard, source="GB/T 40432—2021 §4.5.3.5")
    _metric(section, "voltage_fluctuation_standard", "Applicable voltage-fluctuation/flicker standard", flicker_standard, source="GB/T 40432—2021 §4.5.3.6")

    avg_eff_min = _num(cfg, "standard_profile.power_quality.average_efficiency_min", 0.94)
    configured_eff = _num(cfg, "system.efficiency_min")
    eff_status = _lower_status(configured_eff, avg_eff_min, 1.0)
    _metric(section, "gbt_average_efficiency_min", "E1 average charging-efficiency threshold", avg_eff_min, "pu", source="GB/T 40432—2021 Table 3")
    _metric(section, "configured_worst_case_efficiency", "Configured minimum efficiency used for current sizing", configured_eff, "pu", source="system configuration", status=eff_status, note="This is a sizing assumption, not the ten-point average-efficiency test result.")
    _diag(section, "GBT_EFFICIENCY_EVIDENCE", Status.WARNING, "The configured minimum efficiency is not proof of the GB/T ten-point average-efficiency result.", "Validate after 30 min warm-up at ten evenly spaced output-voltage points.")

    return section


def _calculate_test_matrix(cfg: dict[str, Any], system: SectionResult) -> SectionResult:
    section = SectionResult("03_GBT_Test_Matrix")
    phase_count = int(get(cfg, "system.phase_count", 1))
    nominal, test_min, test_max, _ = _standard_ac_values(cfg)
    standard_freq = _num(cfg, "standard_profile.ac_input.nominal_frequency_hz", 50.0)
    freq_tol = _num(cfg, "standard_profile.ac_input.frequency_tolerance_hz", 1.0)

    _metric(section, "ac_voltage_low_test", "AC lower-voltage operating test", f"{test_min:.3f} V RMS, >=60 s", source="GB/T 40432—2021 §5.3.2.1")
    _metric(section, "ac_voltage_high_test", "AC upper-voltage operating test", f"{test_max:.3f} V RMS, >=60 s", source="GB/T 40432—2021 §5.3.2.1")
    _metric(section, "frequency_low_test", "Lower-frequency operating test", f"{standard_freq-freq_tol:.1f} Hz, 60 s", source="GB/T 40432—2021 §5.3.2.2")
    _metric(section, "frequency_high_test", "Upper-frequency operating test", f"{standard_freq+freq_tol:.1f} Hz, 60 s", source="GB/T 40432—2021 §5.3.2.2")
    if phase_count == 3:
        phase_dev = _num(cfg, "standard_profile.ac_input.three_phase_phase_deviation_deg", 3.0)
        _metric(section, "phase_deviation_test", "Three-phase phase-deviation test", f"any phase ±{phase_dev:.1f}°, 60 s", source="GB/T 40432—2021 §5.3.2.3")
        _metric(section, "phase_loss_protection_test", "Three-phase loss-of-phase protection test", "remove any one phase at rated output; verify derating or shutdown and recovery", source="GB/T 40432—2021 §4.3.2/§5.4.2")

    _metric(section, "startup_inrush_test", "Startup input-current test", "3 starts; >=2 min interval; compare startup/stable peaks", source="GB/T 40432—2021 §5.3.3", note="Microsecond EMI inrush is excluded by the standard.")
    _metric(section, "voltage_error_load_points", "DC voltage-error load points", "10%, 50%, 100% rated load", source="GB/T 40432—2021 §5.3.7")
    _metric(section, "current_error_voltage_points", "DC current-error voltage points", "output-voltage lower limit, rated value, upper limit", source="GB/T 40432—2021 §5.3.8")
    _metric(section, "ripple_load_points", "DC voltage-ripple load points", "50%, 100% rated output current", source="GB/T 40432—2021 §5.3.9")
    _metric(section, "ripple_scope_setting", "External ripple-test oscilloscope", "AC coupling; 20 MHz bandwidth; >=0.5 s/div", source="GB/T 40432—2021 §5.3.9", note="This is not the MCU ADC bandwidth requirement.")
    _metric(section, "efficiency_warmup", "Efficiency-test warm-up", "30 min at rated state", source="GB/T 40432—2021 §5.3.13")
    _metric(section, "efficiency_voltage_points", "Efficiency-test output-voltage points", "10 evenly spaced values across product output range", source="GB/T 40432—2021 §5.3.13")
    _metric(section, "ac_protection_thresholds", "AC over/undervoltage protection thresholds", "product technical document-defined", source="GB/T 40432—2021 §4.3.1/§5.4.1", note="The national standard does not provide one universal threshold value.")
    _metric(section, "dc_protection_thresholds", "DC over/undervoltage protection thresholds", "product technical document-defined", source="GB/T 40432—2021 §4.3.3/§5.4.3", note="Do not replace product protection calibration with the ±15% normal-input test range.")

    dip_tests = get(cfg, "standard_profile.voltage_dip_tests", [])
    for index, item in enumerate(dip_tests, start=1):
        pct = float(item["voltage_percent"])
        cycles = int(item["duration_cycles_50hz"])
        status = str(item["functional_status"])
        duration_s = cycles / standard_freq
        _metric(section, f"voltage_dip_{index}", f"Voltage dip/interruption: {pct:g}%", f"{cycles} cycles / {duration_s:g} s at {standard_freq:g} Hz; state {status}", source="GB/T 40432—2021 Table 7")

    return section


def _calculate_design_allocation(cfg: dict[str, Any], system: SectionResult) -> SectionResult:
    section = SectionResult("04_GBT_Allocation")
    nominal, test_min, test_max, _ = _standard_ac_values(cfg)
    _metric(section, "vac_nominal_handling", "AC nominal-voltage parameter", "Add compliance test nominal; do not overwrite hardware/product rating", source="engineering allocation from GB/T 40432—2021", note=f"GB/T nominal={nominal:.3f} V RMS; test range={test_min:.3f}–{test_max:.3f} V RMS.")
    _metric(section, "vac_range_handling", "AC min/max voltage parameters", "Keep wider hardware range; add separate GB/T test range", source="engineering allocation")
    _metric(section, "pf_handling", "Power-factor parameter", "Keep product target; add 0.98 rated and 0.95 half-load compliance limits", source="GB/T 40432—2021 Table 2")
    _metric(section, "efficiency_handling", "Efficiency parameter", "Keep worst-case sizing efficiency; add E1 average-efficiency threshold 0.94", source="GB/T 40432—2021 Table 3")
    _metric(section, "vdc_accuracy_handling", "VDC accuracy target", "Keep sensing-chain target <=0.5%FS; standard whole-product limit is ±1%", source="GB/T 40432—2021 §4.2.6")
    _metric(section, "idc_accuracy_handling", "IDC accuracy target", "Keep sensing-chain target <=0.5%FS; add whole-product piecewise 5% / 0.5 A limits", source="GB/T 40432—2021 §4.2.7")
    _metric(section, "ripple_handling", "VDC ripple parameter", "Add 5% whole-product ripple test; do not replace ADC/RC bandwidth", source="GB/T 40432—2021 §4.2.8/§5.3.9")
    _metric(section, "scope_bandwidth_handling", "20 MHz oscilloscope bandwidth", "External test-equipment setting only; do not map to F29H85x ADC bandwidth", source="GB/T 40432—2021 §5.3.9")
    _metric(section, "inrush_handling", "Startup current ratio", "Use 1.20 pu as a compliance range floor; retain larger overload/fault margin", source="GB/T 40432—2021 §4.2.2")
    _metric(section, "phase_deviation_handling", "Three-phase ±3° requirement", "Add as grid test case; do not replace ADC inter-channel skew target", source="GB/T 40432—2021 §4.2.1.4")
    _metric(section, "temperature_handling", "Temperature parameters", "Separate vehicle ambient/storage tests from component -40…125 °C error-budget range", source="GB/T 40432—2021 Table 8")
    _metric(section, "emc_handling", "Surge/ESD/EFT requirements", "Add transient withstand requirements; do not enlarge linear sensing range to kV values", source="GB/T 40432—2021 §4.5.2")
    return section


def _calculate_test_equipment(cfg: dict[str, Any]) -> SectionResult:
    section = SectionResult("07_GBT_Test_Equipment")
    sensor_target = min(
        _num(cfg, "channels.iac.accuracy_target_percent_fs", 0.5),
        _num(cfg, "channels.idc.accuracy_target_percent_fs", 0.5),
        _num(cfg, "channels.vac.accuracy_target_percent_fs", 0.5),
        _num(cfg, "channels.vdc.accuracy_target_percent_fs", 0.5),
    )
    instrument_class, digits = _instrument_requirement(sensor_target)
    v_class, v_digits = _instrument_requirement(_num(cfg, "standard_profile.dc_output.voltage_error_percent_max", 1.0))
    i_class, i_digits = _instrument_requirement(_num(cfg, "standard_profile.dc_output.current_error_above_threshold_percent", 5.0))

    _metric(section, "sensor_validation_error_level_percent", "Smallest configured sensing-error target", sensor_target, "%", source="channel configurations")
    _metric(section, "sensor_validation_instrument_class", "Reference instrument for <=0.5% sensing validation", instrument_class, source="GB/T 40432—2021 Table 9", note=f"Recommended digital resolution: {digits}.")
    _metric(section, "voltage_error_test_instrument_class", "Instrument for 1% output-voltage error test", v_class, source="GB/T 40432—2021 Table 9", note=f"Digital resolution: {v_digits}.")
    _metric(section, "current_error_test_instrument_class", "Instrument for 5% output-current error test", i_class, source="GB/T 40432—2021 Table 9", note=f"Digital resolution: {i_digits}.")
    _metric(section, "temperature_instrument_error_c", "Temperature-measurement instrument error", 1.0, "±°C", source="GB/T 40432—2021 §5.1.2")
    _metric(section, "time_instrument_relative_error_percent", "Time-measurement relative error", 1.0, "%", source="GB/T 40432—2021 §5.1.2")
    _metric(section, "chamber_temperature_control_error_c", "Environmental-chamber temperature control", 2.0, "±°C", source="GB/T 40432—2021 §5.1.2")
    _metric(section, "chamber_humidity_control_error_percent", "Environmental-chamber humidity control", 3.0, "±%RH", source="GB/T 40432—2021 §5.1.2")
    _metric(section, "test_ambient_temperature_c", "General test ambient temperature", "18–28", "°C", source="GB/T 40432—2021 §5.1.1")
    _metric(section, "test_relative_humidity_percent", "General test relative humidity", "25–75", "%RH", source="GB/T 40432—2021 §5.1.1")
    _metric(section, "test_pressure_kpa", "General test atmospheric pressure", "86–106", "kPa", source="GB/T 40432—2021 §5.1.1")
    _metric(section, "liquid_coolant_inlet_temperature_c", "Liquid-cooled test inlet temperature", "40±2", "°C", source="GB/T 40432—2021 §5.1.1")
    return section


def _calculate_safety_environment_emc(cfg: dict[str, Any]) -> SectionResult:
    section = SectionResult("08_GBT_Safety_EMC")
    std = "GB/T 40432—2021"
    component_min = _num(cfg, "environment.temperature_min_c", -40.0)
    component_max = _num(cfg, "environment.temperature_max_c", 125.0)
    low_storage = _num(cfg, "standard_profile.environment.storage_temperature_min_c", -40.0)
    high_storage = _num(cfg, "standard_profile.environment.storage_temperature_max_c", 85.0)
    low_operating = _num(cfg, "standard_profile.environment.operating_temperature_min_c", -20.0)
    high_liquid = _num(cfg, "standard_profile.environment.operating_temperature_max_liquid_c", 65.0)
    high_air = _num(cfg, "standard_profile.environment.operating_temperature_max_air_c", 55.0)
    temp_status = Status.PASS if component_min <= low_storage and component_max >= high_storage else Status.FAIL

    _metric(section, "storage_temperature_min_c", "Low storage ambient", low_storage, "°C", source=f"{std} Table 8", status=temp_status)
    _metric(section, "operating_temperature_min_c", "Low operating ambient", low_operating, "°C", source=f"{std} Table 8")
    _metric(section, "storage_temperature_max_c", "High storage ambient", high_storage, "°C", source=f"{std} Table 8", status=temp_status)
    _metric(section, "operating_temperature_max_liquid_c", "High operating ambient — liquid cooled", high_liquid, "°C", source=f"{std} Table 8")
    _metric(section, "operating_temperature_max_air_c", "High operating ambient — air cooled", high_air, "°C", source=f"{std} Table 8")
    _metric(section, "configured_component_temperature_min_c", "Configured component error-budget minimum", component_min, "°C", source="environment configuration", status=temp_status)
    _metric(section, "configured_component_temperature_max_c", "Configured component error-budget maximum", component_max, "°C", source="environment configuration", status=temp_status)
    if temp_status == Status.FAIL:
        _diag(section, "GBT_TEMPERATURE_COVERAGE", Status.FAIL, "Configured component temperature range does not cover the GB/T storage range.", "Expand the component design/error-budget temperature range.")

    _metric(section, "relative_humidity_range_percent", "Relative-humidity range", "5–95", "%RH", source=f"{std} §4.6.1.2")
    _metric(section, "altitude_max_m", "Default maximum altitude", 2000, "m", source=f"{std} §4.6.1.3")
    _metric(section, "insulation_resistance_min_ohm", "Minimum insulation resistance", 1.0e7, "ohm", source=f"{std} §4.4.1")

    configured_udmax = get(cfg, "standard_profile.safety.udmax_v")
    udmax = _num(cfg, "system.vdc_max_v") if configured_udmax is None else float(configured_udmax)
    withstand_rms = _dielectric_test_voltage_rms(udmax)
    _metric(section, "dielectric_udmax_v", "Highest working voltage used for dielectric test", udmax, "V", source="standard_profile.safety.udmax_v or system.vdc_max_v")
    _metric(section, "dielectric_test_voltage_rms_v", "Required dielectric test voltage", withstand_rms, "V RMS", source=f"{std} Table 4")
    _metric(section, "dielectric_test_voltage_dc_equiv_v", "Equivalent DC dielectric test voltage", 1.4 * withstand_rms, "V DC", "1.4*Vac_rms", source=f"{std} Table 4 Note 2")
    _metric(section, "dielectric_test_duration_s", "Dielectric test duration", 60, "s", source=f"{std} §4.4.2")
    _metric(section, "contact_current_max_ma", "Maximum contact current", 3.5, "mA", source=f"{std} §4.4.3")

    actual_withstand = get(cfg, "standard_profile.safety.actual_isolation_withstand_rms_v")
    if actual_withstand is None:
        _metric(section, "actual_isolation_withstand_rms_v", "Configured isolation-component/system withstand", None, "V RMS", source="missing component/system input", status=Status.NOT_EVALUATED)
        _diag(section, "GBT_ISOLATION_NOT_CHECKED", Status.NOT_EVALUATED, "No actual isolation withstand rating is configured, so dielectric compliance cannot be verified.", "Enter standard_profile.safety.actual_isolation_withstand_rms_v after selecting the isolation architecture.")
    else:
        actual = float(actual_withstand)
        withstand_status = _lower_status(actual, withstand_rms, 1.0)
        _metric(section, "actual_isolation_withstand_rms_v", "Configured isolation-component/system withstand", actual, "V RMS", source="configuration", status=withstand_status)
        if withstand_status == Status.FAIL:
            _diag(section, "GBT_ISOLATION_WITHSTAND", Status.FAIL, "Configured isolation withstand is below the GB/T dielectric test voltage.", "Select a higher-rated isolation architecture and verify creepage/clearance.")

    _metric(section, "surge_differential_v", "AC-port differential-mode surge", 1000, "±V", source=f"{std} Table 6")
    _metric(section, "surge_common_mode_v", "AC-port common-mode surge", 2000, "±V", source=f"{std} Table 6")
    _metric(section, "eft_level", "EFT severity level", "Level 3, 5 kHz repetition", source=f"{std} §4.5.2.3")
    _metric(section, "radiated_immunity", "Radiated immunity", "75 V/m, 80 MHz–2 GHz", source=f"{std} §4.5.2.2")
    _metric(section, "esd_powered", "Powered ESD", "±8 kV contact; ±15 kV air; ±20 kV indirect contact", source=f"{std} Table 5")
    _metric(section, "esd_unpowered", "Unpowered ESD", "±8 kV contact; ±15 kV air", source=f"{std} Table 5")
    _diag(section, "GBT_EMC_COMPONENT_CHECK", Status.NOT_EVALUATED, "The standard EMC values are system-level tests; current component pulse/CMTI/ESD ratings are not available in the calculation profile.", "Use these requirements in the future MCP component-selection layer and verify at system level.")
    return section


def _calculate_inverter_requirements(cfg: dict[str, Any], system: SectionResult) -> SectionResult:
    section = SectionResult("09_GBT_Inverter")
    phase_count = int(get(cfg, "system.phase_count", 1))
    output_nominal = _num(
        cfg,
        "standard_profile.inverter.single_phase_nominal_v" if phase_count == 1 else "standard_profile.inverter.three_phase_line_nominal_v",
        220.0 if phase_count == 1 else 380.0,
    )
    rated_current = float(system.metric_value("iac_rms_max_a"))
    dc_component_limit = max(
        _num(cfg, "standard_profile.inverter.grid_current_dc_component_min_a", 0.005),
        rated_current * _num(cfg, "standard_profile.inverter.grid_current_dc_component_percent", 0.5) / 100.0,
    )
    _metric(section, "inverter_output_nominal_v", "Inverter AC output nominal", output_nominal, "V RMS", source="GB/T 40432—2021 Table A.1")
    _metric(section, "inverter_voltage_accuracy_percent", "Inverter AC voltage accuracy", 5.0, "±%", source="GB/T 40432—2021 §A.1.1.2")
    _metric(section, "inverter_frequency_nominal_hz", "Inverter nominal frequency", 50.0, "Hz", source="GB/T 40432—2021 §A.1.1.3")
    _metric(section, "inverter_frequency_tolerance_hz", "Inverter frequency tolerance", 0.5, "±Hz", source="GB/T 40432—2021 §A.1.1.3")
    _metric(section, "load_step_voltage_deviation_percent", "Load-step AC-voltage peak deviation", 15.0, "±%", source="GB/T 40432—2021 §A.1.1.4")
    _metric(section, "load_step_recovery_time_ms", "Load-step recovery time", 20.0, "ms", source="GB/T 40432—2021 §A.1.1.4")
    _metric(section, "voltage_thd_resistive_percent", "Voltage THD with resistive load", 5.0, "%", source="GB/T 40432—2021 §A.1.1.5")
    _metric(section, "voltage_thd_non_resistive_percent", "Voltage THD with non-resistive load", 8.0, "%", source="GB/T 40432—2021 §A.1.1.9")
    _metric(section, "grid_current_dc_component_limit_a", "Grid-current DC-component limit", dc_component_limit, "A", "max(0.5%*Irated,5mA)", source="GB/T 40432—2021 §A.1.1.6")
    _metric(section, "inverter_efficiency_min", "Minimum inverter efficiency", 0.92, "pu", source="GB/T 40432—2021 §A.1.1.7")
    _metric(section, "no_load_loss_limit_w", "No-load loss limit", max(_num(cfg, "system.rated_power_w") * 0.03, 50.0), "W", "max(3%*Prated,50W)", source="GB/T 40432—2021 §A.1.1.8")
    _diag(section, "GBT_INVERTER_EVIDENCE", Status.NOT_EVALUATED, "The calculator now exposes reverse-power compliance requirements but does not simulate THD, dynamic recovery or grid-current DC injection.", "Use the requirements as controller/sensing budgets and verify with the Appendix A test procedures.")
    return section
