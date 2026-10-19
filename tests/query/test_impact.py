from pathlib import Path
from uuid import uuid4

import pytest

from context_forge.models.directory import Directory
from context_forge.models.file import File
from context_forge.models.project import Project
from context_forge.models.relationship import Relationship, RelationshipType
from context_forge.models.symbol import Symbol
from context_forge.query import (
    DEFAULT_IMPACT_MAX_DEPTH,
    ImpactPathStep,
    ProjectQuery,
    find_direct_impact,
    find_impact,
    find_transitive_impact,
    resolve_impact_target,
)


def create_impact_test_project(tmp_path: Path) -> Project:
    """Create a structured test project with files, symbols, and relationships."""
    project = Project(
        name="Impact Test Project",
        root_path=tmp_path,
        analysis_status="analyzed",
    )

    src_dir = Directory(
        project_id=project.id,
        path=Path("src"),
        name="src",
    )
    pkg_dir = Directory(
        project_id=project.id,
        path=Path("src/pkg"),
        name="pkg",
        parent_id=src_dir.id,
        depth=1,
    )
    project.add_directory(src_dir)
    project.add_directory(pkg_dir)

    # Files
    init_file = File(
        project_id=project.id,
        path=Path("src/pkg/__init__.py"),
        name="__init__.py",
        extension=".py",
        directory_id=pkg_dir.id,
    )
    models_file = File(
        project_id=project.id,
        path=Path("src/pkg/models.py"),
        name="models.py",
        extension=".py",
        directory_id=pkg_dir.id,
    )
    service_file = File(
        project_id=project.id,
        path=Path("src/pkg/service.py"),
        name="service.py",
        extension=".py",
        directory_id=pkg_dir.id,
    )
    client_file = File(
        project_id=project.id,
        path=Path("src/pkg/client.py"),
        name="client.py",
        extension=".py",
        directory_id=pkg_dir.id,
    )
    standalone_file = File(
        project_id=project.id,
        path=Path("src/pkg/standalone.py"),
        name="standalone.py",
        extension=".py",
        directory_id=pkg_dir.id,
    )

    project.add_file(init_file)
    project.add_file(models_file)
    project.add_file(service_file)
    project.add_file(client_file)
    project.add_file(standalone_file)

    # Symbols
    # In models.py: User (class), BaseEntity (class)
    base_entity = Symbol(
        file_id=models_file.id,
        name="BaseEntity",
        kind="class",
        qualified_name="pkg.models.BaseEntity",
        start_line=1,
        end_line=10,
    )
    user_model = Symbol(
        file_id=models_file.id,
        name="User",
        kind="class",
        qualified_name="pkg.models.User",
        start_line=12,
        end_line=30,
    )
    # Ambiguous symbol: Config in models.py and Config in client.py
    config_models = Symbol(
        file_id=models_file.id,
        name="Config",
        kind="class",
        qualified_name="pkg.models.Config",
        start_line=32,
        end_line=45,
    )
    config_client = Symbol(
        file_id=client_file.id,
        name="Config",
        kind="class",
        qualified_name="pkg.client.Config",
        start_line=5,
        end_line=15,
    )

    # In service.py: UserService (class), get_user (function), User (nested helper class to test ambiguity)
    user_service = Symbol(
        file_id=service_file.id,
        name="UserService",
        kind="class",
        qualified_name="pkg.service.UserService",
        start_line=5,
        end_line=50,
    )
    get_user = Symbol(
        file_id=service_file.id,
        name="get_user",
        kind="function",
        qualified_name="pkg.service.get_user",
        start_line=52,
        end_line=60,
        signature="def get_user(user_id: int) -> User",
    )
    user_service_method = Symbol(
        file_id=service_file.id,
        name="fetch",
        kind="method",
        qualified_name="pkg.service.UserService.fetch",
        parent_symbol_id=user_service.id,
        start_line=10,
        end_line=20,
    )

    project.add_symbol(base_entity)
    project.add_symbol(user_model)
    project.add_symbol(config_models)
    project.add_symbol(config_client)
    project.add_symbol(user_service)
    project.add_symbol(get_user)
    project.add_symbol(user_service_method)

    # Relationships
    # 1. Containment (DEFINES & CONTAINS) - should be excluded from impact by default
    project.add_relationship(
        Relationship(
            source_id=models_file.id,
            target_id=user_model.id,
            relationship_type=RelationshipType.DEFINES,
            confidence=1.0,
        )
    )
    project.add_relationship(
        Relationship(
            source_id=user_service.id,
            target_id=user_service_method.id,
            relationship_type=RelationshipType.CONTAINS,
            confidence=1.0,
        )
    )

    # 2. File-to-file IMPORTS: service.py imports models.py
    project.add_relationship(
        Relationship(
            source_id=service_file.id,
            target_id=models_file.id,
            relationship_type=RelationshipType.IMPORTS,
            confidence=1.0,
            metadata={"imported_module": "pkg.models", "line_number": "2"},
        )
    )
    # client.py imports service.py
    project.add_relationship(
        Relationship(
            source_id=client_file.id,
            target_id=service_file.id,
            relationship_type=RelationshipType.IMPORTS,
            confidence=1.0,
            metadata={"imported_module": "pkg.service", "line_number": "1"},
        )
    )

    # 3. Symbol-to-symbol INHERITS: User inherits BaseEntity
    project.add_relationship(
        Relationship(
            source_id=user_model.id,
            target_id=base_entity.id,
            relationship_type=RelationshipType.INHERITS,
            confidence=1.0,
        )
    )

    # 4. Symbol-to-symbol REFERENCES: UserService references User
    project.add_relationship(
        Relationship(
            source_id=user_service.id,
            target_id=user_model.id,
            relationship_type=RelationshipType.REFERENCES,
            confidence=0.9,
            metadata={"context": "type_annotation", "line": "6"},
        )
    )

    # 5. Symbol-to-symbol CALLS: UserService.fetch calls get_user
    project.add_relationship(
        Relationship(
            source_id=user_service_method.id,
            target_id=get_user.id,
            relationship_type=RelationshipType.CALLS,
            confidence=0.95,
        )
    )

    # 6. Second distinct relationship between same entities (multiple edges preserved):
    # UserService also references User on line 25
    project.add_relationship(
        Relationship(
            source_id=user_service.id,
            target_id=user_model.id,
            relationship_type=RelationshipType.REFERENCES,
            confidence=0.85,
            metadata={"context": "instantiation", "line": "25"},
        )
    )

    return project


