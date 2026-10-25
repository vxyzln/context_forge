# Inventory Management Architecture

The `inventory` package implements an event-driven domain and inventory policy architecture:

```
           [application.py]
             /          \
            v            v
     [operations/]   [reporting/]
          |               |
          v               v
     [storage/] <--- [policies/]
          |               |
          v               v
     [domain/] <----------+
```

## Layers

- **Domain (`inventory/domain`)**: Entities (`Product`, `Supplier`, `StockMovement`) and Enums (`MovementType`, `StockStatus`).
- **Storage (`inventory/storage`)**: In-memory inventory state tracking per-SKU quantities and audit trails of movements.
- **Policies (`inventory/policies`)**: Pure business logic determining reorder points, low-stock thresholds, and reorder quantities.
- **Operations (`inventory/operations`)**: Controlled state transitions (`receive_stock`, `withdraw_stock`) with overdraw protection.
- **Reporting (`inventory/reporting`)**: Portfolio valuation and replenishment requirement audits.
