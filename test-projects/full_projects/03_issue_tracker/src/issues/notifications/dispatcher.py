from issues.domain.event import IssueEvent
from issues.domain.issue import Issue
from issues.reporting.metrics import IssueMetricsReporter  # noqa: F401


class NotificationDispatcher:
    def __init__(self) -> None:
        self.sent_notifications: list[dict[str, str]] = []

    def notify_assignment(self, issue: Issue) -> None:
        if issue.assignee:
            self.sent_notifications.append(
                {
                    "recipient": issue.assignee,
                    "type": "ASSIGNMENT",
                    "message": f"Assigned to {issue.issue_id}: {issue.title}",
                }
            )

    def notify_status_change(self, issue: Issue, event: IssueEvent) -> None:
        recipients = {issue.reporter}
        if issue.assignee:
            recipients.add(issue.assignee)

        for recipient in recipients:
            self.sent_notifications.append(
                {
                    "recipient": recipient,
                    "type": "STATUS_UPDATE",
                    "message": f"{issue.issue_id} update: {event.details}",
                }
            )
