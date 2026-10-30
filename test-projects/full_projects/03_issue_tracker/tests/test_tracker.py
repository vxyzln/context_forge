import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import unittest

from issues.application import IssueTrackerApp
from issues.domain.enums import IssueStatus
from issues.services.issue_service import WorkflowError


class TestIssueTracker(unittest.TestCase):
    def setUp(self) -> None:
        self.app = IssueTrackerApp()
        self.app.bootstrap_sample_data()

    def test_bootstrap_issues(self) -> None:
        issue = self.app.repo.get_issue("ISSUE-1")
        self.assertIsNotNone(issue)
        self.assertEqual(issue.assignee, "backend_dev")
        events = self.app.repo.get_events("ISSUE-1")
        self.assertEqual(len(events), 2)

    def test_valid_status_transition(self) -> None:
        issue = self.app.service.transition_status(
            "ISSUE-1", IssueStatus.TRIAGED, "team_lead"
        )
        self.assertEqual(issue.status, IssueStatus.TRIAGED)

    def test_invalid_status_transition_raises_error(self) -> None:
        with self.assertRaises(WorkflowError):
            self.app.service.transition_status(
                "ISSUE-1", IssueStatus.RESOLVED, "team_lead"
            )

    def test_notification_dispatch(self) -> None:
        self.assertEqual(len(self.app.dispatcher.sent_notifications), 1)
        notif = self.app.dispatcher.sent_notifications[0]
        self.assertEqual(notif["recipient"], "backend_dev")


if __name__ == "__main__":
    unittest.main()
