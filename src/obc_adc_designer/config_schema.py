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


def _section_for(key: str) -> str:
    return key.split(".", 1)[0].replace("_", " ").title()


def _name_for(key: str) -> str:
    return key.rsplit(".", 1)[-1].replace("_", " ").title()


def _field(
    key: str,
    data_type: DataType,
    *,
    blank_mode: BlankMode = BlankMode.OMIT,
    required_when: str = "",
    allowed_values: tuple[str, ...] = (),
    template_default: Any = None,
    pattern: Pattern[str] | None = None,
) -> FieldSpec:
    return FieldSpec(
        key=key,
        section=_section_for(key),
        name=_name_for(key),
        data_type=data_type,
        blank_mode=blank_mode,
        required_when=required_when,
        allowed_values=allowed_values,
        template_default=template_default,
        pattern=pattern,
    )


_REQUIRED_KEYS = {
    "metadata.profile",
    "system.rated_power_w",
    "system.peak_power_w",
    "system.vac_min_rms_v",
    "system.vac_max_rms_v",
    "system.vdc_min_v",
    "system.vdc_max_v",
    "system.efficiency_min",
    "system.power_factor_min",
    "system.switching_frequency_hz",
    "adc.resolution_bits",
    "adc.reference_voltage_v",
    "adc.sysclk_hz",
    "control.iac_loop_bandwidth_hz",
    "control.idc_loop_bandwidth_hz",
    "control.vdc_loop_bandwidth_hz",
    "control.pll_bandwidth_hz",
}

_NULLABLE_KEYS = {
    "adc.acquisition.exact_sample_capacitance_f",
    "adc.acquisition.exact_source_resistance_ohm",
    "adc.acquisition.exact_switch_resistance_ohm",
    "channels.iac.delay.adc_s",
    "channels.iac.delay.isr_s",
    "channels.iac.delay.pwm_s",
    "channels.idc.amplifier.input_offset_v",
    "channels.idc.delay.adc_s",
    "channels.idc.delay.isolation_s",
    "channels.idc.delay.isr_s",
    "channels.idc.delay.pwm_s",
    "channels.vac.delay.adc_s",
    "channels.vac.delay.isr_s",
    "channels.vac.delay.pwm_s",
    "channels.vdc.delay.adc_s",
    "channels.vdc.delay.isolation_s",
    "channels.vdc.delay.isr_s",
    "channels.vdc.delay.pwm_s",
    "channels.vdc.delay.sensor_s",
    "channels.vdc.direct_hv.bandwidth_hz",
    "standard_profile.safety.actual_isolation_withstand_rms_v",
    "standard_profile.safety.udmax_v",
}

_STANDARD_REQUIRED_KEYS = {
    "standard_profile.name",
    "standard_profile.scope.max_dc_output_v",
    "standard_profile.ac_input.single_phase_nominal_v",
    "standard_profile.ac_input.three_phase_line_nominal_v",
    "standard_profile.ac_input.voltage_tolerance_percent",
    "standard_profile.ac_input.nominal_frequency_hz",
    "standard_profile.ac_input.frequency_tolerance_hz",
    "standard_profile.current.startup_inrush_peak_ratio_max",
    "standard_profile.dc_output.voltage_error_percent_max",
    "standard_profile.dc_output.current_error_threshold_a",
    "standard_profile.dc_output.current_error_above_threshold_percent",
    "standard_profile.dc_output.current_error_at_or_below_threshold_a",
    "standard_profile.dc_output.voltage_ripple_factor_percent_max",
    "standard_profile.power_quality.pf_rated_min",
    "standard_profile.power_quality.pf_half_load_min",
    "standard_profile.power_quality.average_efficiency_min",
    "standard_profile.design_allocation.sensing_error_budget_fraction",
}

_STRING_KEYS = (
    "metadata.description",
    "metadata.profile",
    "metadata.version",
    "channels.iac.reconstruction",
    "channels.vac.measurement_basis",
    "channels.vdc.architecture",
    "sampling.trigger_position",
    "sampling.trigger_source",
    "standard_profile.name",
    "standard_profile.power_quality.efficiency_class",
    "standard_profile.source_document",
)

