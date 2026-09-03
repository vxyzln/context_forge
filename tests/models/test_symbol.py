from uuid import uuid4

import pytest

from context_forge.models.symbol import Symbol


def test_symbol_creation() -> None:
    file_id = uuid4()

    symbol = Symbol(
        file_id=file_id,
        name="Calculator",
        kind="class",
        start_line=1,
        end_line=10,
    )

    assert symbol.file_id == file_id
    assert symbol.name == "Calculator"
    assert symbol.kind == "class"
    assert symbol.start_line == 1
    assert symbol.end_line == 10
    assert symbol.qualified_name is None
    assert symbol.parent_symbol_id is None
    assert symbol.signature is None


def test_symbol_generates_unique_id() -> None:
    file_id = uuid4()

    symbol_a = Symbol(
        file_id=file_id,
        name="A",
        kind="class",
        start_line=1,
        end_line=2,
    )

    symbol_b = Symbol(
        file_id=file_id,
        name="B",
        kind="class",
        start_line=4,
        end_line=5,
    )

    assert symbol_a.id != symbol_b.id


def test_symbol_rejects_empty_name() -> None:
    with pytest.raises(ValueError, match="Symbol name cannot be empty"):
        Symbol(
            file_id=uuid4(),
            name="   ",
            kind="function",
            start_line=1,
            end_line=2,
        )


def test_symbol_rejects_empty_kind() -> None:
    with pytest.raises(ValueError, match="Symbol kind cannot be empty"):
        Symbol(
            file_id=uuid4(),
            name="hello",
            kind="   ",
            start_line=1,
            end_line=2,
        )


def test_symbol_rejects_invalid_start_line() -> None:
    with pytest.raises(ValueError, match="start line must be positive"):
        Symbol(
            file_id=uuid4(),
            name="hello",
            kind="function",
            start_line=0,
            end_line=2,
        )


def test_symbol_rejects_invalid_line_range() -> None:
    with pytest.raises(
        ValueError,
        match="end line cannot precede start line",
    ):
        Symbol(
            file_id=uuid4(),
            name="hello",
            kind="function",
            start_line=5,
            end_line=2,
        )


def test_symbol_accepts_structural_metadata() -> None:
    parent_id = uuid4()

    symbol = Symbol(
        file_id=uuid4(),
        name="add",
        kind="method",
        start_line=5,
        end_line=8,
        qualified_name="Calculator.add",
        parent_symbol_id=parent_id,
        signature="add(self, a, b)",
    )

    assert symbol.qualified_name == "Calculator.add"
    assert symbol.parent_symbol_id == parent_id
    assert symbol.signature == "add(self, a, b)"