# ==============================================================================
# TARGET RESOLUTION TESTS
# ==============================================================================


def test_resolve_file_by_exact_relative_path(tmp_path: Path) -> None:
    project = create_impact_test_project(tmp_path)
    res = resolve_impact_target(project, "src/pkg/models.py")

    assert res.is_resolved
    assert not res.is_ambiguous
    assert not res.is_not_found
    assert res.status == "resolved"
    assert res.target is not None
    assert res.target.target_type == "file"
    assert res.target.name == "models.py"
    assert res.target.path == "src/pkg/models.py"
    assert res.target.kind == "file"


def test_resolve_file_with_dot_slash_prefix(tmp_path: Path) -> None:
    project = create_impact_test_project(tmp_path)
    res = resolve_impact_target(project, "./src/pkg/models.py")

    assert res.is_resolved
    assert res.target is not None
    assert res.target.path == "src/pkg/models.py"


def test_resolve_file_with_backslashes(tmp_path: Path) -> None:
    project = create_impact_test_project(tmp_path)
    res = resolve_impact_target(project, "src\\pkg\\models.py")

    assert res.is_resolved
    assert res.target is not None
    assert res.target.path == "src/pkg/models.py"


def test_resolve_file_by_absolute_path_within_root(tmp_path: Path) -> None:
    project = create_impact_test_project(tmp_path)
    abs_path = (tmp_path / "src" / "pkg" / "models.py").resolve().as_posix()
    res = resolve_impact_target(project, abs_path)

    assert res.is_resolved
    assert res.target is not None
    assert res.target.path == "src/pkg/models.py"


def test_resolve_file_missing(tmp_path: Path) -> None:
    project = create_impact_test_project(tmp_path)
    res = resolve_impact_target(project, "src/pkg/nonexistent.py")

    assert not res.is_resolved
    assert res.is_not_found
    assert res.status == "not_found"
    assert res.target is None
    assert "not found in repository" in res.message


def test_resolve_module_target(tmp_path: Path) -> None:
    project = create_impact_test_project(tmp_path)
    # pkg.models resolves to src/pkg/models.py
    res = resolve_impact_target(project, "pkg.models")

    assert res.is_resolved
    assert res.target is not None
    assert res.target.target_type == "file"
    assert res.target.path == "src/pkg/models.py"


def test_resolve_package_init_module(tmp_path: Path) -> None:
    project = create_impact_test_project(tmp_path)
    res = resolve_impact_target(project, "pkg")

    assert res.is_resolved
    assert res.target is not None
    assert res.target.path == "src/pkg/__init__.py"