_INT_KEYS = (
    "adc.existing_sample_window_cycles",
    "adc.resolution_bits",
    "sampling.samples_per_pwm_period",
    "standard_profile.emc.eft_level",
    "standard_profile.power_quality.efficiency_voltage_points",
    "standard_profile.power_quality.efficiency_warmup_min",
    "system.phase_count",
)

_BOOL_KEYS = (
    "sampling.simultaneous_required",
    "standard_profile.enabled",
    "system.bidirectional",
)

_LIST_STRING_KEYS = (
    "channels.iac.phase_names",
    "channels.vac.phase_names",
)

_FLOAT_KEYS = (
    "adc.acquisition.exact_sample_capacitance_f",
    "adc.acquisition.exact_source_resistance_ohm",
    "adc.acquisition.exact_switch_resistance_ohm",
    "adc.acquisition.safety_factor",
    "adc.acquisition.simplified_source_resistance_ohm",
    "adc.acquisition.simplified_total_capacitance_f",
    "adc.acquisition.target_error_lsb",
    "adc.minimum_sample_window_s",
    "adc.reference_voltage_v",
    "adc.sysclk_hz",
    "channels.iac.accuracy_target_percent_fs",
    "channels.iac.adc_headroom_high_v",
    "channels.iac.adc_headroom_low_v",
    "channels.iac.delay.adc_s",
    "channels.iac.delay.isolation_s",
    "channels.iac.delay.isr_s",
    "channels.iac.delay.pwm_s",
    "channels.iac.delay.sensor_s",
    "channels.iac.filter.capacitor_f",
    "channels.iac.filter.resistor_ohm",
    "channels.iac.hall.front_end_gain",
    "channels.iac.hall.sensor_bandwidth_hz",
    "channels.iac.hall.sensor_sensitivity_v_per_a",
    "channels.iac.hall.sensor_zero_output_v",
    "channels.iac.range_margin",
    "channels.idc.accuracy_target_percent_fs",
    "channels.idc.adc_headroom_high_v",
    "channels.idc.adc_headroom_low_v",
    "channels.idc.amplifier.bandwidth_hz",
    "channels.idc.amplifier.input_clip_v",
    "channels.idc.amplifier.input_offset_v",
    "channels.idc.amplifier.input_range_utilization",
    "channels.idc.amplifier.reference_voltage_v",
    "channels.idc.delay.adc_s",
    "channels.idc.delay.isolation_s",
    "channels.idc.delay.isr_s",
    "channels.idc.delay.pwm_s",
    "channels.idc.delay.sensor_s",
    "channels.idc.filter.capacitor_f",
    "channels.idc.filter.resistor_ohm",
    "channels.idc.range_margin",
    "channels.idc.shunt.resistance_ohm",
    "channels.vac.accuracy_target_percent_fs",
    "channels.vac.delay.adc_s",
    "channels.vac.delay.isolation_s",
    "channels.vac.delay.isr_s",
    "channels.vac.delay.pwm_s",
    "channels.vac.delay.sensor_s",
    "channels.vac.divider.high_side_total_ohm",
    "channels.vac.divider.low_side_ohm",
    "channels.vac.filter.capacitor_f",
    "channels.vac.filter.resistor_ohm",
    "channels.vac.isolation.bandwidth_hz",
    "channels.vac.isolation.gain_v_per_v",
    "channels.vac.isolation.input_range_utilization",
    "channels.vac.isolation.linear_input_abs_max_v",
    "channels.vac.isolation.reference_voltage_v",
    "channels.vac.range_margin",
    "channels.vdc.accuracy_target_percent_fs",
    "channels.vdc.delay.adc_s",
    "channels.vdc.delay.isolation_s",
    "channels.vdc.delay.isr_s",
    "channels.vdc.delay.pwm_s",
    "channels.vdc.delay.sensor_s",
    "channels.vdc.direct_hv.bandwidth_hz",
    "channels.vdc.direct_hv.high_voltage_clip_v",
    "channels.vdc.direct_hv.reference_voltage_v",
    "channels.vdc.divider.low_side_ohm",
    "channels.vdc.divider.target_sense_v",
    "channels.vdc.filter.capacitor_f",
    "channels.vdc.filter.resistor_ohm",
    "channels.vdc.range_margin",
    "control.iac_loop_bandwidth_hz",
    "control.idc_loop_bandwidth_hz",
    "control.line_frequency_hz",
    "control.pll_bandwidth_hz",
    "control.vdc_loop_bandwidth_hz",
    "environment.temperature_max_c",
    "environment.temperature_min_c",
    "environment.temperature_span_c",
    "sampling.max_current_slew_rate_a_per_s",
    "sampling.max_skew_error_percent_fs",
    "sampling.max_voltage_slew_rate_v_per_s",
    "sampling.maximum_channel_skew_s",
    "standard_profile.ac_input.frequency_tolerance_hz",
    "standard_profile.ac_input.nominal_frequency_hz",
    "standard_profile.ac_input.single_phase_nominal_v",
    "standard_profile.ac_input.three_phase_line_nominal_v",
    "standard_profile.ac_input.three_phase_phase_deviation_deg",
    "standard_profile.ac_input.voltage_tolerance_percent",
    "standard_profile.current.startup_inrush_peak_ratio_max",
    "standard_profile.dc_output.current_error_above_threshold_percent",
    "standard_profile.dc_output.current_error_at_or_below_threshold_a",
    "standard_profile.dc_output.current_error_threshold_a",
    "standard_profile.dc_output.startup_current_overshoot_percent_max",
    "standard_profile.dc_output.startup_voltage_overshoot_percent_max",
    "standard_profile.dc_output.voltage_error_percent_max",
    "standard_profile.dc_output.voltage_ripple_factor_percent_max",
    "standard_profile.design_allocation.sensing_error_budget_fraction",
    "standard_profile.emc.eft_repetition_hz",
    "standard_profile.emc.radiated_immunity_max_hz",
    "standard_profile.emc.radiated_immunity_min_hz",
    "standard_profile.emc.radiated_immunity_v_per_m",
    "standard_profile.emc.surge_common_mode_v",
    "standard_profile.emc.surge_differential_v",
    "standard_profile.environment.altitude_max_m",
    "standard_profile.environment.operating_temperature_max_air_c",
    "standard_profile.environment.operating_temperature_max_liquid_c",
    "standard_profile.environment.operating_temperature_min_c",
    "standard_profile.environment.relative_humidity_max_percent",
    "standard_profile.environment.relative_humidity_min_percent",
    "standard_profile.environment.storage_temperature_max_c",
    "standard_profile.environment.storage_temperature_min_c",
    "standard_profile.inverter.efficiency_min",
    "standard_profile.inverter.frequency_nominal_hz",
    "standard_profile.inverter.frequency_tolerance_hz",
    "standard_profile.inverter.grid_current_dc_component_min_a",
    "standard_profile.inverter.grid_current_dc_component_percent",
    "standard_profile.inverter.load_step_voltage_deviation_percent",
    "standard_profile.inverter.recovery_time_max_ms",
    "standard_profile.inverter.single_phase_nominal_v",
    "standard_profile.inverter.three_phase_line_nominal_v",
    "standard_profile.inverter.voltage_accuracy_percent",
    "standard_profile.inverter.voltage_thd_non_resistive_percent",
    "standard_profile.inverter.voltage_thd_resistive_percent",
    "standard_profile.power_quality.average_efficiency_min",
    "standard_profile.power_quality.pf_half_load_min",
    "standard_profile.power_quality.pf_rated_min",
    "standard_profile.safety.actual_isolation_withstand_rms_v",
    "standard_profile.safety.udmax_v",
    "standard_profile.scope.max_dc_output_v",
    "standard_profile.test_equipment.ripple_scope_bandwidth_hz",
    "standard_profile.test_equipment.ripple_scope_timebase_min_s_per_div",
    "system.default_range_margin",
    "system.efficiency_min",
    "system.overload_factor",
    "system.peak_power_w",
    "system.phase_unbalance_factor",
    "system.power_factor_min",
    "system.rated_power_w",
    "system.switching_frequency_hz",
    "system.vac_max_rms_v",
    "system.vac_min_rms_v",
    "system.vac_nom_rms_v",
    "system.vdc_max_v",
    "system.vdc_min_v",
    "system.vdc_nom_v",
    "targets.bandwidth_multiplier",
    "targets.iac_phase_loss_deg",
    "targets.idc_phase_loss_deg",
    "targets.phase_current_gain_mismatch_percent",
    "targets.phase_voltage_gain_mismatch_percent",
    "targets.phase_zero_code_mismatch",
    "targets.vac_line_phase_error_deg",
    "targets.vac_pll_phase_loss_deg",
    "targets.vdc_phase_loss_deg",
)

