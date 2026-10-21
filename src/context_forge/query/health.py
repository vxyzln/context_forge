"""Deterministic repository health reports and metrics."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from context_forge.models.project import Project
from context_forge.query.architecture import ArchitectureInventory
from context_forge.query.architecture_report import (
    DEFAULT_REPORT_LIMIT,
    _cycle_payloads,
    _finding_payload,
    _limited_section,
    _path,
    _unresolved_import_payload,
)
from context_forge.reporting.contract import (
    DiagnosticItem,
    OperationOutcome,
    OperationStatus,
)
from context_forge.storage.cache import CacheFreshness, RepositoryCacheMetadata

DEFAULT_HEALTH_LIMIT = DEFAULT_REPORT_LIMIT


def build_health_report(
    project: Project | None = None,
    repository_path: str | Path = ".",
    metadata: RepositoryCacheMetadata | None = None,
    freshness: CacheFreshness | None = None,
    inventory: ArchitectureInventory | None = None,
    limit: int = DEFAULT_HEALTH_LIMIT,
) -> dict[str, Any]:
    """Build a deterministic, evidence-based repository health report.

    Integrates repository inventory metrics, analysis status, cache freshness,
    and supported dependency and structural findings without overstating certainty.

    A measured count of zero is distinguished from unavailable information (which
    is represented as ``None``).
    """
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("Report limit must be a positive integer")

    resolved_path = _path(repository_path)

    # 1. Unanalyzed or unavailable project state
    if project is None:
        missing_limitation = (
            "No persisted analysis found for repository; inventory metrics "
            "and structural findings are unavailable."
        )
        outcome = OperationOutcome.incomplete(
            message=missing_limitation,
            diagnostics=[
                DiagnosticItem.blocker(
                    "No persisted analysis found for repository",
                    code="MISSING_ANALYSIS",
                    source="storage",
                )
            ],
            limitations=[missing_limitation],
        )
        return {
            "schema_version": 1,
            "repository": resolved_path,
            "project": None,
            "analysis": {
                "status": "not_analyzed",
                "error_count": 0,
                "errors": [],
            },
            "cache": {
                "status": "unavailable",
                "reason": "missing_analysis",
            },
            "inventory": {
                "directories": None,
                "files": None,
                "python_modules": None,
                "packages": None,
                "symbols": None,
                "relationships": None,
                "containment_edges": None,
                "dependencies": None,
            },
            "findings": {
                "summary": {
                    "unresolved_imports": None,
                    "dependency_cycles": None,
                    "structural_integrity": None,
                    "total_findings": None,
                },
                "unresolved_imports": _limited_section([], limit),
                "dependency_cycles": _limited_section([], limit),
                "structural_integrity": _limited_section([], limit),
            },
            "limitations": [missing_limitation],
            "outcome": outcome.to_dict(),
        }

    # 2. Project metadata and analysis state
    project_payload = {
        "name": project.name,
        "project_type": project.project_type or "unknown",
    }

    analysis_status = str(project.analysis_status)
    analysis_errors = sorted(str(err) for err in project.errors)
    analysis_payload = {
        "status": analysis_status,
        "error_count": len(analysis_errors),
        "errors": analysis_errors,
    }

    # 3. Cache freshness state
    if freshness is not None:
        cache_status = "fresh" if freshness.is_fresh else "stale"
        freshness_reason = freshness.reason
    else:
        cache_status = "unavailable"
        freshness_reason = "not_checked"

    cache_payload = {
        "status": cache_status,
        "reason": freshness_reason,
    }

    # 4. Inventory metrics and findings
    if inventory is None:
        from context_forge.query.project import ProjectQuery

        inventory = ProjectQuery(project).get_architecture_inventory()

    files_by_id = {file.id: file for file in inventory.files}

    python_files = sorted(
        (file for file in inventory.files if file.path.suffix.lower() == ".py"),
        key=lambda file: (file.path.as_posix(), file.id.hex),
    )
    python_paths = {file.path.as_posix() for file in python_files}

    initializer_directories = {
        file.path.parent.as_posix()
        for file in python_files
        if file.path.name == "__init__.py"
    }

    inventory_payload = {
        "directories": len(inventory.directories),
        "files": len(inventory.files),
        "python_modules": len(python_files),
        "packages": len(initializer_directories),
        "symbols": len(inventory.symbols),
        "relationships": len(project.relationships),
        "containment_edges": len(inventory.containment),
        "dependencies": len(inventory.dependencies),
    }

    # 5. Dependency and structural findings
    dependency_pairs: set[tuple[str, str]] = set()
    for rel in inventory.dependencies:
        source_file = files_by_id.get(rel.source_id)
        target_file = files_by_id.get(rel.target_id)
        if source_file is not None and target_file is not None:
            dependency_pairs.add(
                (source_file.path.as_posix(), target_file.path.as_posix())
            )

    cycles = _cycle_payloads(
        python_paths,
        dependency_pairs,
        limit=limit,
    )

    unresolved_imports = sorted(
        (
            _unresolved_import_payload(item, files_by_id)
            for item in inventory.unresolved_imports
        ),
        key=lambda item: (
            item["source_path"] or "",
            item["module_name"],
            item["imported_name"] or "",
            item["alias"] or "",
            item["level"],
        ),
    )

    integrity_findings = sorted(
        (_finding_payload(item) for item in inventory.integrity_findings),
        key=lambda item: (
            item["type"],
            item["source_path"] or "",
            item["source_id"] or "",
            item["target_id"] or "",
            item["message"],
        ),
    )

    total_findings = len(unresolved_imports) + len(cycles) + len(integrity_findings)

    findings_payload = {
        "summary": {
            "unresolved_imports": len(unresolved_imports),
            "dependency_cycles": len(cycles),
            "structural_integrity": len(integrity_findings),
            "total_findings": total_findings,
        },
        "unresolved_imports": _limited_section(unresolved_imports, limit),
        "dependency_cycles": _limited_section(cycles, limit),
        "structural_integrity": _limited_section(integrity_findings, limit),
    }

    # 6. Honest limitations and caveats
    limitations: list[str] = [
        (
            "The report describes persisted static analysis evidence; it does not "
            "establish runtime behavior or guarantee execution correctness."
        ),
        (
            "Package detection identifies conventional Python packages containing "
            "__init__.py files; namespace packages without __init__.py are not "
            "inventoried as packages."
        ),
        (
            "Dependency cycles are detected only among indexed Python modules "
            "using resolved import relationships."
        ),
        (
            "Unresolved imports represent import references that could not be "
            "resolved against indexed repository files."
        ),
    ]

    if analysis_status != "analyzed":
        limitations.append(
            f"Analysis status is {analysis_status!r}; health metrics and findings "
            "may be incomplete."
        )

    if analysis_errors:
        limitations.append(
            "The persisted analysis contains errors; some symbols, dependencies, "
            "or findings may be missing."
        )

    if freshness is not None and not freshness.is_fresh:
        limitations.append(
            f"Cached analysis is stale ({freshness.reason}); recent repository "
            "modifications may not be reflected in these metrics and findings."
        )
    elif freshness is None:
        limitations.append("Cache freshness was not verified.")

    if (
        findings_payload["unresolved_imports"]["truncated"]
        or findings_payload["dependency_cycles"]["truncated"]
        or findings_payload["structural_integrity"]["truncated"]
    ):
        limitations.append(
            f"Findings display was limited to {limit} items per category."
        )

    # 7. Structured outcome semantics
    diagnostics: list[DiagnosticItem] = []
    for err in analysis_errors:
        diagnostics.append(
            DiagnosticItem.error(
                str(err),
                code="ANALYSIS_ERROR",
                source="analyzer",
            )
        )

    if freshness is not None and not freshness.is_fresh:
        diagnostics.append(
            DiagnosticItem.warning(
                f"Cached analysis is stale ({freshness.reason})",
                code="STALE_CACHE",
                source="cache",
            )
        )
    elif freshness is None:
        diagnostics.append(
            DiagnosticItem.info(
                "Cache freshness was not verified",
                code="UNVERIFIED_CACHE",
                source="cache",
            )
        )

    for item in integrity_findings:
        diagnostics.append(
            DiagnosticItem.warning(
                item["message"],
                code=item["type"],
                path=item.get("source_path"),
                source="integrity",
            )
        )

    if analysis_status == "failed":
        status = OperationStatus.FAILED
        message = "Repository analysis failed"
    elif analysis_status != "analyzed" or analysis_errors:
        status = OperationStatus.PARTIAL
        message = "Repository health report generated with analysis warnings or errors"
    elif freshness is not None and not freshness.is_fresh:
        status = OperationStatus.PARTIAL
        message = "Repository health report generated from stale cache"
    else:
        status = OperationStatus.SUCCESS
        message = "Repository health report generated successfully"

    outcome = OperationOutcome(
        status=status,
        message=message,
        diagnostics=tuple(diagnostics),
        limitations=tuple(limitations),
    )

    return {
        "schema_version": 1,
        "repository": resolved_path,
        "project": project_payload,
        "analysis": analysis_payload,
        "cache": cache_payload,
        "inventory": inventory_payload,
        "findings": findings_payload,
        "limitations": limitations,
        "outcome": outcome.to_dict(),
    }
