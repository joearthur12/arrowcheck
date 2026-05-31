from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import arrowcheck.batch as batch


def write_batch_file(tmp_path: Path, name: str = "batch.jsonl") -> Path:
    path = tmp_path / name
    path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "case_id": "valid-1",
                        "mechsmiles": "C[C:2](=[O:3])C.[NH3:1]|(1,2);((2,3),3)",
                        "metadata": {"source": "demo", "rank": 1},
                    }
                ),
                "",
                json.dumps(
                    {
                        "case_id": "bad-tuple",
                        "mechsmiles": "[OH-:1].[H+:2]|(1,2,3)",
                    }
                ),
                json.dumps(
                    {
                        "case_id": "unknown-map",
                        "mechsmiles": "C[C:2](=[O:3])C.[NH3:1]|(9,2)",
                    }
                ),
                '{"case_id":"broken-json","mechsmiles":"[CH3:1]|"',
                json.dumps(
                    {
                        "case_id": "missing-mech",
                        "metadata": {"source": "schema"},
                    }
                ),
                json.dumps(
                    {
                        "mechsmiles": "[CH3:1]|",
                        "metadata": {"note": "radical-noop"},
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() == "":
            continue
        rows.append(json.loads(line))
    return rows


def test_mixed_batch_summary_and_streaming_output(tmp_path: Path) -> None:
    input_path = write_batch_file(tmp_path)
    output_path = tmp_path / "results.jsonl"

    summary = batch.lint_jsonl(input_path, output_path=output_path)

    assert summary.total_records == 6
    assert summary.valid_records == 2
    assert summary.invalid_records == 4
    assert summary.error_counts == {
        "E_ARROW_SHAPE_INVALID": 1,
        "E_ATOM_MAP_UNKNOWN": 1,
        "E_BATCH_JSON_INVALID": 1,
        "E_BATCH_SCHEMA_INVALID": 1,
    }

    rows = load_jsonl(output_path)
    assert len(rows) == 6
    assert rows[0]["case_id"] == "valid-1"
    assert rows[0]["metadata"] == {"source": "demo", "rank": 1}
    assert rows[-1]["case_id"] == "line-7"
    assert rows[-1]["validation"]["is_valid"] is True


def test_blank_lines_are_ignored(tmp_path: Path) -> None:
    input_path = write_batch_file(tmp_path)

    summary = batch.lint_jsonl(input_path)

    assert summary.total_records == 6


def test_malformed_json_emits_batch_json_invalid(tmp_path: Path) -> None:
    input_path = write_batch_file(tmp_path)
    output_path = tmp_path / "results.jsonl"

    batch.lint_jsonl(input_path, output_path=output_path)
    rows = load_jsonl(output_path)
    broken_row = next(row for row in rows if row["case_id"] == "line-5")

    assert broken_row["validation"]["issues"][0]["code"] == "E_BATCH_JSON_INVALID"
    assert broken_row["raw_record"] == '{"case_id":"broken-json","mechsmiles":"[CH3:1]|"'


def test_schema_invalid_json_emits_batch_schema_invalid(tmp_path: Path) -> None:
    input_path = write_batch_file(tmp_path)
    output_path = tmp_path / "results.jsonl"

    batch.lint_jsonl(input_path, output_path=output_path)
    rows = load_jsonl(output_path)
    schema_row = next(row for row in rows if row["case_id"] == "missing-mech")

    assert schema_row["validation"]["issues"][0]["code"] == "E_BATCH_SCHEMA_INVALID"
    assert schema_row["metadata"] == {"source": "schema"}


def test_later_records_continue_after_malformed_rows(tmp_path: Path) -> None:
    input_path = write_batch_file(tmp_path)
    output_path = tmp_path / "results.jsonl"

    batch.lint_jsonl(input_path, output_path=output_path)
    rows = load_jsonl(output_path)

    assert rows[-1]["case_id"] == "line-7"
    assert rows[-1]["validation"]["is_valid"] is True


def test_batch_mode_reuses_existing_lint_mechanism(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    input_path = write_batch_file(tmp_path)
    calls: list[tuple[str, str | None]] = []

    def fake_lint(mechsmiles: str, context: str | None = None):
        calls.append((mechsmiles, context))
        return batch.ValidationResult(
            is_valid=True,
            original_mechsmiles=mechsmiles,
            final_smiles="fake",
        )

    monkeypatch.setattr(batch, "lint_mechanism", fake_lint)

    summary = batch.lint_jsonl(input_path)

    assert summary.total_records == 6
    assert calls == [
        ("C[C:2](=[O:3])C.[NH3:1]|(1,2);((2,3),3)", None),
        ("[OH-:1].[H+:2]|(1,2,3)", None),
        ("C[C:2](=[O:3])C.[NH3:1]|(9,2)", None),
        ("[CH3:1]|", None),
    ]
