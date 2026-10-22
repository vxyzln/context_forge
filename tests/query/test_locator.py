from __future__ import annotations

from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest

from context_forge.models.file import File
from context_forge.models.project import Project
from context_forge.models.symbol import Symbol
from context_forge.query.impact import ResolvedTarget
from context_forge.query.locator import (
    get_source_evidence,
    locate_and_get_evidence,
    locate_symbol,
)
from context_forge.query.project import ProjectQuery
from context_forge.reporting.contract import DiagnosticSeverity, OperationStatus


@pytest.fixture
def sample_project(tmp_path: Path) -> Project:
    project = Project(
        name="test_project",
        root_path=tmp_path.resolve(),
    )

    file1_path = Path("src/calculator.py")
    file1_full = tmp_path / file1_path
    file1_full.parent.mkdir(parents=True, exist_ok=True)
    file1_content = (
        "class Calculator:\n"
        "    def __init__(self):\n"
        "        self.value = 0\n"
        "\n"
        "    def add(self, x, y):\n"
        "        return x + y\n"
        "\n"
        "    def multiply(self, x, y):\n"
        "        return x * y\n"
        "\n"
        "def compute_total(items):\n"
        "    return sum(items)\n"
    )
    file1_full.write_text(file1_content, encoding="utf-8")
    file1 = File(
        id=uuid4(),
        project_id=project.id,
        path=file1_path,
        name="calculator.py",
        extension=".py",
    )
    project.add_file(file1)

    sym_calc = Symbol(
        id=uuid4(),
        file_id=file1.id,
        name="Calculator",
        kind="class",
        qualified_name="calculator.Calculator",
        start_line=1,
        end_line=9,
        signature="class Calculator:",
    )
    sym_calc_add = Symbol(
        id=uuid4(),
        file_id=file1.id,
        name="add",
        kind="method",
        qualified_name="calculator.Calculator.add",
        start_line=5,
        end_line=6,
        signature="def add(self, x, y):",
    )
    sym_calc_mul = Symbol(
        id=uuid4(),
        file_id=file1.id,
        name="multiply",
        kind="method",
        qualified_name="calculator.Calculator.multiply",
        start_line=8,
        end_line=9,
        signature="def multiply(self, x, y):",
    )
    sym_compute = Symbol(
        id=uuid4(),
        file_id=file1.id,
        name="compute_total",
        kind="function",
        qualified_name="calculator.compute_total",
        start_line=11,
        end_line=12,
        signature="def compute_total(items):",
    )
    project.add_symbol(sym_calc)
    project.add_symbol(sym_calc_add)
    project.add_symbol(sym_calc_mul)
    project.add_symbol(sym_compute)

    file2_path = Path("src/math_ops.py")
    file2_full = tmp_path / file2_path
    file2_full.parent.mkdir(parents=True, exist_ok=True)
    file2_content = (
        "def add(a, b):\n    return a + b\n\ndef subtract(a, b):\n    return a - b\n"
    )
    file2_full.write_text(file2_content, encoding="utf-8")
    file2 = File(
        id=uuid4(),
        project_id=project.id,
        path=file2_path,
        name="math_ops.py",
        extension=".py",
    )
    project.add_file(file2)

    sym_ops_add = Symbol(
        id=uuid4(),
        file_id=file2.id,
        name="add",
        kind="function",
        qualified_name="math_ops.add",
        start_line=1,
        end_line=2,
        signature="def add(a, b):",
    )
    sym_ops_sub = Symbol(
        id=uuid4(),
        file_id=file2.id,
        name="subtract",
        kind="function",
        qualified_name="math_ops.subtract",
        start_line=4,
        end_line=5,
        signature="def subtract(a, b):",
    )
    project.add_symbol(sym_ops_add)
    project.add_symbol(sym_ops_sub)

    return project


