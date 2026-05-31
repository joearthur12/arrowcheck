from __future__ import annotations

import pytest

import arrowcheck.engine as engine
from arrowcheck.taxonomy import ErrorCode


class FakeUpstreamMechanism:
    def __init__(self, product: str) -> None:
        self._product = product

    @property
    def prod(self) -> str:
        return self._product


def test_verified_valid_product() -> None:
    result = engine.lint_mechanism("C[C:2](=[O:3])C.[NH3:1]|(1,2);((2,3),3)")

    assert result.is_valid is True
    assert result.final_smiles == "CC(C)([NH3+])[O-]"
    assert result.issues == []


def test_invalid_smiles_maps_to_smiles_invalid() -> None:
    result = engine.lint_mechanism("notasmiles|(1,2)")

    assert result.is_valid is False
    assert result.issues[0].code == ErrorCode.SMILES_INVALID


def test_context_mismatch_maps_to_context_incoherent() -> None:
    result = engine.lint_mechanism("C[C:2](=[O:3])C.[NH3:1]|(1,2)", context="CCO")

    assert result.is_valid is False
    assert result.issues[0].code == ErrorCode.CONTEXT_INCOHERENT


def test_nonexistent_bond_maps_to_bond_not_found() -> None:
    result = engine.lint_mechanism("[CH3:1].[OH-:2]|((1,2),2)")

    assert result.is_valid is False
    assert result.issues[0].code == ErrorCode.BOND_NOT_FOUND


def test_virtual_transition_state_failure_maps_to_move_state_conflict() -> None:
    result = engine.lint_mechanism("C[C:2](=[O:3])C.[F-:1]|(1,2)")

    assert result.is_valid is False
    assert result.issues[0].code == ErrorCode.MOVE_STATE_CONFLICT


def test_radical_noop_succeeds() -> None:
    result = engine.lint_mechanism("[CH3:1]|")

    assert result.is_valid is True
    assert result.final_smiles == "[CH3]"


@pytest.mark.parametrize(
    ("mechsmiles", "expected_code"),
    [
        ("[OH-:1].[H+:2]|(1,2,3)", ErrorCode.ARROW_SHAPE_INVALID),
        ("[CH3:1][OH:1].[H+:2]|(1,2)", ErrorCode.ATOM_MAP_DUPLICATE),
        ("C[C:2](=[O:3])C.[NH3:1]|(9,2)", ErrorCode.ATOM_MAP_UNKNOWN),
        ('[OH-:1].[H+:2]|__import__("os").system("calc")', ErrorCode.ARROW_PARSE_FAILED),
        ("[OH-:1].[H+:2]|(1+1,2)", ErrorCode.ARROW_PARSE_FAILED),
    ],
)
def test_parser_failures_do_not_reach_upstream(
    monkeypatch: pytest.MonkeyPatch,
    mechsmiles: str,
    expected_code: ErrorCode,
) -> None:
    def fail_loader():
        raise AssertionError("upstream should not be loaded when parser validation fails")

    monkeypatch.setattr(engine, "_load_upstream_mechsmiles_class", fail_loader)

    result = engine.lint_mechanism(mechsmiles)

    assert result.is_valid is False
    assert result.issues[0].code == expected_code


def test_valid_input_reaches_upstream_with_canonical_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, str | None] = {}

    def fake_loader():
        def fake_constructor(value: str, context: str | None = None) -> FakeUpstreamMechanism:
            captured["value"] = value
            captured["context"] = context
            return FakeUpstreamMechanism("canonical-product")

        return fake_constructor

    monkeypatch.setattr(engine, "_load_upstream_mechsmiles_class", fake_loader)

    raw_input = "C[C:2](=[O:3])C.[NH3:1]|(1, 2);((2, 3), 3)"
    result = engine.lint_mechanism(raw_input, context="CCO")

    assert result.is_valid is True
    assert result.final_smiles == "canonical-product"
    assert captured == {
        "value": "C[C:2](=[O:3])C.[NH3:1]|(1,2);((2,3),3)",
        "context": "CCO",
    }
