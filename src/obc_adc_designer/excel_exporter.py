from __future__ import annotations

from pathlib import Path
from typing import Any

from artifact_tool import SpreadsheetFile, Workbook

from .models import DesignResult, Status


_STATUS_FILL = {
    Status.PASS.value: "#DCFCE7",
    Status.WARNING.value: "#FEF3C7",
    Status.FAIL.value: "#FEE2E2",
    Status.NOT_EVALUATED.value: "#E5E7EB",
}


def _style_header(rng: Any) -> None:
    rng.format = {
        "fill": "#B91C1C",
        "font": {"bold": True, "color": "#FFFFFF"},
        "horizontal_alignment": "center",
        "vertical_alignment": "center",
        "wrap_text": True,
    }


def _style_title(rng: Any) -> None:
    rng.format = {
        "fill": "#7F1D1D",
        "font": {"bold": True, "color": "#FFFFFF", "size": 16},
        "vertical_alignment": "center",
    }


def _format_sheet(sheet: Any, used_range: str, freeze_rows: int = 1) -> None:
    sheet.freeze_panes.freeze_rows(freeze_rows)
    sheet.get_range(used_range).format.wrap_text = True
    sheet.get_range(used_range).format.vertical_alignment = "center"
    sheet.get_range(used_range).format.autofit_rows()


