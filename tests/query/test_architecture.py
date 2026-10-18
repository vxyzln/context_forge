from pathlib import Path
from uuid import uuid4

import pytest

from context_forge.models.directory import Directory
from context_forge.models.file import File
from context_forge.models.project import Project
from context_forge.models.relationship import Relationship, RelationshipType
from context_forge.models.symbol import Symbol
from context_forge.parser.result import ImportReference
from context_forge.query import (
    ArchitectureInventory,
    ContainmentEdge,
    ProjectQuery,
    StructuralFinding,
    StructuralIntegrityFinding,
    UnresolvedImport,
)


def create_architecture_project(tmp_path: Path) -> Project:
    project = Project(
        name="Architecture Test",
        root_path=tmp_path,
        analysis_status="analyzed",
    )

    src = Directory(
        project_id=project.id,
        path=Path("src"),
        name="src",
    )
    package = Directory(
        project_id=project.id,
        path=Path("src/package"),
        name="package",
        parent_id=src.id,
        depth=1,
    )

    project.add_directory(src)
    project.add_directory(package)

    main_file = File(
        project_id=project.id,
        path=Path("src/package/main.py"),
        name="main.py",
        extension=".py",
        directory_id=package.id,
    )
    helper_file = File(
        project_id=project.id,
        path=Path("src/package/helper.py"),
        name="helper.py",
        extension=".py",
        directory_id=package.id,
    )

    project.add_file(main_file)
    project.add_file(helper_file)

    main_symbol = Symbol(
        file_id=main_file.id,
        name="main",
        kind="function",
        start_line=1,
        end_line=2,
        qualified_name="main",
    )
    helper_symbol = Symbol(
        file_id=helper_file.id,
        name="helper",
        kind="function",
        start_line=1,
        end_line=2,
        qualified_name="helper",
    )

    project.add_symbol(main_symbol)
    project.add_symbol(helper_symbol)

    project.add_relationship(
        Relationship(
            source_id=main_file.id,
            target_id=helper_file.id,
            relationship_type=RelationshipType.IMPORTS,
        )
    )
    project.add_relationship(
        Relationship(
            source_id=main_file.id,
            target_id=main_symbol.id,
            relationship_type=RelationshipType.DEFINES,
        )
    )

    return project


def test_architecture_inventory_returns_supported_entities(
    tmp_path: Path,
) -> None:
    project = create_architecture_project(tmp_path)

    inventory = ProjectQuery(project).get_architecture_inventory()

    assert isinstance(inventory, ArchitectureInventory)
    assert inventory.project_id == project.id
    assert inventory.analysis_status == "analyzed"
    assert [item.path.as_posix() for item in inventory.directories] == [
        "src",
        "src/package",
    ]
    assert [item.path.as_posix() for item in inventory.files] == [
        "src/package/helper.py",
        "src/package/main.py",
    ]
    assert [item.name for item in inventory.symbols] == ["helper", "main"]


def test_architecture_inventory_separates_containment_and_dependencies(
    tmp_path: Path,
) -> None:
    project = create_architecture_project(tmp_path)

    inventory = ProjectQuery(project).get_architecture_inventory()

    assert len(inventory.dependencies) == 1
    dependency = inventory.dependencies[0]
    assert dependency.relationship_type == RelationshipType.IMPORTS

    assert (
        ContainmentEdge(
            source_type="directory",
            source_id=project.directories[0].id,
            target_type="directory",
            target_id=project.directories[1].id,
        )
        in inventory.containment
    )

    assert any(
        edge.source_type == "directory"
        and edge.target_type == "file"
        and edge.target_id == project.files[0].id
        for edge in inventory.containment
    )

    assert any(
        edge.source_type == "file" and edge.target_type == "symbol"
        for edge in inventory.containment
    )

    assert all(
        edge.source_type != "file" or edge.target_type != "file"
        for edge in inventory.containment
    )


