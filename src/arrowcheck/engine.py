from __future__ import annotations

import os
import re
import sys
import types
from contextlib import redirect_stdout
from functools import lru_cache
from io import StringIO
from pathlib import Path
from typing import Protocol

from arrowcheck.parser import ParsedMechanism, parse_mechanism
from arrowcheck.taxonomy import DiagnosticIssue, ErrorCode, Stage, ValidationResult

PROJECT_ROOT = Path(__file__).resolve().parents[2]
UPSTREAM_SRC = PROJECT_ROOT / "upstream" / "ChRIMP" / "src"
MPLCONFIGDIR = PROJECT_ROOT / ".mplconfig"


class UpstreamMechSmilesInstance(Protocol):
    @property
    def prod(self) -> str: ...


class UpstreamMechSmilesClass(Protocol):
    def __call__(
        self,
        value: str,
        context: str | None = None,
    ) -> UpstreamMechSmilesInstance: ...


def lint_mechanism(
    mechsmiles: str,
    context: str | None = None,
) -> ValidationResult:
    parsed, issues = parse_mechanism(mechsmiles)
    if issues:
        return ValidationResult(
            is_valid=False,
            original_mechsmiles=mechsmiles,
            issues=issues,
        )

    assert parsed is not None

    try:
        mechsmiles_class = _load_upstream_mechsmiles_class()
        with redirect_stdout(StringIO()):
            upstream_mechanism = mechsmiles_class(
                parsed.normalized_mechsmiles,
                context=context,
            )
            final_smiles = upstream_mechanism.prod
    except Exception as exc:
        issue = _classify_upstream_exception(exc, parsed)
        return ValidationResult(
            is_valid=False,
            original_mechsmiles=mechsmiles,
            issues=[issue],
        )

    return ValidationResult(
        is_valid=True,
        original_mechsmiles=mechsmiles,
        final_smiles=final_smiles,
    )


@lru_cache(maxsize=1)
def _load_upstream_mechsmiles_class() -> UpstreamMechSmilesClass:
    _install_visualizer_stub()
    os.environ.setdefault("MPLCONFIGDIR", str(MPLCONFIGDIR))
    upstream_path = str(UPSTREAM_SRC)
    if upstream_path not in sys.path:
        sys.path.insert(0, upstream_path)

    from chrimp.world.mechsmiles import MechSmiles

    return MechSmiles


def _install_visualizer_stub() -> None:
    module_name = "chrimp.visualization.mechsmiles_visualizer"
    if module_name in sys.modules:
        return

    stub_module = types.ModuleType(module_name)

    class MechSmilesVisualizer:
        def show_reac(self, *args: object, **kwargs: object) -> None:
            raise RuntimeError("Visualizer is disabled in ArrowCheck lint mode.")

        def show_prod(self, *args: object, **kwargs: object) -> None:
            raise RuntimeError("Visualizer is disabled in ArrowCheck lint mode.")

        def show_cond(self, *args: object, **kwargs: object) -> None:
            raise RuntimeError("Visualizer is disabled in ArrowCheck lint mode.")

        def show(self, *args: object, **kwargs: object) -> None:
            raise RuntimeError("Visualizer is disabled in ArrowCheck lint mode.")

    stub_module.__dict__["MechSmilesVisualizer"] = MechSmilesVisualizer
    sys.modules[module_name] = stub_module


