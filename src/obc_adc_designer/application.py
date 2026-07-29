from __future__ import annotations

from typing import Any

from .calculators import (
    analog_filter_metrics,
    calculate_adc_timing,
    calculate_delay_budget,
    calculate_error_budget,
    calculate_iac_hall,
    calculate_iac_hall_phase,
    calculate_idc_shunt,
    calculate_phase_channel_plan,
    calculate_phase_matching,
    calculate_synchronous_sampling,
    calculate_system_rating,
    calculate_vac,
    calculate_vac_phase,
    calculate_vdc,
)
from .config import get, validate_config
from .models import DesignResult


def _phase_names(cfg: dict[str, Any], channel: str, default: list[str]) -> list[str]:
    return [str(x) for x in get(cfg, f"channels.{channel}.phase_names", default)]


def calculate_design(cfg: dict[str, Any]) -> DesignResult:
    validate_config(cfg)
    result = DesignResult(profile_name=str(get(cfg, "metadata.profile", "unnamed")))
    result.assumptions = list(get(cfg, "assumptions", []))

    system = calculate_system_rating(cfg)
    result.add_section(system)
    iac_design = float(system.metric_value("iac_design_peak_a"))
    idc_design = float(system.metric_value("idc_design_peak_a"))
    idc_cont = float(system.metric_value("idc_continuous_max_a"))
    phase_count = int(get(cfg, "system.phase_count", 1))

    result.add_section(calculate_phase_channel_plan(cfg))

    fsw = float(get(cfg, "system.switching_frequency_hz"))
    kbw = float(get(cfg, "targets.bandwidth_multiplier", 5.0))

    if phase_count == 1:
        result.add_section(calculate_iac_hall(cfg, iac_design))
        result.add_section(calculate_vac(cfg))
        result.add_section(
            analog_filter_metrics(
                section_name="21_IAC_Filter",
                resistor_ohm=float(get(cfg, "channels.iac.filter.resistor_ohm")),
                capacitor_f=float(get(cfg, "channels.iac.filter.capacitor_f")),
                loop_bw_hz=float(get(cfg, "control.iac_loop_bandwidth_hz")),
                switching_hz=fsw,
                phase_limit_deg=float(get(cfg, "targets.iac_phase_loss_deg", 15.0)),
                bandwidth_multiplier=kbw,
                sensor_bandwidth_hz=float(get(cfg, "channels.iac.hall.sensor_bandwidth_hz")),
            )
        )
        result.add_section(
            analog_filter_metrics(
                section_name="42_VAC_Filter",
                resistor_ohm=float(get(cfg, "channels.vac.filter.resistor_ohm")),
                capacitor_f=float(get(cfg, "channels.vac.filter.capacitor_f")),
                loop_bw_hz=float(get(cfg, "control.pll_bandwidth_hz")),
                switching_hz=fsw,
                phase_limit_deg=float(get(cfg, "targets.vac_pll_phase_loss_deg", 5.0)),
                bandwidth_multiplier=kbw,
                sensor_bandwidth_hz=float(get(cfg, "channels.vac.isolation.bandwidth_hz")),
            )
        )
    else:
        iac_names = _phase_names(cfg, "iac", ["A", "B", "C"])
        vac_basis = str(get(cfg, "channels.vac.measurement_basis", "phase_to_neutral"))
        vac_default = ["A", "B", "C"] if vac_basis == "phase_to_neutral" else ["AB", "BC", "CA"]
        vac_names = _phase_names(cfg, "vac", vac_default)
        iac_sections = {name: calculate_iac_hall_phase(cfg, name, iac_design) for name in iac_names}
        vac_sections = {name: calculate_vac_phase(cfg, name) for name in vac_names}
        for section in iac_sections.values():
            result.add_section(section)
        for name in iac_names:
            phase_cfg = get(cfg, f"channels.iac.phase_overrides.{name}", {}) or {}
            base_r = float(phase_cfg.get("filter", {}).get("resistor_ohm", get(cfg, "channels.iac.filter.resistor_ohm")))
            base_c = float(phase_cfg.get("filter", {}).get("capacitor_f", get(cfg, "channels.iac.filter.capacitor_f")))
            sensor_bw = float(phase_cfg.get("hall", {}).get("sensor_bandwidth_hz", get(cfg, "channels.iac.hall.sensor_bandwidth_hz")))
            result.add_section(
                analog_filter_metrics(
                    section_name=f"21_IAC_{name}_Filter",
                    resistor_ohm=base_r,
                    capacitor_f=base_c,
                    loop_bw_hz=float(get(cfg, "control.iac_loop_bandwidth_hz")),
                    switching_hz=fsw,
                    phase_limit_deg=float(get(cfg, "targets.iac_phase_loss_deg", 15.0)),
                    bandwidth_multiplier=kbw,
                    sensor_bandwidth_hz=sensor_bw,
                )
            )
        for section in vac_sections.values():
            result.add_section(section)
        for name in vac_names:
            phase_cfg = get(cfg, f"channels.vac.phase_overrides.{name}", {}) or {}
            base_r = float(phase_cfg.get("filter", {}).get("resistor_ohm", get(cfg, "channels.vac.filter.resistor_ohm")))
            base_c = float(phase_cfg.get("filter", {}).get("capacitor_f", get(cfg, "channels.vac.filter.capacitor_f")))
            sensor_bw = float(phase_cfg.get("isolation", {}).get("bandwidth_hz", get(cfg, "channels.vac.isolation.bandwidth_hz")))
            result.add_section(
                analog_filter_metrics(
                    section_name=f"42_VAC_{name}_Filter",
                    resistor_ohm=base_r,
                    capacitor_f=base_c,
                    loop_bw_hz=float(get(cfg, "control.pll_bandwidth_hz")),
                    switching_hz=fsw,
                    phase_limit_deg=float(get(cfg, "targets.vac_pll_phase_loss_deg", 5.0)),
                    bandwidth_multiplier=kbw,
                    sensor_bandwidth_hz=sensor_bw,
                )
            )
        result.add_section(calculate_phase_matching(cfg, iac_sections, vac_sections))
        result.add_section(calculate_synchronous_sampling(cfg, iac_design))

    result.add_section(calculate_idc_shunt(cfg, idc_design, idc_cont))
    result.add_section(calculate_vdc(cfg))

    result.add_section(
        analog_filter_metrics(
            section_name="31_IDC_Filter",
            resistor_ohm=float(get(cfg, "channels.idc.filter.resistor_ohm")),
            capacitor_f=float(get(cfg, "channels.idc.filter.capacitor_f")),
            loop_bw_hz=float(get(cfg, "control.idc_loop_bandwidth_hz")),
            switching_hz=fsw,
            phase_limit_deg=float(get(cfg, "targets.idc_phase_loss_deg", 15.0)),
            bandwidth_multiplier=kbw,
            sensor_bandwidth_hz=float(get(cfg, "channels.idc.amplifier.bandwidth_hz")),
        )
    )
    result.add_section(
        analog_filter_metrics(
            section_name="43_VDC_Filter",
            resistor_ohm=float(get(cfg, "channels.vdc.filter.resistor_ohm")),
            capacitor_f=float(get(cfg, "channels.vdc.filter.capacitor_f")),
            loop_bw_hz=float(get(cfg, "control.vdc_loop_bandwidth_hz")),
            switching_hz=fsw,
            phase_limit_deg=float(get(cfg, "targets.vdc_phase_loss_deg", 5.0)),
            bandwidth_multiplier=kbw,
            sensor_bandwidth_hz=None if get(cfg, "channels.vdc.direct_hv.bandwidth_hz") is None else float(get(cfg, "channels.vdc.direct_hv.bandwidth_hz")),
        )
    )

    result.add_section(calculate_adc_timing(cfg))
    result.add_section(calculate_delay_budget(cfg, "iac", float(get(cfg, "control.iac_loop_bandwidth_hz")), float(get(cfg, "targets.iac_phase_loss_deg", 15.0))))
    result.add_section(calculate_delay_budget(cfg, "idc", float(get(cfg, "control.idc_loop_bandwidth_hz")), float(get(cfg, "targets.idc_phase_loss_deg", 15.0))))
    result.add_section(calculate_delay_budget(cfg, "vac", float(get(cfg, "control.pll_bandwidth_hz")), float(get(cfg, "targets.vac_pll_phase_loss_deg", 5.0))))
    result.add_section(calculate_delay_budget(cfg, "vdc", float(get(cfg, "control.vdc_loop_bandwidth_hz")), float(get(cfg, "targets.vdc_phase_loss_deg", 5.0))))

    for channel in ("iac", "idc", "vac", "vdc"):
        result.add_section(calculate_error_budget(cfg, channel))
    return result
