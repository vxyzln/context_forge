from uuid import uuid4

from context_forge.parser.result import ParseError, ParseResult


def test_empty_parse_result_is_successful() -> None:
    result = ParseResult()

    assert result.success is True
    assert result.symbols == []
    assert result.relationships == []
    assert result.errors == []


def test_parse_result_with_error_is_unsuccessful() -> None:
    file_id = uuid4()

    result = ParseResult(
        errors=[
            ParseError(
                message="Invalid syntax",
                file_id=file_id,
                line=10,
                column=5,
            )
        ]
    )

    assert result.success is False
    assert len(result.errors) == 1
    assert result.errors[0].message == "Invalid syntax"
    assert result.errors[0].file_id == file_id
    assert result.errors[0].line == 10
    assert result.errors[0].column == 5
