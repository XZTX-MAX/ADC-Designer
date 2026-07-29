from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml


class ConfigError(ValueError):
    pass


def load_yaml(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"Configuration file does not exist: {path}")
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ConfigError("The YAML root must be a mapping.")
    return data


def save_yaml(data: dict[str, Any], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(data, handle, allow_unicode=True, sort_keys=False)


def require(data: dict[str, Any], dotted_path: str) -> Any:
    current: Any = data
    for token in dotted_path.split("."):
        if not isinstance(current, dict) or token not in current:
            raise ConfigError(f"Missing required parameter: {dotted_path}")
        current = current[token]
    return current


def get(data: dict[str, Any], dotted_path: str, default: Any = None) -> Any:
    current: Any = data
    for token in dotted_path.split("."):
        if not isinstance(current, dict) or token not in current:
            return default
        current = current[token]
    return current


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _validate_positive(data: dict[str, Any], paths: list[str]) -> None:
    for item in paths:
        value = float(require(data, item))
        if value <= 0:
            raise ConfigError(f"{item} must be greater than zero.")


def validate_config(data: dict[str, Any]) -> None:
    required = [
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
    ]
    for item in required:
        require(data, item)

    _validate_positive(
        data,
        [
            "system.rated_power_w",
            "system.peak_power_w",
            "system.vac_min_rms_v",
            "system.vac_max_rms_v",
            "system.vdc_min_v",
            "system.vdc_max_v",
            "system.switching_frequency_hz",
            "adc.reference_voltage_v",
            "adc.sysclk_hz",
        ],
    )

    for item in ["system.efficiency_min", "system.power_factor_min"]:
        value = float(require(data, item))
        if not 0 < value <= 1:
            raise ConfigError(f"{item} must be in the interval (0, 1].")

    if float(require(data, "system.vac_min_rms_v")) >= float(require(data, "system.vac_max_rms_v")):
        raise ConfigError("VAC minimum must be lower than VAC maximum.")
    if float(require(data, "system.vdc_min_v")) >= float(require(data, "system.vdc_max_v")):
        raise ConfigError("VDC minimum must be lower than VDC maximum.")

    phase_count = int(get(data, "system.phase_count", 1))
    if phase_count not in (1, 3):
        raise ConfigError("system.phase_count must be 1 or 3.")

    if phase_count == 1:
        basis = str(get(data, "system.ac_voltage_basis", "single_phase"))
        if basis not in ("single_phase", "line_to_line", "phase_to_neutral"):
            raise ConfigError("Unsupported system.ac_voltage_basis for single-phase configuration.")
    else:
        basis = str(get(data, "system.ac_voltage_basis", "line_to_line"))
        if basis not in ("line_to_line", "phase_to_neutral"):
            raise ConfigError("Three-phase system.ac_voltage_basis must be line_to_line or phase_to_neutral.")
        unbalance = float(get(data, "system.phase_unbalance_factor", 1.0))
        if unbalance < 1.0:
            raise ConfigError("system.phase_unbalance_factor must be at least 1.0.")

        current_phases = get(data, "channels.iac.phase_names", ["A", "B", "C"])
        if not isinstance(current_phases, list) or len(current_phases) not in (2, 3):
            raise ConfigError("channels.iac.phase_names must contain two or three phase labels for a three-phase design.")
        if len(set(str(x) for x in current_phases)) != len(current_phases):
            raise ConfigError("channels.iac.phase_names must be unique.")

        vac_basis = str(get(data, "channels.vac.measurement_basis", "phase_to_neutral"))
        if vac_basis not in ("phase_to_neutral", "line_to_line"):
            raise ConfigError("channels.vac.measurement_basis must be phase_to_neutral or line_to_line.")
        voltage_names = get(
            data,
            "channels.vac.phase_names",
            ["A", "B", "C"] if vac_basis == "phase_to_neutral" else ["AB", "BC", "CA"],
        )
        if not isinstance(voltage_names, list) or len(voltage_names) not in (2, 3):
            raise ConfigError("channels.vac.phase_names must contain two or three voltage-channel labels.")

        simultaneous_required = bool(get(data, "sampling.simultaneous_required", True))
        assignments = get(data, "sampling.channels", [])
        if simultaneous_required and not assignments:
            raise ConfigError("Three-phase simultaneous sampling requires sampling.channels assignments.")
        if assignments and not isinstance(assignments, list):
            raise ConfigError("sampling.channels must be a list.")
        assignment_names: list[str] = []
        for item in assignments:
            if not isinstance(item, dict):
                raise ConfigError("Each sampling.channels item must be a mapping.")
            name = str(item.get("name", ""))
            if not name:
                raise ConfigError("Each sampling channel requires a non-empty name.")
            assignment_names.append(name)
            if "adc_module" not in item:
                raise ConfigError(f"Sampling channel {name} is missing adc_module.")
            delay = item.get("aperture_delay_s")
            if delay is not None and float(delay) < 0:
                raise ConfigError(f"Sampling channel {name} aperture_delay_s must be non-negative.")
        if len(assignment_names) != len(set(assignment_names)):
            raise ConfigError("sampling.channels names must be unique.")


    if bool(get(data, "standard_profile.enabled", False)):
        standard_required = [
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
        ]
        for item in standard_required:
            require(data, item)

        tolerance = float(require(data, "standard_profile.ac_input.voltage_tolerance_percent"))
        if not 0 < tolerance < 100:
            raise ConfigError("standard_profile.ac_input.voltage_tolerance_percent must be between 0 and 100.")
        allocation = float(require(data, "standard_profile.design_allocation.sensing_error_budget_fraction"))
        if not 0 < allocation <= 1:
            raise ConfigError("standard_profile.design_allocation.sensing_error_budget_fraction must be in (0, 1].")
        for item in [
            "standard_profile.power_quality.pf_rated_min",
            "standard_profile.power_quality.pf_half_load_min",
            "standard_profile.power_quality.average_efficiency_min",
        ]:
            value = float(require(data, item))
            if not 0 < value <= 1:
                raise ConfigError(f"{item} must be in the interval (0, 1].")

        dip_tests = get(data, "standard_profile.voltage_dip_tests", [])
        if not isinstance(dip_tests, list):
            raise ConfigError("standard_profile.voltage_dip_tests must be a list.")
        for index, item in enumerate(dip_tests):
            if not isinstance(item, dict):
                raise ConfigError(f"standard_profile.voltage_dip_tests[{index}] must be a mapping.")
            for key in ("voltage_percent", "duration_cycles_50hz", "functional_status"):
                if key not in item:
                    raise ConfigError(f"standard_profile.voltage_dip_tests[{index}] is missing {key}.")
