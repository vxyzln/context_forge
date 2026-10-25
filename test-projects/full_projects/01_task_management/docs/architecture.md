# Task Management Architecture

The `task_mgmt` package implements a layered architecture:

```
[application.py] -> Orchestration
       |
       v
  [services/] ----> [validation/]
       |
       v
[repositories/] ---> In-memory data store
       |
       v
   [models/] ------> Pure data models & Enums
```

## Layers

- **Models (`task_mgmt/models`)**: Immutable or dataclass entities (`User`, `Project`, `Task`) and enums (`TaskStatus`, `TaskPriority`, `ProjectStatus`).
- **Validation (`task_mgmt/validation`)**: Reusable input guards and business rule assertions (`validate_not_empty`, `validate_email`).
- **Repositories (`task_mgmt/repositories`)**: Storage abstractions inheriting from `BaseRepository` storing domain entities.
- **Services (`task_mgmt/services`)**: Business operations including status transition validation (`ALLOWED_TRANSITIONS`) and assignee presence checks.
- **Reporting (`task_mgmt/reporting`)**: Project analytics and task completion percentage calculations.
