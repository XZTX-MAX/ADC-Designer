from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ComponentRequirement:
    category: str
    parameters: dict[str, float | int | str | bool]


@dataclass(frozen=True)
class ComponentCandidate:
    part_number: str
    manufacturer: str
    parameters: dict[str, float | int | str | bool]
    source_id: str = ""


class ComponentProvider(Protocol):
    """Reserved interface for a future company-product-database MCP adapter."""

    def search(self, requirement: ComponentRequirement) -> list[ComponentCandidate]:
        ...


class McuProfile(Protocol):
    """Reserved interface for future non-F29H85x ADC timing/resource models."""

    @property
    def name(self) -> str:
        ...

    def adc_defaults(self) -> dict[str, float | int | None]:
        ...