def test_locate_symbol_unique_exact_name(sample_project: Project) -> None:
    resolution = locate_symbol(sample_project, "Calculator")

    assert resolution.is_resolved is True
    assert resolution.is_ambiguous is False
    assert resolution.is_not_found is False
    assert resolution.status == "resolved"
    assert resolution.target is not None
    assert resolution.target.name == "Calculator"
    assert resolution.target.kind == "class"
    assert resolution.target.path == "src/calculator.py"
    assert resolution.target.start_line == 1
    assert resolution.target.end_line == 9
    assert resolution.outcome.is_success is True


def test_locate_symbol_qualified_name(sample_project: Project) -> None:

    res_qual = locate_symbol(sample_project, "calculator.Calculator.add")

    assert res_qual.is_resolved is True
    assert res_qual.target is not None
    assert res_qual.target.name == "add"
    assert res_qual.target.kind == "method"
    assert res_qual.target.path == "src/calculator.py"

    res_qual2 = locate_symbol(sample_project, "math_ops.add")
    assert res_qual2.is_resolved is True
    assert res_qual2.target is not None
    assert res_qual2.target.kind == "function"
    assert res_qual2.target.path == "src/math_ops.py"


def test_locate_symbol_explicit_qualified_name_argument(
    sample_project: Project,
) -> None:
    resolution = locate_symbol(
        sample_project,
        "add",
        qualified_name="calculator.Calculator.add",
    )
    assert resolution.is_resolved is True
    assert resolution.target is not None
    assert resolution.target.path == "src/calculator.py"


def test_locate_symbol_ambiguous_without_filter(sample_project: Project) -> None:

    resolution = locate_symbol(sample_project, "add")

    assert resolution.is_resolved is False
    assert resolution.is_ambiguous is True
    assert resolution.status == "ambiguous"
    assert resolution.target is None
    assert len(resolution.candidates) == 2

    paths = [c.path for c in resolution.candidates]
    assert paths == ["src/calculator.py", "src/math_ops.py"]

    assert resolution.candidates[0].name == "add"
    assert resolution.candidates[0].kind == "method"
    assert resolution.candidates[1].name == "add"
    assert resolution.candidates[1].kind == "function"

    assert resolution.outcome.is_success is False
    assert resolution.outcome.status == OperationStatus.BLOCKED
    assert resolution.outcome.diagnostics[0].code == "TARGET_AMBIGUOUS"


def test_locate_symbol_file_filter_disambiguates(sample_project: Project) -> None:

    res1 = locate_symbol(sample_project, "add", file_path="src/calculator.py")
    assert res1.is_resolved is True
    assert res1.target is not None
    assert res1.target.path == "src/calculator.py"
    assert res1.target.kind == "method"

    res2 = locate_symbol(sample_project, "add", file_path="math_ops.py")
    assert res2.is_resolved is True
    assert res2.target is not None
    assert res2.target.path == "src/math_ops.py"
    assert res2.target.kind == "function"


def test_locate_symbol_type_filter_disambiguates(sample_project: Project) -> None:

    res_method = locate_symbol(sample_project, "add", symbol_type="method")
    assert res_method.is_resolved is True
    assert res_method.target is not None
    assert res_method.target.kind == "method"
    assert res_method.target.path == "src/calculator.py"

    res_func = locate_symbol(sample_project, "add", symbol_type="function")
    assert res_func.is_resolved is True
    assert res_func.target is not None
    assert res_func.target.kind == "function"
    assert res_func.target.path == "src/math_ops.py"


def test_locate_symbol_combined_filters(sample_project: Project) -> None:
    resolution = locate_symbol(
        sample_project,
        "add",
        file_path="src/calculator.py",
        symbol_type="method",
    )
    assert resolution.is_resolved is True
    assert resolution.target is not None
    assert resolution.target.name == "add"
    assert resolution.target.kind == "method"

    res_none = locate_symbol(
        sample_project,
        "add",
        file_path="src/calculator.py",
        symbol_type="function",
    )
    assert res_none.is_not_found is True
    assert res_none.status == "not_found"
    assert "not found" in res_none.message


def test_locate_symbol_not_found(sample_project: Project) -> None:
    resolution = locate_symbol(sample_project, "nonexistent_symbol")

    assert resolution.is_not_found is True
    assert resolution.is_resolved is False
    assert resolution.status == "not_found"
    assert resolution.target is None
    assert resolution.outcome.is_success is False
    assert resolution.outcome.status == OperationStatus.BLOCKED
    assert resolution.outcome.diagnostics[0].code == "TARGET_NOT_FOUND"


