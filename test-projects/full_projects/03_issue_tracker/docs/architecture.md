# Issue Tracker Architecture

The `issues` package separates core domain modeling from workflow services, notification dispatching, metrics reporting, and repositories:

```
        [application.py]
          /           \
         v             v
  [services/] ----> [notifications/] ---> (VIOLATION) ---> [reporting/]
       |                   |                                    |
       v                   v                                    v
 [repositories/] <---------+------------------------------------+
       |
       v
    [domain/]
```

## Architectural Policy & Boundary Violation

- **Policy Definition**: Configured in `src/.contextforge.toml`.
- **Allowed Flows**: `services` -> `repositories`, `notifications` -> `domain`.
- **Prohibited Rule**: `notifications` must NOT import or depend upon `reporting`.
- **Intentional Violation**: `issues/notifications/dispatcher.py` imports `IssueMetricsReporter` from `issues/reporting/metrics.py`.