_ALLOWED_VALUES = {
    "channels.iac.reconstruction": ("none",),
    "channels.vac.measurement_basis": ("phase_to_neutral", "line_to_line"),
    "channels.vdc.architecture": ("direct_hv", "divider"),
    "sampling.trigger_position": ("PWM_CENTER",),
    "system.ac_voltage_basis": ("single_phase", "line_to_line", "phase_to_neutral"),
}

_STATIC_TYPES: dict[str, DataType] = {
    **{key: "str" for key in _STRING_KEYS},
    **{key: "int" for key in _INT_KEYS},
    **{key: "bool" for key in _BOOL_KEYS},
    **{key: "list[str]" for key in _LIST_STRING_KEYS},
    **{key: "float" for key in _FLOAT_KEYS},
    "system.ac_voltage_basis": "str",
}


def _blank_mode_for(key: str) -> BlankMode:
    if key in _REQUIRED_KEYS or key in _STANDARD_REQUIRED_KEYS:
        return BlankMode.ERROR
    if key in _NULLABLE_KEYS:
        return BlankMode.NONE
    return BlankMode.OMIT


def _required_when_for(key: str) -> str:
    return "standard_profile.enabled" if key in _STANDARD_REQUIRED_KEYS else ""


_IAC_OVERRIDE_LEAVES = (
    "accuracy_target_percent_fs",
    "adc_headroom_high_v",
    "adc_headroom_low_v",
    "filter.capacitor_f",
    "filter.resistor_ohm",
    "hall.front_end_gain",
    "hall.sensor_bandwidth_hz",
    "hall.sensor_sensitivity_v_per_a",
    "hall.sensor_zero_output_v",
    "range_margin",
)
_VAC_OVERRIDE_LEAVES = (
    "accuracy_target_percent_fs",
    "divider.high_side_total_ohm",
    "divider.low_side_ohm",
    "filter.capacitor_f",
    "filter.resistor_ohm",
    "isolation.bandwidth_hz",
    "isolation.gain_v_per_v",
    "isolation.input_range_utilization",
    "isolation.linear_input_abs_max_v",
    "isolation.reference_voltage_v",
    "range_margin",
)