def test_locate_symbol_invalid_requests(sample_project: Project) -> None:

    res_empty = locate_symbol(sample_project, "   ")
    assert res_empty.status == "invalid"
    assert res_empty.is_invalid is True
    assert res_empty.is_resolved is False
    assert res_empty.outcome.is_success is False

    res_type = locate_symbol(sample_project, 123)  # type: ignore[arg-type]
    assert res_type.status == "invalid"

    res_bad_file = locate_symbol(sample_project, "Calculator", file_path="   ")
    assert res_bad_file.status == "invalid"

    res_bad_type = locate_symbol(sample_project, "Calculator", symbol_type="  ")
    assert res_bad_type.status == "invalid"


def test_locate_symbol_preserves_stable_identity(sample_project: Project) -> None:
    original_sym = next(s for s in sample_project.symbols if s.name == "Calculator")
    resolution = locate_symbol(sample_project, "Calculator")

    assert resolution.target is not None
    assert resolution.target.id == original_sym.id
    assert resolution.target.start_line == original_sym.start_line
    assert resolution.target.end_line == original_sym.end_line
    assert resolution.target.signature == original_sym.signature


def test_get_source_evidence_successful_excerpt(sample_project: Project) -> None:
    resolution = locate_symbol(sample_project, "Calculator")
    assert resolution.target is not None

    evidence = get_source_evidence(sample_project, resolution.target)

    assert evidence.status == "success"
    assert evidence.is_success is True
    assert evidence.path == "src/calculator.py"
    assert evidence.start_line == 1
    assert evidence.end_line == 9
    assert evidence.total_lines == 9
    assert evidence.is_truncated is False
    assert "class Calculator:" in evidence.content
    assert "def multiply(self, x, y):" in evidence.content
    assert evidence.outcome.is_success is True
    assert evidence.outcome.status == OperationStatus.SUCCESS


def test_get_source_evidence_first_and_last_lines_mapping(
    sample_project: Project,
) -> None:
    resolution = locate_symbol(sample_project, "add", file_path="src/calculator.py")
    assert resolution.target is not None

    evidence = get_source_evidence(sample_project, resolution.target)

    assert evidence.status == "success"
    assert evidence.start_line == 5
    assert evidence.end_line == 6
    assert evidence.total_lines == 2
    expected_lines = ["    def add(self, x, y):", "        return x + y"]
    assert evidence.content == "\n".join(expected_lines)


def test_get_source_evidence_truncation_boundary(
    sample_project: Project,
    tmp_path: Path,
) -> None:

    large_file = tmp_path / "src/large.py"
    lines = [f"def large_function():  # line {i}" for i in range(1, 31)]
    large_file.write_text("\n".join(lines), encoding="utf-8")

    f_large = File(
        id=uuid4(),
        project_id=sample_project.id,
        path=Path("src/large.py"),
        name="large.py",
        extension=".py",
    )
    sample_project.add_file(f_large)

    sym_large = Symbol(
        id=uuid4(),
        file_id=f_large.id,
        name="large_function",
        kind="function",
        start_line=1,
        end_line=30,
    )
    sample_project.add_symbol(sym_large)

    evidence = get_source_evidence(sample_project, sym_large, max_lines=10)

    assert evidence.status == "success"
    assert evidence.is_truncated is True
    assert evidence.start_line == 1
    assert evidence.end_line == 10
    assert evidence.total_lines == 10
    assert len(evidence.content.splitlines()) == 10
    assert any("truncated to 10 lines" in lim for lim in evidence.limitations)


