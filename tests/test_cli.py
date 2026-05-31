from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from arrowcheck.batch import lint_jsonl
from arrowcheck.cli import app

runner = CliRunner()


def write_mechanism(tmp_path: Path, name: str, contents: str) -> Path:
    path = tmp_path / name
    path.write_text(contents, encoding="utf-8")
    return path


def write_batch_input(tmp_path: Path, name: str = "batch.jsonl") -> Path:
    path = tmp_path / name
    path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "case_id": "valid-1",
                        "mechsmiles": "C[C:2](=[O:3])C.[NH3:1]|(1,2);((2,3),3)",
                        "metadata": {"source": "demo"},
                    }
                ),
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
                json.dumps({"case_id": "missing-mech"}),
                json.dumps({"mechsmiles": "[CH3:1]|"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def test_valid_text_output_and_exit_code(tmp_path: Path) -> None:
    mechanism = write_mechanism(
        tmp_path,
        "valid.txt",
        "C[C:2](=[O:3])C.[NH3:1]|(1,2);((2,3),3)",
    )

    result = runner.invoke(app, ["lint", str(mechanism)])

    assert result.exit_code == 0
    assert "Mechanism is valid." in result.stdout
    assert "CC(C)([NH3+])[O-]" in result.stdout


def test_invalid_text_output_and_exit_code(tmp_path: Path) -> None:
    mechanism = write_mechanism(tmp_path, "bad.txt", "[OH-:1].[H+:2]|(1,2,3)")

    result = runner.invoke(app, ["lint", str(mechanism)])

    assert result.exit_code == 1
    assert "Mechanism is invalid." in result.stdout
    assert "E_ARROW_SHAPE_INVALID" in result.stdout


def test_valid_json_output(tmp_path: Path) -> None:
    mechanism = write_mechanism(tmp_path, "valid.json.txt", "[CH3:1]|")

    result = runner.invoke(app, ["lint", str(mechanism), "--format", "json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["is_valid"] is True
    assert payload["final_smiles"] == "[CH3]"


def test_invalid_json_output(tmp_path: Path) -> None:
    mechanism = write_mechanism(tmp_path, "invalid.json.txt", "notasmiles|(1,2)")

    result = runner.invoke(app, ["lint", str(mechanism), "--format", "json"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["is_valid"] is False
    assert payload["issues"][0]["code"] == "E_SMILES_INVALID"


def test_missing_file_exit_code(tmp_path: Path) -> None:
    missing = tmp_path / "missing.txt"

    result = runner.invoke(app, ["lint", str(missing)])

    assert result.exit_code == 2
    assert "mechanism file not found" in result.stdout


def test_batch_cli_default_exit_code_is_zero_for_mixed_batch(tmp_path: Path) -> None:
    batch_input = write_batch_input(tmp_path)

    result = runner.invoke(app, ["batch", str(batch_input)])

    assert result.exit_code == 0
    assert "ArrowCheck Batch Summary" in result.stdout
    assert "Total records:" in result.stdout
    assert "E_BATCH_JSON_INVALID" in result.stdout


def test_batch_cli_fail_on_invalid_returns_one(tmp_path: Path) -> None:
    batch_input = write_batch_input(tmp_path)

    result = runner.invoke(app, ["batch", str(batch_input), "--fail-on-invalid"])

    assert result.exit_code == 1
    assert "Invalid records:" in result.stdout


def test_batch_cli_missing_input_file_returns_two(tmp_path: Path) -> None:
    missing = tmp_path / "missing.jsonl"

    result = runner.invoke(app, ["batch", str(missing)])

    assert result.exit_code == 2
    assert "batch input file not found" in result.stdout


def test_batch_cli_writes_output_and_summary_and_creates_nested_directories(tmp_path: Path) -> None:
    batch_input = write_batch_input(tmp_path)
    output_path = tmp_path / "artifacts" / "nested" / "results.jsonl"
    summary_path = tmp_path / "artifacts" / "nested" / "summary.json"

    result = runner.invoke(
        app,
        [
            "batch",
            str(batch_input),
            "--output",
            str(output_path),
            "--summary",
            str(summary_path),
        ],
    )

    assert result.exit_code == 0
    assert output_path.is_file()
    assert summary_path.is_file()

    rows = [
        json.loads(line)
        for line in output_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(rows) == 6

    summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))
    expected_summary = lint_jsonl(batch_input).model_dump()
    assert summary_payload == expected_summary
