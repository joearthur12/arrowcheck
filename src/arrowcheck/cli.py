from __future__ import annotations

from enum import StrEnum
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from arrowcheck.engine import lint_mechanism
from arrowcheck.taxonomy import ValidationResult

console = Console()
app = typer.Typer(
    add_completion=False,
    help="Secure structural linter for single-step MechSMILES.",
)


class OutputFormat(StrEnum):
    TEXT = "text"
    JSON = "json"


MECHANISM_FILE_ARGUMENT = typer.Argument(
    ...,
    help="Path to a text file containing one MechSMILES string.",
)
FORMAT_OPTION = typer.Option(
    OutputFormat.TEXT,
    "--format",
    help="Output format.",
)
CONTEXT_OPTION = typer.Option(
    None,
    "--context",
    help="Optional context string for upstream ChRIMP.",
)


@app.callback()
def main() -> None:
    """ArrowCheck command group."""


@app.command()
def lint(
    mechanism_file: Path = MECHANISM_FILE_ARGUMENT,
    format: OutputFormat = FORMAT_OPTION,
    context: str | None = CONTEXT_OPTION,
) -> None:
    if not mechanism_file.is_file():
        console.print(
            f"Error: mechanism file not found: {mechanism_file}",
            style="bold red",
        )
        raise typer.Exit(code=2)

    mechsmiles = mechanism_file.read_text(encoding="utf-8").strip()
    result = lint_mechanism(mechsmiles, context=context)

    if format is OutputFormat.JSON:
        typer.echo(result.model_dump_json(indent=2))
    else:
        _render_text_result(result)

    raise typer.Exit(code=0 if result.is_valid else 1)


def _render_text_result(result: ValidationResult) -> None:
    if result.is_valid:
        final_smiles = result.final_smiles or "<none>"
        console.print(
            Panel.fit(
                f"Mechanism is valid.\nFinal SMILES: {final_smiles}",
                title="ArrowCheck",
                border_style="green",
            )
        )
        return

    console.print(
        Panel.fit(
            "Mechanism is invalid.",
            title="ArrowCheck",
            border_style="red",
        )
    )
    for issue in result.issues:
        console.print(
            f"[bold red]{issue.code}[/bold red] "
            f"[{issue.stage}] {issue.message}"
        )
        if issue.atom_map_numbers:
            console.print(f"  atom maps: {issue.atom_map_numbers}")
        if issue.suggested_fix:
            console.print(f"  suggested fix: {issue.suggested_fix}")
        if issue.raw_exception_type or issue.raw_exception_message:
            console.print(
                "  upstream: "
                f"{issue.raw_exception_type or '<none>'}: "
                f"{issue.raw_exception_message or '<none>'}"
            )


if __name__ == "__main__":
    app()
