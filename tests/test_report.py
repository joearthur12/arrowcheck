from __future__ import annotations

import builtins
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

import arrowcheck.batch as batch
from arrowcheck.batch import BatchRunResult, lint_jsonl_detailed, summarize_results_jsonl
from arrowcheck.report import LIMITATIONS_NOTE, TRUNCATION_NOTE, write_batch_report

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = REPO_ROOT / "examples"


class ReportHTMLInspector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tag_counts: Counter[str] = Counter()
        self.summary_values: dict[str, str] = {}
        self.error_code_order: list[str] = []
        self.record_row_texts: list[str] = []
        self.text_chunks: list[str] = []
        self._active_summary_key: str | None = None
        self._active_record_row = False
        self._current_row_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        self.tag_counts[tag] += 1
        if tag == "span" and attrs_dict.get("data-summary-value") is not None:
            self._active_summary_key = attrs_dict["data-summary-value"]
        if tag == "tr" and attrs_dict.get("data-error-code") is not None:
            self.error_code_order.append(attrs_dict["data-error-code"])
        if tag == "tr" and "data-record-row" in attrs_dict:
            self._active_record_row = True
            self._current_row_text = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "span":
            self._active_summary_key = None
        if tag == "tr" and self._active_record_row:
            self.record_row_texts.append(" ".join(self._current_row_text))
            self._active_record_row = False
            self._current_row_text = []

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text == "":
            return
        self.text_chunks.append(text)
        if self._active_summary_key is not None:
            self.summary_values[self._active_summary_key] = text
        if self._active_record_row:
            self._current_row_text.append(text)


def inspect_html(path: Path) -> tuple[str, ReportHTMLInspector]:
    html = path.read_text(encoding="utf-8")
    inspector = ReportHTMLInspector()
    inspector.feed(html)
    return html, inspector


def build_report(
    *,
    input_path: Path,
    tmp_path: Path,
    report_max_rows: int,
) -> tuple[BatchRunResult, Path]:
    report_path = tmp_path / "nested" / "reports" / "batch_report.html"
    batch_result = lint_jsonl_detailed(
        input_path,
        retained_invalid_limit=report_max_rows,
    )
    write_batch_report(
        summary=batch_result.summary,
        invalid_rows=batch_result.retained_invalid_rows,
        omitted_invalid_rows=batch_result.omitted_invalid_rows,
        output_path=report_path,
    )
    return batch_result, report_path


def build_saved_results(input_path: Path, tmp_path: Path, name: str = "results.jsonl") -> Path:
    results_path = tmp_path / name
    lint_jsonl_detailed(input_path, output_path=results_path)
    return results_path


def test_report_is_generated_with_summary_cards_and_parent_dirs(tmp_path: Path) -> None:
    input_path = EXAMPLES_DIR / "batch_mixed.jsonl"

    _, report_path = build_report(input_path=input_path, tmp_path=tmp_path, report_max_rows=10)

    assert report_path.is_file()
    html, inspector = inspect_html(report_path)
    assert inspector.summary_values == {
        "total-records": "6",
        "valid-records": "2",
        "invalid-records": "4",
        "pass-rate": "33.3%",
    }
    assert LIMITATIONS_NOTE in html


def test_report_sorts_error_categories_and_excludes_valid_rows_from_failure_table(tmp_path: Path) -> None:
    input_path = EXAMPLES_DIR / "batch_mixed.jsonl"

    _, report_path = build_report(input_path=input_path, tmp_path=tmp_path, report_max_rows=10)

    _, inspector = inspect_html(report_path)
    assert inspector.error_code_order == [
        "E_ARROW_SHAPE_INVALID",
        "E_ATOM_MAP_UNKNOWN",
        "E_BATCH_JSON_INVALID",
        "E_BATCH_SCHEMA_INVALID",
    ]
    combined_row_text = " ".join(inspector.record_row_texts)
    assert "bad-tuple" in combined_row_text
    assert "unknown-map" in combined_row_text
    assert "missing-mech" in combined_row_text
    assert "valid-1" not in combined_row_text


