# Context Forge Full Real-World Test Projects

A public, reproducible collection of four complete, realistic Python applications under `test-projects/full_projects/` designed to evaluate Context Forge repository intelligence against complete codebases.

## Structure

```text
test-projects/
├── README.md
├── LICENSE
├── full_projects/
│   ├── 01_task_management/          # Layered task & workflow system
│   ├── 02_inventory_management/     # Event-driven inventory control
│   ├── 03_issue_tracker/            # Issue tracking & architectural boundary governance
│   └── 04_data_pipeline/            # Staged data processing ETL pipeline
└── scripts/
    ├── README.md
    └── verify_manifest.py           # Standard-library offline manifest verifier
```

## The Four Full Projects

| Project Directory | Domain / Architecture | Key Validation Capabilities |
|---|---|---|
| [`01_task_management`](full_projects/01_task_management/README.md) | Layered Task & Workflow System | Multi-entity domain modeling (`User`, `Project`, `Task`), state machines, validation rules, repositories, and analytics reporting. |
| [`02_inventory_management`](full_projects/02_inventory_management/README.md) | Event-Driven Inventory Control | Stock movements, intake/withdrawal operations, reorder policies, valuation reporting, and dependency chains. |
| [`03_issue_tracker`](full_projects/03_issue_tracker/README.md) | Issue Tracking & Architectural Governance | Workflow transitions, immutable event logging, notification queues, and a **deliberate architectural boundary violation** enforced via `.contextforge.toml`. |
| [`04_data_pipeline`](full_projects/04_data_pipeline/README.md) | Staged Data Processing Pipeline | Multi-stage pipeline (`readers` -> `transforms` / `validation` -> `aggregation` -> `reporting`), schema enforcement, and sample CSV data. |

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

## Running Context Forge on a Fixture

Ensure `context-forge` (or `cf`) is installed or available via virtualenv:

```bash
# Analyze a fixture
context-forge analyze test-projects/full_projects/01_task_management/src

# Inspect status
context-forge status test-projects/full_projects/01_task_management/src --format json

# Search symbols
context-forge memory search TaskService test-projects/full_projects/01_task_management/src --format json
```

## Verifying Expected Manifests

Use the bundled standard-library verifier `scripts/verify_manifest.py`:

```bash
# Verify all four full projects in sequence
for proj in test-projects/full_projects/*/; do
    python3 test-projects/scripts/verify_manifest.py "$proj"
done
```

## Cross-Platform Validation Procedure (macOS, Windows, Linux)

1. **Clone the repository** on the target OS:
   ```bash
   git clone https://github.com/context-forge/context-forge.git
   cd context-forge
   ```
2. **Execute the verification script** across all projects:
   ```bash
   python3 test-projects/scripts/verify_manifest.py test-projects/full_projects/01_task_management
   python3 test-projects/scripts/verify_manifest.py test-projects/full_projects/02_inventory_management
   python3 test-projects/scripts/verify_manifest.py test-projects/full_projects/03_issue_tracker
   python3 test-projects/scripts/verify_manifest.py test-projects/full_projects/04_data_pipeline
   ```
3. All paths in manifests use forward slashes (`/`) and relative path notation, ensuring consistent behavior across Windows NTFS and POSIX filesystems.
