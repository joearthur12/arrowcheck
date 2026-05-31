from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape
from pydantic import BaseModel, Field

from arrowcheck.batch import BatchRecordResult, BatchSummary

LIMITATIONS_NOTE = (
    "ArrowCheck performs deterministic structural linting and conservative "
    "exception classification. It does not prove that every structurally valid "
    "mechanism is chemically plausible."
)
TRUNCATION_NOTE = (
    "The invalid-record table is truncated. Use --output results.jsonl to "
    "inspect every processed row."
)


class ErrorCategoryView(BaseModel):
    code: str
    count: int
    percentage_label: str
    bar_width_percent: float


class DiagnosticIssueView(BaseModel):
    code: str
    severity: str
    stage: str
    message: str
    suggested_fix: str | None = None
    atom_map_numbers: list[int] = Field(default_factory=list)
    step_index: int | None = None
    arrow_index: int | None = None
    raw_exception_type: str | None = None
    raw_exception_message: str | None = None
    details_json: str


class InvalidRecordView(BaseModel):
    line_number: int
    case_id: str
    primary_error_code: str
    primary_message: str
    original_mechsmiles: str
    metadata_json: str
    raw_row_text: str | None = None
    issues: list[DiagnosticIssueView] = Field(default_factory=list)


class BatchReportView(BaseModel):
    total_records: int
    valid_records: int
    invalid_records: int
    pass_rate_label: str
    error_categories: list[ErrorCategoryView] = Field(default_factory=list)
    invalid_rows: list[InvalidRecordView] = Field(default_factory=list)
    omitted_invalid_rows: int = 0
    show_truncation_note: bool = False
    show_summary_only_note: bool = False


def write_batch_report(
    *,
    summary: BatchSummary,
    invalid_rows: list[BatchRecordResult],
    omitted_invalid_rows: int,
    output_path: Path,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    report_view = _build_report_view(
        summary=summary,
        invalid_rows=invalid_rows,
        omitted_invalid_rows=omitted_invalid_rows,
    )
    template = _get_environment().get_template("batch_report.html.jinja2")
    html = template.render(
        report=report_view,
        limitations_note=LIMITATIONS_NOTE,
        truncation_note=TRUNCATION_NOTE,
    )
    output_path.write_text(html, encoding="utf-8")
    return output_path


def _build_report_view(
    *,
    summary: BatchSummary,
    invalid_rows: list[BatchRecordResult],
    omitted_invalid_rows: int,
) -> BatchReportView:
    total_records = summary.total_records
    pass_rate = 0.0 if total_records == 0 else (summary.valid_records / total_records) * 100
    return BatchReportView(
        total_records=summary.total_records,
        valid_records=summary.valid_records,
        invalid_records=summary.invalid_records,
        pass_rate_label=f"{pass_rate:.1f}%",
        error_categories=_build_error_categories(summary),
        invalid_rows=[_build_invalid_record_view(row) for row in invalid_rows],
        omitted_invalid_rows=omitted_invalid_rows,
        show_truncation_note=omitted_invalid_rows > 0,
        show_summary_only_note=summary.invalid_records > 0 and not invalid_rows,
    )


def _build_error_categories(summary: BatchSummary) -> list[ErrorCategoryView]:
    total_records = summary.total_records
    categories: list[ErrorCategoryView] = []
    for code, count in sorted(summary.error_counts.items(), key=lambda item: (-item[1], item[0])):
        percentage = 0.0 if total_records == 0 else (count / total_records) * 100
        categories.append(
            ErrorCategoryView(
                code=code,
                count=count,
                percentage_label=f"{percentage:.1f}%",
                bar_width_percent=percentage,
            )
        )
    return categories


def _build_invalid_record_view(row: BatchRecordResult) -> InvalidRecordView:
    primary_issue = row.validation.issues[0]
    return InvalidRecordView(
        line_number=row.line_number,
        case_id=row.case_id,
        primary_error_code=primary_issue.code.value,
        primary_message=primary_issue.message,
        original_mechsmiles=row.validation.original_mechsmiles,
        metadata_json=_pretty_json(row.metadata),
        raw_row_text=row.raw_record,
        issues=[
            DiagnosticIssueView(
                code=issue.code.value,
                severity=issue.severity.value,
                stage=issue.stage.value,
                message=issue.message,
                suggested_fix=issue.suggested_fix,
                atom_map_numbers=issue.atom_map_numbers,
                step_index=issue.step_index,
                arrow_index=issue.arrow_index,
                raw_exception_type=issue.raw_exception_type,
                raw_exception_message=issue.raw_exception_message,
                details_json=_pretty_json(issue.details),
            )
            for issue in row.validation.issues
        ],
    )


def _pretty_json(value: object) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False)


@lru_cache(maxsize=1)
def _get_environment() -> Environment:
    return Environment(
        loader=PackageLoader("arrowcheck", "templates"),
        autoescape=select_autoescape(default=True, default_for_string=True),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