def test_resolve_unique_symbol_by_unqualified_name(tmp_path: Path) -> None:
    project = create_impact_test_project(tmp_path)
    res = resolve_impact_target(project, "BaseEntity")

    assert res.is_resolved
    assert res.target is not None
    assert res.target.target_type == "symbol"
    assert res.target.name == "BaseEntity"
    assert res.target.kind == "class"
    assert res.target.path == "src/pkg/models.py"
    assert res.target.qualified_name == "pkg.models.BaseEntity"
    assert res.target.start_line == 1
    assert res.target.end_line == 10


def test_resolve_symbol_with_signature(tmp_path: Path) -> None:
    project = create_impact_test_project(tmp_path)
    res = resolve_impact_target(project, "get_user")

    assert res.is_resolved
    assert res.target is not None
    assert res.target.name == "get_user"
    assert res.target.signature == "def get_user(user_id: int) -> User"


def test_resolve_symbol_by_qualified_name(tmp_path: Path) -> None:
    project = create_impact_test_project(tmp_path)
    res = resolve_impact_target(project, "pkg.models.Config")

    assert res.is_resolved
    assert res.target is not None
    assert res.target.name == "Config"
    assert res.target.qualified_name == "pkg.models.Config"
    assert res.target.path == "src/pkg/models.py"


def test_resolve_ambiguous_symbol(tmp_path: Path) -> None:
    project = create_impact_test_project(tmp_path)
    res = resolve_impact_target(project, "Config")

    assert not res.is_resolved
    assert res.is_ambiguous
    assert res.status == "ambiguous"
    assert res.target is None
    assert len(res.candidates) == 2

    # Verify deterministic ordering: sorted by (path, start_line, name, qualified_name, id.hex)
    assert res.candidates[0].path == "src/pkg/client.py"
    assert res.candidates[0].start_line == 5
    assert res.candidates[0].qualified_name == "pkg.client.Config"

    assert res.candidates[1].path == "src/pkg/models.py"
    assert res.candidates[1].start_line == 32
    assert res.candidates[1].qualified_name == "pkg.models.Config"

    assert "Multiple symbols match 'Config'" in res.message


def test_resolve_missing_symbol(tmp_path: Path) -> None:
    project = create_impact_test_project(tmp_path)
    res = resolve_impact_target(project, "NonexistentSymbol")

    assert res.is_not_found
    assert res.status == "not_found"
    assert "not found in repository" in res.message


def test_resolve_direct_file_instance(tmp_path: Path) -> None:
    project = create_impact_test_project(tmp_path)
    file_obj = project.files[0]
    res = resolve_impact_target(project, file_obj)

    assert res.is_resolved
    assert res.target is not None
    assert res.target.id == file_obj.id
    assert res.target.path == file_obj.path.as_posix()


def test_resolve_direct_file_not_in_project(tmp_path: Path) -> None:
    project = create_impact_test_project(tmp_path)
    orphan_file = File(
        project_id=uuid4(),
        path=Path("orphan.py"),
        name="orphan.py",
        extension=".py",
    )
    res = resolve_impact_target(project, orphan_file)

    assert res.is_not_found
    assert "does not belong to the project" in res.message


def test_resolve_direct_symbol_instance(tmp_path: Path) -> None:
    project = create_impact_test_project(tmp_path)
    sym_obj = project.symbols[0]
    res = resolve_impact_target(project, sym_obj)

    assert res.is_resolved
    assert res.target is not None
    assert res.target.id == sym_obj.id
    assert res.target.name == sym_obj.name


def test_resolve_direct_symbol_not_in_project(tmp_path: Path) -> None:
    project = create_impact_test_project(tmp_path)
    orphan_sym = Symbol(
        file_id=uuid4(),
        name="Orphan",
        kind="class",
        start_line=1,
        end_line=5,
    )
    res = resolve_impact_target(project, orphan_sym)

    assert res.is_not_found
    assert "does not belong to the project" in res.message


def test_resolve_rejects_empty_or_whitespace_target(tmp_path: Path) -> None:
    project = create_impact_test_project(tmp_path)
    with pytest.raises(ValueError, match="Target cannot be empty"):
        resolve_impact_target(project, "")
    with pytest.raises(ValueError, match="Target cannot be empty"):
        resolve_impact_target(project, "   ")


def test_resolve_rejects_invalid_type(tmp_path: Path) -> None:
    project = create_impact_test_project(tmp_path)
    with pytest.raises(TypeError, match="Target must be a str, File, or Symbol"):
        resolve_impact_target(project, 123)  # type: ignore[arg-type]


