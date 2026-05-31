from __future__ import annotations

from arrowcheck.parser import parse_mechanism
from arrowcheck.taxonomy import ErrorCode


def test_valid_attack_parses() -> None:
    parsed, issues = parse_mechanism("[OH-:1].[H+:2]|(1,2)")

    assert issues == []
    assert parsed is not None
    assert parsed.normalized_mechsmiles == "[OH-:1].[H+:2]|(1,2)"


def test_valid_nested_tuple_parses() -> None:
    parsed, issues = parse_mechanism("C[C:2](=[O:3])C.[NH3:1]|(1,2);((2,3),3)")

    assert issues == []
    assert parsed is not None
    assert parsed.normalized_mechsmiles == "C[C:2](=[O:3])C.[NH3:1]|(1,2);((2,3),3)"


def test_valid_empty_arrow_section_parses() -> None:
    parsed, issues = parse_mechanism("[CH3:1]|")

    assert issues == []
    assert parsed is not None
    assert parsed.normalized_mechsmiles == "[CH3:1]|"


def test_empty_input_rejected() -> None:
    _, issues = parse_mechanism("")

    assert [issue.code for issue in issues] == [ErrorCode.INPUT_EMPTY]


def test_missing_delimiter_rejected() -> None:
    _, issues = parse_mechanism("[CH3:1]")

    assert [issue.code for issue in issues] == [ErrorCode.FORMAT_DELIMITER]


def test_multiple_delimiters_rejected() -> None:
    _, issues = parse_mechanism("[CH3:1]||")

    assert [issue.code for issue in issues] == [ErrorCode.FORMAT_DELIMITER]


def test_malformed_tuple_rejected() -> None:
    _, issues = parse_mechanism("[OH-:1].[H+:2]|(1,2,3)")

    assert [issue.code for issue in issues] == [ErrorCode.ARROW_SHAPE_INVALID]


def test_duplicate_map_rejected() -> None:
    _, issues = parse_mechanism("[CH3:1][OH:1].[H+:2]|(1,2)")

    assert [issue.code for issue in issues] == [ErrorCode.ATOM_MAP_DUPLICATE]


def test_unknown_map_rejected() -> None:
    _, issues = parse_mechanism("C[C:2](=[O:3])C.[NH3:1]|(9,2)")

    assert [issue.code for issue in issues] == [ErrorCode.ATOM_MAP_UNKNOWN]


def test_malicious_function_like_input_rejected() -> None:
    _, issues = parse_mechanism('[OH-:1].[H+:2]|__import__("os").system("calc")')

    assert [issue.code for issue in issues] == [ErrorCode.ARROW_PARSE_FAILED]


def test_arithmetic_expression_rejected() -> None:
    _, issues = parse_mechanism("[OH-:1].[H+:2]|(1+1,2)")

    assert [issue.code for issue in issues] == [ErrorCode.ARROW_PARSE_FAILED]


def test_list_input_rejected() -> None:
    _, issues = parse_mechanism("[OH-:1].[H+:2]|[1,2]")

    assert [issue.code for issue in issues] == [ErrorCode.ARROW_SHAPE_INVALID]
