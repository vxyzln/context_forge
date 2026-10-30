from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def run_command(cmd: list[str], cwd: Path | None = None) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            check=False,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except FileNotFoundError as err:
        return 127, "", f"Command not found: {cmd[0]} ({err})"


def verify_manifest(
    project_dir: Path,
    cli_prefix: list[str],
    verbose: bool = False,
) -> bool:
    manifest_path = project_dir / "expected" / "manifest.json"
    if not manifest_path.exists():
        print(f"Error: Manifest not found at {manifest_path}", file=sys.stderr)
        return False

    with manifest_path.open("r", encoding="utf-8") as f:
        manifest = json.load(f)

    project_id = manifest.get("project_id", project_dir.name)
    target_rel = manifest.get("target_directory", "src")
    target_path = (project_dir / target_rel).resolve()

    if not target_path.exists():
        print(
            f"Error: Target directory does not exist: {target_path}",
            file=sys.stderr,
        )
        return False

    print(f"=== Verifying [{project_id}] at {target_path} ===")

    analyze_cmd = cli_prefix + ["analyze", str(target_path)]
    if verbose:
        print(f"Running: {' '.join(analyze_cmd)}")
    code, stdout, stderr = run_command(analyze_cmd)
    if code != 0:
        print(f"FAIL: analyze command exited with {code}\n{stderr}", file=sys.stderr)
        return False

    status_cmd = cli_prefix + ["status", str(target_path), "--format", "json"]
    if verbose:
        print(f"Running: {' '.join(status_cmd)}")
    code, stdout, stderr = run_command(status_cmd)
    if code != 0:
        print(f"FAIL: status command exited with {code}\n{stderr}", file=sys.stderr)
        return False

    try:
        status_data = json.loads(stdout)
    except json.JSONDecodeError as err:
        print(
            f"FAIL: Could not decode status JSON: {err}\nOutput was: {stdout}",
            file=sys.stderr,
        )
        return False

    expected = manifest.get("expected", {})
    failures: list[str] = []

    if "file_count" in expected:
        actual_files = status_data.get("files", 0)
        if actual_files != expected["file_count"]:
            failures.append(
                f"files count mismatch: expected {expected['file_count']}, got {actual_files}"
            )

    if "symbol_count" in expected:
        actual_symbols = status_data.get("symbols", 0)
        if actual_symbols != expected["symbol_count"]:
            failures.append(
                f"symbols count mismatch: expected {expected['symbol_count']}, got {actual_symbols}"
            )

    if "relationship_count" in expected:
        actual_rels = status_data.get("relationships", 0)
        if actual_rels != expected["relationship_count"]:
            failures.append(
                f"relationships count mismatch: expected {expected['relationship_count']}, got {actual_rels}"
            )

    if "analysis_errors" in expected:
        actual_errors = status_data.get("analysis_errors", 0)
        if actual_errors != expected["analysis_errors"]:
            failures.append(
                f"analysis_errors mismatch: expected {expected['analysis_errors']}, got {actual_errors}"
            )

    inspect_cmd = cli_prefix + ["inspect", str(target_path), "--format", "json"]
    if verbose:
        print(f"Running: {' '.join(inspect_cmd)}")
    code, stdout, stderr = run_command(inspect_cmd)
    if code == 0:
        try:
            inspect_data = json.loads(stdout)
            discovered_files = {
                f["path"].replace("\\", "/") for f in inspect_data.get("files", [])
            }
            discovered_symbols = {
                (s["name"], s.get("kind")) for s in inspect_data.get("symbols", [])
            }

            for expected_file in expected.get("source_files", []):
                norm_file = expected_file.replace("\\", "/")
                if norm_file not in discovered_files:
                    failures.append(f"missing expected source file: {norm_file}")

            for sym in expected.get("symbols", []):
                sym_tuple = (sym["name"], sym.get("kind"))
                if sym_tuple not in discovered_symbols:
                    failures.append(
                        f"missing expected symbol: {sym['name']} (kind: {sym.get('kind')})"
                    )
        except json.JSONDecodeError as err:
            failures.append(f"could not decode inspect JSON: {err}")
    else:
        failures.append(f"inspect command exited with {code}: {stderr}")

    extra_commands = manifest.get("extra_checks", [])
    for extra in extra_commands:
        extra_args = extra.get("command", [])
        resolved_args = [
            str(target_path)
            if arg == "{target}"
            else str(project_dir)
            if arg == "{project}"
            else arg
            for arg in extra_args
        ]
        cmd = cli_prefix + resolved_args
        if verbose:
            print(f"Running extra check: {' '.join(cmd)}")
        c_code, c_out, _c_err = run_command(cmd)
        expected_code = extra.get("expected_exit_code", 0)
        if c_code != expected_code:
            failures.append(
                f"extra command {' '.join(resolved_args)} exited with {c_code}, expected {expected_code}"
            )
            continue

        if "expected_json_subset" in extra and c_out.strip():
            try:
                actual_json = json.loads(c_out)
                subset = extra["expected_json_subset"]
                for k, v in subset.items():
                    act_v = actual_json.get(k)
                    if act_v != v:
                        failures.append(
                            f"extra command {resolved_args[0]} JSON key '{k}' mismatch: expected {v}, got {act_v}"
                        )
            except json.JSONDecodeError as err:
                failures.append(
                    f"extra command {resolved_args[0]} output not JSON: {err}"
                )

    if failures:
        print(f"FAIL: {len(failures)} assertion(s) failed for [{project_id}]:")
        for fail in failures:
            print(f"  - {fail}")
        return False

    print(f"PASS: All assertions verified for [{project_id}]")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify Context Forge test project manifests"
    )
    parser.add_argument(
        "project_dir",
        type=Path,
        help="Path to project directory containing expected/manifest.json",
    )
    parser.add_argument(
        "--cli",
        default="context-forge",
        help="Command or prefix to execute context-forge (e.g. 'context-forge' or 'uv run context-forge')",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose logging"
    )
    args = parser.parse_args()

    cli_prefix = args.cli.split()
    success = verify_manifest(args.project_dir, cli_prefix, verbose=args.verbose)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
