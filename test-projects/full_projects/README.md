# Context Forge Full Real-World Test Projects

A public, reproducible collection of four complete, realistic Python applications under `test-projects/full_projects/` designed to evaluate Context Forge repository intelligence against complete codebases.

## Role & Comparison with Part 1

While Part 1 (`test-projects/projects/`) isolates individual features (such as syntax error resilience, boundary checks, or git changes), Part 2 provides **complete, cohesive software architectures** where multiple behaviors interact naturally:
- Coherent domain modeling and realistic business rules.
- 15 to 20 Python modules per project with clear architectural layers.
- Full standard-library test suites verifying functional behavior.
- Clean offline operation without remote services, databases, or container dependencies.
- Reproducible expected manifests verified via `test-projects/scripts/verify_manifest.py`.

## The Four Full Projects

| Project Directory | Domain / Architecture | Key Validation Capabilities |
|---|---|---|
| [`01_task_management`](file:///Users/dakshjain/Vault/Projects/cff/test-projects/full_projects/01_task_management/README.md) | Layered Task & Workflow System | Multi-entity domain modeling (`User`, `Project`, `Task`), state machines, validation rules, repositories, and analytics reporting. |
| [`02_inventory_management`](file:///Users/dakshjain/Vault/Projects/cff/test-projects/full_projects/02_inventory_management/README.md) | Event-Driven Inventory Control | Stock movements, intake/withdrawal operations, reorder policies, valuation reporting, and dependency chains. |
| [`03_issue_tracker`](file:///Users/dakshjain/Vault/Projects/cff/test-projects/full_projects/03_issue_tracker/README.md) | Issue Tracking & Architectural Governance | Workflow transitions, immutable event logging, notification queues, and a **deliberate architectural boundary violation** enforced via `.contextforge.toml`. |
| [`04_data_pipeline`](file:///Users/dakshjain/Vault/Projects/cff/test-projects/full_projects/04_data_pipeline/README.md) | Staged Data Processing Pipeline | Multi-stage pipeline (`readers` -> `transforms` / `validation` -> `aggregation` -> `reporting`), schema enforcement, and sample CSV data. |

## Running Application Tests

Each project contains an independent, standard-library unit test suite:

```bash
# 01_task_management
PYTHONPATH=test-projects/full_projects/01_task_management/src python3 -m unittest discover -s test-projects/full_projects/01_task_management/tests

# 02_inventory_management
PYTHONPATH=test-projects/full_projects/02_inventory_management/src python3 -m unittest discover -s test-projects/full_projects/02_inventory_management/tests

# 03_issue_tracker
PYTHONPATH=test-projects/full_projects/03_issue_tracker/src python3 -m unittest discover -s test-projects/full_projects/03_issue_tracker/tests

# 04_data_pipeline
PYTHONPATH=test-projects/full_projects/04_data_pipeline/src python3 -m unittest discover -s test-projects/full_projects/04_data_pipeline/tests
```

## Running Context Forge Against Full Projects

```bash
# Analyze any full project
context-forge analyze test-projects/full_projects/01_task_management/src

# Inspect status
context-forge status test-projects/full_projects/01_task_management/src --format json

# Evaluate architectural boundaries (demonstrated in 03_issue_tracker)
context-forge package-boundaries test-projects/full_projects/03_issue_tracker/src --format json
```

## Verifying Expected Manifests

```bash
# Verify all four full projects in sequence
for proj in test-projects/full_projects/*/; do
    python3 test-projects/scripts/verify_manifest.py "$proj"
done
```

## Cross-Platform Validation Procedure (macOS, Windows, Linux)

1. Clone the repository on the target operating system.
2. Ensure Python 3.11+ is installed.
3. Run the application test discovery command (`python -m unittest discover`).
4. Run the manifest verifier against all four projects.
5. All paths in manifests and source code use normalized relative notation with forward slashes (`/`) and `pathlib.Path`, guaranteeing portability across Windows, Linux, and macOS.
