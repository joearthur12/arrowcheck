from __future__ import annotations

import json
from collections import Counter
from contextlib import nullcontext
from json import JSONDecodeError
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, Field, ValidationError

from arrowcheck.taxonomy import DiagnosticIssue, ErrorCode, Stage, ValidationResult


class LintMechanism(Protocol):
    def __call__(
        self,
        mechsmiles: str,
        context: str | None = None,
    ) -> ValidationResult: ...


class BatchInputRecord(BaseModel):
    case_id: str | None = None
    mechsmiles: str
    context: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class BatchRecordResult(BaseModel):
    line_number: int
    case_id: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    validation: ValidationResult
    raw_record: str | None = None


class BatchSummary(BaseModel):
    total_records: int
    valid_records: int
    invalid_records: int
    error_counts: dict[str, int] = Field(default_factory=dict)


class BatchRunResult(BaseModel):
    summary: BatchSummary
    retained_invalid_rows: list[BatchRecordResult] = Field(default_factory=list)
    omitted_invalid_rows: int = 0


class SavedResultsCorruptionError(Exception):
    def __init__(self, *, line_number: int, message: str) -> None:
        self.line_number = line_number
        self.message = message
        super().__init__(f"line {line_number}: {message}")


def lint_jsonl(
    input_path: Path,
    output_path: Path | None = None,
) -> BatchSummary:
    return lint_jsonl_detailed(input_path, output_path=output_path).summary


def lint_jsonl_detailed(
    input_path: Path,
    output_path: Path | None = None,
    retained_invalid_limit: int = 0,
    linter: LintMechanism | None = None,
) -> BatchRunResult:
    if retained_invalid_limit < 0:
        raise ValueError("retained_invalid_limit must be >= 0")

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)

    total_records = 0
    valid_records = 0
    invalid_records = 0
    error_counts: Counter[str] = Counter()
    retained_invalid_rows: list[BatchRecordResult] = []
    omitted_invalid_rows = 0

    output_context = (
        output_path.open("w", encoding="utf-8")
        if output_path is not None
        else nullcontext(None)
    )

    with input_path.open("r", encoding="utf-8") as input_handle, output_context as output_handle:
        for line_number, raw_line in enumerate(input_handle, start=1):
            raw_record = raw_line.rstrip("\r\n")
            if raw_record.strip() == "":
                continue

            record_result = _process_nonblank_record(
                line_number=line_number,
                raw_record=raw_record,
                linter=linter,
            )
            total_records += 1
            if record_result.validation.is_valid:
                valid_records += 1
            else:
                invalid_records += 1
                if len(retained_invalid_rows) < retained_invalid_limit:
                    retained_invalid_rows.append(record_result)
                else:
                    omitted_invalid_rows += 1

            for issue in record_result.validation.issues:
                error_counts[issue.code.value] += 1

            if output_handle is not None:
                output_handle.write(record_result.model_dump_json())
                output_handle.write("\n")

    return _build_batch_run_result(
        total_records=total_records,
        valid_records=valid_records,
        invalid_records=invalid_records,
        error_counts=error_counts,
        retained_invalid_rows=retained_invalid_rows,
        omitted_invalid_rows=omitted_invalid_rows,
    )


def summarize_results_jsonl(
    input_path: Path,
    retained_invalid_limit: int = 0,
) -> BatchRunResult:
    if retained_invalid_limit < 0:
        raise ValueError("retained_invalid_limit must be >= 0")

    total_records = 0
    valid_records = 0
    invalid_records = 0
    error_counts: Counter[str] = Counter()
    retained_invalid_rows: list[BatchRecordResult] = []
    omitted_invalid_rows = 0

    with input_path.open("r", encoding="utf-8") as input_handle:
        for line_number, raw_line in enumerate(input_handle, start=1):
            raw_record = raw_line.rstrip("\r\n")
            record_result = _load_saved_result_row(
                line_number=line_number,
                raw_record=raw_record,
            )
            _validate_saved_result_row(
                record_result=record_result,
                results_file_line_number=line_number,
            )

            total_records += 1
            if record_result.validation.is_valid:
                valid_records += 1
            else:
                invalid_records += 1
                if len(retained_invalid_rows) < retained_invalid_limit:
                    retained_invalid_rows.append(record_result)
                else:
                    omitted_invalid_rows += 1

            for issue in record_result.validation.issues:
                error_counts[issue.code.value] += 1

    return _build_batch_run_result(
        total_records=total_records,
        valid_records=valid_records,
        invalid_records=invalid_records,
        error_counts=error_counts,
        retained_invalid_rows=retained_invalid_rows,
        omitted_invalid_rows=omitted_invalid_rows,
    )


