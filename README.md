# ArrowCheck

ArrowCheck is a secure structural linter for single-step MechSMILES.

Version 0.1 wraps the pinned local ChRIMP checkout for the scientific move
execution path, but it adds strict safe parsing before upstream execution.
ArrowCheck does not use `eval()` in its own code.

## What ArrowCheck does

- validates one MechSMILES string at a time;
- streams JSONL batch inputs one record at a time for large model-output files;
- can emit a self-contained offline HTML batch report for retained invalid rows;
- safely parses the input with RDKit plus `ast.literal_eval()`;
- rejects malformed tuple shapes and duplicate atom-map identifiers even where
  upstream ChRIMP currently accepts them;
- calls the pinned upstream ChRIMP logic only after local validation succeeds;
- reports stable error codes and preserves raw upstream exception details.

## What ArrowCheck does not claim yet

- It does not prove full chemical plausibility.
- It does not provide rendering or visualisation.
- It does not render chemical structure diagrams inside reports yet.
- `hv` handling is deferred to a later milestone.

The lint-only adapter deliberately bypasses upstream visualisation imports
because rendering is outside Milestone 1A and direct visualisation imports pull
in native Cairo requirements that are not needed for `.prod` linting.

## Install

The project uses a modern `src/` layout and is intended to be installed
editable during development:

```powershell
C:\Users\joear\miniconda3\envs\arrowcheck\python.exe -m pip install -e .
```

## CLI

Lint a mechanism file:

```powershell
arrowcheck lint examples\valid.txt
```

Emit full JSON:

```powershell
arrowcheck lint examples\valid.txt --format json
```

Provide optional context:

```powershell
arrowcheck lint examples\valid.txt --context "CCO"
```

Run streaming batch linting:

```powershell
arrowcheck batch examples\batch_mixed.jsonl
```

Write streaming JSONL results plus a JSON summary:

```powershell
arrowcheck batch examples\batch_mixed.jsonl --output artifacts\batch_results.jsonl --summary artifacts\batch_summary.json
```

Write a secure offline HTML report:

```powershell
arrowcheck batch examples\batch_mixed.jsonl --html-report artifacts\batch_report.html
```

Write JSONL results, a summary, and a truncated HTML report together:

```powershell
arrowcheck batch examples\batch_mixed.jsonl --output artifacts\batch_results.jsonl --summary artifacts\batch_summary.json --html-report artifacts\batch_report.html --report-max-rows 500
```

Make invalid records fail the shell command after processing completes:

```powershell
arrowcheck batch examples\batch_mixed.jsonl --fail-on-invalid
```

## JSONL batch input schema

Each nonblank line must be a JSON object with:

```json
{
  "case_id": "optional-string",
  "mechsmiles": "required-mechsmiles-string",
  "context": "optional-context-string",
  "metadata": {
    "optional": "json-compatible values"
  }
}
```

- Blank lines are ignored.
- Missing `case_id` falls back to `line-<line_number>`.
- Malformed JSON rows and schema-invalid rows are reported without stopping the batch.

## JSONL batch output schema

When `--output` is provided, ArrowCheck writes one JSON object per processed
nonblank input row with this shape:

```json
{
  "line_number": 1,
  "case_id": "valid-1",
  "metadata": {
    "source": "demo"
  },
  "validation": {
    "is_valid": true,
    "original_mechsmiles": "C[C:2](=[O:3])C.[NH3:1]|(1,2);((2,3),3)",
    "final_smiles": "CC(C)([NH3+])[O-]",
    "issues": []
  },
  "raw_record": null
}
```

Malformed JSON and schema-invalid rows remain in the output stream with a batch
diagnostic and preserved raw row text when available.

## HTML batch reports

- `--html-report` writes one self-contained UTF-8 HTML file with no external
  scripts, fonts, stylesheets, or CDN dependencies.
- `--report-max-rows` defaults to `500` and retains only invalid rows for the
  HTML table while batch processing continues streaming through the full JSONL
  file.
- A value of `0` creates a summary-only report.
- The HTML report never attempts to show every processed row by default. When
  you need every individual record, use `--output results.jsonl`.
- Only invalid rows appear in the HTML table so the report stays focused and
  bounded in memory on large model-output files.
- Structure diagrams and other chemistry rendering remain deferred.

## Exit codes

- `arrowcheck lint ...` returns `0` for valid input and `1` for invalid input.
- `arrowcheck batch ...` returns `0` when processing completes, even if some
  records are invalid.
- `arrowcheck batch ... --fail-on-invalid` returns `1` if any processed record
  is invalid.
- CLI misuse such as a missing input file returns `2`.

## Batch notes

- Batch mode is streaming and suitable for large JSONL model-output files.
- HTML reporting retains only a bounded number of invalid rows in memory.
- `hv` handling is still deferred.

## Security stance

- ArrowCheck never calls `eval()` on mechanism text.
- ArrowCheck rejects malformed tuple shapes such as `(1,2,3)`.
- ArrowCheck rejects duplicate atom-map identifiers such as
  `[CH3:1][OH:1].[H+:2]|(1,2)`.
- ArrowCheck rejects function-call-like input such as
  `__import__("os").system("calc")` before upstream execution.
- The HTML report treats case IDs, metadata, raw rows, exception messages, and
  MechSMILES text as untrusted content and escapes them before rendering.
- Client-side search uses DOM `textContent` matching and does not inject
  untrusted strings with `innerHTML`.

## Upstream basis

- Local pinned upstream checkout: `upstream/ChRIMP`
- Pinned SHA: `56dd595af0ce2ab8d594d2201c9906cc48489089`
- Experimentally observed behavior is documented in `UPSTREAM_NOTES.md`
