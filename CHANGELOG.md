# Changelog

All notable changes to this project will be documented in this file.

## Unreleased

- Added `arrowcheck setup` for safe automated acquisition and verification of
  the pinned ChRIMP checkout.

## [0.1.0] - 2026-05-31

- Added secure single-step MechSMILES linting on top of the pinned local
  ChRIMP checkout.
- Added canonical safe MechSMILES reconstruction before upstream execution.
- Added a stable diagnostic taxonomy for parser, mapping, move, sanitization,
  and batch failures.
- Added streaming JSONL batch linting with per-record results and batch
  summaries.
- Added secure offline HTML reports for invalid batch rows.
- Added saved-results report regeneration without rerunning ChRIMP.
- Current limitations remain explicit: no `hv`, no chemical-structure
  rendering, no full chemical plausibility assessment, and no hosted service.
