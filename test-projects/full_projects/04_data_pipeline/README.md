# Full Project 04 — Data Pipeline

A complete multi-stage data processing pipeline application reading raw structured inputs, enforcing schemas, executing transformations, aggregating summary metrics, and generating reports.

## Purpose

Validate Context Forge's dependency chain tracking across staged processing workflows:
- Multi-tier pipeline architecture: `readers` -> `transforms` / `validation` -> `aggregation` -> `reporting` -> `orchestrator`.
- Dependency flow from consumer stages back to shared domain records (`RawRecord`, `CleanedRecord`, `CategorySummary`).
- Evaluating impact when validation schemas or cleaner rules change.
- Completely deterministic, offline data processing using checked-in sample CSV data (`data/sample.csv`).

## Structure

```text
04_data_pipeline/
├── README.md
├── pyproject.toml
├── data/
│   └── sample.csv                 # Deterministic sample dataset
├── docs/
│   └── architecture.md
├── src/
│   └── pipeline/
│       ├── __init__.py
│       ├── orchestrator.py        # Top-level pipeline orchestrator
│       ├── models/                # RawRecord, CleanedRecord, CategorySummary
│       ├── readers/               # CSV / JSON file loader
│       ├── validation/            # Schema validation rules & parse_numeric
│       ├── transforms/            # Cleaning & field normalization
│       ├── aggregation/           # Grouping & category metric calculations
│       └── reporting/             # Report formatting
├── tests/
│   └── test_pipeline.py           # Unit tests
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
context-forge analyze test-projects/full_projects/04_data_pipeline/src

# 2. Check dependencies of cleaner module
context-forge memory dependencies pipeline/transforms/cleaner.py test-projects/full_projects/04_data_pipeline/src --format json

# 3. Analyze impact of modifying validation schema
context-forge changeset pipeline/validation/schema.py -p test-projects/full_projects/04_data_pipeline/src --format json
```

## Controlled Change Scenarios

1. **Modify Required Field**: Adding `merchant` to `REQUIRED_FIELDS` in `transforms/cleaner.py`. Direct impact on `tests/test_pipeline.py`.
2. **Change Aggregation Metric**: Adding median calculation in `aggregation/aggregator.py`. Direct impact on `models/summary.py` and `reporting/formatter.py`.
3. **Add Input Reader**: Implementing Parquet reader in `readers/loader.py`.

## Manifest Verification

```bash
python test-projects/scripts/verify_manifest.py test-projects/full_projects/04_data_pipeline
```
