# Manifest Verification Utility

`verify_manifest.py` is a lightweight, offline verification utility that executes Context Forge commands against test project fixtures and validates the resulting JSON output against expected facts declared in `expected/manifest.json`.

## Requirements

- Python 3.11+ (Standard Library only)
- `context-forge` executable available in `PATH` or virtual environment (or provided via `--cli`)

## Usage

```bash
# Basic invocation
python verify_manifest.py <path-to-project>

# Example
python test-projects/scripts/verify_manifest.py test-projects/projects/01_basic_python

# Specify custom context-forge executable path
python test-projects/scripts/verify_manifest.py test-projects/projects/01_basic_python --cli uv run context-forge

# Verbose output
python test-projects/scripts/verify_manifest.py test-projects/projects/01_basic_python -v
```

## How It Works

1. Locates `expected/manifest.json` inside the specified project directory.
2. Identifies the project target source directory (defaults to `<project_dir>/src`).
3. Executes `context-forge analyze <target>` to generate the repository database.
4. Executes `context-forge status <target> --format json` and asserts:
   - File counts
   - Symbol counts
   - Relationship counts
   - Error counts
5. Executes `context-forge inspect <target> --format json` and verifies:
   - Expected files exist in inventory
   - Expected symbols and kinds are discovered
6. Executes any command-specific assertions declared in the manifest (e.g. `package-boundaries`, `memory symbol`).
7. Exits with return code `0` on total success or `1` on any assertion mismatch.
