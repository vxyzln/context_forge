from abc import ABC, abstractmethod
from typing import Generic, TypeVar

T = TypeVar("T")


class BaseRepository(ABC, Generic[T]):
    @abstractmethod
    def add(self, entity: T) -> None:
        pass

    @abstractmethod
    def get(self, identifier: str) -> T | None:
        pass

    @abstractmethod
    def list_all(self) -> list[T]:
        pass
