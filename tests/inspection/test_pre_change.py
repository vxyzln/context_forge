from __future__ import annotations

import dataclasses
import hashlib
import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from context_forge.git import EntityMappingStatus
from context_forge.inspection import (
    PreChangeInspectionResult,
    format_pre_change_inspection_summary,
    inspect_pre_change,
)
from context_forge.main import parse_args
from context_forge.pipeline.analyzer import ProjectAnalyzer
from context_forge.pipeline.freshness import FreshnessState
from context_forge.query.project import ProjectQuery
from context_forge.reporting.contract import OperationStatus


def run_git(path: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", *arguments],
        cwd=path,
        check=True,
        capture_output=True,
        text=True,
    )


def configure_git(path: Path) -> None:
    run_git(path, "init")
    run_git(path, "config", "user.name", "Context Forge Test")
    run_git(path, "config", "user.email", "test@example.com")


def _dir_hash(directory: Path) -> str:
    hasher = hashlib.sha256()
    for p in sorted(directory.rglob("*")):
        if p.is_file():
            hasher.update(str(p.relative_to(directory)).encode("utf-8"))
            hasher.update(p.read_bytes())
    return hasher.hexdigest()


@pytest.fixture
def sample_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "test_repo"
    repo.mkdir()
    configure_git(repo)

    (repo / ".gitignore").write_text(".context_forge.db\n", encoding="utf-8")

    src_dir = repo / "src"
    src_dir.mkdir()

    auth_file = src_dir / "auth.py"
    auth_file.write_text(
        "class AuthService:\n"
        "    def login(self, username: str) -> bool:\n"
        "        return True\n"
        "\n"
        "def hash_password(pw: str) -> str:\n"
        "    return 'hashed'\n",
        encoding="utf-8",
    )

    utils_file = src_dir / "utils.py"
    utils_file.write_text(
        "def format_user(name: str) -> str:\n    return name.strip()\n",
        encoding="utf-8",
    )

    run_git(repo, "add", ".")
    run_git(repo, "commit", "-m", "Initial commit")

    analyzer = ProjectAnalyzer(root_path=repo, database_path=repo / ".context_forge.db")
    analyzer.analyze()
    return repo


def test_scenario_1_successful_inspection(sample_repo: Path) -> None:
    result = inspect_pre_change(sample_repo, "AuthService")

    assert isinstance(result, PreChangeInspectionResult)
    assert result.is_success is True
    assert result.outcome.status == OperationStatus.SUCCESS
    assert result.outcome.message == "Pre-change inspection completed successfully"

    assert result.target_resolution is not None
    assert result.target_resolution.is_resolved is True
    assert result.target_resolution.target is not None
    assert result.target_resolution.target.name == "AuthService"
    assert result.target_resolution.target.kind == "class"
    assert result.target_resolution.target.path == "src/auth.py"

    assert result.freshness is not None
    assert result.freshness.is_current is True

    assert result.source_evidence is not None
    assert result.source_evidence.is_success is True
    assert "class AuthService:" in result.source_evidence.content
    assert result.source_evidence.path == "src/auth.py"

    assert result.structural_evidence is not None
    assert result.structural_evidence.status == "resolved"

    assert result.git_context is not None
    assert result.git_context.is_clean is True


def test_scenario_2_blocked_preflight(tmp_path: Path) -> None:
    nonexistent = tmp_path / "does_not_exist"
    result = inspect_pre_change(nonexistent, "AuthService")

    assert result.is_blocked is True
    assert result.outcome.status == OperationStatus.BLOCKED
    assert result.readiness["readiness"] == "blocked"
    assert any(d.code == "REPOSITORY_NOT_FOUND" for d in result.diagnostics)
    assert not nonexistent.exists()

    dummy_file = tmp_path / "dummy.txt"
    dummy_file.write_text("hello", encoding="utf-8")
    result_file = inspect_pre_change(dummy_file, "AuthService")
    assert result_file.is_blocked is True
    assert any(d.code == "REPOSITORY_NOT_A_DIRECTORY" for d in result_file.diagnostics)