def _classify_upstream_exception(
    exc: Exception,
    parsed: ParsedMechanism,
) -> DiagnosticIssue:
    exc_type = type(exc).__name__
    raw_message = str(exc)
    details: dict[str, object] = {
        "normalized_mechsmiles": parsed.normalized_mechsmiles
    }

    if exc_type == "MechSmilesInitError":
        return DiagnosticIssue(
            code=ErrorCode.SMILES_INVALID,
            stage=Stage.INITIALIZE,
            message="Upstream ChRIMP could not initialize the reactant-side SMILES.",
            suggested_fix="Check the reactant-side SMILES syntax and atom mappings.",
            raw_exception_type=exc_type,
            raw_exception_message=raw_message,
            details=details,
        )

    if exc_type == "MechSmilesContextError":
        return DiagnosticIssue(
            code=ErrorCode.CONTEXT_INCOHERENT,
            stage=Stage.CONTEXT,
            message="Provided context is incoherent with the reactant-side SMILES.",
            suggested_fix=(
                "Ensure the optional context contains the reacting species "
                "and any extra conditions consistently."
            ),
            raw_exception_type=exc_type,
            raw_exception_message=raw_message,
            details=details,
        )

    if isinstance(exc, KeyError) and len(exc.args) == 1 and type(exc.args[0]) is int:
        missing_map = exc.args[0]
        return DiagnosticIssue(
            code=ErrorCode.ATOM_MAP_UNKNOWN,
            stage=Stage.MAP,
            message=(
                "Upstream ChRIMP referenced an atom-map identifier absent "
                "from the reactant-side SMILES."
            ),
            suggested_fix=(
                "Use only atom-map identifiers that exist exactly once in "
                "the reactant-side SMILES."
            ),
            atom_map_numbers=[missing_map],
            raw_exception_type=exc_type,
            raw_exception_message=raw_message,
            details=details,
        )

    if exc_type == "BondNotFoundError":
        internal_indices = _extract_internal_indices(raw_message)
        bond_details: dict[str, object] = details.copy()
        if internal_indices:
            bond_details["internal_atom_indices"] = internal_indices
        return DiagnosticIssue(
            code=ErrorCode.BOND_NOT_FOUND,
            stage=Stage.MOVE,
            message=(
                "The requested move references a bond that does not exist in "
                "the initialized reactant graph."
            ),
            suggested_fix=(
                "Check that each ((a, b), c) arrow references a real bond "
                "between mapped atoms a and b."
            ),
            raw_exception_type=exc_type,
            raw_exception_message=raw_message,
            details=bond_details,
        )

    if exc_type == "ReusedVirtualTSException":
        return DiagnosticIssue(
            code=ErrorCode.MOVE_STATE_CONFLICT,
            stage=Stage.MOVE,
            message=(
                "Upstream ChRIMP entered a conflicting move state while "
                "applying the mechanism."
            ),
            suggested_fix=(
                "Check whether the requested move sequence creates an "
                "unsupported intermediate or conflicting bond/electron state."
            ),
            raw_exception_type=exc_type,
            raw_exception_message=raw_message,
            details=details,
        )

    if _is_rdkit_valence_exception(exc):
        return DiagnosticIssue(
            code=ErrorCode.VALENCE_EXCEEDED,
            stage=Stage.SANITIZE,
            message=(
                "RDKit reported a valence-related failure while processing "
                "the upstream result."
            ),
            suggested_fix="Inspect whether the move creates an impossible valence pattern.",
            raw_exception_type=exc_type,
            raw_exception_message=raw_message,
            details=details,
        )

    if _is_rdkit_sanitize_exception(exc):
        return DiagnosticIssue(
            code=ErrorCode.RDKIT_SANITIZE_FAILED,
            stage=Stage.SANITIZE,
            message=(
                "RDKit reported a sanitization failure while processing the "
                "upstream result."
            ),
            suggested_fix="Inspect the move for a structure that RDKit cannot sanitize cleanly.",
            raw_exception_type=exc_type,
            raw_exception_message=raw_message,
            details=details,
        )

    return DiagnosticIssue(
        code=ErrorCode.UPSTREAM_INTERNAL,
        stage=Stage.INTERNAL,
        message="Upstream ChRIMP raised an unexpected internal exception during linting.",
        suggested_fix=(
            "Review the raw upstream exception details and reduce the input "
            "to a smaller reproducer if the issue persists."
        ),
        raw_exception_type=exc_type,
        raw_exception_message=raw_message,
        details=details,
    )


def _extract_internal_indices(message: str) -> list[int]:
    match = re.search(r"between (\d+) and (\d+)", message)
    if match is None:
        return []
    return [int(match.group(1)), int(match.group(2))]


def _is_rdkit_valence_exception(exc: Exception) -> bool:
    module_name = type(exc).__module__.lower()
    if not module_name.startswith("rdkit"):
        return False
    lowered_message = str(exc).lower()
    lowered_type = type(exc).__name__.lower()
    return "valence" in lowered_message or "valence" in lowered_type


def _is_rdkit_sanitize_exception(exc: Exception) -> bool:
    module_name = type(exc).__module__.lower()
    if not module_name.startswith("rdkit"):
        return False
    lowered_message = str(exc).lower()
    lowered_type = type(exc).__name__.lower()
    return "sanitize" in lowered_message or "sanitize" in lowered_type