def _override_specs(channel: str, phases: str, leaves: tuple[str, ...]) -> tuple[FieldSpec, ...]:
    return tuple(
        _field(
            f"channels.{channel}.phase_overrides.{{phase}}.{leaf}",
            "float",
            pattern=re.compile(
                rf"channels\.{channel}\.phase_overrides\.(?:{phases})\.{re.escape(leaf)}"
            ),
        )
        for leaf in leaves
    )


FIELD_SPECS = (
    tuple(
        _field(
            key,
            data_type,
            blank_mode=_blank_mode_for(key),
            required_when=_required_when_for(key),
            allowed_values=_ALLOWED_VALUES.get(key, ()),
        )
        for key, data_type in _STATIC_TYPES.items()
    )
    + _override_specs("iac", "A|B|C", _IAC_OVERRIDE_LEAVES)
    + _override_specs("vac", "A|B|C|AB|BC|CA", _VAC_OVERRIDE_LEAVES)
)

EXACT_FIELD_SPECS = {spec.key: spec for spec in FIELD_SPECS if spec.pattern is None}
PATTERN_FIELD_SPECS = tuple(spec for spec in FIELD_SPECS if spec.pattern is not None)


def field_spec_for_key(key: str) -> FieldSpec | None:
    exact = EXACT_FIELD_SPECS.get(key)
    if exact is not None:
        return exact
    return next((spec for spec in PATTERN_FIELD_SPECS if spec.matches(key)), None)


def template_value_for(spec: FieldSpec) -> Any:
    return spec.template_default
