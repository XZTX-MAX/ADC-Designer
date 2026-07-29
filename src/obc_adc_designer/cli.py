from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from .application import calculate_design
from .config import ConfigError, load_yaml, save_yaml, validate_config


def _default_config_path() -> Path:
    package_root = Path(__file__).resolve().parents[2]
    candidate = package_root / "config" / "pmp23607_default.yaml"
    if candidate.exists():
        return candidate
    return Path.cwd() / "config" / "pmp23607_default.yaml"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="obc-adc", description="Single-/three-phase F29H85x OBC ADC sensing design calculator")
    sub = parser.add_subparsers(dest="command", required=True)

    init_cmd = sub.add_parser("init", help="Create a user-editable YAML configuration from a preset")
    init_cmd.add_argument("--output", default="config/pmp23607_user.yaml")
    init_cmd.add_argument("--preset", default=None, help="Optional explicit preset YAML path")

    calc_cmd = sub.add_parser("calculate", help="Calculate the design and export an Excel report")
    calc_cmd.add_argument("--config", required=True)
    calc_cmd.add_argument("--output", default="results/PMP23607_ADC_Sensing_Design.xlsx")
    calc_cmd.add_argument("--json", default=None, help="Optional JSON summary output")

    validate_cmd = sub.add_parser("validate", help="Validate YAML inputs only")
    validate_cmd.add_argument("--config", required=True)
    return parser


def _json_summary(result) -> dict:
    return {
        "profile": result.profile_name,
        "sections": {
            name: {
                "status": result.summary_status(name).value,
                "metrics": {metric.key: metric.value for metric in section.metrics},
                "diagnostics": [
                    {"code": d.code, "status": d.status.value, "message": d.message, "recommendation": d.recommendation}
                    for d in section.diagnostics
                ],
            }
            for name, section in result.sections.items()
        },
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "init":
            source = Path(args.preset) if args.preset else _default_config_path()
            if not source.exists():
                raise ConfigError(f"Preset not found: {source}")
            destination = Path(args.output)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            print(f"Created configuration: {destination}")
            return 0

        cfg = load_yaml(args.config)
        validate_config(cfg)
        if args.command == "validate":
            print("Configuration is valid.")
            return 0

        result = calculate_design(cfg)
        try:
            from .excel_exporter import export_excel
        except ImportError as exc:
            raise ConfigError("Excel export requires the artifact_tool runtime. Core calculations remain available through the Python API.") from exc
        output = export_excel(result, cfg, args.output)
        print(f"Excel report created: {output}")
        failures = sum(1 for diagnostic in result.diagnostics if diagnostic.status.value == "FAIL")
        warnings = sum(1 for diagnostic in result.diagnostics if diagnostic.status.value == "WARNING")
        not_eval = sum(1 for diagnostic in result.diagnostics if diagnostic.status.value == "NOT_EVALUATED")
        print(f"Diagnostics: FAIL={failures}, WARNING={warnings}, NOT_EVALUATED={not_eval}")
        if args.json:
            json_path = Path(args.json)
            json_path.parent.mkdir(parents=True, exist_ok=True)
            json_path.write_text(json.dumps(_json_summary(result), indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"JSON summary created: {json_path}")
        return 2 if failures else 0
    except (ConfigError, ValueError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