@pytest.mark.parametrize(
    ("entity_type", "expected_count"),
    [
        ("directory", 2),
        ("file", 2),
        ("symbol", 2),
    ],
)
def test_architecture_inventory_filters_entity_types(
    tmp_path: Path,
    entity_type: str,
    expected_count: int,
) -> None:
    project = create_architecture_project(tmp_path)

    inventory = ProjectQuery(project).get_architecture_inventory({entity_type})
    inventory_attributes = {
        "directory": "directories",
        "file": "files",
        "symbol": "symbols",
    }

    assert len(getattr(inventory, inventory_attributes[entity_type])) == (
        expected_count
    )

    for other_type in {"directory", "file", "symbol"} - {entity_type}:
        assert getattr(inventory, inventory_attributes[other_type]) == ()


def test_architecture_inventory_rejects_unsupported_entity_types(
    tmp_path: Path,
) -> None:
    project = create_architecture_project(tmp_path)

    with pytest.raises(ValueError, match="Unsupported architecture entity types"):
        ProjectQuery(project).get_architecture_inventory({"package"})


def test_architecture_inventory_empty_filter_returns_empty_inventory(
    tmp_path: Path,
) -> None:
    project = create_architecture_project(tmp_path)

    inventory = ProjectQuery(project).get_architecture_inventory(set())

    assert inventory.directories == ()
    assert inventory.files == ()
    assert inventory.symbols == ()
    assert inventory.containment == ()
    assert len(inventory.dependencies) == 1
    assert inventory.dependencies[0].relationship_type == RelationshipType.IMPORTS


def test_architecture_inventory_preserves_analysis_errors(
    tmp_path: Path,
) -> None:
    project = create_architecture_project(tmp_path)
    project.analysis_status = "failed"
    project.errors.append("Parser failed for one file")

    inventory = ProjectQuery(project).get_architecture_inventory()

    assert inventory.analysis_status == "failed"
    assert inventory.errors == ("Parser failed for one file",)


def test_architecture_inventory_is_deterministic(
    tmp_path: Path,
) -> None:
    project = create_architecture_project(tmp_path)
    query = ProjectQuery(project)

    first = query.get_architecture_inventory()
    second = query.get_architecture_inventory()

    assert first == second
    assert [item.path.as_posix() for item in first.files] == sorted(
        item.path.as_posix() for item in first.files
    )


def test_architecture_inventory_supports_empty_project(
    tmp_path: Path,
) -> None:
    project = Project(
        name="Empty Project",
        root_path=tmp_path,
        analysis_status="not_analyzed",
    )

    inventory = ProjectQuery(project).get_architecture_inventory()

    assert inventory.analysis_status == "not_analyzed"
    assert inventory.directories == ()
    assert inventory.files == ()
    assert inventory.symbols == ()
    assert inventory.containment == ()
    assert inventory.dependencies == ()


def test_architecture_inventory_preserves_dependencies_with_entity_filters(
    tmp_path: Path,
) -> None:
    project = create_architecture_project(tmp_path)
    query = ProjectQuery(project)

    for entity_type in ("directory", "file", "symbol"):
        inventory = query.get_architecture_inventory({entity_type})

        assert len(inventory.dependencies) == 1
        assert inventory.dependencies[0].relationship_type == RelationshipType.IMPORTS


def test_architecture_inventory_filters_containment_endpoints(
    tmp_path: Path,
) -> None:
    project = create_architecture_project(tmp_path)
    query = ProjectQuery(project)

    inventory = query.get_architecture_inventory({"symbol"})
    returned_symbol_ids = {symbol.id for symbol in inventory.symbols}

    assert inventory.directories == ()
    assert inventory.files == ()
    assert inventory.containment == ()
    assert all(
        edge.source_id in returned_symbol_ids and edge.target_id in returned_symbol_ids
        for edge in inventory.containment
    )


def test_architecture_inventory_includes_empty_directories(
    tmp_path: Path,
) -> None:
    project = create_architecture_project(tmp_path)
    empty_dir = Directory(
        project_id=project.id,
        path=Path("src/empty"),
        name="empty",
        parent_id=project.directories[0].id,
        depth=1,
    )
    project.add_directory(empty_dir)

    inventory = ProjectQuery(project).get_architecture_inventory()

    assert empty_dir in inventory.directories
    assert (
        ContainmentEdge(
            source_type="directory",
            source_id=project.directories[0].id,
            target_type="directory",
            target_id=empty_dir.id,
        )
        in inventory.containment
    )


