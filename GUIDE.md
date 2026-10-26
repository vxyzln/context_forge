# GUIDE

This document helps you get started with Context Forge.

## PREREQUISITES

- Python 3.13 or newer
- A Python repository you want to analyze
- `uv` is recommended for installing the tool, but `pip` is also supported

## INSTALLATION

**Recommended — uv**

```bash
uv tool install context-forge-local
```

**Alternative — pip**

```bash
python -m pip install context-forge-local
```

Check that the installation works:

```bash
cf --help
```

**Note:** You can also use `context-forge` instead of `cf`.

## FIRST REPOSITORY ANALYSIS

### Step 1: Open Your Project Directory

Move to the root of the Python repository you want to analyze.

### Step 2: Analyze the Repository

```bash
cf analyze
```

To analyze a specific directory, use its path:

```bash
cf analyze /path/to/your-project
```

For JSON or machine-readable output:

```bash
cf analyze . --format json
```

After the analysis finishes, check its status:

```bash
cf status
cf cache
```

These commands show the analysis status and whether the saved information is up to date.

## EXPLORE YOUR CODEBASE

Use these commands to find and understand different parts of your project:

```bash
cf locate MyClass
cf memory search "MyClass"
cf memory file src/example.py
cf memory symbol MyClass
cf memory references MyClass
cf memory relationships MyClass
cf memory dependencies src/example.py
```

Replace the example names and paths with those from your repository.

## UNDERSTAND YOUR PROJECT

```bash
cf architecture
cf package-boundaries
cf path --help
cf health
```

These commands help you inspect the architecture, package boundaries, relationships, and overall health of the repository.

## BEFORE AND AFTER MAKING CHANGES

Before changing a file or symbol, inspect it and check what may be affected:

```bash
cf inspect-change MyClass
cf impact MyClass
cf risk --help
```

After making changes, review the affected files and run post-change verification:

```bash
cf changeset --help
cf post-change
```

You can also specify changed files:

```bash
cf post-change src/example.py
```

Review the reports and run your project's tests separately.

## REFRESH THE REPOSITORY INFORMATION

Context Forge can automatically refresh stale analysis when supported commands need it.

To refresh manually:

```bash
cf refresh
```

To check freshness without refreshing:

```bash
cf cache
```

Some commands support `--no-refresh` to prevent automatic refreshing.

## USEFUL COMMANDS

```bash
cf preflight
cf locate --help
cf diagnostics
cf unused
cf --help
```

Use command-specific help whenever you need to check the exact arguments or options:

```bash
cf COMMAND --help
```

Replace `COMMAND` with the command you want to use.

## DOCUMENTATION AND LICENSE

- `README.md` — project overview and getting started.
- `GUIDE.md` — practical usage workflows.
- `CLI_COMMANDS.md` — detailed command reference.
- `AI_USAGE.md` — notes on AI-assisted development.
- `STORY.md` — the development journey.
- `TECH_STACK.md` — technologies and tools used.
- `WORKFLOW.md` — development workflow.
- `LICENSE` — MIT License.

## PRACTICAL WORKFLOW

1. Install Context Forge.
2. Open your Python repository and run `cf analyze`.
3. Check `cf status` and `cf cache`.
4. Explore files, symbols, and relationships.
5. Inspect impact before making important changes.
6. Run `cf post-change` and your project's tests after making changes.

