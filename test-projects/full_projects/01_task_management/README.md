# Full Project 01 — Task Management

A complete layered task management application implementing project planning, task lifecycles, user assignments, validation rules, and analytics reporting.

## Purpose

Validate Context Forge repository intelligence on a realistic layered enterprise architecture:
- Layered separation of concerns: Models -> Repositories -> Services -> Reporting -> Application orchestration.
- Cross-package dependency resolution across 20 source modules.
- Verification of complex domain workflows: state transitions (`ALLOWED_TRANSITIONS`), assignee validation, and project metrics calculation.
- Clean dependency trees without circular imports or heavyweight external database dependencies.

## Structure

```text
01_task_management/
├── README.md
├── pyproject.toml
├── docs/
│   └── architecture.md
├── src/
│   └── task_mgmt/
│       ├── __init__.py
│       ├── application.py         # Top-level orchestrator
│       ├── models/                # Domain entities & Enums (User, Project, Task)
│       ├── repositories/          # Storage abstraction (Base, UserRepo, ProjectRepo, TaskRepo)
│       ├── services/              # Business logic (UserService, ProjectService, TaskService)
│       ├── validation/            # Reusable validation guards & exceptions
│       └── reporting/             # Analytical summary generation
├── tests/
│   └── test_tasks.py              # Full business workflow unit tests
└── expected/
    └── manifest.json
```

## Running the Application Tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
```

## Running Context Forge

```bash
# 1. Analyze the project
context-forge analyze test-projects/full_projects/01_task_management/src

# 2. Check analysis status
context-forge status test-projects/full_projects/01_task_management/src --format json

# 3. Inspect symbol references
context-forge memory symbol TaskService test-projects/full_projects/01_task_management/src --format json

# 4. Analyze changeset impact on Task model change
context-forge changeset task_mgmt/models/task.py -p test-projects/full_projects/01_task_management/src --format json
```

## Controlled Change Scenarios

1. **Add Field to Task Model**: Adding `estimated_hours: float = 0.0` to `Task` in `models/task.py`. Impacted files: `repositories/task_repo.py`, `services/task_service.py`, `application.py`.
2. **Modify Validation Rule**: Tightening `validate_not_empty` or adding deadline validation in `validation/rules.py`. Impacted files: `services/task_service.py`, `services/project_service.py`, `services/user_service.py`.
3. **Add Task Status**: Adding `TaskStatus.BLOCKED` to `models/enums.py` and `services/task_service.py`. Impacted files: `reporting/summary.py`, `services/task_service.py`.

## Manifest Verification

```bash
python test-projects/scripts/verify_manifest.py test-projects/full_projects/01_task_management
```
