from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from context_forge.query.architecture_report import (
    build_architecture_report,
)


def _file(path: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        path=Path(path),
        extension=Path(path).suffix,
    )


def _relationship(source, target) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        source_id=source.id,
        target_id=target.id,
    )


def _inventory(
    *,
    files=(),
    directories=(),
    symbols=(),
    containment=(),
    dependencies=(),
    unresolved_imports=(),
    integrity_findings=(),
    errors=(),
    analysis_status="analyzed",
) -> SimpleNamespace:
    return SimpleNamespace(
        project_id=uuid4(),
        analysis_status=analysis_status,
        errors=tuple(errors),
        directories=tuple(directories),
        files=tuple(files),
        symbols=tuple(symbols),
        containment=tuple(containment),
        dependencies=tuple(dependencies),
        unresolved_imports=tuple(unresolved_imports),
        integrity_findings=tuple(integrity_findings),
    )


def test_report_counts_modules_packages_and_dependencies() -> None:
    init_file = _file("src/example/__init__.py")
    first = _file("src/example/first.py")
    second = _file("src/example/second.py")
    readme = _file("README.md")

    inventory = _inventory(
        files=(second, readme, first, init_file),
        dependencies=(
            _relationship(first, second),
            _relationship(first, second),
            _relationship(second, first),
        ),
    )

    report = build_architecture_report(inventory, "/repo")

    assert report["repository"] == "/repo"
    assert report["analysis"]["status"] == "analyzed"
    assert report["counts"] == {
        "directories": 0,
        "files": 4,
        "python_modules": 3,
        "packages": 1,
        "symbols": 0,
        "containment_edges": 0,
        "resolved_dependencies": 2,
        "unresolved_imports": 0,
        "structural_findings": 0,
        "cyclic_components": 1,
        "dependency_cycles": 1,
    }

    assert report["packages"]["items"] == [
        {
            "path": "src/example",
            "module_count": 3,
            "modules": [
                "src/example/__init__.py",
                "src/example/first.py",
                "src/example/second.py",
            ],
            "modules_truncated": False,
        }
    ]

    first_module = next(
        item
        for item in report["modules"]["items"]
        if item["path"] == "src/example/first.py"
    )
    assert first_module["direct_dependencies"] == ["src/example/second.py"]
    assert first_module["direct_dependency_count"] == 1
    assert first_module["direct_dependents"] == ["src/example/second.py"]


def test_dependency_direction_is_importer_to_imported_module() -> None:
    importer = _file("app.py")
    imported = _file("library.py")

    report = build_architecture_report(
        _inventory(
            files=(imported, importer),
            dependencies=(_relationship(importer, imported),),
        ),
        ".",
    )

    assert report["dependencies"]["items"] == [
        {"source": "app.py", "target": "library.py"}
    ]

    app = next(item for item in report["modules"]["items"] if item["path"] == "app.py")
    library = next(
        item for item in report["modules"]["items"] if item["path"] == "library.py"
    )

    assert app["direct_dependencies"] == ["library.py"]
    assert library["direct_dependents"] == ["app.py"]


def test_report_detects_self_import_cycle() -> None:
    module = _file("module.py")

    report = build_architecture_report(
        _inventory(
            files=(module,),
            dependencies=(_relationship(module, module),),
        ),
        ".",
    )

    assert report["counts"]["cyclic_components"] == 1
    assert report["counts"]["dependency_cycles"] == 1
    assert report["cycles"]["items"] == [
        {
            "module_count": 1,
            "modules": ["module.py"],
            "modules_truncated": False,
            "dependency_count": 1,
            "dependencies": [{"source": "module.py", "target": "module.py"}],
            "dependencies_truncated": False,
        }
    ]


