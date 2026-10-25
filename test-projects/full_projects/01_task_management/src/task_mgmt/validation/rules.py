class ValidationError(Exception):
    """Raised when validation fails."""


def validate_not_empty(value: str, field_name: str) -> None:
    if not value or not value.strip():
        raise ValidationError(f"{field_name} cannot be empty")


def validate_email(email: str) -> None:
    if "@" not in email or "." not in email:
        raise ValidationError(f"Invalid email address: {email}")
