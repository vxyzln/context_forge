from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True)
class IssueEvent:
    event_id: str
    issue_id: str
    action: str
    details: str
    author: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
