from task_mgmt.models.user import User
from task_mgmt.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    def __init__(self) -> None:
        self._users: dict[str, User] = {}

    def add(self, entity: User) -> None:
        self._users[entity.user_id] = entity

    def get(self, identifier: str) -> User | None:
        return self._users.get(identifier)

    def list_all(self) -> list[User]:
        return list(self._users.values())