def test_architecture_inventory_handles_duplicate_names_in_different_paths(
    tmp_path: Path,
) -> None:
    project = create_architecture_project(tmp_path)

    pkg2 = Directory(
        project_id=project.id,
        path=Path("src/other/package"),
        name="package",
        depth=2,
    )
    project.add_directory(pkg2)

    duplicate_file = File(
        project_id=project.id,
        path=Path("src/other/package/main.py"),
        name="main.py",
        extension=".py",
        directory_id=pkg2.id,
    )
    project.add_file(duplicate_file)

    inventory = ProjectQuery(project).get_architecture_inventory()

    file_paths = [f.path.as_posix() for f in inventory.files]
    assert "src/package/main.py" in file_paths
    assert "src/other/package/main.py" in file_paths
    assert len(inventory.files) == 3


def test_architecture_inventory_reports_unresolved_imports_separately(
    tmp_path: Path,
) -> None:
    project = create_architecture_project(tmp_path)
    main_file = next(f for f in project.files if f.name == "main.py")

    external_import = ImportReference(
        file_id=main_file.id,
        module_name="requests",
        imported_name="get",
        alias="req_get",
    )
    missing_relative = ImportReference(
        file_id=main_file.id,
        module_name=".nonexistent",
        imported_name="item",
        level=1,
    )
    project.add_import(external_import)
    project.add_import(missing_relative)

    inventory = ProjectQuery(project).get_architecture_inventory()

    # Dependencies must only contain resolved IMPORTS relationships.
    assert len(inventory.dependencies) == 1
    assert inventory.dependencies[0].relationship_type == RelationshipType.IMPORTS

    # Unresolved imports must be reported as separate evidence.
    assert len(inventory.unresolved_imports) == 2
    unresolved_modules = [u.module_name for u in inventory.unresolved_imports]
    assert ".nonexistent" in unresolved_modules
    assert "requests" in unresolved_modules

    req_finding = next(
        u for u in inventory.unresolved_imports if u.module_name == "requests"
    )
    assert isinstance(req_finding, UnresolvedImport)
    assert req_finding.file_id == main_file.id
    assert req_finding.source_id == main_file.id
    assert req_finding.imported_name == "get"
    assert req_finding.alias == "req_get"
    assert req_finding.source_path == main_file.path


def test_architecture_inventory_unresolved_imports_preserved_across_entity_filters(
    tmp_path: Path,
) -> None:
    project = create_architecture_project(tmp_path)
    main_file = next(f for f in project.files if f.name == "main.py")
    project.add_import(
        ImportReference(file_id=main_file.id, module_name="external_lib")
    )

    query = ProjectQuery(project)
    for entity_type in ("directory", "symbol"):
        inventory = query.get_architecture_inventory({entity_type})
        assert len(inventory.unresolved_imports) == 1
        assert inventory.unresolved_imports[0].module_name == "external_lib"


def test_architecture_inventory_structural_integrity_clean_for_valid_project(
    tmp_path: Path,
) -> None:
    project = create_architecture_project(tmp_path)
    inventory = ProjectQuery(project).get_architecture_inventory()

    assert inventory.integrity_findings == ()
    assert inventory.structural_findings == ()


def test_architecture_inventory_detects_missing_directory_parent(
    tmp_path: Path,
) -> None:
    project = create_architecture_project(tmp_path)
    missing_parent_id = uuid4()
    broken_dir = Directory(
        project_id=project.id,
        path=Path("orphan"),
        name="orphan",
        parent_id=missing_parent_id,
    )
    project.add_directory(broken_dir)

    inventory = ProjectQuery(project).get_architecture_inventory()

    parent_findings = [
        f
        for f in inventory.integrity_findings
        if f.finding_type == "missing_directory_parent"
    ]
    assert len(parent_findings) == 1
    finding = parent_findings[0]
    assert isinstance(finding, StructuralIntegrityFinding)
    assert isinstance(finding, StructuralFinding)
    assert finding.source_id == broken_dir.id
    assert finding.target_id == missing_parent_id
    assert finding.source_path == "orphan"


