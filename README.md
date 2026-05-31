# ArrowCheck

Secure structural linting and batch debugging for MechSMILES reaction mechanisms.

ArrowCheck checks machine-generated reaction mechanisms before they reach the
underlying chemistry engine. It rejects unsafe text, malformed arrows, invalid
atom mappings, nonexistent bonds, and other structural failures, then returns
stable diagnostics for researchers evaluating chemistry models.

ArrowCheck currently wraps a pinned local ChRIMP checkout for the underlying
move-execution path, but it adds a strict safe-parser boundary and canonical
reconstruction before upstream execution.

## Quick Start

```powershell
conda create -n arrowcheck python=3.12 -y
conda activate arrowcheck
python -m pip install -e .
arrowcheck lint examples\valid.txt
arrowcheck batch examples\batch_mixed.jsonl --output artifacts\batch_results.jsonl --html-report artifacts\batch_report.html
arrowcheck report artifacts\batch_results.jsonl --html-report artifacts\regenerated_report.html
```

Current repository expectation:

- local pinned upstream checkout path: `upstream/ChRIMP`
- pinned upstream SHA: `56dd595af0ce2ab8d594d2201c9906cc48489089`

Automated upstream acquisition and packaging will be improved later. For now,
the repository expects the pinned local checkout to already exist under
`upstream/ChRIMP`.

## Features

- Secure single-step structural linting for MechSMILES reaction mechanisms.
- Canonical safe reconstruction before ChRIMP execution.
- Stable error taxonomy for parser, mapping, move, sanitization, and batch
  failures.
- Streaming JSONL batch linting for large model-output files.
- Secure offline HTML reports for invalid rows.
- Saved-results HTML regeneration so you can lint once, report many times.

## CLI

Lint one mechanism file:

```powershell
arrowcheck lint examples\valid.txt
```

Emit JSON instead of Rich text:

```powershell
arrowcheck lint examples\valid.txt --format json
```

Provide optional context to the upstream engine:

```powershell
arrowcheck lint examples\valid.txt --context "CCO"
```

Run streaming batch linting:

```powershell
arrowcheck batch examples\batch_mixed.jsonl
```

Write per-record JSONL results and an HTML report:

```powershell
arrowcheck batch examples\batch_mixed.jsonl --output artifacts\batch_results.jsonl --html-report artifacts\batch_report.html
```

Regenerate the same report from saved ArrowCheck results without rerunning
ChRIMP:

```powershell
arrowcheck report artifacts\batch_results.jsonl --html-report artifacts\regenerated_report.html
```

Regenerate a shorter or summary-only report later:

```powershell
arrowcheck report artifacts\batch_results.jsonl --html-report artifacts\short_report.html --report-max-rows 2
arrowcheck report artifacts\batch_results.jsonl --html-report artifacts\summary_only.html --report-max-rows 0
```

## JSONL batch input schema

Each nonblank input line must be a JSON object with:

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
- Malformed JSON rows and schema-invalid rows are recorded as batch diagnostics
  and processing continues.

## JSONL batch output schema

When `--output` is provided, ArrowCheck writes one JSON object per processed
nonblank row with this shape:

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

Malformed JSON and schema-invalid model-output rows remain in the streamed
results with preserved raw-row text when available.

## HTML reports

- `--html-report` writes one self-contained UTF-8 HTML file with no external
  scripts, fonts, stylesheets, or CDN dependencies.
- `--report-max-rows` defaults to `500` and retains only invalid rows for the
  HTML table, keeping batch and report regeneration paths bounded in memory.
- A value of `0` creates a summary-only report.
- Only invalid rows appear in the HTML table by default. Use
  `--output results.jsonl` when you need every processed record.
- `arrowcheck report ...` reads saved `results.jsonl` incrementally and fails
  fast on corruption instead of producing a misleading partial report.

## Architecture

ArrowCheck currently has four main layers:

1. CLI entry points in `src/arrowcheck/cli.py`.
2. Strict parsing and typed validation in `src/arrowcheck/parser.py`.
3. A lazy upstream adapter in `src/arrowcheck/engine.py` that reconstructs
   canonical MechSMILES before calling the pinned ChRIMP checkout.
4. Streaming batch and report pipelines in `src/arrowcheck/batch.py` and
   `src/arrowcheck/report.py`.

The lint-only adapter deliberately bypasses upstream visualization imports so
that ArrowCheck can validate `.prod` behavior without requiring native Cairo.

## Limitations

- ArrowCheck currently targets single-step linting only.
- `hv` support remains deferred.
- Chemical-structure rendering remains deferred.
- Full chemical plausibility assessment remains deferred.
- Hosted services and websites remain deferred.
- The repository still expects a pinned local ChRIMP checkout under
  `upstream/ChRIMP`.

## Security

- Raw mechanism strings, metadata, exception messages, and saved results must
  be treated as untrusted input.
- ArrowCheck never uses `eval()` in its own code.
- ArrowCheck rejects malformed tuple shapes such as `(1,2,3)` and duplicate
  atom-map identifiers before upstream execution.
- The HTML report escapes untrusted content and uses safe client-side text
  filtering instead of untrusted HTML injection.
- The same HTML escaping rules apply to regenerated reports from saved
  `results.jsonl` files.

See [SECURITY.md](SECURITY.md) for the current security policy.

## Exit codes

- `arrowcheck lint ...` returns `0` for valid input and `1` for invalid input.
- `arrowcheck batch ...` returns `0` when processing completes, even if some
  records are invalid.
- `arrowcheck batch ... --fail-on-invalid` returns `1` if any processed record
  is invalid.
- `arrowcheck report ...` returns `1` for corrupted saved-result files.
- CLI misuse such as missing input files returns `2`.

## Upstream basis

- Local pinned upstream checkout: `upstream/ChRIMP`
- Pinned SHA: `56dd595af0ce2ab8d594d2201c9906cc48489089`
- Experimentally observed behavior: `UPSTREAM_NOTES.md`

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, local validation
commands, and contribution guardrails.