# ==============================================================================
# DIRECT IMPACT ANALYSIS TESTS
# ==============================================================================


def test_find_direct_impact_file_incoming(tmp_path: Path) -> None:
    project = create_impact_test_project(tmp_path)
    # models.py is imported by service.py
    result = find_direct_impact(
        project,
        "src/pkg/models.py",
        direction="incoming",
    )

    assert result.status == "resolved"
    assert result.target is not None
    assert result.target.name == "models.py"
    assert result.direction == "incoming"
    assert result.total == 1
    assert len(result.items) == 1
    assert not result.truncated

    item = result.items[0]
    assert item.direction == "incoming"
    assert item.relationship_type == "imports"
    assert item.related_type == "file"
    assert item.related_name == "service.py"
    assert item.related_path == "src/pkg/service.py"
    assert item.confidence == 1.0
    assert item.metadata.get("imported_module") == "pkg.models"


def test_find_direct_impact_file_outgoing(tmp_path: Path) -> None:
    project = create_impact_test_project(tmp_path)
    # service.py imports models.py
    result = find_direct_impact(
        project,
        "src/pkg/service.py",
        direction="outgoing",
    )

    assert result.status == "resolved"
    assert result.direction == "outgoing"
    assert result.total == 1
    assert len(result.items) == 1

    item = result.items[0]
    assert item.direction == "outgoing"
    assert item.relationship_type == "imports"
    assert item.related_type == "file"
    assert item.related_name == "models.py"
    assert item.related_path == "src/pkg/models.py"


def test_find_direct_impact_file_both_directions(tmp_path: Path) -> None:
    project = create_impact_test_project(tmp_path)
    # service.py: incoming from client.py (client imports service), outgoing to models.py (service imports models)
    result = find_direct_impact(
        project,
        "src/pkg/service.py",
        direction="both",
    )

    assert result.status == "resolved"
    assert result.direction == "both"
    assert result.total == 2
    assert len(result.items) == 2

    # Deterministic sort: incoming first, then outgoing
    incoming = result.items[0]
    assert incoming.direction == "incoming"
    assert incoming.related_name == "client.py"

    outgoing = result.items[1]
    assert outgoing.direction == "outgoing"
    assert outgoing.related_name == "models.py"


def test_find_direct_impact_symbol_both_directions(tmp_path: Path) -> None:
    project = create_impact_test_project(tmp_path)
    # User model:
    # Incoming: UserService references User (2 edges)
    # Outgoing: User inherits BaseEntity (1 edge)
    # DEFINES from models.py should be excluded by default
    result = find_direct_impact(
        project,
        "User",
        direction="both",
    )

    assert result.status == "resolved"
    assert result.target is not None
    assert result.target.name == "User"
    assert result.total == 3
    assert len(result.items) == 3

    # Check incoming (references from UserService)
    incoming_items = [it for it in result.items if it.direction == "incoming"]
    assert len(incoming_items) == 2
    for it in incoming_items:
        assert it.relationship_type == "references"
        assert it.related_type == "symbol"
        assert it.related_name == "UserService"
        assert it.related_path == "src/pkg/service.py"

    # Distinct relationships: both references preserved with their unique metadata
    lines = {it.metadata.get("line") for it in incoming_items}
    assert lines == {"6", "25"}

    # Check outgoing (inherits BaseEntity)
    outgoing_items = [it for it in result.items if it.direction == "outgoing"]
    assert len(outgoing_items) == 1
    assert outgoing_items[0].relationship_type == "inherits"
    assert outgoing_items[0].related_name == "BaseEntity"
    assert outgoing_items[0].related_path == "src/pkg/models.py"


def test_find_direct_impact_excludes_containment_by_default(tmp_path: Path) -> None:
    project = create_impact_test_project(tmp_path)
    # models_file DEFINES User, UserService CONTAINS UserService.fetch
    # When querying models.py, DEFINES should not appear
    res_file = find_direct_impact(project, "src/pkg/models.py", direction="both")
    for it in res_file.items:
        assert it.relationship_type != "defines"
        assert it.relationship_type != "contains"

    # When querying UserService, CONTAINS should not appear
    res_sym = find_direct_impact(project, "UserService", direction="both")
    for it in res_sym.items:
        assert it.relationship_type != "defines"
        assert it.relationship_type != "contains"


def test_find_direct_impact_includes_containment_when_requested(tmp_path: Path) -> None:
    project = create_impact_test_project(tmp_path)
    res = find_direct_impact(
        project,
        "src/pkg/models.py",
        direction="outgoing",
        relationship_types={"defines"},
    )
    assert res.total == 1
    assert res.items[0].relationship_type == "defines"
    assert res.items[0].related_name == "User"


