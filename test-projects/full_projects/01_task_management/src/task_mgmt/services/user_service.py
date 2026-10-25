from task_mgmt.models.user import User
from task_mgmt.repositories.user_repo import UserRepository
from task_mgmt.validation.rules import validate_email, validate_not_empty


class UserService:
    def __init__(self, user_repo: UserRepository) -> None:
        self.user_repo = user_repo

    def create_user(self, user_id: str, username: str, email: str) -> User:
        validate_not_empty(user_id, "user_id")
        validate_not_empty(username, "username")
        validate_email(email)
        user = User(user_id=user_id, username=username, email=email)
        self.user_repo.add(user)
        return user

    def get_user(self, user_id: str) -> User | None:
        return self.user_repo.get(user_id)
