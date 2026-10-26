# All CLI Commands — Usage Explained

Context Forge (`context-forge` or `cf`) is a deterministic repository intelligence and persistent memory engine for Python codebases. It indexes repository structure, symbols, imports, calls, containment, and references into a local SQLite database (`.context_forge.db`), enabling structural inspection, task-focused context packaging, dependency tracking, impact assessment, and change verification.

This document is a comprehensive, complete reference for every command and subcommand available in the Context Forge CLI. It describes the syntax, arguments, options, defaults, output behavior, side effects, and error handling of the current implementation.

To inspect the commands supported by your installed version at any time, run:

```bash
cf --help
```

---

## Table of Contents

1. [Before Using the CLI](#before-using-the-cli)
2. [General Command Syntax](#general-command-syntax)
3. [Global Options and Common Behavior](#global-options-and-common-behavior)
4. [Repository Analysis & Cache Commands](#repository-analysis--cache-commands)
   - [`cf analyze`](#cf-analyze)
   - [`cf refresh`](#cf-refresh)
   - [`cf status`](#cf-status)
   - [`cf cache`](#cf-cache)
   - [`cf preflight`](#cf-preflight)
5. [Context Retrieval & Memory Commands](#context-retrieval--memory-commands)
   - [`cf context`](#cf-context)
   - [`cf inspect`](#cf-inspect)
   - [`cf locate`](#cf-locate)
   - [`cf memory inspect`](#cf-memory-inspect)
   - [`cf memory search`](#cf-memory-search)
   - [`cf memory file`](#cf-memory-file)
   - [`cf memory symbol`](#cf-memory-symbol)
   - [`cf memory references`](#cf-memory-references)
   - [`cf memory relationships`](#cf-memory-relationships)
   - [`cf memory dependencies`](#cf-memory-dependencies)
6. [Architecture & Relationship Commands](#architecture--relationship-commands)
   - [`cf architecture`](#cf-architecture)
   - [`cf path` (aliases: `query-path`)](#cf-path-aliases-query-path)
   - [`cf package-boundaries` (aliases: `package-boundary`, `boundaries`)](#cf-package-boundaries-aliases-package-boundary-boundaries)
   - [`cf health`](#cf-health)
7. [Change Analysis & Verification Commands](#change-analysis--verification-commands)
   - [`cf inspect-change` (aliases: `pre-change`)](#cf-inspect-change-aliases-pre-change)
   - [`cf impact`](#cf-impact)
   - [`cf changeset` (aliases: `change-set`)](#cf-changeset-aliases-change-set)
   - [`cf risk` (aliases: `change-risk`)](#cf-risk-aliases-change-risk)
   - [`cf rules` (aliases: `evaluate-rules`, `check-rules`)](#cf-rules-aliases-evaluate-rules-check-rules)
   - [`cf post-change` (aliases: `verify-change`, `post_change`, `verify`)](#cf-post-change-aliases-verify-change-post_change-verify)
8. [Diagnostics & Utility Commands](#diagnostics--utility-commands)
   - [`cf diagnostics`](#cf-diagnostics)
   - [`cf unused` (aliases: `unused-entities`, `find-unused`)](#cf-unused-aliases-unused-entities-find-unused)
   - [`cf logo`](#cf-logo)
9. [Common Errors and Troubleshooting](#common-errors-and-troubleshooting)
10. [Quick Command Lookup](#quick-command-lookup)

---

## Before Using the CLI

### Prerequisites

- **Python Runtime**: Python 3.13 or newer (specified in `pyproject.toml` as `>=3.13`).
- **Environment**: Context Forge can be executed directly as `cf` or `context-forge` when installed in your active virtual environment, or via `uv run cf` / `uv run context-forge`.

### Invocation Methods

Both executable entry points (`cf` and `context-forge`) are registered identically:

```bash
# Direct binary invocation (when venv is active or installed globally)
cf <command> [arguments...] [options...]
context-forge <command> [arguments...] [options...]

# Via uv runner
uv run cf <command> [arguments...] [options...]
uv run context-forge <command> [arguments...] [options...]
```

### Requesting Help

To view the top-level help and command category overview:

```bash
cf --help
# or
cf -h
```

To view command-specific arguments and options:

```bash
cf <command> --help
cf memory <subcommand> --help
```

> [!NOTE]
> Context Forge does not implement a dedicated `cf version` command or `--version` flag. Running `cf --version` will return an error code 2 (`unrecognized arguments`). Package versioning is tracked in `pyproject.toml` (`1.0`).

---

## General Command Syntax

Context Forge commands follow standard POSIX CLI conventions:

```bash
cf [GLOBAL_OPTIONS] <command> [<subcommand>] [ARGUMENTS...] [OPTIONS...]
```

- **Executable**: `cf` or `context-forge`.
- **Command**: The top-level action to perform (e.g., `analyze`, `status`, `memory`, `impact`).
- **Subcommand**: Required for compound commands such as `cf memory <subcommand>`.
- **Positional Arguments**: Mandatory or optional arguments identifying entities, symbols, queries, or repository paths.
- **Options and Flags**: Preceded by `--` (or short flag `-`), controlling formatting (`--format`), graph depth (`--depth`), result limits (`--limit`), or background freshness behavior (`--no-refresh`).
- **Bare Path Shortcut**: When invoked with a single bare path argument without a command name (e.g. `cf /path/to/project`), the CLI automatically defaults to `cf status /path/to/project`.

Placeholders throughout this reference are formatted in angle brackets (e.g., `<path>`, `<symbol_name>`, `<target>`). Replace them with actual project paths or identifier names.

---

## Global Options and Common Behavior

### Global Options

The root CLI parser provides two top-level options:

| Option | Type | Description |
|---|---|---|
| `-h`, `--help` | Flag | Displays the root help message showing all command categories and exits with code 0. |
| `--logo` | Flag | Displays the ASCII Context Forge logo and exits with code 0. Cannot be combined with a command. |

### Output Formatting (`--format`)

Most query and inspection commands accept the `--format` option:

- **Choices**: `text` (default), `json`
- **`text`**: Human-readable, structured multi-line report formatted for terminal viewing.
- **`json`**: Machine-readable, single-line serialized JSON object printed to stdout with sorted keys and minimal delimiters, suitable for piping to `jq` or agent consumers. When an error occurs and `--format json` was selected, failure details and diagnostic items are emitted as a structured JSON outcome payload to `stderr`.

### Automatic Freshness & Refresh Control (`--no-refresh`)

Context Forge tracks file modifications and source fingerprints. Many query and workflow commands automatically perform a background refresh of repository intelligence if the persisted SQLite database is stale relative to current source files on disk.

- **Default Behavior**: If repository files have changed since the last analysis, the command transparently refreshes stale modules before answering the query.
- **`--no-refresh` Flag**: Disables automatic background refreshing. If repository intelligence is stale or incomplete when `--no-refresh` is passed, the command aborts with a `StaleAnalysisError` or `IncompleteAnalysisError` rather than modifying the database.

### Exit Codes

- `0`: Successful execution.
- `1`: Operational failure, analysis error, validation error, unresolved target, missing analysis, or query exception.
- `2`: Command-line syntax error (invalid arguments, unrecognized options, missing required parameters).
- `130`: Process interrupted by SIGINT / KeyboardInterrupt (`Ctrl+C`).

---

## Repository Analysis & Cache Commands

### `cf analyze`

**What it does**  
Scans a Python repository, parses source files into Abstract Syntax Trees (ASTs), discovers symbols and relationships (containment, definitions, imports, calls, inheritance, references), and persists full repository intelligence and cache fingerprints into `.context_forge.db`.

**Syntax**
```bash
cf analyze [<path>] [--format {text,json}]
```

**Arguments**
- `<path>` *(optional, positional)*: Repository root directory to analyze. Defaults to the current working directory (`.`).

**Options and flags**
- `--format {text,json}`: Output format (`text` or `json`). Default: `text`.

**Examples**
```bash
# Analyze the current project directory
cf analyze

# Analyze an explicit directory
cf analyze /path/to/project

# Analyze and receive machine-readable summary
cf analyze /path/to/project --format json
```

**Output**  
- **Text output**:
  ```text
  Analyzed: /path/to/project
  Files: 20
  Symbols: 168
  Relationships: 364
  Status: analyzed
  ```
- **JSON output**:
  ```json
  {"analysis_errors":0,"analysis_status":"analyzed","files":20,"relationships":364,"repository":"/path/to/project","symbols":168}
  ```

**When to use it**  
Run this command when first setting up Context Forge on a project or when performing a clean, full index rebuild.

**Behavior and limitations**  
- **Database creation**: Creates or overwrites `<resolved-project-root>/.context_forge.db`.
- **Filesystem access**: Reads all non-ignored Python source files under the project root.
- **Ignored paths**: Automatically skips standard directories like `.git`, `.venv`, `venv`, `__pycache__`, `.pytest_cache`, and `.ruff_cache`.

**Errors and exit behavior**  
Exits with code 1 if `<path>` does not exist or is not a directory.

---

### `cf refresh`

**What it does**  
Re-analyzes the repository and updates persisted cached intelligence and fingerprints.

**Syntax**
```bash
cf refresh [<path>] [--format {text,json}]
```

**Arguments**
- `<path>` *(optional, positional)*: Repository root directory to refresh. Defaults to current directory (`.`).

**Options and flags**
- `--format {text,json}`: Output format (`text` or `json`). Default: `text`.

**Examples**
```bash
cf refresh
cf refresh src/ --format json
```

**Output**  
Prints the same analysis summary structure as `cf analyze`.

**When to use it**  
Use `cf refresh` after editing or pulling changes when you want to explicitly update the database before running queries.

---

### `cf status`

**What it does**  
Displays the current status of repository intelligence, including file counts, symbol counts, relationship counts, recorded analysis errors, and cache freshness.

**Syntax**
```bash
cf status [<path>] [--format {text,json}]
```

**Arguments**
- `<path>` *(optional, positional)*: Repository root directory to inspect. Defaults to current directory (`.`).

**Options and flags**
- `--format {text,json}`: Output format (`text` or `json`). Default: `text`.

**Examples**
```bash
cf status
cf status /path/to/project --format json
```

**Output**  
- **Text output**:
  ```text
  Repository: /path/to/project
  Project: src
  Analysis status: analyzed
  Project type: unknown
  Files: 20
  Symbols: 168
  Relationships: 364
  Analysis errors: 0

  Cache status: fresh
  ```
- **JSON output**:
  ```json
  {"analysis_errors":0,"analysis_status":"analyzed","cache_status":"fresh","files":20,"project":"src","project_type":"unknown","relationships":364,"repository":"/path/to/project","symbols":168}
  ```

**When to use it**  
Use `cf status` as a quick health and freshness check before initiating coding sessions or automated workflows.

---

### `cf cache`

**What it does**  
Reports detailed cache state and file freshness without running a re-analysis. Displays the number of tracked files and identifies files added, modified, or deleted since the last analysis.

**Syntax**
```bash
cf cache [<path>] [--format {text,json}]
```

**Arguments**
- `<path>` *(optional, positional)*: Repository root directory to check cache freshness for. Defaults to current directory (`.`).

**Options and flags**
- `--format {text,json}`: Output format (`text` or `json`). Default: `text`.

**Examples**
```bash
cf cache
cf cache /path/to/project --format json
```

**Output**  
- **Text output**:
  ```text
  Repository: /path/to/project
  Cache status: fresh
  Tracked files: 20
  Freshness reason: fresh
  Added paths: 0
  Modified paths: 0
  Deleted paths: 0
  ```
- **JSON output**:
  ```json
  {"added_paths":[],"cache_status":"fresh","deleted_paths":[],"freshness_reason":"fresh","modified_paths":[],"repository":"/path/to/project","tracked_files":20}
  ```

**When to use it**  
Use `cf cache` to determine if project source files have drifted from the indexed database without modifying any database records.

---

### `cf preflight`

**What it does**  
Performs a read-only environment, configuration, and repository readiness audit. Checks directory accessibility, Git repository detection, configuration file presence, inventory statistics, and database existence.

**Syntax**
```bash
cf preflight [<path>] [--format {text,json}]
```

**Arguments**
- `<path>` *(optional, positional)*: Repository root directory to audit. Defaults to current directory (`.`).

**Options and flags**
- `--format {text,json}`: Output format (`text` or `json`). Default: `text`.

**Examples**
```bash
cf preflight
cf preflight /path/to/project --format json
```

**Output**  
- **Text output**:
  ```text
  Repository: /path/to/project
  Readiness: READY

  Repository status:
    Exists: True
    Directory: True
    Accessible: True
    Git repository: True

  Configuration:
    Status: default
    Database path: .context_forge.db (default)
    Max context units: 20 (default)
    Project config: /path/to/project/.contextforge.toml (present: False)
    Global config: /Users/username/Library/Application Support/context-forge/config.toml (present: False)

  Inventory:
    Directories: 7
    Files: 20
    Source files: 20

  Languages:
    - Python: 20 file(s) (supported)

  Analysis readiness:
    Persisted database: .context_forge.db (found)
  ```

**When to use it**  
Run `cf preflight` before starting automated pipelines or onboarding a repository to verify that environment paths and configurations are valid.

**Behavior and limitations**  
Strictly read-only. Never creates or modifies `.context_forge.db`.

---

## Context Retrieval & Memory Commands

### `cf context`

**What it does**  
Generates a deterministic context package for AI coding agents or developers. Given a prompt or task description, it selects the most relevant source files, definitions, and relationships bounded by the configured budget (`analysis.max_context_units`).

**Syntax**
```bash
cf context [<path>] [--task <task>] [--output <output_path>] [--no-refresh]
```

**Arguments**
- `<path>` *(optional, positional)*: Repository root directory. Defaults to `.`.

**Options and flags**
- `--task <task>`: Development task description or prompt to guide relevance extraction.
- `--output <output_path>`: File path destination to write the synthesized JSON package. If omitted, outputs JSON to stdout.
- `--no-refresh`: Disables automatic background refresh if cache is stale.

**Examples**
```bash
# Print synthesized context JSON to stdout
cf context --task "Add cancel method to TaskService"

# Write context package to a file
cf context /path/to/project --task "Fix reorder threshold check" --output context.json
```

**Output**  
A JSON package containing matched units, full source contents, entity IDs, AST facts, relevance scores, and selection signals.

---

### `cf inspect`

**What it does**  
Inspects and dumps a complete inventory summary of persisted repository intelligence: all indexed files, all defined symbols (with line ranges), and all resolved relationships with entity UUIDs.

**Syntax**
```bash
cf inspect [<path>] [--format {text,json}]
```

**Arguments**
- `<path>` *(optional, positional)*: Repository root directory to inspect. Defaults to `.`.

**Options and flags**
- `--format {text,json}`: Output format (`text` or `json`). Default: `text`.

**Examples**
```bash
cf inspect
cf inspect /path/to/project --format json
```

**Output**  
Lists repository files, symbols with kinds and line numbers (`[class] User lines 5-9`), and relationship edges (`references: <source-uuid> -> <target-uuid>`).

---

### `cf locate`

**What it does**  
Locates repository symbols precisely by exact name, qualified name, file path, or symbol kind, with optional source evidence code excerpts.

**Syntax**
```bash
cf locate <symbol_name> [<path>] [--file <file_path>] [--type <symbol_type>] [--excerpt] [--max-lines <max_lines>] [--format {text,json}] [--no-refresh]
```

**Arguments**
- `<symbol_name>` *(required, positional)*: Exact or qualified symbol name to locate.
- `<path>` *(optional, positional)*: Repository root directory. Defaults to `.`.

**Options and flags**
- `--file <file_path>`: Filter matches by repository-relative file path.
- `--type <symbol_type>`: Filter matches by symbol kind (e.g., `class`, `function`, `method`, `variable`).
- `--excerpt`: Include bounded source code excerpt from the current source file.
- `--max-lines <max_lines>`: Maximum lines included in source excerpt. Default: `50`.
- `--format {text,json}`: Output format (`text` or `json`). Default: `text`.
- `--no-refresh`: Disable automatic background refresh when stale.

**Examples**
```bash
# Locate a symbol across the project
cf locate TaskManagementApp

# Disambiguate by type and include a 10-line source excerpt
cf locate TaskManagementApp --type class --excerpt --max-lines 10

# Filter by file
cf locate Task --file task_mgmt/models/task.py --excerpt
```

**Output**  
- If uniquely resolved: Displays file location, line range, and source excerpt.
- If ambiguous: Lists all matching candidates with their locations and kinds, prompting further disambiguation.

---

### `cf memory inspect`

**What it does**  
Inspects the persisted repository intelligence summary through the memory interface. Functionally identical to top-level `cf inspect`.

**Syntax**
```bash
cf memory inspect [<path>] [--format {text,json}]
```

---

### `cf memory search`

**What it does**  
Performs fuzzy and exact substring searches across indexed memory, querying file paths, directory paths, and symbol names.

**Syntax**
```bash
cf memory search <query> [<path>] [--format {text,json}] [--no-refresh]
```

**Arguments**
- `<query>` *(required, positional)*: Search query string.
- `<path>` *(optional, positional)*: Repository root directory. Defaults to `.`.

**Options and flags**
- `--format {text,json}`: Output format (`text` or `json`). Default: `text`.
- `--no-refresh`: Disable automatic background refresh when stale.

**Examples**
```bash
cf memory search "TaskService"
cf memory search "models" --format json
```

**Output**  
Returns ranked matches with entity type (`[symbol]`, `[file]`, `[directory]`), repository-relative path, relevance match score (e.g. `1.00`), and match reason (`Exact symbol name match`, `Qualified symbol name contains query`).

---

### `cf memory file`

**What it does**  
Retrieves an indexed file record and enumerates all symbols defined within that file, including line numbers and signatures.

**Syntax**
```bash
cf memory file <file_path> [<path>] [--format {text,json}] [--no-refresh]
```

**Arguments**
- `<file_path>` *(required, positional)*: Repository-relative path of the file to inspect.
- `<path>` *(optional, positional)*: Repository root directory. Defaults to `.`.

**Options and flags**
- `--format {text,json}`: Output format (`text` or `json`). Default: `text`.
- `--no-refresh`: Disable automatic background refresh when stale.

**Examples**
```bash
cf memory file task_mgmt/application.py
cf memory file inventory/domain/product.py --format json
```

---

### `cf memory symbol`

**What it does**  
Retrieves symbol definitions matching an exact symbol name with optional filtering and bounded source excerpt.

**Syntax**
```bash
cf memory symbol <symbol_name> [<path>] [--file <file_path>] [--type <symbol_type>] [--excerpt] [--max-lines <max_lines>] [--format {text,json}] [--no-refresh]
```

**Arguments & Options**  
Identical to `cf locate`. Supports `--file`, `--type`, `--excerpt`, and `--max-lines` (default: 50).

**Examples**
```bash
cf memory symbol TaskService --excerpt --max-lines 20
```

---

### `cf memory references`

**What it does**  
Finds and displays all indexed inbound references pointing to a given symbol.

**Syntax**
```bash
cf memory references <symbol_name> [<path>] [--format {text,json}] [--no-refresh]
```

**Arguments**
- `<symbol_name>` *(required, positional)*: Exact or qualified symbol name to locate inbound references for.
- `<path>` *(optional, positional)*: Repository root directory. Defaults to `.`.

**Options and flags**
- `--format {text,json}`: Output format (`text` or `json`). Default: `text`.
- `--no-refresh`: Disable automatic background refresh when stale.

**Examples**
```bash
cf memory references TaskManagementApp
cf memory references Product --format json
```

---

### `cf memory relationships`

**What it does**  
Inspects all indexed relationships connected to a specific file or symbol entity. Supports filtering by relationship direction and relationship kind.

**Syntax**
```bash
cf memory relationships <entity_name> [<path>] [--direction {both,incoming,outgoing}] [--type {defines,contains,imports,references,inherits}] [--format {text,json}] [--no-refresh]
```

**Arguments**
- `<entity_name>` *(required, positional)*: Repository-relative file path, symbol name, or qualified name.
- `<path>` *(optional, positional)*: Repository root directory. Defaults to `.`.

**Options and flags**
- `--direction {both,incoming,outgoing}`: Direction of relationships. Default: `both`.
- `--type {defines,contains,imports,references,inherits}`: Filter by relationship kind. Default: `None` (all types).
- `--format {text,json}`: Output format (`text` or `json`). Default: `text`.
- `--no-refresh`: Disable automatic background refresh when stale.

**Examples**
```bash
# View all incoming references to a file
cf memory relationships task_mgmt/models/task.py --direction incoming

# View only inheritance relationships for a class
cf memory relationships BaseRepository --type inherits
```

---

### `cf memory dependencies`

**What it does**  
Analyzes direct module dependencies (imports) and dependents (imported by) for an individual Python file.

**Syntax**
```bash
cf memory dependencies <file_path> [<path>] [--direction {both,dependencies,dependents}] [--format {text,json}] [--no-refresh]
```

**Arguments**
- `<file_path>` *(required, positional)*: Repository-relative path of the file to inspect.
- `<path>` *(optional, positional)*: Repository root directory. Defaults to `.`.

**Options and flags**
- `--direction {both,dependencies,dependents}`: Filter direct file dependencies. Default: `both`.
- `--format {text,json}`: Output format (`text` or `json`). Default: `text`.
- `--no-refresh`: Disable automatic background refresh when stale.

**Examples**
```bash
cf memory dependencies task_mgmt/application.py
cf memory dependencies pipeline/transforms/cleaner.py --direction dependencies --format json
```

---

## Architecture & Relationship Commands

### `cf architecture`

**What it does**  
Generates a comprehensive structural architecture report for the repository. Analyzes package structures, Python module dependency counts, resolved dependencies, dependency cycles, unresolved imports, and structural findings.

**Syntax**
```bash
cf architecture [<path>] [--limit <limit>] [--format {text,json}] [--no-refresh]
```

**Arguments**
- `<path>` *(optional, positional)*: Repository root directory. Defaults to `.`.

**Options and flags**
- `--limit <limit>`: Maximum items displayed per report section. Default: `50`.
- `--format {text,json}`: Output format (`text` or `json`). Default: `text`.
- `--no-refresh`: Disable automatic background refresh when stale.

**Examples**
```bash
cf architecture
cf architecture /path/to/project --limit 10
cf architecture --format json
```

**Output**  
Summarizes directory, file, symbol, and edge totals, inventories packages and modules, detects cyclic strongly connected components, lists unresolved imports, and highlights architectural findings.

---

### `cf path` (aliases: `query-path`)

**What it does**  
Finds and reports the shortest bounded relationship path between two entities (files, symbols, or UUIDs) in the repository graph using breadth-first search.

**Syntax**
```bash
cf path <start> <end> [--path <project_path>] [--direction {both,incoming,outgoing}] [--type {imports,references,inherits,calls,depends_on}] [--depth <max_depth>] [--max-expansions <max_expansions>] [--format {text,json}] [--no-refresh]
```

**Aliases**
- `cf query-path`

**Arguments**
- `<start>` *(required, positional)*: Starting entity as file path, symbol name, qualified name, or UUID.
- `<end>` *(required, positional)*: Destination entity as file path, symbol name, qualified name, or UUID.

**Options and flags**
- `--path, -p <project_path>`: Repository root directory. Default: `.`.
- `--direction {both,incoming,outgoing}`: Direction of relationship traversal. Default: `both`.
- `--type {imports,references,inherits,calls,depends_on}`: Filter traversed relationships by type. Default: `None` (all).
- `--depth, --max-depth <max_depth>`: Maximum graph traversal depth. Default: `5`.
- `--max-expansions <max_expansions>`: Maximum graph nodes expanded before terminating search. Default: `1000`.
- `--format {text,json}`: Output format (`text` or `json`). Default: `text`.
- `--no-refresh`: Disable automatic background refresh when stale.

**Examples**
```bash
# Find path between two files
cf path task_mgmt/application.py task_mgmt/models/enums.py

# Find path using alias with custom depth
cf query-path task_mgmt/application.py Task --depth 3
```

---

### `cf package-boundaries` (aliases: `package-boundary`, `boundaries`)

**What it does**  
Analyzes dependencies that cross package boundaries (defined by directories with `__init__.py`) and evaluates them against declarative boundary policies configured in `.contextforge.toml`.

**Syntax**
```bash
cf package-boundaries [<path>] [--limit <limit>] [--format {text,json}] [--no-refresh]
```

**Aliases**
- `cf package-boundary`
- `cf boundaries`

**Arguments**
- `<path>` *(optional, positional)*: Repository root directory. Defaults to `.`.

**Options and flags**
- `--limit <limit>`: Maximum cross-package violations or dependencies displayed. Default: `50`.
- `--format {text,json}`: Output format (`text` or `json`). Default: `text`.
- `--no-refresh`: Disable automatic background refresh when stale.

**Examples**
```bash
cf package-boundaries
cf boundaries src/ --format json
```

**Output**  
Reports all detected packages, cross-package dependency counts, recurring cross-package patterns, and flagged policy violations (e.g. when an unauthorized cross-package import violates a defined rule).

---

### `cf health`

**What it does**  
Audits repository structural health, inventory metrics, unresolved external imports, and dependency cycle violations.

**Syntax**
```bash
cf health [<path>] [--limit <limit>] [--format {text,json}]
```

**Arguments**
- `<path>` *(optional, positional)*: Repository root directory. Defaults to `.`.

**Options and flags**
- `--limit <limit>`: Maximum structural findings displayed per category. Default: `10`.
- `--format {text,json}`: Output format (`text` or `json`). Default: `text`.

**Examples**
```bash
cf health
cf health /path/to/project --limit 5 --format json
```

---

## Change Analysis & Verification Commands

### `cf inspect-change` (aliases: `pre-change`)

**What it does**  
Performs a comprehensive read-only pre-change inspection before modifying code. Composes preflight checks, target resolution, freshness checking, bounded source code excerpt extraction, structural impact analysis, and uncommitted Git status.

**Syntax**
```bash
cf inspect-change <target> [<path>] [--file <file_path>] [--type <symbol_type>] [--direction {both,incoming,outgoing}] [--depth <max_depth>] [--max-lines <max_lines>] [--no-git] [--format {text,json}]
```

**Aliases**
- `cf pre-change`

**Arguments**
- `<target>` *(required, positional)*: Target symbol name, qualified name, or file path to inspect before making changes.
- `<path>` *(optional, positional)*: Repository root directory. Defaults to `.`.

**Options and flags**
- `--file <file_path>`: Filter target symbol by repository-relative file path.
- `--type <symbol_type>`: Filter target symbol by kind (`class`, `function`, `method`).
- `--direction {both,incoming,outgoing}`: Direction of structural impact traversal. Default: `both`.
- `--depth, --max-depth <max_depth>`: Maximum traversal depth for impact discovery. Default: `3`.
- `--max-lines <max_lines>`: Maximum lines included in source evidence excerpt. Default: `50`.
- `--no-git`: Disable Git working tree and status inspection. Default: `False`.
- `--format {text,json}`: Output format (`text` or `json`). Default: `text`.

**Examples**
```bash
cf inspect-change TaskManagementApp --type class
cf pre-change task_mgmt/models/task.py --max-lines 20
```

---

### `cf impact`

**What it does**  
Performs graph reachability analysis to discover direct and transitive components impacted by changes to a file or symbol target.

**Syntax**
```bash
cf impact <target> [<path>] [--direction {both,incoming,outgoing}] [--type {imports,references,inherits,calls,depends_on}] [--depth <max_depth>] [--limit <limit>] [--format {text,json}] [--no-refresh]
```

**Arguments**
- `<target>` *(required, positional)*: Repository-relative file path, symbol name, or qualified name to analyze impact for.
- `<path>` *(optional, positional)*: Repository root directory. Defaults to `.`.

**Options and flags**
- `--direction {both,incoming,outgoing}`: Traversal direction (`incoming` finds dependents that rely on target; `outgoing` finds dependencies target relies on). Default: `both`.
- `--type {imports,references,inherits,calls,depends_on}`: Filter traversed relationships by kind. Default: `None`.
- `--depth, --max-depth <max_depth>`: Maximum graph traversal depth. Default: `3`.
- `--limit <limit>`: Maximum affected entities displayed in the report. Default: `50`.
- `--format {text,json}`: Output format (`text` or `json`). Default: `text`.
- `--no-refresh`: Disable automatic background refresh when stale.

**Examples**
```bash
cf impact task_mgmt/models/task.py
cf impact TaskService --direction incoming --depth 2
cf impact inventory/domain/product.py --format json
```

---

### `cf changeset` (aliases: `change-set`)

**What it does**  
Analyzes the combined impact for a set of multiple changed file paths together. Identifies direct and downstream impacted components, detects relevant test suites, and optionally generates verification checklists and change-risk assessments.

**Syntax**
```bash
cf changeset <paths...> [--path <project_path>] [--direction {both,incoming,outgoing}] [--type {imports,references,inherits,calls,depends_on}] [--depth <max_depth>] [--limit <limit>] [--checklist] [--risk] [--format {text,json}] [--no-refresh]
```

**Aliases**
- `cf change-set`

**Arguments**
- `<paths...>` *(required, positional, one or more)*: Space-separated changed file paths to analyze together.

**Options and flags**
- `--path, -p <project_path>`: Repository root directory containing changed files. Default: `.`.
- `--direction {both,incoming,outgoing}`: Impact traversal direction. Default: `both`.
- `--type {imports,references,inherits,calls,depends_on}`: Filter traversed relationships by kind. Default: `None`.
- `--depth, --max-depth <max_depth>`: Maximum traversal depth. Default: `3`.
- `--limit <limit>`: Maximum affected entities displayed. Default: `50`.
- `--checklist`: Include verification checklist with test recommendations. Default: `False`.
- `--risk`: Include evidence-based change risk report. Default: `False`.
- `--format {text,json}`: Output format (`text` or `json`). Default: `text`.
- `--no-refresh`: Disable automatic background refresh when stale.

**Examples**
```bash
cf changeset task_mgmt/models/task.py task_mgmt/services/task_service.py --checklist
cf change-set file1.py file2.py -p src/ --risk --format json
```

---

### `cf risk` (aliases: `change-risk`)

**What it does**  
Generates an evidence-based change-risk report for one or more changed files. Infers structural concerns (broad impact, unverified areas lacking tests, cross-package boundary crossings) backed by concrete graph evidence.

**Syntax**
```bash
cf risk <paths...> [--path <project_path>] [--direction {both,incoming,outgoing}] [--type {imports,references,inherits,calls,depends_on}] [--depth <max_depth>] [--limit <limit>] [--format {text,json}] [--no-refresh]
```

**Aliases**
- `cf change-risk`

**Arguments**
- `<paths...>` *(required, positional, one or more)*: Space-separated changed file paths to assess risk for.

**Options and flags**
- `--path, -p <project_path>`: Repository root directory. Default: `.`.
- `--direction {both,incoming,outgoing}`: Traversal direction. Default: `both`.
- `--type {imports,references,inherits,calls,depends_on}`: Traversal relationship filter. Default: `None`.
- `--depth, --max-depth <max_depth>`: Maximum graph traversal depth. Default: `3`.
- `--limit <limit>`: Maximum affected entities displayed in the report. Default: `50`.
- `--format {text,json}`: Output format (`text` or `json`). Default: `text`.
- `--no-refresh`: Disable automatic background refresh when stale.

**Examples**
```bash
cf risk task_mgmt/models/task.py -p test-projects/full_projects/01_task_management/src
cf change-risk inventory/domain/product.py inventory/policies/reorder.py
```

---

### `cf rules` (aliases: `evaluate-rules`, `check-rules`)

**What it does**  
Evaluates declarative structural regression rules configured in `.contextforge.toml` against the indexed repository architecture to detect prohibited dependencies or architectural violations.

**Syntax**
```bash
cf rules [<path>] [--limit <limit>] [--format {text,json}] [--no-refresh]
```

**Aliases**
- `cf evaluate-rules`
- `cf check-rules`

**Arguments**
- `<path>` *(optional, positional)*: Repository root directory. Defaults to `.`.

**Options and flags**
- `--limit <limit>`: Maximum rule evaluation results displayed. Default: `50`.
- `--format {text,json}`: Output format (`text` or `json`). Default: `text`.
- `--no-refresh`: Disable automatic background refresh when stale.

**Examples**
```bash
cf rules
cf check-rules /path/to/project --format json
```

---

### `cf post-change` (aliases: `verify-change`, `post_change`, `verify`)

**What it does**  
Runs consolidated post-change verification across structural changes, automated test associations, risk factors, package boundaries, and regression rules. Can compare against an optional baseline repository snapshot or check changed files.

**Syntax**
```bash
cf post-change [<paths...>] [--path <project_path>] [--before <before_state_path>] [--direction {both,incoming,outgoing}] [--depth <max_depth>] [--limit <limit>] [--format {text,json}] [--no-refresh]
```

**Aliases**
- `cf verify-change`
- `cf post_change`
- `cf verify`

**Arguments**
- `<paths...>` *(optional, positional)*: Changed file paths to verify. If omitted, automatically attempts to detect changed files via Git status.

**Options and flags**
- `--path, -p <project_path>`: Repository root directory to verify changes in. Default: `.`.
- `--before <before_state_path>`: Baseline repository directory or snapshot representing state prior to changes for structural diff comparison. Default: `None`.
- `--direction {both,incoming,outgoing}`: Traversal direction for impact analysis. Default: `both`.
- `--depth, --max-depth <max_depth>`: Maximum graph traversal depth. Default: `3`.
- `--limit <limit>`: Maximum verification items displayed per category. Default: `50`.
- `--format {text,json}`: Output format (`text` or `json`). Default: `text`.
- `--no-refresh`: Disable automatic background refresh when stale.

**Examples**
```bash
# Verify explicit changed file in a project
cf post-change task_mgmt/models/task.py -p test-projects/full_projects/01_task_management/src

# Verify using alias with a baseline comparison directory
cf verify-change src/models.py -p . --before /path/to/baseline_repo
```

---

## Diagnostics & Utility Commands

### `cf diagnostics`

**What it does**  
Displays parser, scanner, and pipeline diagnostic warnings or errors recorded during repository analysis.

**Syntax**
```bash
cf diagnostics [<path>] [--format {text,json}]
```

**Arguments**
- `<path>` *(optional, positional)*: Repository root directory to inspect. Defaults to `.`.

**Options and flags**
- `--format {text,json}`: Output format (`text` or `json`). Default: `text`.

**Examples**
```bash
cf diagnostics
cf diagnostics /path/to/project --format json
```

---

### `cf unused` (aliases: `unused-entities`, `find-unused`)

**What it does**  
Scans repository intelligence to identify candidate entities (classes, functions, methods, variables, constants, files) that have zero detected incoming references, calls, imports, or inheritance relationships. Also lists unassessable entities (such as `__init__.py` or dunder methods) with explanations.

**Syntax**
```bash
cf unused [<path>] [--kind <kind>] [--limit <limit>] [--format {text,json}] [--no-refresh]
```

**Aliases**
- `cf unused-entities`
- `cf find-unused`

**Arguments**
- `<path>` *(optional, positional)*: Repository root directory. Defaults to `.`.

**Options and flags**
- `--kind <kind>`: Filter candidates by entity kind.
  - **Choices**: `all`, `*`, `function`, `functions`, `method`, `methods`, `class`, `classes`, `variable`, `variables`, `file`, `files`, `symbol`, `symbols`. Default: `all`.
- `--limit <limit>`: Maximum unused candidates displayed per category. Default: `50`.
- `--format {text,json}`: Output format (`text` or `json`). Default: `text`.
- `--no-refresh`: Disable automatic background refresh when stale.

**Examples**
```bash
cf unused
cf unused --kind function --limit 10
cf find-unused /path/to/project --kind class --format json
```

**Limitations**  
Static AST analysis cannot detect dynamic reflection (`getattr`), framework-injected calls, or external consumer usage. Manual verification is always recommended before deleting unused candidates.

---

### `cf logo`

**What it does**  
Prints the Context Forge ASCII art banner and exits.

**Syntax**
```bash
cf logo
# or
cf --logo
```

---

## Common Errors and Troubleshooting

### 1. `MissingAnalysisError: No persisted analysis found; run 'context-forge analyze' first`
- **Cause**: The command requires an analyzed repository database (`.context_forge.db`), but no analysis has been run for this project root yet.
- **Remedy**: Run `cf analyze <path>` to build the initial database index.

### 2. `StaleAnalysisError: Repository analysis is stale; run 'context-forge analyze <path>' first`
- **Cause**: The project's source files were modified on disk after analysis, and the query was run with `--no-refresh`.
- **Remedy**: Re-run the query without `--no-refresh`, or run `cf refresh <path>` explicitly.

### 3. `ValueError: Project path does not exist: <resolved-path>`
- **Cause**: The path supplied to the CLI does not point to an existing filesystem location.
- **Remedy**: Check the path spelling or pass an existing directory path.

### 4. `Status: AMBIGUOUS: Multiple symbols match '<name>'`
- **Cause**: A symbol name query in `cf locate`, `cf memory symbol`, or `cf inspect-change` matched multiple definitions (e.g. both a class definition and an import statement).
- **Remedy**: Disambiguate by supplying `--type <kind>` (e.g. `--type class`), `--file <file_path>`, or a qualified name.

### 5. `Unrecognized arguments: --version` (Exit Code 2)
- **Cause**: `--version` is not a registered CLI argument.
- **Remedy**: View installed package versioning in `pyproject.toml` or inspect available commands using `cf --help`.

---

## Quick Command Lookup

| Command | Aliases | Description |
|---|---|---|
| [`cf analyze`](#cf-analyze) | — | Analyze a repository and persist repository intelligence into `.context_forge.db`. |
| [`cf refresh`](#cf-refresh) | — | Refresh repository analysis and cached intelligence. |
| [`cf status`](#cf-status) | — | Show repository file, symbol, relationship counts, and cache freshness. |
| [`cf cache`](#cf-cache) | — | Show repository cache state, tracked file count, and file modification details. |
| [`cf preflight`](#cf-preflight) | — | Perform a read-only environment, Git, and configuration readiness audit. |
| [`cf context`](#cf-context) | — | Retrieve deterministic, budgeted context package JSON for a task. |
| [`cf inspect`](#cf-inspect) | — | Inspect complete persisted repository intelligence inventory. |
| [`cf locate`](#cf-locate) | — | Locate repository symbols precisely with optional source code excerpts. |
| [`cf memory inspect`](#cf-memory-inspect) | — | Inspect persisted repository intelligence summary via memory interface. |
| [`cf memory search`](#cf-memory-search) | — | Search persisted repository memory for files, directories, and symbols. |
| [`cf memory file`](#cf-memory-file) | — | Retrieve a file record and all symbols defined in it. |
| [`cf memory symbol`](#cf-memory-symbol) | — | Retrieve symbol definitions by exact name with optional excerpts. |
| [`cf memory references`](#cf-memory-references) | — | Show indexed inbound references to a symbol. |
| [`cf memory relationships`](#cf-memory-relationships) | — | Inspect indexed relationships for a file or symbol with direction and type filters. |
| [`cf memory dependencies`](#cf-memory-dependencies) | — | Show direct dependencies (imports) and dependents (imported by) for a file. |
| [`cf architecture`](#cf-architecture) | — | Report repository architecture, package modules, cycles, and unresolved imports. |
| [`cf path`](#cf-path-aliases-query-path) | `query-path` | Find bounded relationship path between start and end entities in the graph. |
| [`cf package-boundaries`](#cf-package-boundaries-aliases-package-boundary-boundaries) | `package-boundary`, `boundaries` | Analyze dependencies crossing package boundaries and evaluate policies. |
| [`cf health`](#cf-health) | — | Report repository health, inventory metrics, and structural findings. |
| [`cf inspect-change`](#cf-inspect-change-aliases-pre-change) | `pre-change` | Perform comprehensive read-only pre-change inspection with source and Git context. |
| [`cf impact`](#cf-impact) | — | Analyze direct and transitive change impact for a file or symbol. |
| [`cf changeset`](#cf-changeset-aliases-change-set) | `change-set` | Analyze combined impact and test associations for a set of changed paths. |
| [`cf risk`](#cf-risk-aliases-change-risk) | `change-risk` | Generate evidence-based change-risk report for changed paths. |
| [`cf rules`](#cf-rules-aliases-evaluate-rules-check-rules) | `evaluate-rules`, `check-rules` | Evaluate declarative structural regression rules against architecture. |
| [`cf post-change`](#cf-post-change-aliases-verify-change-post_change-verify) | `verify-change`, `post_change`, `verify` | Run consolidated post-change verification across changes, tests, risk, and rules. |
| [`cf diagnostics`](#cf-diagnostics) | — | Show persisted repository analysis diagnostic warnings and errors. |
| [`cf unused`](#cf-unused-aliases-unused-entities-find-unused) | `unused-entities`, `find-unused` | Identify candidate entities with no incoming references or usage evidence. |
| [`cf logo`](#cf-logo) | — | Display Context Forge ASCII logo and exit. |