def test_architecture_inventory_detects_missing_file_directory(
    tmp_path: Path,
) -> None:
    project = create_architecture_project(tmp_path)
    missing_dir_id = uuid4()
    broken_file = File(
        project_id=project.id,
        path=Path("src/orphan.py"),
        name="orphan.py",
        extension=".py",
        directory_id=missing_dir_id,
    )
    project.add_file(broken_file)

    inventory = ProjectQuery(project).get_architecture_inventory()

    dir_findings = [
        f
        for f in inventory.integrity_findings
        if f.finding_type == "missing_file_directory"
    ]
    assert len(dir_findings) == 1
    assert dir_findings[0].source_id == broken_file.id
    assert dir_findings[0].target_id == missing_dir_id


def test_architecture_inventory_top_level_symbol_not_reported_as_broken(
    tmp_path: Path,
) -> None:
    project = create_architecture_project(tmp_path)
    main_file = project.files[0]
    top_symbol = Symbol(
        file_id=main_file.id,
        name="top_level",
        kind="function",
        start_line=10,
        end_line=20,
        parent_symbol_id=None,
    )
    project.add_symbol(top_symbol)

    inventory = ProjectQuery(project).get_architecture_inventory()

    symbol_parent_findings = [
        f
        for f in inventory.integrity_findings
        if f.finding_type == "missing_parent_symbol"
    ]
    assert len(symbol_parent_findings) == 0


def test_architecture_inventory_detects_missing_parent_symbol(
    tmp_path: Path,
) -> None:
    project = create_architecture_project(tmp_path)
    main_file = project.files[0]
    missing_parent = uuid4()
    nested_symbol = Symbol(
        file_id=main_file.id,
        name="child_func",
        kind="method",
        start_line=15,
        end_line=20,
        parent_symbol_id=missing_parent,
    )
    project.add_symbol(nested_symbol)

    inventory = ProjectQuery(project).get_architecture_inventory()

    symbol_findings = [
        f
        for f in inventory.integrity_findings
        if f.finding_type == "missing_parent_symbol"
    ]
    assert len(symbol_findings) == 1
    assert symbol_findings[0].source_id == nested_symbol.id
    assert symbol_findings[0].target_id == missing_parent


def test_architecture_inventory_filtering_does_not_falsely_report_missing_entities(
    tmp_path: Path,
) -> None:
    project = create_architecture_project(tmp_path)
    query = ProjectQuery(project)

    # Filtering for symbol only excludes files and directories from visible collections,
    # but must NOT cause missing_directory_parent, missing_file_directory, etc.
    inventory = query.get_architecture_inventory({"symbol"})

    assert inventory.directories == ()
    assert inventory.files == ()
    assert len(inventory.symbols) == 2
    assert inventory.integrity_findings == ()


def test_architecture_inventory_genuine_integrity_finding_detectable_under_any_filter(
    tmp_path: Path,
) -> None:
    project = create_architecture_project(tmp_path)
    missing_parent_id = uuid4()
    broken_dir = Directory(
        project_id=project.id,
        path=Path("orphan"),
        name="orphan",
        parent_id=missing_parent_id,
    )
    project.add_directory(broken_dir)

    query = ProjectQuery(project)
    # Even when filtering for "symbol", the directory parent integrity finding is present
    inventory = query.get_architecture_inventory({"symbol"})

    assert any(
        f.finding_type == "missing_directory_parent"
        and f.target_id == missing_parent_id
        for f in inventory.integrity_findings
    )


def test_architecture_inventory_reports_incomplete_analysis(
    tmp_path: Path,
) -> None:
    project = create_architecture_project(tmp_path)
    project.analysis_status = "failed"

    inventory = ProjectQuery(project).get_architecture_inventory()

    incomplete_findings = [
        f
        for f in inventory.integrity_findings
        if f.finding_type == "incomplete_analysis"
    ]
    assert len(incomplete_findings) == 1
    assert "failed" in incomplete_findings[0].message


