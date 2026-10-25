from dataclasses import dataclass, field
from datetime import UTC, datetime

from issues.domain.enums import IssuePriority, IssueSeverity, IssueStatus


@dataclass
class Issue:
    issue_id: str
    title: str
    description: str
    reporter: str
    assignee: str | None = None
    status: IssueStatus = IssueStatus.OPEN
    priority: IssuePriority = IssuePriority.MEDIUM
    severity: IssueSeverity = IssueSeverity.MINOR
    tags: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