def test_hostile_strings_are_escaped_and_remain_inert(tmp_path: Path) -> None:
    input_path = EXAMPLES_DIR / "batch_hostile.jsonl"

    _, report_path = build_report(input_path=input_path, tmp_path=tmp_path, report_max_rows=10)

    html, inspector = inspect_html(report_path)
    visible_text = "\n".join(inspector.text_chunks)

    assert "<script>alert(1)</script>" in visible_text
    assert "<img src=x onerror=alert(1)>" in visible_text
    assert '</script><script>alert("x")</script>' in visible_text

    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "&lt;img src=x onerror=alert(1)&gt;" in html
    assert "&lt;/script&gt;&lt;script&gt;alert(" in html

    assert "<script>alert(1)</script>" not in html
    assert "<img src=x onerror=alert(1)>" not in html
    assert inspector.tag_counts["script"] == 1
    assert inspector.tag_counts["img"] == 0


def test_saved_results_regeneration_does_not_call_linter_or_import_chrimp(
    monkeypatch,
    tmp_path: Path,
) -> None:
    input_path = EXAMPLES_DIR / "batch_mixed.jsonl"
    results_path = build_saved_results(input_path, tmp_path)

    monkeypatch.setattr(
        batch,
        "_load_lint_mechanism",
        lambda: (_ for _ in ()).throw(AssertionError("lint loader should not run during report regeneration")),
    )

    original_import = builtins.__import__

    def guarded_import(
        name: str,
        globals: dict[str, object] | None = None,
        locals: dict[str, object] | None = None,
        fromlist: tuple[object, ...] = (),
        level: int = 0,
    ) -> object:
        if name == "arrowcheck.engine" or name.startswith("chrimp"):
            raise AssertionError(f"unexpected import during report regeneration: {name}")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    result = summarize_results_jsonl(results_path, retained_invalid_limit=2)

    assert result.summary.total_records == 6
    assert result.summary.valid_records == 2
    assert result.summary.invalid_records == 4
    assert result.summary.error_counts == {
        "E_ARROW_SHAPE_INVALID": 1,
        "E_ATOM_MAP_UNKNOWN": 1,
        "E_BATCH_JSON_INVALID": 1,
        "E_BATCH_SCHEMA_INVALID": 1,
    }
    assert [row.case_id for row in result.retained_invalid_rows] == [
        "bad-tuple",
        "unknown-map",
    ]
    assert result.omitted_invalid_rows == 2


def test_regenerated_report_preserves_hostile_html_escaping(tmp_path: Path) -> None:
    input_path = EXAMPLES_DIR / "batch_hostile.jsonl"
    results_path = build_saved_results(input_path, tmp_path)

    batch_result = summarize_results_jsonl(results_path, retained_invalid_limit=10)
    report_path = tmp_path / "regenerated" / "hostile_report.html"
    write_batch_report(
        summary=batch_result.summary,
        invalid_rows=batch_result.retained_invalid_rows,
        omitted_invalid_rows=batch_result.omitted_invalid_rows,
        output_path=report_path,
    )

    html, inspector = inspect_html(report_path)
    visible_text = "\n".join(inspector.text_chunks)

    assert "<script>alert(1)</script>" in visible_text
    assert "<img src=x onerror=alert(1)>" in visible_text
    assert '</script><script>alert("x")</script>' in visible_text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "&lt;img src=x onerror=alert(1)&gt;" in html
    assert inspector.tag_counts["script"] == 1
    assert inspector.tag_counts["img"] == 0


def test_report_truncation_and_summary_only_modes(tmp_path: Path) -> None:
    input_path = EXAMPLES_DIR / "batch_mixed.jsonl"

    truncated_result, truncated_path = build_report(
        input_path=input_path,
        tmp_path=tmp_path / "truncated",
        report_max_rows=2,
    )
    truncated_html, truncated_inspector = inspect_html(truncated_path)
    assert truncated_result.omitted_invalid_rows == 2
    assert len(truncated_inspector.record_row_texts) == 2
    assert TRUNCATION_NOTE in truncated_html

    summary_only_result, summary_only_path = build_report(
        input_path=input_path,
        tmp_path=tmp_path / "summary_only",
        report_max_rows=0,
    )
    summary_only_html, summary_only_inspector = inspect_html(summary_only_path)
    assert summary_only_result.omitted_invalid_rows == 4
    assert len(summary_only_inspector.record_row_texts) == 0
    assert "Summary-only report requested or no invalid rows were retained for this file." in summary_only_html
    assert TRUNCATION_NOTE in summary_only_html