def test_find_direct_impact_relationship_filtering(tmp_path: Path) -> None:
    project = create_impact_test_project(tmp_path)
    # Query User with relationship_types={"inherits"}
    result = find_direct_impact(
        project,
        "User",
        direction="both",
        relationship_types={"inherits"},
    )
    assert result.total == 1
    assert result.items[0].relationship_type == "inherits"
    assert result.items[0].related_name == "BaseEntity"


def test_find_direct_impact_target_type_filtering(tmp_path: Path) -> None:
    project = create_impact_test_project(tmp_path)
    # Add a relationship from file to symbol
    project.add_relationship(
        Relationship(
            source_id=project.files[2].id,  # service_file
            target_id=project.symbols[1].id,  # user_model
            relationship_type=RelationshipType.REFERENCES,
        )
    )
    # Query User with target_types={"file"} vs target_types={"symbol"}
    res_files = find_direct_impact(
        project,
        "User",
        direction="incoming",
        target_types={"file"},
    )
    for it in res_files.items:
        assert it.related_type == "file"

    res_symbols = find_direct_impact(
        project,
        "User",
        direction="incoming",
        target_types={"symbol"},
    )
    for it in res_symbols.items:
        assert it.related_type == "symbol"


def test_find_direct_impact_empty_results_on_valid_target(tmp_path: Path) -> None:
    project = create_impact_test_project(tmp_path)
    # standalone.py has no relationships
    result = find_direct_impact(
        project,
        "src/pkg/standalone.py",
        direction="both",
    )

    assert result.status == "resolved"
    assert result.target is not None
    assert result.target.name == "standalone.py"
    assert result.total == 0
    assert result.items == ()
    assert not result.truncated


def test_find_direct_impact_on_missing_target(tmp_path: Path) -> None:
    project = create_impact_test_project(tmp_path)
    result = find_direct_impact(
        project,
        "missing_component",
    )

    assert result.status == "not_found"
    assert result.target is None
    assert result.total == 0
    assert result.items == ()
    assert "not found" in result.message


def test_find_direct_impact_on_ambiguous_target(tmp_path: Path) -> None:
    project = create_impact_test_project(tmp_path)
    result = find_direct_impact(
        project,
        "Config",
    )

    assert result.status == "ambiguous"
    assert result.target is None
    assert result.total == 0
    assert result.items == ()
    assert len(result.candidates) == 2
    assert "Multiple symbols match" in result.message


def test_find_direct_impact_limit_and_truncation(tmp_path: Path) -> None:
    project = create_impact_test_project(tmp_path)
    # User has 3 direct relationships (2 incoming references, 1 outgoing inherits)
    result = find_direct_impact(
        project,
        "User",
        direction="both",
        limit=2,
    )

    assert result.status == "resolved"
    assert result.total == 3
    assert len(result.items) == 2
    assert result.truncated is True
    assert result.limit == 2


def test_find_direct_impact_invalid_direction(tmp_path: Path) -> None:
    project = create_impact_test_project(tmp_path)
    with pytest.raises(ValueError, match="Direction must be"):
        find_direct_impact(project, "User", direction="sideways")


def test_find_direct_impact_invalid_limit(tmp_path: Path) -> None:
    project = create_impact_test_project(tmp_path)
    with pytest.raises(ValueError, match="Limit must be a positive integer"):
        find_direct_impact(project, "User", limit=0)
    with pytest.raises(ValueError, match="Limit must be a positive integer"):
        find_direct_impact(project, "User", limit=-5)
    with pytest.raises(ValueError, match="Limit must be a positive integer"):
        find_direct_impact(project, "User", limit=True)  # type: ignore[arg-type]


def test_find_direct_impact_determinism_across_permutations(tmp_path: Path) -> None:
    project = create_impact_test_project(tmp_path)

    res1 = find_direct_impact(project, "User", direction="both")

    # Reverse symbols and relationships in-place
    project.symbols.reverse()
    project.relationships.reverse()

    res2 = find_direct_impact(project, "User", direction="both")

    assert res1.total == res2.total
    assert len(res1.items) == len(res2.items)
    for it1, it2 in zip(res1.items, res2.items, strict=True):
        assert it1.direction == it2.direction
        assert it1.relationship_type == it2.relationship_type
        assert it1.related_name == it2.related_name
        assert it1.related_path == it2.related_path
        assert it1.related_id == it2.related_id
        assert it1.relationship_id == it2.relationship_id


