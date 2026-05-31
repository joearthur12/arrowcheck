from __future__ import annotations

from enum import StrEnum
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from arrowcheck.batch import BatchSummary, lint_jsonl
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
BATCH_INPUT_ARGUMENT = typer.Argument(
    ...,
    help="Path to a JSONL file containing batch records.",
)
BATCH_OUTPUT_OPTION = typer.Option(
    None,
    "--output",
    help="Optional output JSONL path for per-record results.",
)
BATCH_SUMMARY_OPTION = typer.Option(
    None,
    "--summary",
    help="Optional JSON summary output path.",
)
FAIL_ON_INVALID_OPTION = typer.Option(
    False,
    "--fail-on-invalid",
    help="Return exit code 1 if any processed record is invalid.",
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


@app.command()
def batch(
    input_file: Path = BATCH_INPUT_ARGUMENT,
    output: Path | None = BATCH_OUTPUT_OPTION,
    summary: Path | None = BATCH_SUMMARY_OPTION,
    fail_on_invalid: bool = FAIL_ON_INVALID_OPTION,
) -> None:
    if not input_file.is_file():
        console.print(
            f"Error: batch input file not found: {input_file}",
            style="bold red",
        )
        raise typer.Exit(code=2)

    batch_summary = lint_jsonl(input_file, output_path=output)
    if summary is not None:
        summary.parent.mkdir(parents=True, exist_ok=True)
        summary.write_text(batch_summary.model_dump_json(indent=2), encoding="utf-8")

    _render_batch_summary(batch_summary)

    if fail_on_invalid and batch_summary.invalid_records > 0:
        raise typer.Exit(code=1)
    raise typer.Exit(code=0)


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


def _render_batch_summary(summary: BatchSummary) -> None:
    console.print("[bold]ArrowCheck Batch Summary[/bold]")
    console.print()

    counts_table = Table.grid(padding=(0, 2))
    counts_table.add_column(justify="left")
    counts_table.add_column(justify="right")
    counts_table.add_row("Total records:", str(summary.total_records))
    counts_table.add_row("Valid records:", str(summary.valid_records))
    counts_table.add_row("Invalid records:", str(summary.invalid_records))
    console.print(counts_table)

    if summary.error_counts:
        console.print()
        console.print("[bold]Errors:[/bold]")
        errors_table = Table.grid(padding=(0, 2))
        errors_table.add_column(justify="left")
        errors_table.add_column(justify="right")
        for error_code, count in summary.error_counts.items():
            errors_table.add_row(error_code, str(count))
        console.print(errors_table)


if __name__ == "__main__":
    app()
