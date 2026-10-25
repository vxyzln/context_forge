from dataclasses import dataclass


@dataclass(frozen=True)
class User:
    user_id: str
    username: str
    email: str
    is_active: bool = True