def test_architecture_inventory_detects_cross_file_symbol_parent(
    tmp_path: Path,
) -> None:
    project = create_architecture_project(tmp_path)
    file_1 = project.files[0]
    file_2 = project.files[1]

    parent_sym = Symbol(
        file_id=file_1.id,
        name="ParentClass",
        kind="class",
        start_line=1,
        end_line=10,
    )
    child_sym = Symbol(
        file_id=file_2.id,
        name="child_method",
        kind="method",
        start_line=2,
        end_line=5,
        parent_symbol_id=parent_sym.id,
    )
    project.add_symbol(parent_sym)
    project.add_symbol(child_sym)

    inventory = ProjectQuery(project).get_architecture_inventory()

    findings = [
        f
        for f in inventory.integrity_findings
        if f.finding_type == "inconsistent_symbol_parent"
    ]
    assert len(findings) == 1
    finding = findings[0]
    assert finding.source_id == child_sym.id
    assert finding.target_id == parent_sym.id
    assert "different file" in finding.message


def test_architecture_inventory_detects_invalid_defines_endpoint_types(
    tmp_path: Path,
) -> None:
    project = create_architecture_project(tmp_path)
    sym_1 = project.symbols[0]
    sym_2 = project.symbols[1]

    # DEFINES requires file -> symbol. Connecting symbol -> symbol is invalid type.
    invalid_rel = Relationship(
        source_id=sym_1.id,
        target_id=sym_2.id,
        relationship_type=RelationshipType.DEFINES,
    )
    project.add_relationship(invalid_rel)

    inventory = ProjectQuery(project).get_architecture_inventory()

    # Must NOT report missing entity since both sym_1 and sym_2 exist
    missing_findings = [
        f
        for f in inventory.integrity_findings
        if f.finding_type == "missing_relationship_endpoint" and f.source_id == sym_1.id
    ]
    assert len(missing_findings) == 0

    invalid_type_findings = [
        f
        for f in inventory.integrity_findings
        if f.finding_type == "invalid_relationship_endpoint_type"
        and f.source_id == sym_1.id
    ]
    assert len(invalid_type_findings) == 1
    finding = invalid_type_findings[0]
    assert finding.source_type == "symbol"
    assert finding.target_type == "symbol"
    assert "file -> symbol" in finding.message


def test_architecture_inventory_detects_invalid_contains_endpoint_types(
    tmp_path: Path,
) -> None:
    project = create_architecture_project(tmp_path)
    file_1 = project.files[0]
    sym_1 = project.symbols[0]

    # CONTAINS requires symbol -> symbol. Connecting file -> symbol is invalid type.
    invalid_rel = Relationship(
        source_id=file_1.id,
        target_id=sym_1.id,
        relationship_type=RelationshipType.CONTAINS,
    )
    project.add_relationship(invalid_rel)

    inventory = ProjectQuery(project).get_architecture_inventory()

    missing_findings = [
        f
        for f in inventory.integrity_findings
        if f.finding_type == "missing_relationship_endpoint"
        and f.source_id == file_1.id
    ]
    assert len(missing_findings) == 0

    invalid_type_findings = [
        f
        for f in inventory.integrity_findings
        if f.finding_type == "invalid_relationship_endpoint_type"
        and f.source_id == file_1.id
    ]
    assert len(invalid_type_findings) == 1
    finding = invalid_type_findings[0]
    assert finding.source_type == "file"
    assert finding.target_type == "symbol"
    assert "symbol -> symbol" in finding.message


def test_architecture_inventory_detects_invalid_adjacent_structural_reference_types(
    tmp_path: Path,
) -> None:
    project = create_architecture_project(tmp_path)
    file_1 = project.files[0]
    sym_1 = project.symbols[0]

    # Directory parent pointing to a file
    dir_with_file_parent = Directory(
        project_id=project.id,
        path=Path("src/invalid_dir"),
        name="invalid_dir",
        parent_id=file_1.id,
    )
    project.add_directory(dir_with_file_parent)

    # File directory pointing to a symbol
    file_with_sym_dir = File(
        project_id=project.id,
        path=Path("src/invalid_file.py"),
        name="invalid_file.py",
        extension=".py",
        directory_id=sym_1.id,
    )
    project.add_file(file_with_sym_dir)

    inventory = ProjectQuery(project).get_architecture_inventory()

    dir_parent_findings = [
        f
        for f in inventory.integrity_findings
        if f.finding_type == "invalid_directory_parent_type"
    ]
    assert len(dir_parent_findings) == 1
    assert dir_parent_findings[0].source_id == dir_with_file_parent.id
    assert dir_parent_findings[0].target_type == "file"

    file_dir_findings = [
        f
        for f in inventory.integrity_findings
        if f.finding_type == "invalid_file_directory_type"
    ]
    assert len(file_dir_findings) == 1
    assert file_dir_findings[0].source_id == file_with_sym_dir.id
    assert file_dir_findings[0].target_type == "symbol"