def _process_nonblank_record(
    *,
    line_number: int,
    raw_record: str,
    linter: LintMechanism | None,
) -> BatchRecordResult:
    try:
        payload = json.loads(raw_record)
    except JSONDecodeError as exc:
        return BatchRecordResult(
            line_number=line_number,
            case_id=f"line-{line_number}",
            validation=_build_batch_validation_result(
                error_code=ErrorCode.BATCH_JSON_INVALID,
                message="JSONL row could not be parsed as valid JSON.",
                suggested_fix="Ensure each nonblank line is a complete JSON object.",
                raw_record=raw_record,
                raw_exception=exc,
                details={
                    "json_error": {
                        "msg": exc.msg,
                        "lineno": exc.lineno,
                        "colno": exc.colno,
                        "pos": exc.pos,
                    }
                },
            ),
            raw_record=raw_record,
        )

    try:
        record = BatchInputRecord.model_validate(payload)
    except ValidationError as exc:
        return BatchRecordResult(
            line_number=line_number,
            case_id=_extract_case_id(payload, line_number),
            metadata=_extract_metadata(payload),
            validation=_build_batch_validation_result(
                error_code=ErrorCode.BATCH_SCHEMA_INVALID,
                message="JSON row does not match the expected batch input schema.",
                suggested_fix=(
                    "Provide a JSON object with a string mechsmiles field "
                    "and optional case_id, context, and metadata."
                ),
                raw_record=_extract_original_mechsmiles(payload),
                raw_exception=exc,
                details={"validation_errors": exc.errors()},
            ),
            raw_record=raw_record,
        )

    case_id = record.case_id if record.case_id is not None else f"line-{line_number}"
    active_linter = linter if linter is not None else _load_lint_mechanism()
    validation = active_linter(record.mechsmiles, context=record.context)
    return BatchRecordResult(
        line_number=line_number,
        case_id=case_id,
        metadata=record.metadata,
        validation=validation,
    )


def _build_batch_validation_result(
    *,
    error_code: ErrorCode,
    message: str,
    suggested_fix: str,
    raw_record: str,
    raw_exception: Exception,
    details: dict[str, Any],
) -> ValidationResult:
    issue = DiagnosticIssue(
        code=error_code,
        stage=Stage.BATCH,
        message=message,
        suggested_fix=suggested_fix,
        raw_exception_type=type(raw_exception).__name__,
        raw_exception_message=str(raw_exception),
        details=details,
    )
    return ValidationResult(
        is_valid=False,
        original_mechsmiles=raw_record,
        issues=[issue],
    )


def _extract_case_id(payload: object, line_number: int) -> str:
    if isinstance(payload, dict) and isinstance(payload.get("case_id"), str):
        return payload["case_id"]
    return f"line-{line_number}"


def _extract_metadata(payload: object) -> dict[str, Any]:
    if isinstance(payload, dict) and isinstance(payload.get("metadata"), dict):
        return payload["metadata"]
    return {}


def _extract_original_mechsmiles(payload: object) -> str:
    if isinstance(payload, dict) and isinstance(payload.get("mechsmiles"), str):
        return payload["mechsmiles"]
    return ""


def _build_batch_run_result(
    *,
    total_records: int,
    valid_records: int,
    invalid_records: int,
    error_counts: Counter[str],
    retained_invalid_rows: list[BatchRecordResult],
    omitted_invalid_rows: int,
) -> BatchRunResult:
    return BatchRunResult(
        summary=BatchSummary(
            total_records=total_records,
            valid_records=valid_records,
            invalid_records=invalid_records,
            error_counts=dict(sorted(error_counts.items())),
        ),
        retained_invalid_rows=retained_invalid_rows,
        omitted_invalid_rows=omitted_invalid_rows,
    )


def _load_saved_result_row(
    *,
    line_number: int,
    raw_record: str,
) -> BatchRecordResult:
    try:
        payload = json.loads(raw_record)
    except JSONDecodeError as exc:
        raise SavedResultsCorruptionError(
            line_number=line_number,
            message=f"Invalid JSON in saved results: {exc.msg}.",
        ) from exc

    try:
        return BatchRecordResult.model_validate(payload)
    except ValidationError as exc:
        raise SavedResultsCorruptionError(
            line_number=line_number,
            message=_format_saved_results_validation_error(exc),
        ) from exc


def _validate_saved_result_row(
    *,
    record_result: BatchRecordResult,
    results_file_line_number: int,
) -> None:
    if record_result.validation.is_valid and record_result.validation.issues:
        raise SavedResultsCorruptionError(
            line_number=results_file_line_number,
            message="Saved result row is marked valid but still contains diagnostic issues.",
        )
    if not record_result.validation.is_valid and not record_result.validation.issues:
        raise SavedResultsCorruptionError(
            line_number=results_file_line_number,
            message="Saved result row is marked invalid but contains no diagnostic issues.",
        )


def _format_saved_results_validation_error(exc: ValidationError) -> str:
    first_error = exc.errors()[0]
    location = ".".join(str(item) for item in first_error["loc"])
    return f"Row does not match the ArrowCheck saved-results schema at {location}: {first_error['msg']}."


def _load_lint_mechanism() -> LintMechanism:
    from arrowcheck.engine import lint_mechanism

    return lint_mechanism
