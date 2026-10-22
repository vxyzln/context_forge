from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any
from uuid import UUID

from context_forge.reporting.contract import (
    DiagnosticItem,
    OperationOutcome,
    OperationStatus,
)

DEFAULT_REPORT_LIMIT = 50


def _path(value: Any) -> str:
    if isinstance(value, Path):
        return value.as_posix()
    return str(value).replace("\\", "/")


def _identifier(value: Any) -> str:
    if isinstance(value, UUID):
        return str(value)
    return str(value)


def _limited_section(
    items: list[dict[str, Any]],
    limit: int,
) -> dict[str, Any]:
    return {
        "items": items[:limit],
        "total": len(items),
        "limit": limit,
        "truncated": len(items) > limit,
    }


def _finding_payload(finding: Any) -> dict[str, Any]:
    return {
        "type": finding.finding_type,
        "message": finding.message,
        "source_type": finding.source_type,
        "source_id": (
            _identifier(finding.source_id) if finding.source_id is not None else None
        ),
        "source_path": (
            _path(finding.source_path) if finding.source_path is not None else None
        ),
        "target_type": finding.target_type,
        "target_id": (
            _identifier(finding.target_id) if finding.target_id is not None else None
        ),
    }


def _unresolved_import_payload(
    unresolved_import: Any,
    files_by_id: dict[Any, Any],
) -> dict[str, Any]:
    source_file = files_by_id.get(unresolved_import.file_id)
    source_path = unresolved_import.source_path

    if source_path is None and source_file is not None:
        source_path = source_file.path

    return {
        "source_id": _identifier(unresolved_import.file_id),
        "source_path": _path(source_path) if source_path is not None else None,
        "module_name": unresolved_import.module_name,
        "imported_name": unresolved_import.imported_name,
        "alias": unresolved_import.alias,
        "level": unresolved_import.level,
    }


def _strongly_connected_components(
    nodes: list[str],
    adjacency: dict[str, set[str]],
) -> list[tuple[str, ...]]:
    index = 0
    indices: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    components: list[tuple[str, ...]] = []

    def visit(node: str) -> None:
        nonlocal index

        indices[node] = index
        lowlinks[node] = index
        index += 1

        stack.append(node)
        on_stack.add(node)

        for neighbor in sorted(adjacency.get(node, set())):
            if neighbor not in indices:
                visit(neighbor)
                lowlinks[node] = min(lowlinks[node], lowlinks[neighbor])
            elif neighbor in on_stack:
                lowlinks[node] = min(lowlinks[node], indices[neighbor])

        if lowlinks[node] != indices[node]:
            return

        component: list[str] = []

        while stack:
            member = stack.pop()
            on_stack.remove(member)
            component.append(member)

            if member == node:
                break

        components.append(tuple(sorted(component)))

    for node in sorted(nodes):
        if node not in indices:
            visit(node)

    return sorted(components)


def _cycle_payloads(
    module_paths: set[str],
    dependency_pairs: set[tuple[str, str]],
    limit: int = DEFAULT_REPORT_LIMIT,
) -> list[dict[str, Any]]:
    adjacency: dict[str, set[str]] = {path: set() for path in module_paths}

    for source, target in dependency_pairs:
        if source in module_paths and target in module_paths:
            adjacency[source].add(target)

    components = _strongly_connected_components(
        sorted(module_paths),
        adjacency,
    )

    cycles: list[dict[str, Any]] = []

    for component in components:
        members = set(component)
        internal_edges = sorted(
            (source, target)
            for source, target in dependency_pairs
            if source in members and target in members
        )

        is_cycle = len(component) > 1 or any(
            source == target for source, target in internal_edges
        )

        if not is_cycle:
            continue

        cycles.append(
            {
                "module_count": len(component),
                "modules": list(component)[:limit],
                "modules_truncated": len(component) > limit,
                "dependency_count": len(internal_edges),
                "dependencies": [
                    {"source": source, "target": target}
                    for source, target in internal_edges[:limit]
                ],
                "dependencies_truncated": len(internal_edges) > limit,
            }
        )

    return sorted(
        cycles,
        key=lambda cycle: tuple(cycle["modules"]),
    )


