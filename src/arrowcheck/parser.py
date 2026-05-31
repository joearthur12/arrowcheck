from __future__ import annotations

import re
from ast import literal_eval
from dataclasses import dataclass

from rdkit import Chem

from arrowcheck.taxonomy import DiagnosticIssue, ErrorCode, Stage

type ArrowValue = tuple[int, int] | tuple[tuple[int, int], int]


@dataclass(frozen=True)
class ParsedArrow:
    arrow_index: int
    raw_text: str
    value: ArrowValue

    @property
    def atom_map_numbers(self) -> tuple[int, ...]:
        if isinstance(self.value[0], int):
            return (self.value[0], self.value[1])
        return (self.value[0][0], self.value[0][1], self.value[1])

    @property
    def canonical_text(self) -> str:
        if isinstance(self.value[0], int):
            return f"({self.value[0]},{self.value[1]})"
        bond, sink = self.value
        return f"(({bond[0]},{bond[1]}),{sink})"


@dataclass(frozen=True)
class ParsedMechanism:
    original_mechsmiles: str
    reactant_smiles: str
    arrow_section: str
    atom_map_numbers: tuple[int, ...]
    arrows: tuple[ParsedArrow, ...]

    @property
    def normalized_mechsmiles(self) -> str:
        if not self.arrows:
            return f"{self.reactant_smiles}|"
        arrow_text = ";".join(arrow.canonical_text for arrow in self.arrows)
        return f"{self.reactant_smiles}|{arrow_text}"


def parse_mechanism(
    mechsmiles: str,
) -> tuple[ParsedMechanism | None, list[DiagnosticIssue]]:
    raw_text = mechsmiles
    stripped_text = mechsmiles.strip()
    issues: list[DiagnosticIssue] = []

    if stripped_text == "":
        issues.append(
            DiagnosticIssue(
                code=ErrorCode.INPUT_EMPTY,
                stage=Stage.INPUT,
                message="MechSMILES input is empty.",
                suggested_fix=(
                    "Provide input in the form "
                    "reactant_smiles|arrow_1;arrow_2;..."
                ),
            )
        )
        return None, issues

    if stripped_text.count("|") != 1:
        issues.append(
            DiagnosticIssue(
                code=ErrorCode.FORMAT_DELIMITER,
                stage=Stage.INPUT,
                message="MechSMILES input must contain exactly one '|' delimiter.",
                suggested_fix=(
                    "Use the form reactant_smiles|arrow_1;arrow_2;... "
                    "or reactant_smiles| for a no-op."
                ),
            )
        )
        return None, issues

    reactant_smiles, arrow_section = stripped_text.split("|", maxsplit=1)
    if reactant_smiles == "":
        issues.append(
            DiagnosticIssue(
                code=ErrorCode.SMILES_INVALID,
                stage=Stage.PARSE,
                message="Reactant-side SMILES is empty.",
                suggested_fix=(
                    "Provide a non-empty reactant SMILES string before "
                    "the '|' delimiter."
                ),
            )
        )
        return None, issues

    mol = Chem.MolFromSmiles(reactant_smiles, sanitize=False)
    if mol is None:
        issues.append(
            DiagnosticIssue(
                code=ErrorCode.SMILES_INVALID,
                stage=Stage.PARSE,
                message="Reactant-side SMILES could not be parsed by RDKit.",
                suggested_fix=(
                    "Check the reactant-side SMILES syntax before "
                    "the '|' delimiter."
                ),
            )
        )
        return None, issues

    atom_map_numbers, duplicate_maps = _extract_atom_maps(mol)
    if duplicate_maps:
        issues.append(
            DiagnosticIssue(
                code=ErrorCode.ATOM_MAP_DUPLICATE,
                stage=Stage.MAP,
                message="Duplicate nonzero atom-map identifiers are not allowed.",
                suggested_fix=(
                    "Assign each mapped atom a unique nonzero atom-map number."
                ),
                atom_map_numbers=duplicate_maps,
            )
        )

    parsed_arrows: list[ParsedArrow] = []
    if arrow_section != "":
        for arrow_index, arrow_text in enumerate(arrow_section.split(";")):
            issue_or_arrow = _parse_arrow(arrow_text, arrow_index)
            if isinstance(issue_or_arrow, DiagnosticIssue):
                issues.append(issue_or_arrow)
                continue
            parsed_arrows.append(issue_or_arrow)

    known_map_numbers = set(atom_map_numbers)
    for parsed_arrow in parsed_arrows:
        missing_maps = sorted(
            {
                atom_map
                for atom_map in parsed_arrow.atom_map_numbers
                if atom_map not in known_map_numbers
            }
        )
        if missing_maps:
            issues.append(
                DiagnosticIssue(
                    code=ErrorCode.ATOM_MAP_UNKNOWN,
                    stage=Stage.MAP,
                    message=(
                        "Arrow references atom-map identifiers that are absent "
                        "from the reactant SMILES."
                    ),
                    suggested_fix=(
                        "Check that every atom-map identifier used in an "
                        "arrow exists exactly once in the reactant-side SMILES."
                    ),
                    arrow_index=parsed_arrow.arrow_index,
                    atom_map_numbers=missing_maps,
                )
            )

    if issues:
        return None, issues

    parsed_mechanism = ParsedMechanism(
        original_mechsmiles=raw_text,
        reactant_smiles=reactant_smiles,
        arrow_section=arrow_section,
        atom_map_numbers=tuple(atom_map_numbers),
        arrows=tuple(parsed_arrows),
    )
    return parsed_mechanism, []