def test_report_detects_multi_module_cycle_with_supporting_edges() -> None:
    first = _file("first.py")
    second = _file("second.py")
    third = _file("third.py")

    report = build_architecture_report(
        _inventory(
            files=(third, first, second),
            dependencies=(
                _relationship(first, second),
                _relationship(second, third),
                _relationship(third, first),
            ),
        ),
        ".",
    )

    assert report["counts"]["cyclic_components"] == 1
    assert report["counts"]["dependency_cycles"] == 1
    assert report["cycles"]["items"] == [
        {
            "module_count": 3,
            "modules": ["first.py", "second.py", "third.py"],
            "modules_truncated": False,
            "dependency_count": 3,
            "dependencies": [
                {"source": "first.py", "target": "second.py"},
                {"source": "second.py", "target": "third.py"},
                {"source": "third.py", "target": "first.py"},
            ],
            "dependencies_truncated": False,
        }
    ]


def test_report_keeps_unresolved_imports_out_of_dependencies() -> None:
    source = _file("app.py")
    unresolved = SimpleNamespace(
        file_id=source.id,
        module_name="missing_package",
        imported_name="MissingClass",
        alias="Missing",
        level=0,
        source_path=None,
    )

    report = build_architecture_report(
        _inventory(
            files=(source,),
            unresolved_imports=(unresolved,),
        ),
        ".",
    )

    assert report["counts"]["resolved_dependencies"] == 0
    assert report["dependencies"]["items"] == []
    assert report["counts"]["unresolved_imports"] == 1
    assert report["unresolved_imports"]["items"] == [
        {
            "source_id": str(source.id),
            "source_path": "app.py",
            "module_name": "missing_package",
            "imported_name": "MissingClass",
            "alias": "Missing",
            "level": 0,
        }
    ]


def test_report_preserves_incomplete_analysis_and_errors() -> None:
    report = build_architecture_report(
        _inventory(
            analysis_status="partial",
            errors=("Could not parse broken.py",),
        ),
        ".",
    )

    assert report["analysis"] == {
        "status": "partial",
        "errors": ["Could not parse broken.py"],
    }
    assert any(
        "may be incomplete" in limitation for limitation in report["limitations"]
    )
    assert any("contains errors" in limitation for limitation in report["limitations"])


def test_empty_inventory_produces_empty_sections_and_zero_counts() -> None:
    report = build_architecture_report(_inventory(), ".")

    assert report["counts"] == {
        "directories": 0,
        "files": 0,
        "python_modules": 0,
        "packages": 0,
        "symbols": 0,
        "containment_edges": 0,
        "resolved_dependencies": 0,
        "unresolved_imports": 0,
        "structural_findings": 0,
        "cyclic_components": 0,
        "dependency_cycles": 0,
    }

    for section in (
        "packages",
        "modules",
        "dependencies",
        "cycles",
        "unresolved_imports",
        "findings",
    ):
        assert report[section] == {
            "items": [],
            "total": 0,
            "limit": 50,
            "truncated": False,
        }


def test_report_limit_bounds_items_without_changing_counts() -> None:
    files = tuple(_file(f"module_{index}.py") for index in range(4))

    report = build_architecture_report(
        _inventory(files=files),
        ".",
        limit=2,
    )

    assert report["counts"]["python_modules"] == 4
    assert len(report["modules"]["items"]) == 2
    assert report["modules"]["total"] == 4
    assert report["modules"]["limit"] == 2
    assert report["modules"]["truncated"] is True


@pytest.mark.parametrize("limit", [0, -1, True, 1.5, "5"])
def test_report_rejects_invalid_limit(limit) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        build_architecture_report(_inventory(), ".", limit=limit)


def test_report_is_deterministic_regardless_of_inventory_order() -> None:
    first = _file("first.py")
    second = _file("second.py")
    third = _file("third.py")

    first_inventory = _inventory(
        files=(first, second, third),
        dependencies=(
            _relationship(first, second),
            _relationship(second, third),
        ),
    )
    second_inventory = _inventory(
        files=(third, first, second),
        dependencies=(
            _relationship(second, third),
            _relationship(first, second),
        ),
    )

    first_report = build_architecture_report(first_inventory, "/repo")
    second_report = build_architecture_report(second_inventory, "/repo")

    assert first_report["counts"] == second_report["counts"]
    assert first_report["modules"] == second_report["modules"]
    assert first_report["dependencies"] == second_report["dependencies"]
    assert first_report["cycles"] == second_report["cycles"]


