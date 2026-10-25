# Data Pipeline Architecture

The `pipeline` package implements a deterministic staged data transformation and aggregation pipeline:

```
[DataReader] ----------> Reads Raw CSV / JSON into RawRecord
     |
     v
[RecordCleaner] -------> Validates against schema & transforms into CleanedRecord
     |
     v
[DataAggregator] ------> Aggregates metrics by category into CategorySummary
     |
     v
[PipelineReporter] ----> Generates consolidated execution report
```

## Layers

- **Readers (`pipeline/readers`)**: File adapters extracting raw tabular rows into `RawRecord` instances.
- **Models (`pipeline/models`)**: Immutable records (`RawRecord`, `CleanedRecord`, `CategorySummary`).
- **Validation (`pipeline/validation`)**: Schema guards enforcing required fields and non-negative numbers.
- **Transforms (`pipeline/transforms`)**: Field normalization, string trimming, and casting.
- **Aggregation (`pipeline/aggregation`)**: Metric grouping, count, sum, and average calculations.
- **Reporting (`pipeline/reporting`)**: Final JSON report structure generation.