def test_find_direct_impact_repository_isolation(tmp_path: Path) -> None:
    project_a = create_impact_test_project(tmp_path / "proj_a")
    project_b = Project(
        name="Project B",
        root_path=tmp_path / "proj_b",
        analysis_status="analyzed",
    )
    secret_file = File(
        project_id=project_b.id,
        path=Path("secret.py"),
        name="secret.py",
        extension=".py",
    )
    project_b.add_file(secret_file)

    # Project A cannot resolve entities from Project B
    res_a = resolve_impact_target(project_a, "secret.py")
    assert res_a.is_not_found

    # Direct entity from B passed to A returns not found
    res_cross = resolve_impact_target(project_a, secret_file)
    assert res_cross.is_not_found


def test_direct_impact_limitations_on_incomplete_analysis(tmp_path: Path) -> None:
    project = create_impact_test_project(tmp_path)
    project.analysis_status = "failed"
    project.errors = ["SyntaxError in client.py"]

    result = find_direct_impact(project, "User")
    assert any("failed" in lim for lim in result.limitations)
    assert any("contains errors" in lim for lim in result.limitations)
    assert any(
        "does not establish or guarantee runtime behavior" in lim
        for lim in result.limitations
    )


def test_impact_to_dict_serialization(tmp_path: Path) -> None:
    project = create_impact_test_project(tmp_path)
    result = find_direct_impact(project, "User", direction="both")
    data = result.to_dict()

    assert data["status"] == "resolved"
    assert data["target"]["name"] == "User"
    assert data["direction"] == "both"
    assert data["total"] == 3
    assert len(data["items"]) == 3
    assert isinstance(data["items"][0]["relationship_id"], str)
    assert isinstance(data["items"][0]["source_id"], str)
    assert isinstance(data["items"][0]["target_id"], str)
    assert isinstance(data["items"][0]["related_id"], str)


def test_project_query_impact_methods(tmp_path: Path) -> None:
    project = create_impact_test_project(tmp_path)
    query = ProjectQuery(project)

    # resolve_target
    res = query.resolve_target("User")
    assert res.is_resolved
    assert res.target is not None
    assert res.target.name == "User"

    # find_direct_impact
    impact_res = query.find_direct_impact("User", direction="both")
    assert impact_res.status == "resolved"
    assert impact_res.total == 3


def test_find_impact_multi_hop_traversal(tmp_path: Path) -> None:
    project = create_impact_test_project(tmp_path)

    # models.py is imported by service.py (depth 1), which is imported by client.py (depth 2)
    result = find_impact(
        project,
        "src/pkg/models.py",
        direction="incoming",
        max_depth=3,
    )

    assert result.status == "resolved"
    assert result.total == 2
    assert result.direct_count == 1
    assert result.indirect_count == 1
    assert result.depth_reached == 2
    assert result.max_depth == DEFAULT_IMPACT_MAX_DEPTH
    assert result.truncated is False

    service_item = next(it for it in result.items if it.related_name == "service.py")
    client_item = next(it for it in result.items if it.related_name == "client.py")

    # Direct item verification
    assert service_item.depth == 1
    assert service_item.classification == "direct"
    assert len(service_item.path) == 1
    step0 = service_item.path[0]
    assert step0.from_name == "models.py"
    assert step0.to_name == "service.py"
    assert step0.relationship_type == "imports"
    assert step0.direction == "incoming"
    assert step0.from_id == result.target.id
    assert step0.to_id == service_item.related_id

    # Indirect item verification
    assert client_item.depth == 2
    assert client_item.classification == "indirect"
    assert len(client_item.path) == 2
    c_step0, c_step1 = client_item.path
    assert c_step0.from_name == "models.py"
    assert c_step0.to_name == "service.py"
    assert c_step1.from_name == "service.py"
    assert c_step1.to_name == "client.py"
    assert c_step1.from_id == c_step0.to_id
    assert c_step0.from_id == result.target.id
    assert c_step1.to_id == client_item.related_id


def test_find_impact_depth_limiting(tmp_path: Path) -> None:
    project = create_impact_test_project(tmp_path)

    # max_depth=1 should only return direct impact
    res_d1 = find_impact(
        project,
        "src/pkg/models.py",
        direction="incoming",
        max_depth=1,
    )
    assert res_d1.total == 1
    assert res_d1.direct_count == 1
    assert res_d1.indirect_count == 0
    assert res_d1.depth_reached == 1
    assert res_d1.items[0].related_name == "service.py"
    assert any(
        "Traversal depth was limited to 1 hop(s)" in lim for lim in res_d1.limitations
    )

    # max_depth=2 discovers both
    res_d2 = find_impact(
        project,
        "src/pkg/models.py",
        direction="incoming",
        max_depth=2,
    )
    assert res_d2.total == 2
    assert res_d2.direct_count == 1
    assert res_d2.indirect_count == 1
    assert res_d2.depth_reached == 2


