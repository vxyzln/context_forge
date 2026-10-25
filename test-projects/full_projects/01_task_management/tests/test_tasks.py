import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import unittest

from task_mgmt.application import TaskManagementApp
from task_mgmt.models.enums import TaskPriority, TaskStatus
from task_mgmt.validation.rules import ValidationError


class TestTaskManagement(unittest.TestCase):
    def setUp(self) -> None:
        self.app = TaskManagementApp()
        self.app.bootstrap_sample_data()

    def test_bootstrap_data_present(self) -> None:
        user = self.app.users.get_user("u1")
        self.assertIsNotNone(user)
        self.assertEqual(user.username, "alice")

    def test_task_creation_and_transition(self) -> None:
        task = self.app.tasks.create_task(
            "t3", "p1", "Write unit tests", priority=TaskPriority.HIGH, assignee_id="u1"
        )
        self.assertEqual(task.status, TaskStatus.TODO)

        updated = self.app.tasks.transition_status("t3", TaskStatus.IN_PROGRESS)
        self.assertEqual(updated.status, TaskStatus.IN_PROGRESS)

    def test_invalid_status_transition_raises_error(self) -> None:
        with self.assertRaises(ValidationError):
            self.app.tasks.transition_status("t1", TaskStatus.DONE)

    def test_assignee_validation(self) -> None:
        with self.assertRaises(ValidationError):
            self.app.tasks.create_task(
                "t_bad", "p1", "Task", assignee_id="nonexistent_user"
            )

    def test_project_summary(self) -> None:
        summary = self.app.reporter.summarize_project("p1")
        self.assertEqual(summary["total_tasks"], 2)
        self.assertEqual(summary["completion_rate_pct"], 0.0)


if __name__ == "__main__":
    unittest.main()