def test_scenario_3_ambiguous_target(tmp_path: Path) -> None:
    repo = tmp_path / "ambig_repo"
    repo.mkdir()
    configure_git(repo)

    (repo / "mod1.py").write_text("def process(): pass\n", encoding="utf-8")
    (repo / "mod2.py").write_text("def process(): pass\n", encoding="utf-8")

    run_git(repo, "add", ".")
    run_git(repo, "commit", "-m", "Initial")

    analyzer = ProjectAnalyzer(root_path=repo, database_path=repo / ".context_forge.db")
    analyzer.analyze()

    result = inspect_pre_change(repo, "process")

    assert result.is_partial is True
    assert result.outcome.status == OperationStatus.PARTIAL
    assert result.target_resolution is not None
    assert result.target_resolution.is_ambiguous is True
    assert len(result.target_resolution.candidates) == 2
    assert result.source_evidence is None
    assert any(d.code == "TARGET_AMBIGUOUS" for d in result.diagnostics)


def test_scenario_4_target_not_found(sample_repo: Path) -> None:
    result = inspect_pre_change(sample_repo, "NonexistentSymbol")

    assert result.is_blocked is True
    assert result.outcome.status == OperationStatus.BLOCKED
    assert result.target_resolution is not None
    assert result.target_resolution.is_not_found is True
    assert result.source_evidence is None
    assert any(d.code == "TARGET_NOT_FOUND" for d in result.diagnostics)


def test_scenario_5_stale_repository_analysis(sample_repo: Path) -> None:
    auth_file = sample_repo / "src" / "auth.py"
    current_content = auth_file.read_text(encoding="utf-8")
    auth_file.write_text(current_content + "\n# Modified file\n", encoding="utf-8")

    result = inspect_pre_change(sample_repo, "AuthService")

    assert result.is_partial is True
    assert result.outcome.status == OperationStatus.PARTIAL
    assert result.freshness is not None
    assert result.freshness.is_stale is True
    assert result.freshness.refreshed is False
    assert any(d.code == "STALE_ANALYSIS" for d in result.diagnostics)

    assert result.git_context is not None
    assert result.git_context.has_changes is True
    modified_paths = [
        m.git_path
        for m in result.git_context.mappings
        if m.git_status_entry and m.git_status_entry.is_modified
    ]
    assert "src/auth.py" in modified_paths


def test_scenario_6_missing_and_incomplete_analysis(tmp_path: Path) -> None:
    repo = tmp_path / "unanalyzed_repo"
    repo.mkdir()
    configure_git(repo)
    (repo / "main.py").write_text("def start(): pass\n", encoding="utf-8")

    db_path = repo / ".context_forge.db"
    assert not db_path.exists()

    result = inspect_pre_change(repo, "start")

    assert result.is_blocked is True
    assert result.outcome.status == OperationStatus.BLOCKED
    assert result.freshness is not None
    assert result.freshness.state == FreshnessState.INDETERMINATE
    assert result.freshness.reason == "missing_analysis"
    assert not db_path.exists()
    assert any(d.code == "MISSING_ANALYSIS" for d in result.diagnostics)


def test_scenario_7_deleted_source_evidence(sample_repo: Path) -> None:
    auth_file = sample_repo / "src" / "auth.py"
    auth_file.unlink()

    result = inspect_pre_change(sample_repo, "AuthService")

    assert result.is_partial is True
    assert result.outcome.status == OperationStatus.PARTIAL
    assert result.target_resolution is not None
    assert result.target_resolution.is_resolved is True
    assert result.source_evidence is not None
    assert result.source_evidence.status == "missing_file"
    assert result.source_evidence.content == ""


def test_scenario_8_git_changes_map_to_known_entities(
    sample_repo: Path,
) -> None:
    auth_file = sample_repo / "src" / "auth.py"
    auth_file.write_text(
        auth_file.read_text(encoding="utf-8") + "\n# extra\n",
        encoding="utf-8",
    )

    result = inspect_pre_change(sample_repo, "AuthService")

    assert result.git_context is not None
    assert len(result.git_context.mappings) == 1
    mapping = result.git_context.mappings[0]
    assert mapping.git_path == "src/auth.py"
    assert mapping.status == EntityMappingStatus.MATCHED
    assert mapping.matched_entity is not None
    assert mapping.matched_entity.name == "auth.py"


