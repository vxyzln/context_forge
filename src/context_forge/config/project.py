import fnmatch
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ProjectStorageConfiguration:
    database_path: str | None = None


@dataclass(frozen=True)
class ProjectAnalysisConfiguration:
    max_context_units: int | None = None


@dataclass(frozen=True)
class PackageDependencyRule:
    source_package: str
    target_package: str
    policy: str = "deny"
    description: str | None = None
    rule_id: str | None = None

    def __post_init__(self) -> None:
        if not self.rule_id:
            object.__setattr__(
                self,
                "rule_id",
                f"{self.source_package}->{self.target_package}",
            )


@dataclass(frozen=True)
class PackageBoundaryPolicy:
    rules: tuple[PackageDependencyRule, ...] = ()
    default_policy: str = "unrestricted"

    def matching_rules(
        self, source_package: str, target_package: str
    ) -> tuple[PackageDependencyRule, ...]:
        matched: list[PackageDependencyRule] = []
        for rule in self.rules:
            src_match = (
                rule.source_package == "*"
                or rule.source_package == source_package
                or fnmatch.fnmatchcase(source_package, rule.source_package)
            )
            tgt_match = (
                rule.target_package == "*"
                or rule.target_package == target_package
                or fnmatch.fnmatchcase(target_package, rule.target_package)
            )
            if src_match and tgt_match:
                matched.append(rule)
        return tuple(matched)

    def evaluate(
        self, source_package: str, target_package: str
    ) -> tuple[str, PackageDependencyRule | None]:
        # 1. Exact matches take precedence
        exact_rules = [
            r
            for r in self.rules
            if "*" not in r.source_package and "*" not in r.target_package
        ]
        for rule in exact_rules:
            if (
                rule.source_package == source_package
                and rule.target_package == target_package
            ):
                pol = "prohibited" if rule.policy in {"deny", "prohibit"} else "allowed"
                return pol, rule

        # 2. Check wildcard patterns
        pattern_rules = [
            r for r in self.rules if "*" in r.source_package or "*" in r.target_package
        ]
        matching_patterns: list[PackageDependencyRule] = []
        for rule in pattern_rules:
            src_match = (
                rule.source_package == "*"
                or rule.source_package == source_package
                or fnmatch.fnmatchcase(source_package, rule.source_package)
            )
            tgt_match = (
                rule.target_package == "*"
                or rule.target_package == target_package
                or fnmatch.fnmatchcase(target_package, rule.target_package)
            )
            if src_match and tgt_match:
                matching_patterns.append(rule)

        if matching_patterns:
            decisions = {
                "prohibited" if r.policy in {"deny", "prohibit"} else "allowed"
                for r in matching_patterns
            }
            if len(decisions) > 1:
                return "ambiguous", None
            decision = decisions.pop()
            return decision, matching_patterns[0]

        # 3. Default fallback
        if self.default_policy in {"deny", "prohibit"}:
            return "prohibited", None
        if self.default_policy == "allow":
            return "allowed", None
        return "unrestricted", None


@dataclass(frozen=True)
class StructuralRule:
    rule_id: str
    kind: str
    source: str
    target: str | None = None
    relationship_type: str | None = None
    description: str | None = None
    severity: str = "error"

    def to_dict(self) -> dict[str, Any]:
        return {
            "description": self.description,
            "kind": self.kind,
            "relationship_type": self.relationship_type,
            "rule_id": self.rule_id,
            "severity": self.severity,
            "source": self.source,
            "target": self.target,
        }


@dataclass(frozen=True)
class ProjectConfiguration:
    storage: ProjectStorageConfiguration = field(
        default_factory=ProjectStorageConfiguration
    )
    analysis: ProjectAnalysisConfiguration = field(
        default_factory=ProjectAnalysisConfiguration
    )
    packages: PackageBoundaryPolicy = field(default_factory=PackageBoundaryPolicy)
    rules: tuple[StructuralRule, ...] = ()
