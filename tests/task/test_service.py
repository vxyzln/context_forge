from context_forge.provider import (
    ContextProvider,
    GenerationRequest,
    GenerationResponse,
    ProviderConfig,
    ProviderUsage,
)
from context_forge.task import TaskUnderstandingService


class StubProvider(ContextProvider):
    def __init__(self, content: str) -> None:
        self.content = content
        self.requests: list[GenerationRequest] = []

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        self.requests.append(request)

        return GenerationResponse(
            content=self.content,
            provider="test",
            model="test-model",
            usage=ProviderUsage(),
        )


def make_service(
    content: str,
) -> tuple[TaskUnderstandingService, StubProvider]:
    provider = StubProvider(content)

    service = TaskUnderstandingService(
        provider=provider,
        config=ProviderConfig(model="test-model"),
    )

    return service, provider


def test_understand_parses_structured_response() -> None:
    service, _ = make_service(
        '{"intent":"bug_fix",'
        '"target":"settings page",'
        '"concepts":["scrolling","overflow"],'
        '"requested_action":"fix",'
        '"constraints":["preserve existing behavior"],'
        '"ambiguity":null}'
    )

    result = service.understand("Fix the scrolling on the settings page.")

    assert result.task == "Fix the scrolling on the settings page."
    assert result.intent == "bug_fix"
    assert result.target == "settings page"
    assert result.concepts == ("scrolling", "overflow")
    assert result.requested_action == "fix"
    assert result.constraints == ("preserve existing behavior",)
    assert result.ambiguity is None


def test_understand_sends_task_to_provider() -> None:
    service, provider = make_service(
        '{"intent":"bug_fix",'
        '"target":"settings page",'
        '"concepts":[],"requested_action":"fix",'
        '"constraints":[],"ambiguity":null}'
    )

    service.understand("Fix the scrolling on the settings page.")

    request = provider.requests[0]

    assert "Fix the scrolling on the settings page." in request.task
    assert request.context == ""
    assert request.config == ProviderConfig(model="test-model")


def test_understand_rejects_empty_task() -> None:
    service, provider = make_service("{}")

    try:
        service.understand("   ")
    except ValueError as exc:
        assert str(exc) == "task must not be empty"
    else:
        raise AssertionError("Expected ValueError")

    assert provider.requests == []


def test_understand_rejects_invalid_json() -> None:
    service, _ = make_service("not json")

    try:
        service.understand("Fix scrolling")
    except ValueError as exc:
        assert str(exc) == "provider returned invalid task interpretation JSON"
    else:
        raise AssertionError("Expected ValueError")


def test_understand_rejects_non_object_json() -> None:
    service, _ = make_service("[]")

    try:
        service.understand("Fix scrolling")
    except TypeError as exc:
        assert str(exc) == (
            "provider returned a task interpretation that is not an object"
        )
    else:
        raise AssertionError("Expected TypeError")


def test_understand_rejects_invalid_required_field() -> None:
    service, _ = make_service(
        '{"intent":123,'
        '"target":null,'
        '"concepts":[],"requested_action":null,'
        '"constraints":[],"ambiguity":null}'
    )

    try:
        service.understand("Fix scrolling")
    except TypeError as exc:
        assert "intent" in str(exc)
    else:
        raise AssertionError("Expected TypeError")


def test_understand_rejects_invalid_concepts() -> None:
    service, _ = make_service(
        '{"intent":"bug_fix",'
        '"target":"settings",'
        '"concepts":"scrolling",'
        '"requested_action":"fix",'
        '"constraints":[],"ambiguity":null}'
    )

    try:
        service.understand("Fix scrolling")
    except TypeError as exc:
        assert "concepts" in str(exc)
    else:
        raise AssertionError("Expected TypeError")
