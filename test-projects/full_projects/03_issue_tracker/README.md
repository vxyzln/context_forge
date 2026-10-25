# Full Project 03 — Issue Tracker

A complete issue tracking application implementing bug reporting, triage workflows, assignments, state machine validation, notification queuing, and architectural boundary enforcement.

## Purpose

Validate Context Forge's architectural policy enforcement and state-machine dependency modeling:
- Multi-package architecture: `domain`, `services`, `repositories`, `notifications`, `reporting`.
- Status transition state machine validation (`ALLOWED_TRANSITIONS`).
- Immutable event audit trail logging (`IssueEvent`).
- **Deliberate Architectural Boundary Violation**: `issues/notifications` is prohibited from depending on `issues/reporting` via `.contextforge.toml`, but `dispatcher.py` imports `IssueMetricsReporter`.
- Verification that Context Forge detects and reports the violation with exact package paths.

## Structure

```text
03_issue_tracker/
├── README.md
├── pyproject.toml
├── docs/
│   └── architecture.md
├── src/
│   ├── .contextforge.toml         # Policy prohibiting notifications -> reporting
│   └── issues/
│       ├── __init__.py
│       ├── application.py         # Application facade and sample bootstrap
│       ├── domain/                # Enums, Issue, and IssueEvent entities
│       ├── notifications/         # Notification queuing (contains intentional violation)
│       ├── reporting/             # Metrics aggregation
│       ├── repositories/          # In-memory issue and event store
│       └── services/              # Status transition validation & issue lifecycle
├── tests/
│   └── test_tracker.py            # Workflow unit test suite
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
context-forge analyze test-projects/full_projects/03_issue_tracker/src

# 2. Evaluate package boundary policy (detects intentional violation)
context-forge package-boundaries test-projects/full_projects/03_issue_tracker/src --format json

# 3. Analyze changeset on Issue entity
context-forge changeset issues/domain/issue.py -p test-projects/full_projects/03_issue_tracker/src --format json
```

## Controlled Change Scenarios

1. **Fix Architectural Violation**: Remove the `IssueMetricsReporter` import from `notifications/dispatcher.py`. Rerunning `package-boundaries` produces 0 violations.
2. **Add Workflow State**: Add `IssueStatus.VERIFIED` to `domain/enums.py` and `ALLOWED_TRANSITIONS` in `services/issue_service.py`.
3. **Add Notification Channel**: Add webhook routing to `notifications/dispatcher.py`.

## Manifest Verification

```bash
python test-projects/scripts/verify_manifest.py test-projects/full_projects/03_issue_tracker
```