def export_excel(result: DesignResult, cfg: dict[str, Any], output_path: str | Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook.create()

    summary = wb.worksheets.add("00_Summary")
    summary.merge_cells("A1:H1")
    summary.get_range("A1").values = [[f"OBC ADC Sensing Design — {result.profile_name}"]]
    _style_title(summary.get_range("A1:H1"))
    summary.get_range("A3:H3").values = [["Section", "Status", "Metric Count", "FAIL", "WARNING", "NOT EVALUATED", "Purpose", "Engineering Note"]]
    _style_header(summary.get_range("A3:H3"))

    summary_rows: list[list[Any]] = []
    for section_name, section in result.sections.items():
        statuses = [d.status.value for d in section.diagnostics]
        section_status = result.summary_status(section_name).value
        summary_rows.append([
            section_name,
            section_status,
            len(section.metrics),
            statuses.count(Status.FAIL.value),
            statuses.count(Status.WARNING.value),
            statuses.count(Status.NOT_EVALUATED.value),
            "Calculation / validation section",
            section.diagnostics[0].message if section.diagnostics else "No diagnostic raised",
        ])
    if summary_rows:
        summary.get_range(f"A4:H{3+len(summary_rows)}").values = summary_rows
        summary.tables.add(f"A3:H{3+len(summary_rows)}", True, "SummaryTable")
        status_range = summary.get_range(f"B4:B{3+len(summary_rows)}")
        for status, fill in _STATUS_FILL.items():
            status_range.conditional_formats.add_custom(f'=B4="{status}"', {"fill": fill})
    summary.get_range("J2:K2").values = [["KPI", "Value"]]
    _style_header(summary.get_range("J2:K2"))
    summary.get_range("J3:J6").values = [["FAIL diagnostics"], ["WARNING diagnostics"], ["Not evaluated"], ["Sections"]]
    summary.get_range("K3:K6").formulas = [["=SUM(D4:D200)"], ["=SUM(E4:E200)"], ["=SUM(F4:F200)"], ["=COUNTA(A4:A200)"]]
    summary.get_range("A1:K30").format.column_width = 16
    summary.get_range("A:A").format.column_width = 24
    summary.get_range("G:H").format.column_width = 32
    _format_sheet(summary, "A1:K30", 3)

    inputs = wb.worksheets.add("01_Input_Config")
    inputs.get_range("A1:D1").values = [["Path", "Value", "Type", "Source/Qualification"]]
    _style_header(inputs.get_range("A1:D1"))
    flattened: list[list[Any]] = []

    def flatten(prefix: str, value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                flatten(f"{prefix}.{key}" if prefix else key, child)
        elif isinstance(value, list):
            flattened.append([prefix, str(value), "list", "user/profile input"])
        else:
            flattened.append([prefix, value, type(value).__name__, "user/profile input"])

    flatten("", cfg)
    inputs.get_range(f"A2:D{1+len(flattened)}").values = flattened
    inputs.tables.add(f"A1:D{1+len(flattened)}", True, "InputConfigTable")
    inputs.get_range("A:A").format.column_width = 48
    inputs.get_range("B:B").format.column_width = 24
    inputs.get_range("D:D").format.column_width = 26
    _format_sheet(inputs, f"A1:D{1+len(flattened)}")

    formula_rows: list[list[Any]] = [["Section", "Key", "Result", "Unit", "Formula", "Inputs", "Source", "Status", "Note"]]
    warning_rows: list[list[Any]] = [["Scope", "Code", "Status", "Message", "Recommendation"]]

    for section_index, (section_name, section) in enumerate(result.sections.items(), start=1):
        safe_name = section_name[:31]
        sheet = wb.worksheets.add(safe_name)
        sheet.get_range("A1:I1").values = [["Key", "Metric", "Value", "Unit", "Formula", "Inputs", "Source", "Status", "Note"]]
        _style_header(sheet.get_range("A1:I1"))
        rows = []
        for metric in section.metrics:
            rows.append([metric.key, metric.label, metric.value, metric.unit, metric.formula, metric.inputs, metric.source, metric.status.value, metric.note])
            formula_rows.append([section_name, metric.key, metric.value, metric.unit, metric.formula, metric.inputs, metric.source, metric.status.value, metric.note])
        if rows:
            end = 1 + len(rows)
            sheet.get_range(f"A2:I{end}").values = rows
            sheet.tables.add(f"A1:I{end}", True, f"MetricsTable{section_index}")
            status_rng = sheet.get_range(f"H2:H{end}")
            for status, fill in _STATUS_FILL.items():
                status_rng.conditional_formats.add_custom(f'=H2="{status}"', {"fill": fill})
        sheet.get_range("A:A").format.column_width = 30
        sheet.get_range("B:B").format.column_width = 34
        sheet.get_range("C:D").format.column_width = 16
        sheet.get_range("E:F").format.column_width = 34
        sheet.get_range("G:I").format.column_width = 24
        _format_sheet(sheet, f"A1:I{max(2,1+len(rows))}")
        for diagnostic in section.diagnostics:
            warning_rows.append([diagnostic.scope, diagnostic.code, diagnostic.status.value, diagnostic.message, diagnostic.recommendation])

    formulas = wb.worksheets.add("90_Formula_Trace")
    formulas.get_range(f"A1:I{len(formula_rows)}").values = formula_rows
    _style_header(formulas.get_range("A1:I1"))
    formulas.tables.add(f"A1:I{len(formula_rows)}", True, "FormulaTraceTable")
    formulas.get_range("A:B").format.column_width = 28
    formulas.get_range("E:F").format.column_width = 38
    formulas.get_range("I:I").format.column_width = 32
    _format_sheet(formulas, f"A1:I{len(formula_rows)}")

    warnings = wb.worksheets.add("80_Warnings")
    warnings.get_range(f"A1:E{len(warning_rows)}").values = warning_rows
    _style_header(warnings.get_range("A1:E1"))
    warnings.tables.add(f"A1:E{len(warning_rows)}", True, "WarningsTable")
    if len(warning_rows) > 1:
        status_rng = warnings.get_range(f"C2:C{len(warning_rows)}")
        for status, fill in _STATUS_FILL.items():
            status_rng.conditional_formats.add_custom(f'=C2="{status}"', {"fill": fill})
    warnings.get_range("A:B").format.column_width = 28
    warnings.get_range("D:E").format.column_width = 54
    _format_sheet(warnings, f"A1:E{len(warning_rows)}")

    assumptions = wb.worksheets.add("70_Assumptions")
    assumptions.get_range("A1:D1").values = [["Parameter/Topic", "Value/Assumption", "Source Type", "Qualification/Action"]]
    _style_header(assumptions.get_range("A1:D1"))
    assumption_rows = [[item.get("topic", ""), item.get("value", ""), item.get("source_type", ""), item.get("qualification", "")] for item in result.assumptions]
    if assumption_rows:
        assumptions.get_range(f"A2:D{1+len(assumption_rows)}").values = assumption_rows
        assumptions.tables.add(f"A1:D{1+len(assumption_rows)}", True, "AssumptionsTable")
    assumptions.get_range("A:D").format.column_width = 34
    _format_sheet(assumptions, f"A1:D{max(2,1+len(assumption_rows))}")

    SpreadsheetFile.export_xlsx(wb).save(str(output_path))
    return output_path