def test_get_source_evidence_missing_or_deleted_file(
    sample_project: Project,
    tmp_path: Path,
) -> None:
    resolution = locate_symbol(sample_project, "Calculator")
    assert resolution.target is not None

    (tmp_path / "src/calculator.py").unlink()

    evidence = get_source_evidence(sample_project, resolution.target)

    assert evidence.status == "missing_file"
    assert evidence.is_success is False
    assert evidence.content == ""
    assert "does not exist" in evidence.message
    assert evidence.outcome.is_success is False
    assert evidence.outcome.status == OperationStatus.BLOCKED
    assert evidence.outcome.diagnostics[0].code == "MISSING_FILE"


def test_get_source_evidence_unreadable_file_io_error(sample_project: Project) -> None:
    resolution = locate_symbol(sample_project, "Calculator")
    assert resolution.target is not None

    with patch.object(
        Path, "read_text", side_effect=PermissionError("Permission denied")
    ):
        evidence = get_source_evidence(sample_project, resolution.target)

    assert evidence.status == "unreadable_file"
    assert evidence.is_success is False
    assert "Permission denied" in evidence.message
    assert evidence.outcome.status == OperationStatus.BLOCKED
    assert evidence.outcome.diagnostics[0].code == "UNREADABLE_FILE"


def test_get_source_evidence_invalid_location(sample_project: Project) -> None:
    sym_invalid_start = Symbol(
        id=uuid4(),
        file_id=sample_project.files[0].id,
        name="bad_start",
        kind="function",
        start_line=1,
        end_line=5,
    )

    object.__setattr__(sym_invalid_start, "start_line", 0)

    evidence = get_source_evidence(sample_project, sym_invalid_start)
    assert evidence.status == "invalid_location"
    assert evidence.is_success is False
    assert evidence.outcome.status == OperationStatus.BLOCKED


def test_get_source_evidence_location_out_of_range(
    sample_project: Project,
    tmp_path: Path,
) -> None:

    (tmp_path / "src/calculator.py").write_text("x = 1\n", encoding="utf-8")

    resolution = locate_symbol(sample_project, "compute_total")
    assert resolution.target is not None

    evidence = get_source_evidence(sample_project, resolution.target)

    assert evidence.status == "location_out_of_range"
    assert evidence.is_success is False
    assert "exceeds current file line count" in evidence.message
    assert evidence.outcome.status == OperationStatus.BLOCKED


def test_get_source_evidence_stale_location_detected(
    sample_project: Project,
    tmp_path: Path,
) -> None:

    new_content = (
        "# Modified file without target class\n"
        "a = 10\n"
        "b = 20\n"
        "c = 30\n"
        "d = 40\n"
        "e = 50\n"
        "f = 60\n"
        "g = 70\n"
        "h = 80\n"
    )
    (tmp_path / "src/calculator.py").write_text(new_content, encoding="utf-8")

    resolution = locate_symbol(sample_project, "Calculator")
    assert resolution.target is not None

    evidence = get_source_evidence(sample_project, resolution.target)

    assert evidence.status == "stale_location"
    assert evidence.is_success is True
    assert evidence.total_lines == 9
    assert any(
        "does not contain symbol 'Calculator'" in lim for lim in evidence.limitations
    )
    assert evidence.outcome.status == OperationStatus.PARTIAL
    assert evidence.outcome.diagnostics[0].code == "STALE_SOURCE_LOCATION"
    assert evidence.outcome.diagnostics[0].severity == DiagnosticSeverity.WARNING


def test_get_source_evidence_never_uses_cached_source_text(
    sample_project: Project,
    tmp_path: Path,
) -> None:

    (tmp_path / "src/calculator.py").write_text(
        "class Calculator:\n    # UPDATED ON DISK\n    pass\n",
        encoding="utf-8",
    )

    resolution = locate_symbol(sample_project, "Calculator")
    assert resolution.target is not None

    evidence = get_source_evidence(sample_project, resolution.target)

    assert "# UPDATED ON DISK" in evidence.content


def test_locate_and_get_evidence_integrated_flow(sample_project: Project) -> None:

    res1, ev1 = locate_and_get_evidence(sample_project, "Calculator")
    assert res1.is_resolved is True
    assert ev1 is not None
    assert ev1.status == "success"
    assert "class Calculator:" in ev1.content

    res2, ev2 = locate_and_get_evidence(sample_project, "add")
    assert res2.is_ambiguous is True
    assert ev2 is None

    res3, ev3 = locate_and_get_evidence(sample_project, "missing")
    assert res3.is_not_found is True
    assert ev3 is None


