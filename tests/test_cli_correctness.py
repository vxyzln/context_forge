from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from context_forge.main import main, parse_args


@pytest.fixture
def sample_project(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()

    pkg_a = root / "pkg_a"
    pkg_a.mkdir()
    (pkg_a / "__init__.py").write_text("", encoding="utf-8")
    (pkg_a / "service.py").write_text(
        "def process_data(val: int) -> int:\n"
        "    return val * 2\n\n"
        "class Service:\n"
        "    def run(self) -> None:\n"
        "        pass\n",
        encoding="utf-8",
    )

    pkg_b = root / "pkg_b"
    pkg_b.mkdir()
    (pkg_b / "__init__.py").write_text("", encoding="utf-8")
    (pkg_b / "pipeline.py").write_text(
        "from pkg_a.service import process_data\n\n"
        "def run_pipeline() -> int:\n"
        "    return process_data(42)\n",
        encoding="utf-8",
    )

    pkg_c = root / "pkg_c"
    pkg_c.mkdir()
    (pkg_c / "__init__.py").write_text("", encoding="utf-8")
    (pkg_c / "models.py").write_text(
        "class Config:\n    debug: bool = True\n",
        encoding="utf-8",
    )

    pkg_d = root / "pkg_d"
    pkg_d.mkdir()
    (pkg_d / "__init__.py").write_text("", encoding="utf-8")
    (pkg_d / "models.py").write_text(
        "class Config:\n    timeout: int = 30\n",
        encoding="utf-8",
    )

    (root / "orphan.py").write_text(
        "def standalone() -> None:\n    pass\n",
        encoding="utf-8",
    )

    with patch.object(sys, "argv", ["context-forge", "analyze", str(root)]):
        main()

    return root


def test_unknown_command_exits_2(capsys: pytest.CaptureFixture[str]) -> None:
    with (
        patch.object(sys, "argv", ["cf", "anlyze"]),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert "invalid choice: 'anlyze'" in captured.err


def test_unknown_subcommand_exits_2(capsys: pytest.CaptureFixture[str]) -> None:
    with (
        patch.object(sys, "argv", ["cf", "memory", "foobar"]),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert "invalid choice: 'foobar'" in captured.err


def test_unknown_flag_exits_2(capsys: pytest.CaptureFixture[str]) -> None:
    with (
        patch.object(sys, "argv", ["cf", "--unrecognized-option"]),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 2


def test_bare_path_status_detection(sample_project: Path) -> None:
    args = parse_args([str(sample_project)])
    assert args.command == "status"
    assert args.path == Path(str(sample_project))

    args_dot = parse_args(["."])
    assert args_dot.command == "status"
    assert args_dot.path == Path(".")


def test_bare_path_nonexistent_fails_with_exit_1(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with (
        patch.object(sys, "argv", ["cf", "/nonexistent/test/directory/path"]),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "Project path does not exist" in captured.err


def test_impact_missing_target_text(
    sample_project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with (
        patch.object(
            sys, "argv", ["cf", "impact", "nonexistent_target", str(sample_project)]
        ),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "Status: Target not found." in captured.out
    assert "not found in repository" in captured.out


def test_impact_missing_target_json(
    sample_project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with (
        patch.object(
            sys,
            "argv",
            [
                "cf",
                "impact",
                "nonexistent_target",
                str(sample_project),
                "--format",
                "json",
            ],
        ),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["status"] == "not_found"
    assert data["target"] is None


def test_impact_ambiguous_target_text(
    sample_project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with (
        patch.object(sys, "argv", ["cf", "impact", "Config", str(sample_project)]),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "Status: Ambiguous target." in captured.out
    assert "Candidates (2):" in captured.out


def test_impact_ambiguous_target_json(
    sample_project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with (
        patch.object(
            sys,
            "argv",
            ["cf", "impact", "Config", str(sample_project), "--format", "json"],
        ),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["status"] == "ambiguous"
    assert len(data["candidates"]) == 2


def test_impact_valid_target_with_zero_impact_exits_0(
    sample_project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with patch.object(sys, "argv", ["cf", "impact", "orphan.py", str(sample_project)]):
        main()

    captured = capsys.readouterr()
    assert "Resolved target: [file] orphan.py (orphan.py)" in captured.out
    assert "Impacted components: 0" in captured.out


def test_impact_valid_target_with_impact_exits_0(
    sample_project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with patch.object(
        sys, "argv", ["cf", "impact", "pkg_a/service.py", str(sample_project)]
    ):
        main()

    captured = capsys.readouterr()
    assert "Resolved target: [file] service.py (pkg_a/service.py)" in captured.out
    assert "pkg_b/pipeline.py" in captured.out


def test_impact_empty_target_exits_1(
    sample_project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with (
        patch.object(sys, "argv", ["cf", "impact", "   ", str(sample_project)]),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "Target cannot be empty" in captured.err


def test_memory_file_missing_text(
    sample_project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with (
        patch.object(
            sys, "argv", ["cf", "memory", "file", "nonexistent.py", str(sample_project)]
        ),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "File not found." in captured.out


def test_memory_file_missing_json(
    sample_project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with (
        patch.object(
            sys,
            "argv",
            [
                "cf",
                "memory",
                "file",
                "nonexistent.py",
                str(sample_project),
                "--format",
                "json",
            ],
        ),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["file"] is None
    assert data["requested_path"] == "nonexistent.py"


def test_memory_file_valid_relative_path(
    sample_project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with patch.object(
        sys,
        "argv",
        ["cf", "memory", "file", "pkg_a/service.py", str(sample_project)],
    ):
        main()

    captured = capsys.readouterr()
    assert "File: pkg_a/service.py" in captured.out
    assert "Name: service.py" in captured.out
    assert "Symbols: 3" in captured.out


def test_memory_file_resolves_dot_slash_and_absolute_paths(
    sample_project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with patch.object(
        sys,
        "argv",
        [
            "cf",
            "memory",
            "file",
            "./pkg_a/service.py",
            str(sample_project),
            "--format",
            "json",
        ],
    ):
        main()

    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["file"] is not None
    assert data["file"]["path"] == "pkg_a/service.py"

    abs_file = sample_project / "pkg_a" / "service.py"
    with patch.object(
        sys,
        "argv",
        [
            "cf",
            "memory",
            "file",
            str(abs_file),
            str(sample_project),
            "--format",
            "json",
        ],
    ):
        main()

    captured_abs = capsys.readouterr()
    data_abs = json.loads(captured_abs.out)
    assert data_abs["file"] is not None
    assert data_abs["file"]["path"] == "pkg_a/service.py"


def test_memory_symbol_missing_exits_1(
    sample_project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with (
        patch.object(
            sys,
            "argv",
            ["cf", "memory", "symbol", "nonexistent_sym", str(sample_project)],
        ),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()
    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "No matching symbol found." in captured.out

    with (
        patch.object(
            sys,
            "argv",
            [
                "cf",
                "memory",
                "symbol",
                "nonexistent_sym",
                str(sample_project),
                "--format",
                "json",
            ],
        ),
        pytest.raises(SystemExit) as exc_info_json,
    ):
        main()
    assert exc_info_json.value.code == 1
    data = json.loads(capsys.readouterr().out)
    assert data["matches"] == []


def test_memory_symbol_ambiguous_exits_1_without_excerpt(
    sample_project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with (
        patch.object(
            sys,
            "argv",
            ["cf", "memory", "symbol", "Config", str(sample_project), "--excerpt"],
        ),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "Multiple definitions found:" in captured.out
    assert "Source excerpt" not in captured.out


def test_memory_symbol_disambiguation_with_file_filter(
    sample_project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with patch.object(
        sys,
        "argv",
        [
            "cf",
            "memory",
            "symbol",
            "Config",
            str(sample_project),
            "--file",
            "pkg_c/models.py",
        ],
    ):
        main()

    captured = capsys.readouterr()
    assert "Matches: 1" in captured.out
    assert "Path: pkg_c/models.py" in captured.out


def test_symbol_imported_disambiguation_prefers_definition(
    sample_project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with patch.object(
        sys, "argv", ["cf", "memory", "symbol", "process_data", str(sample_project)]
    ):
        main()

    captured = capsys.readouterr()
    assert "Matches: 1" in captured.out
    assert (
        "[function] pkg_a.service.process_data" in captured.out
        or "[function] process_data" in captured.out
    )
    assert "pkg_a/service.py" in captured.out

    with patch.object(
        sys, "argv", ["cf", "locate", "process_data", str(sample_project)]
    ):
        main()

    locate_out = capsys.readouterr().out
    assert "Status: RESOLVED" in locate_out
    assert "pkg_a/service.py" in locate_out


def test_locate_and_memory_symbol_file_filter_selects_import_candidate(
    sample_project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with patch.object(
        sys,
        "argv",
        [
            "cf",
            "locate",
            "process_data",
            str(sample_project),
            "--file",
            "pkg_b/pipeline.py",
        ],
    ):
        main()

    locate_out = capsys.readouterr().out
    assert "Status: RESOLVED" in locate_out
    assert "Target: [import]" in locate_out
    assert "pkg_b/pipeline.py" in locate_out

    with patch.object(
        sys,
        "argv",
        [
            "cf",
            "memory",
            "symbol",
            "process_data",
            str(sample_project),
            "--file",
            "pkg_b/pipeline.py",
        ],
    ):
        main()

    mem_out = capsys.readouterr().out
    assert "Matches: 1" in mem_out
    assert "- [import]" in mem_out
    assert "Path: pkg_b/pipeline.py" in mem_out


def test_locate_and_memory_symbol_file_filter_selects_definition_candidate(
    sample_project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with patch.object(
        sys,
        "argv",
        [
            "cf",
            "locate",
            "process_data",
            str(sample_project),
            "--file",
            "pkg_a/service.py",
        ],
    ):
        main()

    locate_out = capsys.readouterr().out
    assert "Status: RESOLVED" in locate_out
    assert "Target: [function]" in locate_out
    assert "pkg_a/service.py" in locate_out

    with patch.object(
        sys,
        "argv",
        [
            "cf",
            "memory",
            "symbol",
            "process_data",
            str(sample_project),
            "--file",
            "pkg_a/service.py",
        ],
    ):
        main()

    mem_out = capsys.readouterr().out
    assert "Matches: 1" in mem_out
    assert "- [function]" in mem_out
    assert "Path: pkg_a/service.py" in mem_out


def test_locate_and_memory_symbol_type_filter_import(
    sample_project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with patch.object(
        sys,
        "argv",
        ["cf", "locate", "process_data", str(sample_project), "--type", "import"],
    ):
        main()

    locate_out = capsys.readouterr().out
    assert "Status: RESOLVED" in locate_out
    assert "Target: [import]" in locate_out
    assert "pkg_b/pipeline.py" in locate_out

    with patch.object(
        sys,
        "argv",
        [
            "cf",
            "memory",
            "symbol",
            "process_data",
            str(sample_project),
            "--type",
            "import",
        ],
    ):
        main()

    mem_out = capsys.readouterr().out
    assert "Matches: 1" in mem_out
    assert "- [import]" in mem_out
    assert "Path: pkg_b/pipeline.py" in mem_out


def test_locate_and_memory_symbol_type_filter_mismatch_exits_1(
    sample_project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with (
        patch.object(
            sys,
            "argv",
            ["cf", "locate", "process_data", str(sample_project), "--type", "class"],
        ),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 1
    assert "not found in repository" in capsys.readouterr().out

    with (
        patch.object(
            sys,
            "argv",
            [
                "cf",
                "memory",
                "symbol",
                "process_data",
                str(sample_project),
                "--type",
                "class",
            ],
        ),
        pytest.raises(SystemExit) as exc_info_mem,
    ):
        main()

    assert exc_info_mem.value.code == 1
    assert "No matching symbol found." in capsys.readouterr().out


def test_locate_and_memory_symbol_qualified_name_resolution(
    sample_project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with patch.object(
        sys,
        "argv",
        ["cf", "locate", "pkg_a.service.process_data", str(sample_project)],
    ):
        main()

    locate_out = capsys.readouterr().out
    assert "Status: RESOLVED" in locate_out
    assert "pkg_a/service.py" in locate_out

    with patch.object(
        sys,
        "argv",
        ["cf", "memory", "symbol", "pkg_a.service.process_data", str(sample_project)],
    ):
        main()

    mem_out = capsys.readouterr().out
    assert "Matches: 1" in mem_out
    assert "Path: pkg_a/service.py" in mem_out

    with patch.object(
        sys,
        "argv",
        ["cf", "impact", "pkg_a.service.process_data", str(sample_project)],
    ):
        main()

    imp_out = capsys.readouterr().out
    assert "Resolved target: [function] process_data" in imp_out
    assert "pkg_a/service.py" in imp_out


def test_locate_and_memory_symbol_fully_qualified_class_method(
    sample_project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with patch.object(
        sys,
        "argv",
        ["cf", "locate", "pkg_a.service.Service.run", str(sample_project)],
    ):
        main()

    locate_out = capsys.readouterr().out
    assert "Status: RESOLVED" in locate_out
    assert "pkg_a/service.py" in locate_out
    assert "Service.run" in locate_out

    with patch.object(
        sys,
        "argv",
        ["cf", "memory", "symbol", "pkg_a.service.Service.run", str(sample_project)],
    ):
        main()

    mem_out = capsys.readouterr().out
    assert "Matches: 1" in mem_out
    assert "Service.run" in mem_out
    assert "Path: pkg_a/service.py" in mem_out

    with patch.object(
        sys,
        "argv",
        ["cf", "impact", "pkg_a.service.Service.run", str(sample_project)],
    ):
        main()

    imp_out = capsys.readouterr().out
    assert "Resolved target: [method] run (Service.run)" in imp_out
    assert "pkg_a/service.py" in imp_out


def test_locate_and_memory_symbol_method_not_matched_by_simple_module_qualifier(
    sample_project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with (
        patch.object(
            sys,
            "argv",
            ["cf", "locate", "pkg_a.service.run", str(sample_project)],
        ),
        pytest.raises(SystemExit) as exc_info_loc,
    ):
        main()

    assert exc_info_loc.value.code == 1
    locate_out = capsys.readouterr().out
    assert "Status: NOT_FOUND" in locate_out
    assert "not found" in locate_out

    with (
        patch.object(
            sys,
            "argv",
            ["cf", "memory", "symbol", "pkg_a.service.run", str(sample_project)],
        ),
        pytest.raises(SystemExit) as exc_info_mem,
    ):
        main()

    assert exc_info_mem.value.code == 1
    mem_out = capsys.readouterr().out
    assert "Matches: 0" in mem_out
    assert "No matching symbol found." in mem_out

    with (
        patch.object(
            sys,
            "argv",
            ["cf", "impact", "pkg_a.service.run", str(sample_project)],
        ),
        pytest.raises(SystemExit) as exc_info_imp,
    ):
        main()

    assert exc_info_imp.value.code == 1
    imp_out = capsys.readouterr().out
    assert "Status: Target not found." in imp_out


def test_module_path_resolution_with_nested_src_directory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "repo_nested_src"
    root.mkdir()
    nested = root / "tools" / "src"
    nested.mkdir(parents=True)
    (root / "tools" / "__init__.py").write_text("", encoding="utf-8")
    (nested / "__init__.py").write_text("", encoding="utf-8")
    (nested / "helpers.py").write_text(
        "def compute_hash(val: str) -> str:\n    return val.strip()\n",
        encoding="utf-8",
    )

    with patch.object(sys, "argv", ["cf", "analyze", str(root)]):
        main()
    capsys.readouterr()

    with patch.object(
        sys,
        "argv",
        ["cf", "locate", "tools.src.helpers.compute_hash", str(root)],
    ):
        main()

    locate_out = capsys.readouterr().out
    assert "Status: RESOLVED" in locate_out
    assert "tools/src/helpers.py" in locate_out

    with patch.object(
        sys,
        "argv",
        ["cf", "memory", "symbol", "tools.src.helpers.compute_hash", str(root)],
    ):
        main()

    mem_out = capsys.readouterr().out
    assert "Matches: 1" in mem_out
    assert "Path: tools/src/helpers.py" in mem_out

    with patch.object(
        sys,
        "argv",
        ["cf", "impact", "tools.src.helpers.compute_hash", str(root)],
    ):
        main()

    imp_out = capsys.readouterr().out
    assert "compute_hash" in imp_out
    assert "tools/src/helpers.py" in imp_out

    with (
        patch.object(
            sys,
            "argv",
            ["cf", "locate", "src.helpers.compute_hash", str(root)],
        ),
        pytest.raises(SystemExit) as exc_loc,
    ):
        main()
    assert exc_loc.value.code == 1

    with (
        patch.object(
            sys,
            "argv",
            ["cf", "memory", "symbol", "src.helpers.compute_hash", str(root)],
        ),
        pytest.raises(SystemExit) as exc_mem,
    ):
        main()
    assert exc_mem.value.code == 1

    with (
        patch.object(
            sys,
            "argv",
            ["cf", "impact", "src.helpers.compute_hash", str(root)],
        ),
        pytest.raises(SystemExit) as exc_imp,
    ):
        main()
    assert exc_imp.value.code == 1


def test_module_path_resolution_with_src_layout_and_nested_class(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "repo_src_layout"
    root.mkdir()
    src_pkg = root / "src" / "pkg_src"
    src_pkg.mkdir(parents=True)
    (src_pkg / "__init__.py").write_text("", encoding="utf-8")
    (src_pkg / "service.py").write_text(
        "class Outer:\n"
        "    class Inner:\n"
        "        def execute(self) -> None:\n"
        "            pass\n",
        encoding="utf-8",
    )

    with patch.object(sys, "argv", ["cf", "analyze", str(root)]):
        main()
    capsys.readouterr()

    with patch.object(
        sys,
        "argv",
        ["cf", "locate", "pkg_src.service.Outer.Inner.execute", str(root)],
    ):
        main()
    assert "Status: RESOLVED" in capsys.readouterr().out

    with patch.object(
        sys,
        "argv",
        ["cf", "memory", "symbol", "pkg_src.service.Outer.Inner.execute", str(root)],
    ):
        main()
    assert "Matches: 1" in capsys.readouterr().out

    with patch.object(
        sys,
        "argv",
        ["cf", "impact", "pkg_src.service.Outer.Inner.execute", str(root)],
    ):
        main()
    assert (
        "Resolved target: [method] execute (Outer.Inner.execute)"
        in capsys.readouterr().out
    )

    for incomplete in ["pkg_src.service.execute", "pkg_src.service.Inner.execute"]:
        with (
            patch.object(sys, "argv", ["cf", "locate", incomplete, str(root)]),
            pytest.raises(SystemExit) as exc_l,
        ):
            main()
        assert exc_l.value.code == 1

        with (
            patch.object(
                sys, "argv", ["cf", "memory", "symbol", incomplete, str(root)]
            ),
            pytest.raises(SystemExit) as exc_m,
        ):
            main()
        assert exc_m.value.code == 1

        with (
            patch.object(sys, "argv", ["cf", "impact", incomplete, str(root)]),
            pytest.raises(SystemExit) as exc_i,
        ):
            main()
        assert exc_i.value.code == 1


def test_memory_references_missing_symbol_exits_1(
    sample_project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with (
        patch.object(
            sys,
            "argv",
            ["cf", "memory", "references", "nonexistent_sym", str(sample_project)],
        ),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 1
    assert "No matching symbol found." in capsys.readouterr().out


def test_memory_references_ambiguous_symbol_exits_1(
    sample_project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with (
        patch.object(
            sys,
            "argv",
            ["cf", "memory", "references", "Config", str(sample_project)],
        ),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 1
    assert "Multiple definitions found:" in capsys.readouterr().out


def test_memory_references_resolves_and_finds_incoming_reference(
    sample_project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with patch.object(
        sys,
        "argv",
        [
            "cf",
            "memory",
            "references",
            "process_data",
            str(sample_project),
            "--format",
            "json",
        ],
    ):
        main()

    data = json.loads(capsys.readouterr().out)
    assert data["status"] == "ok"
    assert len(data["matches"]) == 1
    assert len(data["references"]) >= 1
    ref_paths = [r["path"] for r in data["references"]]
    assert "pkg_b/pipeline.py" in ref_paths


def test_memory_references_valid_zero_references_exits_0(
    sample_project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with patch.object(
        sys,
        "argv",
        ["cf", "memory", "references", "standalone", str(sample_project)],
    ):
        main()

    captured = capsys.readouterr()
    assert "Matches: 1" in captured.out
    assert "References: 0" in captured.out
    assert "No indexed references found." in captured.out
