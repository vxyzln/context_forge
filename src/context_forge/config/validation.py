from typing import Any

from context_forge.config.project import (
    PackageBoundaryPolicy,
    PackageDependencyRule,
    ProjectAnalysisConfiguration,
    ProjectConfiguration,
    ProjectStorageConfiguration,
    StructuralRule,
)


class ConfigurationValidationError(ValueError):
    pass


def validate_project_config(
    data: dict[str, Any],
) -> ProjectConfiguration:
    _validate_top_level(data)

    storage_data = _section(data, "storage")
    analysis_data = _section(data, "analysis")
    packages_data = _section(data, "packages") or _section(data, "package_policy")
    rules_data = data.get("rules")

    return ProjectConfiguration(
        storage=ProjectStorageConfiguration(
            database_path=_optional_string(storage_data, "database_path"),
        ),
        analysis=ProjectAnalysisConfiguration(
            max_context_units=_optional_int(analysis_data, "max_context_units"),
        ),
        packages=_validate_packages_policy(packages_data),
        rules=_validate_structural_rules(rules_data),
    )


def _validate_top_level(data: dict[str, Any]) -> None:
    allowed = {"storage", "analysis", "packages", "package_policy", "rules"}

    unknown = set(data) - allowed

    if unknown:
        names = ", ".join(sorted(unknown))
        raise ConfigurationValidationError(f"Unknown configuration section: {names}")


def _section(
    data: dict[str, Any],
    name: str,
) -> dict[str, Any]:
    value = data.get(name)

    if value is None:
        return {}

    if not isinstance(value, dict):
        raise ConfigurationValidationError(
            f"Configuration section '{name}' must be a table"
        )

    return value


def _optional_string(
    section: dict[str, Any],
    name: str,
) -> str | None:
    value = section.get(name)

    if value is None:
        return None

    if not isinstance(value, str):
        raise ConfigurationValidationError(
            f"Configuration value '{name}' must be a string"
        )

    if not value.strip():
        raise ConfigurationValidationError(
            f"Configuration value '{name}' cannot be empty"
        )

    return value


def _optional_int(
    section: dict[str, Any],
    name: str,
) -> int | None:
    value = section.get(name)

    if value is None:
        return None

    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigurationValidationError(
            f"Configuration value '{name}' must be an integer"
        )

    if value <= 0:
        raise ConfigurationValidationError(
            f"Configuration value '{name}' must be positive"
        )

    return value


def _validate_packages_policy(section: dict[str, Any]) -> PackageBoundaryPolicy:
    if not section:
        return PackageBoundaryPolicy()

    allowed_fields = {"default_policy", "rules", "deny", "prohibit"}
    unknown = set(section) - allowed_fields
    if unknown:
        names = ", ".join(sorted(unknown))
        raise ConfigurationValidationError(f"Unknown package policy field: {names}")

    default_policy = section.get("default_policy", "unrestricted")
    if not isinstance(default_policy, str) or default_policy not in {
        "unrestricted",
        "allow",
        "deny",
        "prohibit",
    }:
        raise ConfigurationValidationError(
            f"Package policy default_policy must be 'unrestricted', 'allow', 'deny', or 'prohibit', got {default_policy!r}"
        )

    rules_list: list[PackageDependencyRule] = []
    seen_rule_ids: set[str] = set()
    rule_policies: dict[tuple[str, str], str] = {}

    def _add_rule(
        src: str,
        tgt: str,
        pol: str,
        desc: str | None = None,
        r_id: str | None = None,
    ) -> None:
        norm_pol = "deny" if pol in {"deny", "prohibit"} else "allow"
        key = (src, tgt)
        if key in rule_policies and rule_policies[key] != norm_pol:
            raise ConfigurationValidationError(
                f"Conflicting package policy rules for '{src} -> {tgt}': cannot both allow and deny"
            )
        rule_policies[key] = norm_pol

        rule = PackageDependencyRule(
            source_package=src,
            target_package=tgt,
            policy=pol,
            description=desc,
            rule_id=r_id,
        )
        if rule.rule_id in seen_rule_ids:
            raise ConfigurationValidationError(
                f"Duplicate package policy rule_id: {rule.rule_id!r}"
            )
        seen_rule_ids.add(rule.rule_id)
        rules_list.append(rule)

    raw_rules = section.get("rules", [])
    if not isinstance(raw_rules, list):
        raise ConfigurationValidationError("Package policy 'rules' must be a list")

    for idx, rule in enumerate(raw_rules):
        if not isinstance(rule, dict):
            raise ConfigurationValidationError(
                f"Package policy rule #{idx + 1} must be a table"
            )
        src = rule.get("source") or rule.get("source_package")
        tgt = rule.get("target") or rule.get("target_package")
        if not src or not isinstance(src, str) or not src.strip():
            raise ConfigurationValidationError(
                f"Package policy rule #{idx + 1} missing or invalid 'source'"
            )
        if not tgt or not isinstance(tgt, str) or not tgt.strip():
            raise ConfigurationValidationError(
                f"Package policy rule #{idx + 1} missing or invalid 'target'"
            )
        pol = rule.get("policy", "deny")
        if not isinstance(pol, str) or pol not in {"deny", "prohibit", "allow"}:
            raise ConfigurationValidationError(
                f"Package policy rule #{idx + 1} invalid policy: {pol!r}"
            )
        desc = rule.get("description")
        if desc is not None and not isinstance(desc, str):
            raise ConfigurationValidationError(
                f"Package policy rule #{idx + 1} description must be a string"
            )
        rule_id = rule.get("rule_id") or rule.get("id")
        if rule_id is not None and not isinstance(rule_id, str):
            raise ConfigurationValidationError(
                f"Package policy rule #{idx + 1} rule_id must be a string"
            )

        _add_rule(
            src=src.strip(),
            tgt=tgt.strip(),
            pol=pol.strip(),
            desc=desc.strip() if desc else None,
            r_id=rule_id.strip() if rule_id else None,
        )

    raw_deny = section.get("deny") or section.get("prohibit")
    if raw_deny is not None:
        if not isinstance(raw_deny, list):
            raise ConfigurationValidationError("Package policy 'deny' must be a list")
        for idx, item in enumerate(raw_deny):
            if isinstance(item, str):
                if "->" not in item:
                    raise ConfigurationValidationError(
                        f"Package policy deny item #{idx + 1} string must be in format 'source -> target'"
                    )
                parts = [p.strip() for p in item.split("->", 1)]
                if not parts[0] or not parts[1]:
                    raise ConfigurationValidationError(
                        f"Package policy deny item #{idx + 1} string has empty source or target"
                    )
                _add_rule(
                    src=parts[0],
                    tgt=parts[1],
                    pol="deny",
                )
            elif isinstance(item, dict):
                src = item.get("source") or item.get("source_package")
                tgt = item.get("target") or item.get("target_package")
                if not src or not isinstance(src, str) or not src.strip():
                    raise ConfigurationValidationError(
                        f"Package policy deny item #{idx + 1} missing or invalid 'source'"
                    )
                if not tgt or not isinstance(tgt, str) or not tgt.strip():
                    raise ConfigurationValidationError(
                        f"Package policy deny item #{idx + 1} missing or invalid 'target'"
                    )
                _add_rule(
                    src=src.strip(),
                    tgt=tgt.strip(),
                    pol="deny",
                    desc=item.get("description"),
                    r_id=item.get("rule_id") or item.get("id"),
                )
            else:
                raise ConfigurationValidationError(
                    f"Package policy deny item #{idx + 1} must be a string or table"
                )

    return PackageBoundaryPolicy(
        rules=tuple(rules_list),
        default_policy=default_policy,
    )