def test_project_query_locator_methods(sample_project: Project) -> None:
    query = ProjectQuery(sample_project)

    res = query.locate_symbol("Calculator")
    assert res.is_resolved is True
    assert res.target is not None

    ev = query.get_source_evidence(res.target)
    assert ev.status == "success"

    res_comb, ev_comb = query.locate_and_get_evidence("Calculator")
    assert res_comb.is_resolved is True
    assert ev_comb is not None
    assert ev_comb.status == "success"


def test_get_source_evidence_rejects_parent_traversal(sample_project: Project) -> None:
    target = ResolvedTarget(
        id=uuid4(),
        target_type="symbol",
        name="secret",
        path="../../etc/passwd",
        kind="function",
        start_line=1,
        end_line=5,
    )

    evidence = get_source_evidence(sample_project, target)

    assert evidence.status == "path_outside_root"
    assert evidence.is_success is False
    assert evidence.content == ""
    assert evidence.total_lines == 0
    assert evidence.outcome.status == OperationStatus.BLOCKED
    assert evidence.outcome.diagnostics[0].code == "PATH_OUTSIDE_ROOT"
    assert evidence.outcome.diagnostics[0].severity == DiagnosticSeverity.BLOCKER


def test_get_source_evidence_rejects_absolute_path(
    sample_project: Project,
    tmp_path: Path,
) -> None:
    outside_file = tmp_path.parent / "outside_test.py"
    target = ResolvedTarget(
        id=uuid4(),
        target_type="symbol",
        name="secret",
        path=str(outside_file),
        kind="function",
        start_line=1,
        end_line=5,
    )

    evidence = get_source_evidence(sample_project, target)

    assert evidence.status == "path_outside_root"
    assert evidence.is_success is False
    assert evidence.content == ""
    assert evidence.outcome.status == OperationStatus.BLOCKED
    assert evidence.outcome.diagnostics[0].code == "PATH_OUTSIDE_ROOT"


def test_get_source_evidence_rejects_symlink_escaping_root(
    sample_project: Project,
    tmp_path: Path,
) -> None:
    outside_dir = tmp_path.parent / "test_outside_dir"
    outside_dir.mkdir(parents=True, exist_ok=True)
    outside_file = outside_dir / "external_secret.py"
    outside_file.write_text("SENSITIVE_KEY = 'super_secret'\n", encoding="utf-8")

    link_path = tmp_path / "src" / "symlink_escape.py"
    try:
        link_path.symlink_to(outside_file)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation not supported on this platform/environment")

    target = ResolvedTarget(
        id=uuid4(),
        target_type="symbol",
        name="secret",
        path="src/symlink_escape.py",
        kind="function",
        start_line=1,
        end_line=2,
    )

    evidence = get_source_evidence(sample_project, target)

    assert evidence.status == "path_outside_root"
    assert evidence.is_success is False
    assert evidence.content == ""
    assert "super_secret" not in evidence.content
    assert evidence.outcome.status == OperationStatus.BLOCKED
    assert evidence.outcome.diagnostics[0].code == "PATH_OUTSIDE_ROOT"


def test_get_source_evidence_allows_nested_source_file(
    sample_project: Project,
    tmp_path: Path,
) -> None:
    nested_dir = tmp_path / "src" / "nested" / "subpkg"
    nested_dir.mkdir(parents=True, exist_ok=True)
    nested_file = nested_dir / "service.py"
    nested_file.write_text(
        "class NestedService:\n    def run(self):\n        return True\n",
        encoding="utf-8",
    )

    target = ResolvedTarget(
        id=uuid4(),
        target_type="symbol",
        name="NestedService",
        path="src/nested/subpkg/service.py",
        kind="class",
        start_line=1,
        end_line=3,
    )

    evidence = get_source_evidence(sample_project, target)

    assert evidence.status == "success"
    assert evidence.is_success is True
    assert "class NestedService:" in evidence.content
    assert evidence.total_lines == 3