def test_scenario_9_unmatched_and_ambiguous_git_mapping(
    sample_repo: Path,
) -> None:
    extra = sample_repo / "untracked_new_file.txt"
    extra.write_text("new file", encoding="utf-8")

    result = inspect_pre_change(sample_repo, "AuthService")

    assert result.git_context is not None
    unmatched = [
        m
        for m in result.git_context.mappings
        if m.status == EntityMappingStatus.UNMATCHED
    ]
    assert any(m.git_path == "untracked_new_file.txt" for m in unmatched)


def test_scenario_10_partial_component_failure(sample_repo: Path) -> None:
    mock_git_repo = MagicMock()
    mock_git_repo.get_status.side_effect = RuntimeError("Git status crashed")

    result = inspect_pre_change(
        sample_repo,
        "AuthService",
        git_repository=mock_git_repo,
    )

    assert result.is_partial is True
    assert result.outcome.status == OperationStatus.PARTIAL
    assert any(d.code == "GIT_INSPECTION_FAILED" for d in result.diagnostics)
    assert result.target_resolution is not None
    assert result.target_resolution.is_resolved is True
    assert result.source_evidence is not None
    assert result.source_evidence.is_success is True


def test_scenario_11_structured_output_serialization(
    sample_repo: Path,
) -> None:
    success_result = inspect_pre_change(sample_repo, "AuthService")
    payload = success_result.to_dict()

    assert payload["schema_version"] == 1
    assert payload["repository_path"] == str(sample_repo).replace("\\", "/")
    assert payload["target_query"] == "AuthService"
    assert "readiness" in payload
    assert "target_resolution" in payload
    assert "freshness" in payload
    assert "source_evidence" in payload
    assert "structural_evidence" in payload
    assert "git_context" in payload
    assert "outcome" in payload
    assert "limitations" in payload
    assert "diagnostics" in payload

    serialized = json.dumps(payload, sort_keys=True)
    assert isinstance(serialized, str)

    blocked_result = inspect_pre_change(sample_repo / "nonexistent", "Target")
    blocked_payload = blocked_result.to_dict()
    assert blocked_payload["outcome"]["status"] == "blocked"
    json.dumps(blocked_payload, sort_keys=True)


def test_scenario_12_read_only_invariance(sample_repo: Path) -> None:
    hash_before = _dir_hash(sample_repo)

    result = inspect_pre_change(sample_repo, "AuthService")
    assert result.is_success is True

    hash_after = _dir_hash(sample_repo)
    assert hash_before == hash_after


def test_project_query_inspect_pre_change_method(sample_repo: Path) -> None:
    analyzer = ProjectAnalyzer(
        root_path=sample_repo, database_path=sample_repo / ".context_forge.db"
    )
    project = analyzer.analyze()
    query = ProjectQuery(project)

    result = query.inspect_pre_change("AuthService")
    assert isinstance(result, PreChangeInspectionResult)
    assert result.is_success is True
    assert result.target_resolution.is_resolved is True


def test_format_summary_text_output(sample_repo: Path) -> None:
    result = inspect_pre_change(sample_repo, "AuthService")
    lines = format_pre_change_inspection_summary(result)

    text = "\n".join(lines)
    assert "Repository:" in text
    assert "Target query: AuthService" in text
    assert "Readiness: READY" in text
    assert "Target: [class] AuthService" in text
    assert "Freshness:" in text
    assert "Source Evidence:" in text
    assert "class AuthService:" in text
    assert "Overall Status: SUCCESS" in text