def _validate_structural_rules(raw_rules: Any) -> tuple[StructuralRule, ...]:
    if raw_rules is None:
        return ()

    if not isinstance(raw_rules, list):
        raise ConfigurationValidationError(
            "Configuration section 'rules' must be a list"
        )

    rules_list: list[StructuralRule] = []
    seen_ids: set[str] = set()

    for idx, item in enumerate(raw_rules):
        if not isinstance(item, dict):
            raise ConfigurationValidationError(f"Rule #{idx + 1} must be a table")
        rule_id = item.get("rule_id") or item.get("id")
        kind = item.get("kind") or item.get("type")
        source = (
            item.get("source")
            or item.get("source_component")
            or item.get("source_package")
        )
        target = (
            item.get("target")
            or item.get("target_component")
            or item.get("target_package")
        )
        rel_type = item.get("relationship_type") or item.get("rel_type")
        desc = item.get("description")
        severity = item.get("severity", "error")

        if not kind or not isinstance(kind, str) or not kind.strip():
            raise ConfigurationValidationError(
                f"Rule #{idx + 1} missing or invalid 'kind'"
            )
        kind = kind.strip()

        if not source or not isinstance(source, str) or not source.strip():
            raise ConfigurationValidationError(
                f"Rule #{idx + 1} missing or invalid 'source'"
            )
        source = source.strip()

        if target is not None:
            if not isinstance(target, str) or not target.strip():
                raise ConfigurationValidationError(f"Rule #{idx + 1} invalid 'target'")
            target = target.strip()

        if rel_type is not None:
            if not isinstance(rel_type, str) or not rel_type.strip():
                raise ConfigurationValidationError(
                    f"Rule #{idx + 1} invalid 'relationship_type'"
                )
            rel_type = rel_type.strip()

        if desc is not None and not isinstance(desc, str):
            raise ConfigurationValidationError(f"Rule #{idx + 1} invalid 'description'")
        if desc is not None:
            desc = desc.strip()

        if severity is not None and (
            not isinstance(severity, str)
            or severity not in {"error", "warning", "info", "blocker"}
        ):
            raise ConfigurationValidationError(
                f"Rule #{idx + 1} invalid 'severity': {severity!r}"
            )

        if not rule_id or not isinstance(rule_id, str) or not rule_id.strip():
            rule_id = f"{kind}:{source}->{target}" if target else f"{kind}:{source}"
        else:
            rule_id = rule_id.strip()

        if rule_id in seen_ids:
            raise ConfigurationValidationError(
                f"Duplicate structural rule_id: {rule_id!r}"
            )
        seen_ids.add(rule_id)

        rules_list.append(
            StructuralRule(
                rule_id=rule_id,
                kind=kind,
                source=source,
                target=target,
                relationship_type=rel_type,
                description=desc,
                severity=severity,
            )
        )

    return tuple(rules_list)
