from pathlib import Path

from context_forge.models.file import File
from context_forge.models.project import Project
from context_forge.models.symbol import Symbol
from context_forge.task import (
    TaskGroundingService,
    TaskInterpretation,
)


def make_project() -> tuple[Project, File, File, Symbol, Symbol]:
    project = Project(
        name="demo",
        root_path=Path("/tmp/demo"),
    )

    settings_file = File(
        project_id=project.id,
        path=Path("src/settings.py"),
        name="settings.py",
        extension=".py",
    )
    service_file = File(
        project_id=project.id,
        path=Path("src/service.py"),
        name="service.py",
        extension=".py",
    )

    settings_symbol = Symbol(
        file_id=settings_file.id,
        name="Settings",
        kind="class",
        start_line=1,
        end_line=20,
        qualified_name="settings.Settings",
    )
    service_symbol = Symbol(
        file_id=service_file.id,
        name="SettingsService",
        kind="class",
        start_line=1,
        end_line=20,
        qualified_name="service.SettingsService",
    )

    project.files.extend([settings_file, service_file])
    project.symbols.extend([settings_symbol, service_symbol])

    return (
        project,
        settings_file,
        service_file,
        settings_symbol,
        service_symbol,
    )


def test_ground_resolves_explicit_file_path() -> None:
    project, settings_file, _, _, _ = make_project()

    interpretation = TaskInterpretation(
        task="Fix src/settings.py",
        intent="bug_fix",
        target="src/settings.py",
        concepts=(),
        requested_action="fix",
    )

    result = TaskGroundingService().ground(project, interpretation)

    assert len(result.entities) == 1
    assert result.entities[0].entity_id == settings_file.id
    assert result.entities[0].entity_type == "file"
    assert result.entities[0].confidence == 1.0
    assert result.entities[0].provenance == ("exact repository-relative file path")
    assert result.unresolved_references == ()
    assert result.ambiguous_references == ()


def test_ground_resolves_exact_qualified_symbol() -> None:
    project, _, _, settings_symbol, _ = make_project()

    interpretation = TaskInterpretation(
        task="Fix Settings",
        intent="bug_fix",
        target="settings.Settings",
        concepts=(),
        requested_action="fix",
    )

    result = TaskGroundingService().ground(project, interpretation)

    assert len(result.entities) == 1
    assert result.entities[0].entity_id == settings_symbol.id
    assert result.entities[0].confidence == 1.0
    assert result.entities[0].provenance == ("exact symbol qualified name")


def test_ground_resolves_unique_symbol_name() -> None:
    project, _, _, settings_symbol, _ = make_project()

    interpretation = TaskInterpretation(
        task="Fix Settings",
        intent="bug_fix",
        target="Settings",
        concepts=(),
        requested_action="fix",
    )

    result = TaskGroundingService().ground(project, interpretation)

    assert len(result.entities) == 1
    assert result.entities[0].entity_id == settings_symbol.id
    assert result.entities[0].confidence == 0.9
    assert result.entities[0].provenance == "unique exact symbol name"


def test_ground_reports_unresolved_symbol() -> None:
    project, _, _, _, _ = make_project()

    interpretation = TaskInterpretation(
        task="Fix AuthenticationService",
        intent="bug_fix",
        target="AuthenticationService",
        concepts=(),
        requested_action="fix",
    )

    result = TaskGroundingService().ground(project, interpretation)

    assert result.entities == ()
    assert len(result.unresolved_references) == 1
    assert result.unresolved_references[0].value == "AuthenticationService"
    assert result.unresolved_references[0].kind == "symbol"
    assert result.ambiguous_references == ()


def test_ground_reports_ambiguous_symbol() -> None:
    project, settings_file, service_file, _, _ = make_project()

    first = Symbol(
        file_id=settings_file.id,
        name="Handler",
        kind="class",
        start_line=1,
        end_line=5,
    )
    second = Symbol(
        file_id=service_file.id,
        name="Handler",
        kind="class",
        start_line=1,
        end_line=5,
    )

    project.symbols.extend([first, second])

    interpretation = TaskInterpretation(
        task="Fix Handler",
        intent="bug_fix",
        target="Handler",
        concepts=(),
        requested_action="fix",
    )

    result = TaskGroundingService().ground(project, interpretation)

    assert result.entities == ()
    assert result.unresolved_references == ()
    assert len(result.ambiguous_references) == 1
    assert result.ambiguous_references[0].value == "Handler"
    assert result.ambiguous_references[0].kind == "symbol"


def test_ground_deduplicates_same_entity() -> None:
    project, settings_file, _, _, _ = make_project()

    interpretation = TaskInterpretation(
        task="Fix src/settings.py",
        intent="bug_fix",
        target="src/settings.py",
        concepts=("src/settings.py",),
        requested_action="fix",
    )

    result = TaskGroundingService().ground(project, interpretation)

    assert len(result.entities) == 1
    assert result.entities[0].entity_id == settings_file.id


def test_ground_normalizes_windows_paths() -> None:
    project, settings_file, _, _, _ = make_project()

    interpretation = TaskInterpretation(
        task=r"Fix src\settings.py",
        intent="bug_fix",
        target=r"src\settings.py",
        concepts=(),
        requested_action="fix",
    )

    result = TaskGroundingService().ground(project, interpretation)

    assert len(result.entities) == 1
    assert result.entities[0].entity_id == settings_file.id


def test_ground_preserves_interpretation() -> None:
    project, _, _, _, _ = make_project()

    interpretation = TaskInterpretation(
        task="Fix Settings",
        intent="bug_fix",
        target="Settings",
        concepts=("configuration",),
        requested_action="fix",
    )

    result = TaskGroundingService().ground(project, interpretation)

    assert result.interpretation is interpretation