def test_get_source_evidence_with_root_path_override(
    sample_project: Project,
    tmp_path: Path,
) -> None:

    src_dir = tmp_path / "src"
    target = ResolvedTarget(
        id=uuid4(),
        target_type="symbol",
        name="test",
        path="../outside.py",
        kind="function",
        start_line=1,
        end_line=2,
    )

    evidence = get_source_evidence(sample_project, target, root_path=src_dir)

    assert evidence.status == "path_outside_root"
    assert evidence.is_success is False
    assert evidence.outcome.status == OperationStatus.BLOCKED


def test_stale_source_accepts_valid_class_and_method_definitions(
    sample_project: Project,
    tmp_path: Path,
) -> None:
    code = (
        "class DataProcessor:\n"
        "    def process(self, data):\n"
        "        return data.strip()\n"
    )
    (tmp_path / "src" / "processor.py").write_text(code, encoding="utf-8")

    class_target = ResolvedTarget(
        id=uuid4(),
        target_type="symbol",
        name="DataProcessor",
        path="src/processor.py",
        kind="class",
        start_line=1,
        end_line=3,
    )
    method_target = ResolvedTarget(
        id=uuid4(),
        target_type="symbol",
        name="process",
        path="src/processor.py",
        kind="method",
        start_line=2,
        end_line=3,
    )

    class_ev = get_source_evidence(sample_project, class_target)
    assert class_ev.status == "success"
    assert class_ev.is_success is True
    assert "class DataProcessor:" in class_ev.content

    method_ev = get_source_evidence(sample_project, method_target)
    assert method_ev.status == "success"
    assert method_ev.is_success is True
    assert "def process(self, data):" in method_ev.content


def test_stale_source_rejects_symbol_name_only_in_comment(
    sample_project: Project,
    tmp_path: Path,
) -> None:

    code = (
        "# class DataProcessor:\n"
        "# This comment mentions DataProcessor but is not a definition\n"
        "value = 100\n"
    )
    (tmp_path / "src" / "processor.py").write_text(code, encoding="utf-8")

    target = ResolvedTarget(
        id=uuid4(),
        target_type="symbol",
        name="DataProcessor",
        path="src/processor.py",
        kind="class",
        start_line=1,
        end_line=3,
    )

    evidence = get_source_evidence(sample_project, target)

    assert evidence.status == "stale_location"
    assert evidence.is_success is True
    assert evidence.total_lines == 3
    assert evidence.outcome.status == OperationStatus.PARTIAL
    assert evidence.outcome.diagnostics[0].code == "STALE_SOURCE_LOCATION"
    assert evidence.outcome.diagnostics[0].severity == DiagnosticSeverity.WARNING
    assert any("DataProcessor" in lim for lim in evidence.limitations)


def test_stale_source_rejects_symbol_name_only_in_unrelated_expression_or_string(
    sample_project: Project,
    tmp_path: Path,
) -> None:
    code = (
        "processor_name = 'DataProcessor'\n"
        "active_log = f'Logging for {processor_name}'\n"
        "result = compute(processor_name)\n"
    )
    (tmp_path / "src" / "processor.py").write_text(code, encoding="utf-8")

    target = ResolvedTarget(
        id=uuid4(),
        target_type="symbol",
        name="DataProcessor",
        path="src/processor.py",
        kind="class",
        start_line=1,
        end_line=3,
    )

    evidence = get_source_evidence(sample_project, target)

    assert evidence.status == "stale_location"
    assert evidence.is_success is True
    assert evidence.outcome.status == OperationStatus.PARTIAL
    assert evidence.outcome.diagnostics[0].code == "STALE_SOURCE_LOCATION"