def test_architecture_inventory_detects_missing_symbol_file(
    tmp_path: Path,
) -> None:
    project = create_architecture_project(tmp_path)
    missing_file_id = uuid4()
    orphan_symbol = Symbol(
        file_id=missing_file_id,
        name="orphan_symbol",
        kind="function",
        start_line=1,
        end_line=10,
    )
    project.symbols.append(orphan_symbol)

    inventory = ProjectQuery(project).get_architecture_inventory()

    missing_findings = [
        f
        for f in inventory.integrity_findings
        if f.finding_type == "missing_symbol_file" and f.source_id == orphan_symbol.id
    ]
    assert len(missing_findings) == 1
    finding = missing_findings[0]
    assert finding.source_id == orphan_symbol.id
    assert finding.target_id == missing_file_id
    assert finding.source_type == "symbol"
    assert finding.target_type == "file"


def test_architecture_inventory_detects_invalid_symbol_file_type(
    tmp_path: Path,
) -> None:
    project = create_architecture_project(tmp_path)
    directory = project.directories[0]

    # Symbol whose file_id points to an existing directory instead of a file
    invalid_symbol = Symbol(
        file_id=directory.id,
        name="misplaced_symbol",
        kind="function",
        start_line=1,
        end_line=10,
    )
    project.symbols.append(invalid_symbol)

    inventory = ProjectQuery(project).get_architecture_inventory()

    # Must NOT report missing_symbol_file since the target entity exists
    missing_findings = [
        f
        for f in inventory.integrity_findings
        if f.finding_type == "missing_symbol_file" and f.source_id == invalid_symbol.id
    ]
    assert len(missing_findings) == 0

    invalid_type_findings = [
        f
        for f in inventory.integrity_findings
        if f.finding_type == "invalid_symbol_file_type"
        and f.source_id == invalid_symbol.id
    ]
    assert len(invalid_type_findings) == 1
    finding = invalid_type_findings[0]
    assert finding.source_id == invalid_symbol.id
    assert finding.target_id == directory.id
    assert finding.source_type == "symbol"
    assert finding.target_type == "directory"
    assert "directory" in finding.message


def test_architecture_inventory_detects_invalid_parent_symbol_type(
    tmp_path: Path,
) -> None:
    project = create_architecture_project(tmp_path)
    file_1 = project.files[0]

    # Symbol whose parent_symbol_id points to an existing file instead of a symbol
    invalid_child = Symbol(
        file_id=file_1.id,
        name="misparented_symbol",
        kind="method",
        start_line=5,
        end_line=10,
        parent_symbol_id=file_1.id,
    )
    project.add_symbol(invalid_child)

    inventory = ProjectQuery(project).get_architecture_inventory()

    # Must NOT report missing_parent_symbol since file_1 exists
    missing_findings = [
        f
        for f in inventory.integrity_findings
        if f.finding_type == "missing_parent_symbol" and f.source_id == invalid_child.id
    ]
    assert len(missing_findings) == 0

    invalid_type_findings = [
        f
        for f in inventory.integrity_findings
        if f.finding_type == "invalid_parent_symbol_type"
        and f.source_id == invalid_child.id
    ]
    assert len(invalid_type_findings) == 1
    finding = invalid_type_findings[0]
    assert finding.source_id == invalid_child.id
    assert finding.target_id == file_1.id
    assert finding.source_type == "symbol"
    assert finding.target_type == "file"
    assert "file" in finding.message