def test_report_detects_multiple_independent_cycles() -> None:
    mod_a = _file("a.py")
    mod_b = _file("b.py")
    mod_c = _file("c.py")
    mod_d = _file("d.py")
    mod_e = _file("e.py")
    mod_f = _file("f.py")

    inventory = _inventory(
        files=(mod_a, mod_b, mod_c, mod_d, mod_e, mod_f),
        dependencies=(
            _relationship(mod_a, mod_b),
            _relationship(mod_b, mod_a),
            _relationship(mod_c, mod_d),
            _relationship(mod_d, mod_c),
            _relationship(mod_e, mod_f),
        ),
    )

    report = build_architecture_report(inventory, "/repo")

    assert report["counts"]["cyclic_components"] == 2
    assert report["counts"]["dependency_cycles"] == 2
    cycles = report["cycles"]["items"]
    assert len(cycles) == 2

    assert cycles[0]["module_count"] == 2
    assert cycles[0]["modules"] == ["a.py", "b.py"]
    assert cycles[0]["modules_truncated"] is False
    assert cycles[0]["dependency_count"] == 2
    assert cycles[0]["dependencies"] == [
        {"source": "a.py", "target": "b.py"},
        {"source": "b.py", "target": "a.py"},
    ]
    assert cycles[0]["dependencies_truncated"] is False

    assert cycles[1]["module_count"] == 2
    assert cycles[1]["modules"] == ["c.py", "d.py"]
    assert cycles[1]["modules_truncated"] is False
    assert cycles[1]["dependency_count"] == 2
    assert cycles[1]["dependencies"] == [
        {"source": "c.py", "target": "d.py"},
        {"source": "d.py", "target": "c.py"},
    ]
    assert cycles[1]["dependencies_truncated"] is False


def test_report_detects_overlapping_cycles_as_strongly_connected_component() -> None:
    mod_a = _file("a.py")
    mod_b = _file("b.py")
    mod_c = _file("c.py")
    mod_d = _file("d.py")

    inventory = _inventory(
        files=(mod_a, mod_b, mod_c, mod_d),
        dependencies=(
            _relationship(mod_a, mod_b),
            _relationship(mod_b, mod_c),
            _relationship(mod_c, mod_a),
            _relationship(mod_b, mod_d),
            _relationship(mod_d, mod_b),
        ),
    )

    report = build_architecture_report(inventory, "/repo")

    assert report["counts"]["cyclic_components"] == 1
    assert report["counts"]["dependency_cycles"] == 1
    cycle = report["cycles"]["items"][0]
    assert cycle["module_count"] == 4
    assert cycle["modules"] == ["a.py", "b.py", "c.py", "d.py"]
    assert cycle["modules_truncated"] is False
    assert cycle["dependency_count"] == 5
    assert len(cycle["dependencies"]) == 5
    assert cycle["dependencies_truncated"] is False


def test_report_includes_structural_findings_with_evidence() -> None:
    source_id = uuid4()
    target_id = uuid4()

    finding = SimpleNamespace(
        finding_type="inconsistent_symbol_parent",
        message="Child symbol references parent in different file",
        source_type="symbol",
        source_id=source_id,
        source_path="pkg/child.py::ChildClass",
        target_type="symbol",
        target_id=target_id,
    )

    inventory = _inventory(
        integrity_findings=(finding,),
    )

    report = build_architecture_report(inventory, "/repo")

    assert report["counts"]["structural_findings"] == 1
    assert report["findings"]["items"] == [
        {
            "type": "inconsistent_symbol_parent",
            "message": "Child symbol references parent in different file",
            "source_type": "symbol",
            "source_id": str(source_id),
            "source_path": "pkg/child.py::ChildClass",
            "target_type": "symbol",
            "target_id": str(target_id),
        }
    ]