def test_cli_inspect_change_success(
    sample_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args = parse_args(["inspect-change", "AuthService", str(sample_repo)])
    assert args.command == "inspect-change"
    assert args.target == "AuthService"

    from context_forge.main import _dispatch_command

    _dispatch_command(args)
    captured = capsys.readouterr()
    assert "AuthService" in captured.out
    assert "Overall Status: SUCCESS" in captured.out


def test_cli_inspect_change_json_format(
    sample_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args = parse_args(
        ["inspect-change", "AuthService", str(sample_repo), "--format", "json"]
    )
    from context_forge.main import _dispatch_command

    _dispatch_command(args)
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["schema_version"] == 1
    assert data["outcome"]["status"] == "success"
    assert data["target_resolution"]["target"]["name"] == "AuthService"


def test_cli_pre_change_alias_and_blocked_exit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args = parse_args(["pre-change", "MissingSymbol", str(tmp_path / "nonexistent")])
    assert args.command == "pre-change"

    from context_forge.main import _dispatch_command

    with pytest.raises(SystemExit) as exc_info:
        _dispatch_command(args)
    assert exc_info.value.code == 1


def test_cli_filter_flags(
    sample_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args = parse_args(
        [
            "inspect-change",
            "login",
            str(sample_repo),
            "--file",
            "src/auth.py",
            "--type",
            "method",
            "--direction",
            "both",
            "--depth",
            "2",
            "--max-lines",
            "20",
            "--no-git",
        ]
    )
    assert args.file_path == "src/auth.py"
    assert args.symbol_type == "method"
    assert args.max_depth == 2
    assert args.max_lines == 20
    assert args.no_git is True

    from context_forge.main import _dispatch_command

    _dispatch_command(args)
    captured = capsys.readouterr()
    assert "login" in captured.out


def test_empty_or_whitespace_target(sample_repo: Path) -> None:
    res_empty = inspect_pre_change(sample_repo, "")
    assert res_empty.is_blocked is True
    assert res_empty.target_resolution is not None
    assert res_empty.target_resolution.is_invalid is True
    assert any(d.code == "TARGET_INVALID" for d in res_empty.diagnostics)

    res_ws = inspect_pre_change(sample_repo, "   ")
    assert res_ws.is_blocked is True
    assert res_ws.target_resolution is not None
    assert res_ws.target_resolution.is_invalid is True


def test_filter_disambiguation(tmp_path: Path) -> None:
    repo = tmp_path / "filter_repo"
    repo.mkdir()
    configure_git(repo)
    (repo / ".gitignore").write_text(".context_forge.db\n", encoding="utf-8")

    (repo / "mod1.py").write_text("class Worker:\n    pass\n", encoding="utf-8")
    (repo / "mod2.py").write_text("def Worker():\n    pass\n", encoding="utf-8")
    run_git(repo, "add", ".")
    run_git(repo, "commit", "-m", "Init")

    ProjectAnalyzer(root_path=repo, database_path=repo / ".context_forge.db").analyze()

    ambig = inspect_pre_change(repo, "Worker")
    assert ambig.target_resolution is not None
    assert ambig.target_resolution.is_ambiguous is True

    resolved_by_type = inspect_pre_change(repo, "Worker", symbol_type="class")
    assert resolved_by_type.target_resolution is not None
    assert resolved_by_type.target_resolution.is_resolved is True
    assert resolved_by_type.target_resolution.target is not None
    assert resolved_by_type.target_resolution.target.kind == "class"

    resolved_by_file = inspect_pre_change(repo, "Worker", file_path="mod2.py")
    assert resolved_by_file.target_resolution is not None
    assert resolved_by_file.target_resolution.is_resolved is True
    assert resolved_by_file.target_resolution.target is not None
    assert resolved_by_file.target_resolution.target.kind == "function"


def test_non_git_repository(tmp_path: Path) -> None:
    repo = tmp_path / "plain_repo"
    repo.mkdir()
    (repo / "code.py").write_text("def compute():\n    return 42\n", encoding="utf-8")

    ProjectAnalyzer(root_path=repo, database_path=repo / ".context_forge.db").analyze()

    result = inspect_pre_change(repo, "compute", include_git=True)
    assert result.is_success is True
    assert result.outcome.has_blockers is False
    assert result.git_context is not None
    assert result.git_context.is_git_repository is False

    result_no_git = inspect_pre_change(repo, "compute", include_git=False)
    assert result_no_git.is_success is True
    assert result_no_git.git_context is None


def test_include_git_disabled(sample_repo: Path) -> None:
    result = inspect_pre_change(sample_repo, "AuthService", include_git=False)
    assert result.is_success is True
    assert result.git_context is None


def test_incomplete_analysis_status(tmp_path: Path) -> None:
    repo = tmp_path / "incomplete_repo"
    repo.mkdir()
    configure_git(repo)
    (repo / ".gitignore").write_text(".context_forge.db\n", encoding="utf-8")
    (repo / "test.py").write_text("def run():\n    pass\n", encoding="utf-8")
    run_git(repo, "add", ".")
    run_git(repo, "commit", "-m", "Init")

    analyzer = ProjectAnalyzer(root_path=repo, database_path=repo / ".context_forge.db")
    project = analyzer.analyze()

    incomplete_proj = dataclasses.replace(project, analysis_status="partial")
    result = inspect_pre_change(repo, "run", project=incomplete_proj)
    assert result.is_incomplete is True
    assert result.outcome.status == OperationStatus.INCOMPLETE
    assert result.freshness is not None
    assert result.freshness.is_incomplete is True


def test_cli_empty_target_exits_one(sample_repo: Path) -> None:
    args = parse_args(["inspect-change", "", str(sample_repo)])
    from context_forge.main import _dispatch_command

    with pytest.raises(SystemExit) as exc:
        _dispatch_command(args)
    assert exc.value.code == 1


def test_structural_evidence_on_disambiguated_target(tmp_path: Path) -> None:
    repo = tmp_path / "disambig_impact_repo"
    repo.mkdir()
    configure_git(repo)
    (repo / ".gitignore").write_text(".context_forge.db\n", encoding="utf-8")

    (repo / "alpha.py").write_text(
        "class Config:\n    pass\n\ndef worker():\n    return Config()\n",
        encoding="utf-8",
    )
    (repo / "beta.py").write_text(
        "def worker():\n    return 'standalone'\n",
        encoding="utf-8",
    )
    run_git(repo, "add", ".")
    run_git(repo, "commit", "-m", "Init")

    ProjectAnalyzer(root_path=repo, database_path=repo / ".context_forge.db").analyze()

    result = inspect_pre_change(repo, "worker", file_path="alpha.py")
    assert result.is_success is True
    assert result.target_resolution.is_resolved is True
    assert result.target_resolution.target is not None
    assert result.target_resolution.target.path == "alpha.py"
    assert result.structural_evidence is not None
    assert result.structural_evidence.status == "resolved"


def test_indeterminate_freshness_blocked(tmp_path: Path) -> None:
    repo = tmp_path / "indet_repo"
    repo.mkdir()
    configure_git(repo)
    (repo / ".gitignore").write_text(".context_forge.db\n", encoding="utf-8")
    (repo / "app.py").write_text("def main(): pass\n", encoding="utf-8")
    run_git(repo, "add", ".")
    run_git(repo, "commit", "-m", "Init")

    analyzer = ProjectAnalyzer(root_path=repo, database_path=repo / ".context_forge.db")
    project = analyzer.analyze()

    from context_forge.storage.cache import RepositoryCacheMetadata

    bad_metadata = RepositoryCacheMetadata(
        repository_key=str(repo),
        project_id=project.id,
        cache_schema_version=999,
        analyzer_version="0.1.0",
    )

    result = inspect_pre_change(repo, "main", metadata=bad_metadata)
    assert result.is_blocked is True
    assert result.outcome.status == OperationStatus.BLOCKED
    assert any(d.code == "SCHEMA_VERSION_MISMATCH" for d in result.diagnostics)


def test_relative_repository_path_inspection(
    sample_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(sample_repo)
    result = inspect_pre_change(Path("."), "AuthService")
    assert result.is_success is True
    assert result.git_context is not None
    assert result.git_context.is_git_repository is True
    assert not any(
        "Git repository root path must be absolute" in d.message
        for d in result.diagnostics
    )