def test_stale_source_detects_moved_or_removed_definition(
    sample_project: Project,
    tmp_path: Path,
) -> None:

    code = "def unrelated_helper():\n    return 42\n\nclass DataProcessor:\n    pass\n"
    (tmp_path / "src" / "processor.py").write_text(code, encoding="utf-8")

    target = ResolvedTarget(
        id=uuid4(),
        target_type="symbol",
        name="DataProcessor",
        path="src/processor.py",
        kind="class",
        start_line=1,
        end_line=2,
    )

    evidence = get_source_evidence(sample_project, target)

    assert evidence.status == "stale_location"
    assert evidence.is_success is True
    assert evidence.outcome.status == OperationStatus.PARTIAL
    assert evidence.outcome.diagnostics[0].code == "STALE_SOURCE_LOCATION"


def test_stale_source_accepts_decorated_and_multiline_definitions(
    sample_project: Project,
    tmp_path: Path,
) -> None:
    code = (
        "@staticmethod\n"
        "@registry.register(\n"
        "    version='1.0',\n"
        "    enabled=True,\n"
        ")\n"
        "def execute_task(\n"
        "    task_id: str,\n"
        "    timeout: int = 30,\n"
        ") -> bool:\n"
        "    return True\n"
    )
    (tmp_path / "src" / "task.py").write_text(code, encoding="utf-8")

    target_from_decorator = ResolvedTarget(
        id=uuid4(),
        target_type="symbol",
        name="execute_task",
        path="src/task.py",
        kind="function",
        start_line=1,
        end_line=10,
    )
    ev1 = get_source_evidence(sample_project, target_from_decorator)
    assert ev1.status == "success"
    assert ev1.is_success is True

    target_from_def = ResolvedTarget(
        id=uuid4(),
        target_type="symbol",
        name="execute_task",
        path="src/task.py",
        kind="function",
        start_line=6,
        end_line=10,
    )
    ev2 = get_source_evidence(sample_project, target_from_def)
    assert ev2.status == "success"
    assert ev2.is_success is True


def test_stale_source_constant_valid_and_stale(
    sample_project: Project,
    tmp_path: Path,
) -> None:

    code = "MAX_RETRIES = 5\nDEFAULT_TIMEOUT: int = 30\n"
    (tmp_path / "src" / "constants.py").write_text(code, encoding="utf-8")

    t1 = ResolvedTarget(
        id=uuid4(),
        target_type="symbol",
        name="MAX_RETRIES",
        path="src/constants.py",
        kind="constant",
        start_line=1,
        end_line=1,
    )
    ev1 = get_source_evidence(sample_project, t1)
    assert ev1.status == "success"
    assert ev1.is_success is True
    assert "MAX_RETRIES = 5" in ev1.content

    t2 = ResolvedTarget(
        id=uuid4(),
        target_type="symbol",
        name="DEFAULT_TIMEOUT",
        path="src/constants.py",
        kind="constant",
        start_line=2,
        end_line=2,
    )
    ev2 = get_source_evidence(sample_project, t2)
    assert ev2.status == "success"
    assert ev2.is_success is True
    assert "DEFAULT_TIMEOUT: int = 30" in ev2.content

    (tmp_path / "src" / "constants.py").write_text(
        "# MAX_RETRIES = 5\nOTHER = 1\n",
        encoding="utf-8",
    )
    ev_stale_comment = get_source_evidence(sample_project, t1)
    assert ev_stale_comment.status == "stale_location"
    assert ev_stale_comment.outcome.status == OperationStatus.PARTIAL
    assert ev_stale_comment.outcome.diagnostics[0].code == "STALE_SOURCE_LOCATION"

    (tmp_path / "src" / "constants.py").write_text(
        "if x == MAX_RETRIES:\n    pass\n",
        encoding="utf-8",
    )
    ev_stale_expr = get_source_evidence(sample_project, t1)
    assert ev_stale_expr.status == "stale_location"
    assert ev_stale_expr.outcome.status == OperationStatus.PARTIAL