def test_report_truncation_indicators_across_all_sections() -> None:
    init_1 = _file("pkg1/__init__.py")
    mod_1 = _file("pkg1/a.py")
    init_2 = _file("pkg2/__init__.py")
    mod_2 = _file("pkg2/b.py")

    unres_1 = SimpleNamespace(
        file_id=mod_1.id,
        module_name="missing_1",
        imported_name=None,
        alias=None,
        level=0,
        source_path=mod_1.path,
    )
    unres_2 = SimpleNamespace(
        file_id=mod_2.id,
        module_name="missing_2",
        imported_name=None,
        alias=None,
        level=0,
        source_path=mod_2.path,
    )

    finding_1 = SimpleNamespace(
        finding_type="type_a",
        message="msg 1",
        source_type="file",
        source_id=mod_1.id,
        source_path="pkg1/a.py",
        target_type=None,
        target_id=None,
    )
    finding_2 = SimpleNamespace(
        finding_type="type_b",
        message="msg 2",
        source_type="file",
        source_id=mod_2.id,
        source_path="pkg2/b.py",
        target_type=None,
        target_id=None,
    )

    inventory = _inventory(
        files=(init_1, mod_1, init_2, mod_2),
        dependencies=(
            _relationship(mod_1, mod_2),
            _relationship(mod_2, mod_1),
        ),
        unresolved_imports=(unres_1, unres_2),
        integrity_findings=(finding_1, finding_2),
    )

    report = build_architecture_report(inventory, "/repo", limit=1)

    for section in (
        "packages",
        "modules",
        "dependencies",
        "unresolved_imports",
        "findings",
    ):
        assert report[section]["limit"] == 1
        assert len(report[section]["items"]) == 1
        assert report[section]["total"] > 1
        assert report[section]["truncated"] is True


def test_report_bounds_modules_and_dependencies_inside_large_cyclic_component() -> None:
    files = tuple(_file(f"mod_{i}.py") for i in range(5))
    deps = [
        _relationship(files[0], files[1]),
        _relationship(files[1], files[2]),
        _relationship(files[2], files[3]),
        _relationship(files[3], files[4]),
        _relationship(files[4], files[0]),
        _relationship(files[0], files[2]),
    ]

    report = build_architecture_report(
        _inventory(files=files, dependencies=deps),
        "/repo",
        limit=2,
    )

    assert report["counts"]["cyclic_components"] == 1
    assert report["counts"]["dependency_cycles"] == 1
    cycle = report["cycles"]["items"][0]

    assert cycle["module_count"] == 5
    assert len(cycle["modules"]) == 2
    assert cycle["modules"] == ["mod_0.py", "mod_1.py"]
    assert cycle["modules_truncated"] is True

    assert cycle["dependency_count"] == 6
    assert len(cycle["dependencies"]) == 2
    assert cycle["dependencies"] == [
        {"source": "mod_0.py", "target": "mod_1.py"},
        {"source": "mod_0.py", "target": "mod_2.py"},
    ]
    assert cycle["dependencies_truncated"] is True

    permuted_files = (files[3], files[0], files[4], files[1], files[2])
    permuted_deps = list(reversed(deps))
    permuted_report = build_architecture_report(
        _inventory(files=permuted_files, dependencies=permuted_deps),
        "/repo",
        limit=2,
    )
    assert report["cycles"] == permuted_report["cycles"]


def test_report_limitations_document_scc_semantics_and_conventional_packages() -> None:
    report = build_architecture_report(_inventory(), ".")

    limitations = report["limitations"]
    assert any(
        "strongly connected components" in item and "multiple simple cycles" in item
        for item in limitations
    )
    assert any(
        "conventional Python packages" in item and "__init__.py" in item
        for item in limitations
    )


def test_architecture_report_outcome_contract() -> None:

    clean_report = build_architecture_report(_inventory(), ".")
    assert "outcome" in clean_report
    assert clean_report["outcome"]["status"] == "success"
    assert clean_report["outcome"]["is_success"] is True

    error_inv = _inventory(
        analysis_status="partial",
        errors=("Syntax error in foo.py",),
    )
    error_report = build_architecture_report(error_inv, ".")
    assert error_report["outcome"]["status"] == "partial"
    assert error_report["outcome"]["is_success"] is False
    assert any(
        d["code"] == "ANALYSIS_ERROR" and d["severity"] == "error"
        for d in error_report["outcome"]["diagnostics"]
    )