def _extract_atom_maps(mol: Chem.Mol) -> tuple[list[int], list[int]]:
    map_numbers: list[int] = []
    counts: dict[int, int] = {}

    for atom in mol.GetAtoms():
        atom_map = atom.GetAtomMapNum()
        if atom_map == 0:
            continue
        map_numbers.append(atom_map)
        counts[atom_map] = counts.get(atom_map, 0) + 1

    duplicates = sorted(atom_map for atom_map, count in counts.items() if count > 1)
    return sorted(set(map_numbers)), duplicates


def _parse_arrow(arrow_text: str, arrow_index: int) -> ParsedArrow | DiagnosticIssue:
    stripped_arrow = arrow_text.strip()
    if stripped_arrow == "":
        return DiagnosticIssue(
            code=ErrorCode.ARROW_PARSE_FAILED,
            stage=Stage.PARSE,
            message="Arrow entry is empty.",
            suggested_fix="Remove empty arrow entries or provide a valid arrow tuple.",
            arrow_index=arrow_index,
        )

    if re.search(r"\bhv\b", stripped_arrow):
        return DiagnosticIssue(
            code=ErrorCode.ARROW_SHAPE_INVALID,
            stage=Stage.PARSE,
            message="hv arrow handling is deferred in ArrowCheck Milestone 1A.",
            suggested_fix=(
                "Use only (a, b) and ((a, b), c) arrow forms in this milestone."
            ),
            arrow_index=arrow_index,
        )

    try:
        parsed_value = literal_eval(stripped_arrow)
    except (SyntaxError, ValueError) as exc:
        return DiagnosticIssue(
            code=ErrorCode.ARROW_PARSE_FAILED,
            stage=Stage.PARSE,
            message="Arrow text could not be parsed as a safe Python literal.",
            suggested_fix="Use only tuple literals such as (a, b) or ((a, b), c).",
            arrow_index=arrow_index,
            raw_exception_type=type(exc).__name__,
            raw_exception_message=str(exc),
        )

    arrow_value = _validate_arrow_shape(parsed_value)
    if arrow_value is None:
        return DiagnosticIssue(
            code=ErrorCode.ARROW_SHAPE_INVALID,
            stage=Stage.PARSE,
            message=(
                "Arrow must have shape (a, b) or ((a, b), c) using integer "
                "atom-map identifiers."
            ),
            suggested_fix="Use only the verified structural forms (a, b) and ((a, b), c).",
            arrow_index=arrow_index,
        )

    return ParsedArrow(
        arrow_index=arrow_index,
        raw_text=stripped_arrow,
        value=arrow_value,
    )


def _validate_arrow_shape(parsed_value: object) -> ArrowValue | None:
    if not isinstance(parsed_value, tuple) or len(parsed_value) != 2:
        return None

    left, right = parsed_value
    if _is_plain_int(left) and _is_plain_int(right):
        return left, right

    if (
        isinstance(left, tuple)
        and len(left) == 2
        and _is_plain_int(left[0])
        and _is_plain_int(left[1])
        and _is_plain_int(right)
    ):
        return (left[0], left[1]), right

    return None


def _is_plain_int(value: object) -> bool:
    return type(value) is int
