"""Audit and inspect configuration layers, precedence, and validity."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from context_forge.config.defaults import ConfigurationDefaults
from context_forge.config.global_config import global_config_path
from context_forge.config.loader import (
    ConfigurationLoadError,
    load_global_config,
    load_project_config,
    project_config_path,
)
from context_forge.config.project import ProjectConfiguration
from context_forge.config.resolver import resolve_configuration
from context_forge.config.validation import (
    ConfigurationValidationError,
    validate_project_config,
)
from context_forge.reporting.contract import (
    DiagnosticItem,
    DiagnosticSeverity,
)


@dataclass(frozen=True)
class ConfigurationAuditResult:
    """Detailed audit of configuration sources, validity, resolved values, and precedence."""

    status: str  # "valid", "invalid", "default"
    resolved: ConfigurationDefaults | None
    precedence: dict[str, str] = field(default_factory=dict)
    project_config_path: Path | None = None
    project_config_present: bool = False
    global_config_path: Path | None = None
    global_config_present: bool = False
    diagnostics: tuple[DiagnosticItem, ...] = ()
    project_config: ProjectConfiguration = field(default_factory=ProjectConfiguration)
    global_config: ProjectConfiguration = field(default_factory=ProjectConfiguration)

    @property
    def is_valid(self) -> bool:
        """True if configuration is syntactically and semantically valid."""
        return self.status != "invalid" and not any(
            d.severity == DiagnosticSeverity.BLOCKER for d in self.diagnostics
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize configuration audit to a deterministic dictionary."""
        resolved_payload = (
            {
                "database_path": self.resolved.database_path,
                "max_context_units": self.resolved.max_context_units,
            }
            if self.resolved is not None and self.status != "invalid"
            else None
        )
        precedence_payload = (
            dict(sorted(self.precedence.items())) if self.status != "invalid" else {}
        )
        return {
            "status": self.status,
            "sources": {
                "project_config_path": (
                    self.project_config_path.as_posix()
                    if self.project_config_path is not None
                    else None
                ),
                "project_config_present": self.project_config_present,
                "global_config_path": (
                    self.global_config_path.as_posix()
                    if self.global_config_path is not None
                    else None
                ),
                "global_config_present": self.global_config_present,
            },
            "resolved": resolved_payload,
            "precedence": precedence_payload,
            "diagnostics": [d.to_dict() for d in self.diagnostics],
        }


def audit_configuration(
    project_root: Path | None = None,
    *,
    global_config_path_override: Path | None = None,
) -> ConfigurationAuditResult:
    """Inspect and validate global and project configuration without mutating files.

    Preserves configuration precedence (project > global > default) and reports
    diagnostics for malformed files, invalid structures, or invalid values.
    Missing optional configuration files are treated as normal default sources.
    """
    p_path: Path | None = None
    if project_root is not None:
        p_path = project_config_path(project_root)

    g_path: Path = (
        global_config_path_override
        if global_config_path_override is not None
        else global_config_path()
    )

    diagnostics: list[DiagnosticItem] = []
    p_present = False
    g_present = False
    p_config = ProjectConfiguration()
    g_config = ProjectConfiguration()
    has_blocker = False

    # 1. Audit project configuration
    if p_path is not None and p_path.exists():
        p_present = True
        if not p_path.is_file():
            has_blocker = True
            diagnostics.append(
                DiagnosticItem.blocker(
                    f"Project configuration path is not a file: {p_path.as_posix()}",
                    code="CONFIG_NOT_A_FILE",
                    path=p_path.as_posix(),
                    source="config",
                )
            )
        else:
            try:
                raw_project = load_project_config(project_root)  # type: ignore[arg-type]
                p_config = validate_project_config(raw_project)
            except ConfigurationLoadError as exc:
                has_blocker = True
                diagnostics.append(
                    DiagnosticItem.blocker(
                        str(exc),
                        code="CONFIG_LOAD_ERROR",
                        path=p_path.as_posix(),
                        source="config",
                    )
                )
            except ConfigurationValidationError as exc:
                has_blocker = True
                diagnostics.append(
                    DiagnosticItem.blocker(
                        str(exc),
                        code="CONFIG_VALIDATION_ERROR",
                        path=p_path.as_posix(),
                        source="config",
                    )
                )
            except OSError as exc:
                has_blocker = True
                diagnostics.append(
                    DiagnosticItem.blocker(
                        f"Could not read project configuration: {exc}",
                        code="CONFIG_IO_ERROR",
                        path=p_path.as_posix(),
                        source="config",
                    )
                )

    # 2. Audit global configuration
    if g_path.exists():
        g_present = True
        if not g_path.is_file():
            has_blocker = True
            diagnostics.append(
                DiagnosticItem.blocker(
                    f"Global configuration path is not a file: {g_path.as_posix()}",
                    code="CONFIG_NOT_A_FILE",
                    path=g_path.as_posix(),
                    source="config",
                )
            )
        else:
            try:
                raw_global = load_global_config(g_path)
                g_config = validate_project_config(raw_global)
            except ConfigurationLoadError as exc:
                has_blocker = True
                diagnostics.append(
                    DiagnosticItem.blocker(
                        str(exc),
                        code="CONFIG_LOAD_ERROR",
                        path=g_path.as_posix(),
                        source="config",
                    )
                )
            except ConfigurationValidationError as exc:
                has_blocker = True
                diagnostics.append(
                    DiagnosticItem.blocker(
                        str(exc),
                        code="CONFIG_VALIDATION_ERROR",
                        path=g_path.as_posix(),
                        source="config",
                    )
                )
            except OSError as exc:
                has_blocker = True
                diagnostics.append(
                    DiagnosticItem.blocker(
                        f"Could not read global configuration: {exc}",
                        code="CONFIG_IO_ERROR",
                        path=g_path.as_posix(),
                        source="config",
                    )
                )

    # 3. Determine status and precedence resolution
    if has_blocker:
        status = "invalid"
        resolved = None
        precedence = {}
    else:
        resolved = resolve_configuration(
            global_config=g_config,
            project_config=p_config,
        )
        precedence = {
            "database_path": (
                "project"
                if p_config.storage.database_path is not None
                else (
                    "global"
                    if g_config.storage.database_path is not None
                    else "default"
                )
            ),
            "max_context_units": (
                "project"
                if p_config.analysis.max_context_units is not None
                else (
                    "global"
                    if g_config.analysis.max_context_units is not None
                    else "default"
                )
            ),
        }
        status = "valid" if (p_present or g_present) else "default"

    return ConfigurationAuditResult(
        status=status,
        resolved=resolved,
        precedence=precedence,
        project_config_path=p_path,
        project_config_present=p_present,
        global_config_path=g_path,
        global_config_present=g_present,
        diagnostics=tuple(diagnostics),
        project_config=p_config,
        global_config=g_config,
    )
