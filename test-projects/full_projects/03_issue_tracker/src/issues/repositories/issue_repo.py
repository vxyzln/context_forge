from issues.domain.event import IssueEvent
from issues.domain.issue import Issue


class IssueRepository:
    def __init__(self) -> None:
        self._issues: dict[str, Issue] = {}
        self._events: dict[str, list[IssueEvent]] = {}

    def save_issue(self, issue: Issue) -> None:
        self._issues[issue.issue_id] = issue

    def get_issue(self, issue_id: str) -> Issue | None:
        return self._issues.get(issue_id)

    def list_issues(self) -> list[Issue]:
        return list(self._issues.values())

    def record_event(self, event: IssueEvent) -> None:
        self._events.setdefault(event.issue_id, []).append(event)

    def get_events(self, issue_id: str) -> list[IssueEvent]:
        return list(self._events.get(issue_id, []))
