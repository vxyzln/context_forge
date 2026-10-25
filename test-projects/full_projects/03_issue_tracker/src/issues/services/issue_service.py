from issues.domain.enums import IssueStatus
from issues.domain.event import IssueEvent
from issues.domain.issue import Issue
from issues.repositories.issue_repo import IssueRepository


class WorkflowError(Exception):
    pass


ALLOWED_TRANSITIONS: dict[IssueStatus, set[IssueStatus]] = {
    IssueStatus.OPEN: {IssueStatus.TRIAGED, IssueStatus.CLOSED},
    IssueStatus.TRIAGED: {IssueStatus.IN_PROGRESS, IssueStatus.CLOSED},
    IssueStatus.IN_PROGRESS: {IssueStatus.RESOLVED, IssueStatus.TRIAGED},
    IssueStatus.RESOLVED: {IssueStatus.CLOSED, IssueStatus.IN_PROGRESS},
    IssueStatus.CLOSED: {IssueStatus.OPEN},
}


class IssueService:
    def __init__(self, repo: IssueRepository) -> None:
        self.repo = repo
        self._next_event_id = 1

    def create_issue(
        self, issue_id: str, title: str, description: str, reporter: str
    ) -> Issue:
        if not title.strip():
            raise WorkflowError("Issue title cannot be empty")
        issue = Issue(
            issue_id=issue_id, title=title, description=description, reporter=reporter
        )
        self.repo.save_issue(issue)

        self._add_event(issue_id, "CREATED", f"Issue created by {reporter}", reporter)
        return issue

    def assign_issue(self, issue_id: str, assignee: str, actor: str) -> Issue:
        issue = self.repo.get_issue(issue_id)
        if not issue:
            raise WorkflowError(f"Issue '{issue_id}' not found")
        old_assignee = issue.assignee
        issue.assignee = assignee
        self._add_event(
            issue_id,
            "ASSIGNED",
            f"Assignee changed from {old_assignee} to {assignee}",
            actor,
        )
        return issue

    def transition_status(
        self, issue_id: str, new_status: IssueStatus, actor: str
    ) -> Issue:
        issue = self.repo.get_issue(issue_id)
        if not issue:
            raise WorkflowError(f"Issue '{issue_id}' not found")

        allowed = ALLOWED_TRANSITIONS.get(issue.status, set())
        if new_status not in allowed:
            raise WorkflowError(
                f"Cannot transition issue from {issue.status.value} to {new_status.value}"
            )

        old_status = issue.status
        issue.status = new_status
        self._add_event(
            issue_id,
            "STATUS_CHANGED",
            f"Status changed from {old_status.value} to {new_status.value}",
            actor,
        )
        return issue

    def _add_event(self, issue_id: str, action: str, details: str, author: str) -> None:
        event = IssueEvent(
            event_id=f"evt_{self._next_event_id}",
            issue_id=issue_id,
            action=action,
            details=details,
            author=author,
        )
        self._next_event_id += 1
        self.repo.record_event(event)
