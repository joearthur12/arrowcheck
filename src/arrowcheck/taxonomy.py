from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class Stage(StrEnum):
    INPUT = "input"
    PARSE = "parse"
    INITIALIZE = "initialize"
    CONTEXT = "context"
    MAP = "map"
    MOVE = "move"
    SANITIZE = "sanitize"
    BATCH = "batch"
    INTERNAL = "internal"


class ErrorCode(StrEnum):
    INPUT_EMPTY = "E_INPUT_EMPTY"
    FORMAT_DELIMITER = "E_FORMAT_DELIMITER"
    SMILES_INVALID = "E_SMILES_INVALID"

    ARROW_PARSE_FAILED = "E_ARROW_PARSE_FAILED"
    ARROW_SHAPE_INVALID = "E_ARROW_SHAPE_INVALID"

    ATOM_MAP_UNKNOWN = "E_ATOM_MAP_UNKNOWN"
    ATOM_MAP_DUPLICATE = "E_ATOM_MAP_DUPLICATE"

    BOND_NOT_FOUND = "E_BOND_NOT_FOUND"
    CONTEXT_INCOHERENT = "E_CONTEXT_INCOHERENT"
    MOVE_STATE_CONFLICT = "E_MOVE_STATE_CONFLICT"

    VALENCE_EXCEEDED = "E_VALENCE_EXCEEDED"
    RDKIT_SANITIZE_FAILED = "E_RDKIT_SANITIZE_FAILED"

    BATCH_JSON_INVALID = "E_BATCH_JSON_INVALID"
    BATCH_SCHEMA_INVALID = "E_BATCH_SCHEMA_INVALID"

    UPSTREAM_INTERNAL = "E_UPSTREAM_INTERNAL"


class DiagnosticIssue(BaseModel):
    code: ErrorCode
    severity: Severity = Severity.ERROR
    stage: Stage

    message: str
    suggested_fix: str | None = None

    step_index: int | None = None
    arrow_index: int | None = None
    atom_map_numbers: list[int] = Field(default_factory=list)

    raw_exception_type: str | None = None
    raw_exception_message: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class ValidationResult(BaseModel):
    is_valid: bool
    original_mechsmiles: str
    final_smiles: str | None = None
    issues: list[DiagnosticIssue] = Field(default_factory=list)
