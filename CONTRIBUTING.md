# Contributing to ArrowCheck

## Local setup

ArrowCheck currently assumes a local Python 3.12 Conda environment and a
pinned local upstream ChRIMP checkout under `upstream/ChRIMP`.

```powershell
conda create -n arrowcheck python=3.12 -y
conda activate arrowcheck
python -m pip install -e ".[dev]"
```

Expected upstream checkout:

- path: `upstream/ChRIMP`
- pinned SHA: `56dd595af0ce2ab8d594d2201c9906cc48489089`

Normal ArrowCheck contributions should not modify the upstream ChRIMP checkout.
If upstream behavior needs to be re-audited, document the evidence in
`UPSTREAM_NOTES.md` first.

## Development commands

Run the local verification set before opening a pull request:

```powershell
python -m pytest -q
python -m ruff check .
python -m mypy src
```

Useful CLI smoke tests:

```powershell
arrowcheck lint examples\valid.txt
arrowcheck batch examples\batch_mixed.jsonl --output artifacts\batch_results.jsonl --html-report artifacts\batch_report.html
arrowcheck report artifacts\batch_results.jsonl --html-report artifacts\regenerated_report.html
```

## Safety expectations

- Raw mechanism strings are untrusted input.
- Keep the parser-to-engine boundary strict: parse first, reconstruct
  canonical MechSMILES second, then call the upstream engine.
- Do not introduce `eval()` anywhere in ArrowCheck.
- Keep HTML-report rendering escaped and offline-safe.
- Treat raw MechSMILES, metadata, exception messages, and saved result rows as
  untrusted user-controlled content.

## Scope guardrails

- Do not modify `upstream/ChRIMP` as part of normal ArrowCheck feature or
  maintenance work.
- Do not add new semantics to the chemistry engine without tests and explicit
  milestone scope.
- Keep public documentation honest about current limitations.
