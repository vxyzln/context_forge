class PipelineValidationError(Exception):
    pass


def validate_required_fields(data: dict[str, object], required: list[str]) -> None:
    for field in required:
        if field not in data or data[field] is None or str(data[field]).strip() == "":
            raise PipelineValidationError(f"Missing required field: '{field}'")


def parse_numeric(val: object, field_name: str) -> float:
    try:
        f = float(str(val))
        if f < 0:
            raise PipelineValidationError(
                f"Field '{field_name}' must be non-negative: {f}"
            )
        return f
    except (ValueError, TypeError) as err:
        raise PipelineValidationError(
            f"Invalid numeric format for '{field_name}': {val}"
        ) from err
