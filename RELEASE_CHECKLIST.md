# Release Checklist

- [ ] Git status is clean.
- [ ] `python -m pytest -q` passes.
- [ ] `python -m ruff check .` passes.
- [ ] `python -m mypy src` passes.
- [ ] `arrowcheck lint examples\valid.txt` works.
- [ ] `arrowcheck batch examples\batch_mixed.jsonl --output artifacts\batch_results.jsonl --html-report artifacts\batch_report.html` works.
- [ ] `arrowcheck report artifacts\batch_results.jsonl --html-report artifacts\regenerated_report.html` works.
- [ ] The generated HTML report opens locally.
- [ ] The regenerated report opens locally.
- [ ] The hostile HTML fixture remains inert in generated reports.
- [ ] The pinned upstream SHA is still `56dd595af0ce2ab8d594d2201c9906cc48489089`.
- [ ] Ignored files and generated artifacts have been verified.
- [ ] `README.md` has been reviewed for accuracy.
- [ ] `LICENSE` is present.
- [ ] No secrets or credentials are present.
- [ ] The GitHub remote will be added manually later.
- [ ] The first release tag will be created manually later.
