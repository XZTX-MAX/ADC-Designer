from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Status(str, Enum):
    PASS = "PASS"
    WARNING = "WARNING"
    FAIL = "FAIL"
    NOT_EVALUATED = "NOT_EVALUATED"


@dataclass(frozen=True)
class Metric:
    key: str
    label: str
    value: float | int | str | None
    unit: str = ""
    formula: str = ""
    inputs: str = ""
    source: str = "calculated"
    status: Status = Status.PASS
    note: str = ""


@dataclass(frozen=True)
class Diagnostic:
    code: str
    scope: str
    status: Status
    message: str
    recommendation: str = ""


@dataclass(frozen=True)
class SamplingChannel:
    name: str
    quantity: str
    adc_module: str
    soc: int
    trigger_source: str
    aperture_delay_s: float | None


@dataclass
class SectionResult:
    name: str
    metrics: list[Metric] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)

    def add_metric(self, **kwargs: Any) -> Metric:
        metric = Metric(**kwargs)
        self.metrics.append(metric)
        return metric

    def add_diagnostic(self, **kwargs: Any) -> Diagnostic:
        diagnostic = Diagnostic(**kwargs)
        self.diagnostics.append(diagnostic)
        return diagnostic

    def metric_value(self, key: str) -> float | int | str | None:
        for metric in self.metrics:
            if metric.key == key:
                return metric.value
        raise KeyError(f"Metric not found: {key}")


@dataclass
class DesignResult:
    profile_name: str
    sections: dict[str, SectionResult] = field(default_factory=dict)
    assumptions: list[dict[str, str]] = field(default_factory=list)

    def add_section(self, section: SectionResult) -> None:
        self.sections[section.name] = section

    @property
    def diagnostics(self) -> list[Diagnostic]:
        output: list[Diagnostic] = []
        for section in self.sections.values():
            output.extend(section.diagnostics)
        return output

    def summary_status(self, section_name: str) -> Status:
        section = self.sections[section_name]
        statuses = [d.status for d in section.diagnostics]
        if Status.FAIL in statuses:
            return Status.FAIL
        if Status.WARNING in statuses or Status.NOT_EVALUATED in statuses:
            return Status.WARNING
        return Status.PASS
