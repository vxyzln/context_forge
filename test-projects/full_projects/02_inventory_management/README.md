# Full Project 02 — Inventory Management

A complete inventory control application managing product catalogs, suppliers, stock receipts, order withdrawals, reorder thresholds, and valuation reporting.

## Purpose

Validate Context Forge dependency intelligence across shared calculation logic and state operations:
- Direct dependency chains: `reporting/reports.py` depends on `policies/reorder.py` and `storage/store.py`.
- Shared calculation modules (`policies/reorder.py`) consumed by operational and reporting pipelines.
- Event tracking and stock movement audits (`StockMovement`).
- Testing impact analysis when central reorder policies change.

## Structure

```text
02_inventory_management/
├── README.md
├── pyproject.toml
├── docs/
│   └── architecture.md
├── src/
│   └── inventory/
│       ├── __init__.py
│       ├── application.py         # Application facade and sample bootstrap
│       ├── domain/                # Entities (Product, Supplier, StockMovement, Enums)
│       ├── operations/            # Intake & withdrawal services
│       ├── policies/              # Stock level assessment & reorder calculations
│       ├── reporting/             # Portfolio valuation & replenishment reports
│       └── storage/               # In-memory inventory state & movement store
├── tests/
│   └── test_inventory.py          # Functional test suite
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
context-forge analyze test-projects/full_projects/02_inventory_management/src

# 2. Check dependencies of reorder policy
context-forge memory dependencies inventory/policies/reorder.py test-projects/full_projects/02_inventory_management/src --format json

# 3. Analyze impact of modifying reorder calculation
context-forge changeset inventory/policies/reorder.py -p test-projects/full_projects/02_inventory_management/src --format json
```

## Controlled Change Scenarios

1. **Alter Reorder Formula**: Changing safety stock multiplier in `policies/reorder.py`. Direct consumer: `reporting/reports.py`.
2. **Add Movement Reason Field**: Adding `operator_id: str` to `StockMovement` in `domain/movement.py`. Impacted files: `operations/service.py`, `storage/store.py`.
3. **Add Supplier Rating**: Adding `rating: float` to `domain/supplier.py` and filtering in `reporting/reports.py`.

## Manifest Verification

```bash
python test-projects/scripts/verify_manifest.py test-projects/full_projects/02_inventory_management
```
