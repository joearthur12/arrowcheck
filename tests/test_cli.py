from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from arrowcheck.cli import app

runner = CliRunner()


def write_mechanism(tmp_path: Path, name: str, contents: str) -> Path:
    path = tmp_path / name
    path.write_text(contents, encoding="utf-8")
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