def build_architecture_report(
    inventory: Any,
    repository_path: str | Path,
    limit: int = DEFAULT_REPORT_LIMIT,
) -> dict[str, Any]:
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("Report limit must be a positive integer")

    files_by_id = {file.id: file for file in inventory.files}

    python_files = sorted(
        (file for file in inventory.files if file.path.suffix.lower() == ".py"),
        key=lambda file: (file.path.as_posix(), file.id.hex),
    )
    python_paths = {file.path.as_posix() for file in python_files}

    dependency_pairs: set[tuple[str, str]] = set()

    for relationship in inventory.dependencies:
        source_file = files_by_id.get(relationship.source_id)
        target_file = files_by_id.get(relationship.target_id)

        if source_file is None or target_file is None:
            continue

        dependency_pairs.add(
            (
                source_file.path.as_posix(),
                target_file.path.as_posix(),
            )
        )

    sorted_dependencies = sorted(dependency_pairs)

    dependencies_by_source: dict[str, set[str]] = defaultdict(set)
    dependents_by_target: dict[str, set[str]] = defaultdict(set)

    for source, target in sorted_dependencies:
        dependencies_by_source[source].add(target)
        dependents_by_target[target].add(source)

    initializer_directories = {
        file.path.parent.as_posix()
        for file in python_files
        if file.path.name == "__init__.py"
    }

    packages: list[dict[str, Any]] = []

    for package_path in sorted(initializer_directories):
        package_modules = sorted(
            path
            for path in python_paths
            if path == package_path or path.startswith(f"{package_path}/")
        )
        packages.append(
            {
                "path": package_path,
                "module_count": len(package_modules),
                "modules": package_modules[:limit],
                "modules_truncated": len(package_modules) > limit,
            }
        )

    modules = [
        {
            "path": path,
            "direct_dependency_count": len(dependencies_by_source[path]),
            "direct_dependencies": sorted(dependencies_by_source[path])[:limit],
            "direct_dependencies_truncated": (
                len(dependencies_by_source[path]) > limit
            ),
            "direct_dependent_count": len(dependents_by_target[path]),
            "direct_dependents": sorted(dependents_by_target[path])[:limit],
            "direct_dependents_truncated": (len(dependents_by_target[path]) > limit),
        }
        for path in sorted(python_paths)
    ]

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

    findings = sorted(
        (_finding_payload(item) for item in inventory.integrity_findings),
        key=lambda item: (
            item["type"],
            item["source_path"] or "",
            item["source_id"] or "",
            item["target_id"] or "",
            item["message"],
        ),
    )

    cycles = _cycle_payloads(
        python_paths,
        set(sorted_dependencies),
        limit=limit,
    )

    analysis_errors = sorted(str(error) for error in inventory.errors)
    analysis_status = str(inventory.analysis_status)

    limitations: list[str] = [
        (
            "The report describes persisted analysis evidence; it does not "
            "establish runtime behavior."
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
            "Cycle detection identifies cyclic strongly connected components "
            "among indexed Python modules; a component may contain multiple "
            "simple cycles."
        ),
        (
            "Unresolved imports are evidence records and are not treated as "
            "resolved dependency edges."
        ),
    ]

    if analysis_status != "analyzed":
        limitations.append(
            f"Analysis status is {analysis_status!r}; architecture data may "
            "be incomplete."
        )

    if analysis_errors:
        limitations.append(
            "The persisted analysis contains errors; consult analysis.errors "
            "and structural findings."
        )

    directory_count = len(inventory.directories)
    file_count = len(inventory.files)
    symbol_count = len(inventory.symbols)
    containment_count = len(inventory.containment)

    diagnostics: list[DiagnosticItem] = []
    for err in analysis_errors:
        diagnostics.append(
            DiagnosticItem.error(
                str(err),
                code="ANALYSIS_ERROR",
                source="analyzer",
            )
        )

    for finding in findings:
        diagnostics.append(
            DiagnosticItem.warning(
                finding["message"],
                code=finding["type"],
                path=finding.get("source_path"),
                source="integrity",
            )
        )

    for cycle in cycles:
        diagnostics.append(
            DiagnosticItem.warning(
                f"Dependency cycle detected among {cycle['module_count']} modules",
                code="DEPENDENCY_CYCLE",
                source="graph",
            )
        )

    if analysis_status == "failed":
        status = OperationStatus.FAILED
        message = "Architecture analysis failed"
    elif analysis_status != "analyzed" or analysis_errors:
        status = OperationStatus.PARTIAL
        message = "Architecture report generated with analysis warnings or errors"
    else:
        status = OperationStatus.SUCCESS
        message = "Architecture report generated successfully"

    outcome = OperationOutcome(
        status=status,
        message=message,
        diagnostics=tuple(diagnostics),
        limitations=tuple(limitations),
    )

    return {
        "schema_version": 1,
        "repository": _path(repository_path),
        "analysis": {
            "status": analysis_status,
            "errors": analysis_errors,
        },
        "counts": {
            "directories": directory_count,
            "files": file_count,
            "python_modules": len(python_paths),
            "packages": len(packages),
            "symbols": symbol_count,
            "containment_edges": containment_count,
            "resolved_dependencies": len(sorted_dependencies),
            "unresolved_imports": len(unresolved_imports),
            "structural_findings": len(findings),
            "cyclic_components": len(cycles),
            "dependency_cycles": len(cycles),
        },
        "packages": _limited_section(packages, limit),
        "modules": _limited_section(modules, limit),
        "dependencies": _limited_section(
            [
                {"source": source, "target": target}
                for source, target in sorted_dependencies
            ],
            limit,
        ),
        "cycles": _limited_section(cycles, limit),
        "unresolved_imports": _limited_section(unresolved_imports, limit),
        "findings": _limited_section(findings, limit),
        "limitations": limitations,
        "outcome": outcome.to_dict(),
    }
