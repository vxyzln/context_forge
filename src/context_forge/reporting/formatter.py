"""Formatting helpers for OperationOutcome and DiagnosticItem."""

from __future__ import annotations

from context_forge.reporting.contract import (
    DiagnosticItem,
    DiagnosticSeverity,
    OperationOutcome,
)


def format_diagnostic_line(diag: DiagnosticItem) -> str:
    """Format a single DiagnosticItem for human-readable display."""
    prefix = f"[{diag.severity.value.upper()}]"
    loc_parts: list[str] = []
    if diag.path:
        loc_parts.append(diag.path)
    if diag.line is not None:
        loc_parts.append(str(diag.line))
    if diag.column is not None and diag.line is not None:
        loc_parts.append(str(diag.column))

    loc_str = ":".join(loc_parts)
    if loc_str:
        return f"{prefix} {loc_str}: {diag.message}"
    if diag.code:
        return f"{prefix} ({diag.code}) {diag.message}"
    return f"{prefix} {diag.message}"


def render_outcome_text(
    outcome: OperationOutcome,
    *,
    indent: str = "  ",
) -> list[str]:
    """Render an OperationOutcome as human-readable text lines."""
    lines: list[str] = []
    status_label = outcome.status.value.upper()
    if outcome.message:
        lines.append(f"Outcome: {status_label} - {outcome.message}")
    else:
        lines.append(f"Outcome: {status_label}")

    if outcome.blockers:
        lines.append("Blockers:")
        for blocker in outcome.blockers:
            lines.append(f"{indent}{format_diagnostic_line(blocker)}")

    if outcome.errors:
        lines.append("Errors:")
        for error in outcome.errors:
            lines.append(f"{indent}{format_diagnostic_line(error)}")

    if outcome.warnings:
        lines.append("Warnings:")
        for warning in outcome.warnings:
            lines.append(f"{indent}{format_diagnostic_line(warning)}")

    info_items = [
        d for d in outcome.diagnostics if d.severity == DiagnosticSeverity.INFO
    ]
    if info_items:
        lines.append("Information:")
        for item in info_items:
            lines.append(f"{indent}{format_diagnostic_line(item)}")

    if outcome.limitations:
        lines.append("Limitations:")
        for limitation in outcome.limitations:
            lines.append(f"{indent}- {limitation}")

    return lines
