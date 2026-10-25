from issues.domain.enums import IssuePriority, IssueSeverity
from issues.notifications.dispatcher import NotificationDispatcher
from issues.reporting.metrics import IssueMetricsReporter
from issues.repositories.issue_repo import IssueRepository
from issues.services.issue_service import IssueService


class IssueTrackerApp:
    def __init__(self) -> None:
        self.repo = IssueRepository()
        self.service = IssueService(self.repo)
        self.dispatcher = NotificationDispatcher()
        self.reporter = IssueMetricsReporter(self.repo)

    def bootstrap_sample_data(self) -> None:
        i1 = self.service.create_issue(
            "ISSUE-1", "Database timeout on login", "Users reporting 504", "qa_lead"
        )
        i1.priority = IssuePriority.HIGH
        i1.severity = IssueSeverity.BLOCKER

        self.service.assign_issue("ISSUE-1", "backend_dev", "qa_lead")
        self.dispatcher.notify_assignment(i1)

        i2 = self.service.create_issue(
            "ISSUE-2", "Typo in footer link", "Documentation URL broken", "user_1"
        )
        i2.priority = IssuePriority.LOW
        i2.severity = IssueSeverity.COSMETIC