def test_stale_source_variable_valid_and_stale(
    sample_project: Project,
    tmp_path: Path,
) -> None:

    code = "active_count = 0\nuser_cache: dict[str, str] = {}\n"
    (tmp_path / "src" / "state.py").write_text(code, encoding="utf-8")

    t1 = ResolvedTarget(
        id=uuid4(),
        target_type="symbol",
        name="active_count",
        path="src/state.py",
        kind="variable",
        start_line=1,
        end_line=1,
    )
    ev1 = get_source_evidence(sample_project, t1)
    assert ev1.status == "success"
    assert ev1.is_success is True
    assert "active_count = 0" in ev1.content

    t2 = ResolvedTarget(
        id=uuid4(),
        target_type="symbol",
        name="user_cache",
        path="src/state.py",
        kind="variable",
        start_line=2,
        end_line=2,
    )
    ev2 = get_source_evidence(sample_project, t2)
    assert ev2.status == "success"
    assert ev2.is_success is True

    (tmp_path / "src" / "state.py").write_text(
        "# active_count = 0\nx = 1\n",
        encoding="utf-8",
    )
    ev_stale = get_source_evidence(sample_project, t1)
    assert ev_stale.status == "stale_location"
    assert ev_stale.outcome.status == OperationStatus.PARTIAL

    (tmp_path / "src" / "state.py").write_text(
        "log_msg = 'active_count is reset'\n",
        encoding="utf-8",
    )
    ev_stale_str = get_source_evidence(sample_project, t1)
    assert ev_stale_str.status == "stale_location"


def test_stale_source_import_valid_and_stale(
    sample_project: Project,
    tmp_path: Path,
) -> None:

    code = (
        "import os\n"
        "from pathlib import Path\n"
        "from typing import Any as AnyType\n"
        "from collections import (\n"
        "    defaultdict,\n"
        "    deque,\n"
        ")\n"
    )
    (tmp_path / "src" / "imports.py").write_text(code, encoding="utf-8")

    t_os = ResolvedTarget(
        id=uuid4(),
        target_type="symbol",
        name="os",
        path="src/imports.py",
        kind="import",
        start_line=1,
        end_line=1,
    )
    assert get_source_evidence(sample_project, t_os).status == "success"

    t_path = ResolvedTarget(
        id=uuid4(),
        target_type="symbol",
        name="Path",
        path="src/imports.py",
        kind="import",
        start_line=2,
        end_line=2,
    )
    assert get_source_evidence(sample_project, t_path).status == "success"

    t_alias = ResolvedTarget(
        id=uuid4(),
        target_type="symbol",
        name="AnyType",
        path="src/imports.py",
        kind="import",
        start_line=3,
        end_line=3,
    )
    assert get_source_evidence(sample_project, t_alias).status == "success"

    t_multi = ResolvedTarget(
        id=uuid4(),
        target_type="symbol",
        name="deque",
        path="src/imports.py",
        kind="import",
        start_line=4,
        end_line=7,
    )
    assert get_source_evidence(sample_project, t_multi).status == "success"

    (tmp_path / "src" / "imports.py").write_text(
        "# from pathlib import Path\nx = 1\n",
        encoding="utf-8",
    )
    ev_stale_comment = get_source_evidence(sample_project, t_path)
    assert ev_stale_comment.status == "stale_location"
    assert ev_stale_comment.outcome.status == OperationStatus.PARTIAL

    (tmp_path / "src" / "imports.py").write_text(
        "# Header line\np = Path('some/path')\n",
        encoding="utf-8",
    )
    ev_stale_use = get_source_evidence(sample_project, t_path)
    assert ev_stale_use.status == "stale_location"


def test_stale_source_unsupported_kind_reports_limitation_honestly(
    sample_project: Project,
    tmp_path: Path,
) -> None:
    code = "CUSTOM_MACRO_DEF(Calculator)\n"
    (tmp_path / "src" / "macro.py").write_text(code, encoding="utf-8")

    target = ResolvedTarget(
        id=uuid4(),
        target_type="symbol",
        name="Calculator",
        path="src/macro.py",
        kind="custom_macro",
        start_line=1,
        end_line=1,
    )

    evidence = get_source_evidence(sample_project, target)

    assert evidence.status == "success"
    assert evidence.is_success is True
    assert "CUSTOM_MACRO_DEF(Calculator)" in evidence.content
    assert any(
        "Definition header validation is not supported for symbol kind 'custom_macro'"
        in lim
        for lim in evidence.limitations
    )