def test_find_impact_invalid_depth_rejection(tmp_path: Path) -> None:
    project = create_impact_test_project(tmp_path)

    with pytest.raises(ValueError, match="positive integer"):
        find_impact(project, "src/pkg/models.py", max_depth=0)

    with pytest.raises(ValueError, match="positive integer"):
        find_impact(project, "src/pkg/models.py", max_depth=-1)

    with pytest.raises(ValueError, match="positive integer"):
        find_impact(project, "src/pkg/models.py", max_depth=True)  # type: ignore[arg-type]


def test_find_impact_cycle_and_self_loop_termination(tmp_path: Path) -> None:
    project = Project(name="Cycle Test", root_path=tmp_path, analysis_status="analyzed")
    f_a = File(project_id=project.id, path=Path("a.py"), name="a.py", extension=".py")
    f_b = File(project_id=project.id, path=Path("b.py"), name="b.py", extension=".py")
    f_c = File(project_id=project.id, path=Path("c.py"), name="c.py", extension=".py")
    project.add_file(f_a)
    project.add_file(f_b)
    project.add_file(f_c)

    # Cycle: a -> b -> c -> a
    project.add_relationship(
        Relationship(
            source_id=f_a.id,
            target_id=f_b.id,
            relationship_type=RelationshipType.IMPORTS,
        )
    )
    project.add_relationship(
        Relationship(
            source_id=f_b.id,
            target_id=f_c.id,
            relationship_type=RelationshipType.IMPORTS,
        )
    )
    project.add_relationship(
        Relationship(
            source_id=f_c.id,
            target_id=f_a.id,
            relationship_type=RelationshipType.IMPORTS,
        )
    )
    # Self-loop: a -> a
    project.add_relationship(
        Relationship(
            source_id=f_a.id,
            target_id=f_a.id,
            relationship_type=RelationshipType.IMPORTS,
        )
    )

    result = find_impact(project, "a.py", direction="outgoing", max_depth=10)

    assert result.status == "resolved"
    assert result.total == 2
    names = [it.related_name for it in result.items]
    assert names == ["b.py", "c.py"]
    # Check deduplication: each node appears once
    assert len(set(names)) == len(names)
    assert result.depth_reached == 2


def test_find_impact_shortest_path_selection(tmp_path: Path) -> None:
    project = Project(name="Path Test", root_path=tmp_path, analysis_status="analyzed")
    f_t = File(project_id=project.id, path=Path("t.py"), name="t.py", extension=".py")
    f_a = File(project_id=project.id, path=Path("a.py"), name="a.py", extension=".py")
    f_b = File(project_id=project.id, path=Path("b.py"), name="b.py", extension=".py")
    f_c = File(project_id=project.id, path=Path("c.py"), name="c.py", extension=".py")
    f_d = File(project_id=project.id, path=Path("d.py"), name="d.py", extension=".py")
    for f in (f_t, f_a, f_b, f_c, f_d):
        project.add_file(f)

    # Long path: t -> a -> b -> d (depth 3)
    project.add_relationship(
        Relationship(
            source_id=f_t.id,
            target_id=f_a.id,
            relationship_type=RelationshipType.IMPORTS,
        )
    )
    project.add_relationship(
        Relationship(
            source_id=f_a.id,
            target_id=f_b.id,
            relationship_type=RelationshipType.IMPORTS,
        )
    )
    project.add_relationship(
        Relationship(
            source_id=f_b.id,
            target_id=f_d.id,
            relationship_type=RelationshipType.IMPORTS,
        )
    )

    # Short path: t -> c -> d (depth 2)
    project.add_relationship(
        Relationship(
            source_id=f_t.id,
            target_id=f_c.id,
            relationship_type=RelationshipType.IMPORTS,
        )
    )
    project.add_relationship(
        Relationship(
            source_id=f_c.id,
            target_id=f_d.id,
            relationship_type=RelationshipType.IMPORTS,
        )
    )

    result = find_impact(project, "t.py", direction="outgoing", max_depth=5)
    d_item = next(it for it in result.items if it.related_name == "d.py")

    assert d_item.depth == 2
    assert d_item.classification == "indirect"
    assert len(d_item.path) == 2
    assert [step.to_name for step in d_item.path] == ["c.py", "d.py"]


