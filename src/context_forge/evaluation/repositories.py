from pathlib import Path

from context_forge.evaluation.models import (
    EvaluationRepository,
    EvaluationSet,
    EvaluationTask,
)


def default_evaluation_set(
    root: Path,
) -> EvaluationSet:
    root = root.resolve()

    repositories = (
        EvaluationRepository(
            id="cpython",
            name="CPython",
            source="https://github.com/python/cpython",
            root_path=root / "cpython",
            description="Python reference implementation.",
            tasks=(
                EvaluationTask(
                    id="cpython-import-system",
                    description="Locate the implementation of Python's import machinery.",
                    tags=("imports", "runtime", "architecture"),
                ),
                EvaluationTask(
                    id="cpython-parser",
                    description="Locate the parser-related implementation and its dependencies.",
                    tags=("parser", "dependencies"),
                ),
            ),
        ),
        EvaluationRepository(
            id="requests",
            name="Requests",
            source="https://github.com/psf/requests",
            root_path=root / "requests",
            description="HTTP library for Python.",
            tasks=(
                EvaluationTask(
                    id="requests-session",
                    description="Locate the implementation of HTTP sessions and related modules.",
                    tags=("sessions", "http"),
                ),
                EvaluationTask(
                    id="requests-auth",
                    description="Locate authentication handling and its related code.",
                    tags=("authentication", "dependencies"),
                ),
            ),
        ),
        EvaluationRepository(
            id="flask",
            name="Flask",
            source="https://github.com/pallets/flask",
            root_path=root / "flask",
            description="Python web application framework.",
            tasks=(
                EvaluationTask(
                    id="flask-routing",
                    description="Locate request routing and the code responsible for dispatch.",
                    tags=("routing", "request"),
                ),
                EvaluationTask(
                    id="flask-application",
                    description="Locate the main application object and its dependencies.",
                    tags=("application", "architecture"),
                ),
            ),
        ),
        EvaluationRepository(
            id="click",
            name="Click",
            source="https://github.com/pallets/click",
            root_path=root / "click",
            description="Composable command-line interface toolkit.",
            tasks=(
                EvaluationTask(
                    id="click-command",
                    description="Locate command definitions and command invocation flow.",
                    tags=("commands", "cli"),
                ),
                EvaluationTask(
                    id="click-context",
                    description="Locate the command execution context and related symbols.",
                    tags=("context", "cli"),
                ),
            ),
        ),
        EvaluationRepository(
            id="rich",
            name="Rich",
            source="https://github.com/Textualize/rich",
            root_path=root / "rich",
            description="Terminal rendering library.",
            tasks=(
                EvaluationTask(
                    id="rich-console",
                    description="Locate the main console implementation and its dependencies.",
                    tags=("console", "rendering"),
                ),
                EvaluationTask(
                    id="rich-renderables",
                    description="Locate renderable abstractions and their relationships.",
                    tags=("renderables", "relationships"),
                ),
            ),
        ),
        EvaluationRepository(
            id="httpx",
            name="HTTPX",
            source="https://github.com/encode/httpx",
            root_path=root / "httpx",
            description="HTTP client for Python.",
            tasks=(
                EvaluationTask(
                    id="httpx-client",
                    description="Locate the client implementation and related transport code.",
                    tags=("client", "transport"),
                ),
                EvaluationTask(
                    id="httpx-auth",
                    description="Locate authentication implementations and their relationships.",
                    tags=("authentication", "relationships"),
                ),
            ),
        ),
        EvaluationRepository(
            id="pydantic",
            name="Pydantic",
            source="https://github.com/pydantic/pydantic",
            root_path=root / "pydantic",
            description="Data validation library.",
            tasks=(
                EvaluationTask(
                    id="pydantic-model",
                    description="Locate the core model implementation and related symbols.",
                    tags=("models", "validation"),
                ),
                EvaluationTask(
                    id="pydantic-validation",
                    description="Locate validation machinery and its dependencies.",
                    tags=("validation", "dependencies"),
                ),
            ),
        ),
        EvaluationRepository(
            id="pytest",
            name="pytest",
            source="https://github.com/pytest-dev/pytest",
            root_path=root / "pytest",
            description="Python testing framework.",
            tasks=(
                EvaluationTask(
                    id="pytest-fixtures",
                    description="Locate fixture handling and related implementation code.",
                    tags=("fixtures", "testing"),
                ),
                EvaluationTask(
                    id="pytest-collection",
                    description="Locate test collection and discovery implementation.",
                    tags=("collection", "discovery"),
                ),
            ),
        ),
        EvaluationRepository(
            id="typer",
            name="Typer",
            source="https://github.com/fastapi/typer",
            root_path=root / "typer",
            description="CLI framework based on Python type hints.",
            tasks=(
                EvaluationTask(
                    id="typer-command",
                    description="Locate command construction and invocation logic.",
                    tags=("commands", "cli"),
                ),
                EvaluationTask(
                    id="typer-parameter",
                    description="Locate CLI parameter processing and related code.",
                    tags=("parameters", "cli"),
                ),
            ),
        ),
        EvaluationRepository(
            id="fastapi",
            name="FastAPI",
            source="https://github.com/fastapi/fastapi",
            root_path=root / "fastapi",
            description="Python web API framework.",
            tasks=(
                EvaluationTask(
                    id="fastapi-routing",
                    description="Locate route registration and request handling code.",
                    tags=("routing", "web"),
                ),
                EvaluationTask(
                    id="fastapi-dependencies",
                    description="Locate dependency injection implementation and related symbols.",
                    tags=("dependencies", "web"),
                ),
            ),
        ),
        EvaluationRepository(
            id="sqlalchemy",
            name="SQLAlchemy",
            source="https://github.com/sqlalchemy/sqlalchemy",
            root_path=root / "sqlalchemy",
            description="Python SQL toolkit and ORM.",
            tasks=(
                EvaluationTask(
                    id="sqlalchemy-session",
                    description="Locate session management and related persistence code.",
                    tags=("session", "orm"),
                ),
                EvaluationTask(
                    id="sqlalchemy-engine",
                    description="Locate engine construction and connection-related code.",
                    tags=("engine", "database"),
                ),
            ),
        ),
    )

    return EvaluationSet(repositories=repositories)