def test_architecture_inventory_detects_missing_defines_endpoints(
    tmp_path: Path,
) -> None:
    project = create_architecture_project(tmp_path)
    file_1 = project.files[0]
    sym_1 = project.symbols[0]
    missing_source_id = uuid4()
    missing_target_id = uuid4()

    # DEFINES with missing source (non-existent file ID, existing target symbol)
    rel_missing_source = Relationship(
        source_id=missing_source_id,
        target_id=sym_1.id,
        relationship_type=RelationshipType.DEFINES,
    )
    # DEFINES with missing target (existing source file, non-existent target symbol ID)
    rel_missing_target = Relationship(
        source_id=file_1.id,
        target_id=missing_target_id,
        relationship_type=RelationshipType.DEFINES,
    )
    project.add_relationship(rel_missing_source)
    project.add_relationship(rel_missing_target)

    inventory = ProjectQuery(project).get_architecture_inventory()

    # Check missing source endpoint finding
    source_findings = [
        f
        for f in inventory.integrity_findings
        if f.finding_type == "missing_relationship_endpoint"
        and f.source_id == missing_source_id
    ]
    assert len(source_findings) == 1
    assert source_findings[0].target_id == sym_1.id
    assert "source file" in source_findings[0].message
    # sym_1 must NOT be falsely reported as missing
    assert not any(
        f.finding_type == "missing_relationship_endpoint"
        and f.target_id == sym_1.id
        and f.source_id != missing_source_id
        for f in inventory.integrity_findings
    )

    # Check missing target endpoint finding
    target_findings = [
        f
        for f in inventory.integrity_findings
        if f.finding_type == "missing_relationship_endpoint"
        and f.target_id == missing_target_id
    ]
    assert len(target_findings) == 1
    assert target_findings[0].source_id == file_1.id
    assert "target symbol" in target_findings[0].message
    # file_1 must NOT be falsely reported as missing
    assert not any(
        f.finding_type == "missing_relationship_endpoint"
        and f.source_id == file_1.id
        and f.target_id != missing_target_id
        for f in inventory.integrity_findings
    )


def test_architecture_inventory_detects_missing_contains_endpoints(
    tmp_path: Path,
) -> None:
    project = create_architecture_project(tmp_path)
    sym_1 = project.symbols[0]
    sym_2 = project.symbols[1]
    missing_source_id = uuid4()
    missing_target_id = uuid4()

    # CONTAINS with missing source (non-existent symbol ID, existing target symbol)
    rel_missing_source = Relationship(
        source_id=missing_source_id,
        target_id=sym_1.id,
        relationship_type=RelationshipType.CONTAINS,
    )
    # CONTAINS with missing target (existing source symbol, non-existent target symbol ID)
    rel_missing_target = Relationship(
        source_id=sym_2.id,
        target_id=missing_target_id,
        relationship_type=RelationshipType.CONTAINS,
    )
    project.add_relationship(rel_missing_source)
    project.add_relationship(rel_missing_target)

    inventory = ProjectQuery(project).get_architecture_inventory()

    # Check missing source endpoint finding
    source_findings = [
        f
        for f in inventory.integrity_findings
        if f.finding_type == "missing_relationship_endpoint"
        and f.source_id == missing_source_id
    ]
    assert len(source_findings) == 1
    assert source_findings[0].target_id == sym_1.id
    assert "source symbol" in source_findings[0].message
    # sym_1 must NOT be falsely reported as missing
    assert not any(
        f.finding_type == "missing_relationship_endpoint"
        and f.target_id == sym_1.id
        and f.source_id != missing_source_id
        for f in inventory.integrity_findings
    )

    # Check missing target endpoint finding
    target_findings = [
        f
        for f in inventory.integrity_findings
        if f.finding_type == "missing_relationship_endpoint"
        and f.target_id == missing_target_id
    ]
    assert len(target_findings) == 1
    assert target_findings[0].source_id == sym_2.id
    assert "target symbol" in target_findings[0].message
    # sym_2 must NOT be falsely reported as missing
    assert not any(
        f.finding_type == "missing_relationship_endpoint"
        and f.source_id == sym_2.id
        and f.target_id != missing_target_id
        for f in inventory.integrity_findings
    )