def test_find_impact_deterministic_tie_breaking(tmp_path: Path) -> None:
    project = Project(name="Tie Test", root_path=tmp_path, analysis_status="analyzed")
    f_t = File(project_id=project.id, path=Path("t.py"), name="t.py", extension=".py")
    f_a = File(project_id=project.id, path=Path("a.py"), name="a.py", extension=".py")
    f_b = File(project_id=project.id, path=Path("b.py"), name="b.py", extension=".py")
    f_d = File(project_id=project.id, path=Path("d.py"), name="d.py", extension=".py")
    for f in (f_t, f_a, f_b, f_d):
        project.add_file(f)

    # Path 1: t -> a -> d (depth 2)
    project.add_relationship(
        Relationship(
            source_id=f_t.id,
            target_id=f_a.id,
            relationship_type=RelationshipType.IMPORTS,
        )
    )
    project.add_relationship(
        Relationship(
            source_id=f_a.id,
            target_id=f_d.id,
            relationship_type=RelationshipType.IMPORTS,
        )
    )

    # Path 2: t -> b -> d (depth 2)
    project.add_relationship(
        Relationship(
            source_id=f_t.id,
            target_id=f_b.id,
            relationship_type=RelationshipType.IMPORTS,
        )
    )
    project.add_relationship(
        Relationship(
            source_id=f_b.id,
            target_id=f_d.id,
            relationship_type=RelationshipType.IMPORTS,
        )
    )

    res1 = find_impact(project, "t.py", direction="outgoing", max_depth=3)

    # Reverse relationships in project
    project.relationships.reverse()
    project.files.reverse()
    res2 = find_impact(project, "t.py", direction="outgoing", max_depth=3)

    assert res1.total == res2.total
    d1 = next(it for it in res1.items if it.related_name == "d.py")
    d2 = next(it for it in res2.items if it.related_name == "d.py")
    assert [s.to_name for s in d1.path] == [s.to_name for s in d2.path]


def test_find_impact_pagination_and_truncation(tmp_path: Path) -> None:
    project = create_impact_test_project(tmp_path)

    result = find_impact(
        project,
        "src/pkg/models.py",
        direction="incoming",
        max_depth=3,
        limit=1,
    )

    assert result.total == 2
    assert len(result.items) == 1
    assert result.truncated is True
    assert result.limit == 1
    assert any(
        "Display was limited to 1 of 2 reachable components." in lim
        for lim in result.limitations
    )


def test_find_impact_relationship_and_target_filters(tmp_path: Path) -> None:
    project = create_impact_test_project(tmp_path)

    # Filter to only 'references' - models.py has no incoming 'references', only 'imports'
    res_filtered = find_impact(
        project,
        "src/pkg/models.py",
        direction="incoming",
        relationship_types={"references"},
        max_depth=3,
    )
    assert res_filtered.total == 0

    # Target types filter: only 'symbol'
    res_sym_only = find_impact(
        project,
        "src/pkg/models.py",
        direction="both",
        target_types={"symbol"},
        max_depth=3,
    )
    for it in res_sym_only.items:
        assert it.related_type == "symbol"


def test_project_query_transitive_impact_methods(tmp_path: Path) -> None:
    project = create_impact_test_project(tmp_path)
    query = ProjectQuery(project)

    res1 = query.find_impact("src/pkg/models.py", direction="incoming", max_depth=2)
    res2 = query.find_transitive_impact(
        "src/pkg/models.py", direction="incoming", max_depth=2
    )

    assert res1.total == 2
    assert res2.total == 2
    assert res1.to_dict() == res2.to_dict()


def test_impact_path_step_to_dict() -> None:
    step = ImpactPathStep(
        relationship_id=uuid4(),
        relationship_type="imports",
        direction="incoming",
        source_id=uuid4(),
        target_id=uuid4(),
        from_id=uuid4(),
        to_id=uuid4(),
        from_name="models.py",
        to_name="service.py",
        from_path="src/models.py",
        to_path="src/service.py",
        from_kind="file",
        to_kind="file",
        confidence=0.9,
        metadata={"line_number": "10"},
    )
    d = step.to_dict()
    assert d["from_name"] == "models.py"
    assert d["to_name"] == "service.py"
    assert d["from_path"] == "src/models.py"
    assert d["to_path"] == "src/service.py"
    assert d["relationship_type"] == "imports"
    assert d["direction"] == "incoming"
    assert d["confidence"] == 0.9
    assert d["metadata"] == {"line_number": "10"}
    assert isinstance(d["relationship_id"], str)


def test_find_transitive_impact_alias() -> None:
    assert find_transitive_impact is find_impact
