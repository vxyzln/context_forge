from collections import Counter

from issues.repositories.issue_repo import IssueRepository


class IssueMetricsReporter:
    def __init__(self, repo: IssueRepository) -> None:
        self.repo = repo

    def generate_metrics(self) -> dict[str, object]:
        issues = self.repo.list_issues()
        status_counts = Counter(i.status.value for i in issues)
        severity_counts = Counter(i.severity.value for i in issues)

        return {
            "total_issues": len(issues),
            "by_status": dict(status_counts),
            "by_severity": dict(severity_counts),
        }
