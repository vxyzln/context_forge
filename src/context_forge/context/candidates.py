from context_forge.context.candidate import ContextCandidate
from context_forge.context.git_relevance import GitRelevance
from context_forge.context.signals import RelevanceSignals
from context_forge.context.types import ContextUnitType
from context_forge.git.repository import GitRepository
from context_forge.models.directory import Directory
from context_forge.models.file import File
from context_forge.models.project import Project
from context_forge.models.relationship import RelationshipType
from context_forge.models.symbol import Symbol
from context_forge.query.project import ProjectQuery
from context_forge.task.models import RepositoryGrounding


class CandidateGenerator:
    def generate(
        self,
        project: Project,
        task: str,
        interpretation=None,
        grounding: RepositoryGrounding | None = None,
    ) -> tuple[list[ContextCandidate], dict[object, RelevanceSignals]]:
        candidates = self._generate_candidates(
            project,
            task,
            interpretation,
            grounding,
        )

        git_relevance = GitRelevance(self._get_git_commits(project))

        file_by_id = {file.id: file for file in project.files}
        symbol_by_id = {symbol.id: symbol for symbol in project.symbols}

        signals: dict[object, RelevanceSignals] = {}

        for candidate in candidates:
            file = file_by_id.get(candidate.entity_id)
            symbol = symbol_by_id.get(candidate.entity_id)

            task_signal = self._candidate_task_relevance(
                project,
                file,
                symbol,
                interpretation,
            )
            git_signal = git_relevance.score(file) if file is not None else 0.0

            structural_signal, dependency_signal = self._relationship_relevance(
                project,
                candidate,
            )

            signals[candidate.entity_id] = RelevanceSignals(
                lexical=self._lexical_relevance(candidate),
                structural=structural_signal,
                symbol=self._symbol_relevance(candidate),
                dependency=dependency_signal,
                git=git_signal,
                task=task_signal,
            )

        return candidates, signals

    def _generate_candidates(
        self,
        project: Project,
        task: str,
        interpretation=None,
        grounding: RepositoryGrounding | None = None,
    ) -> list[ContextCandidate]:
        results = ProjectQuery(project).search(task)

        candidates = [ContextCandidate.from_search_result(result) for result in results]

        existing = {
            (candidate.entity_id, candidate.unit_type) for candidate in candidates
        }

        if interpretation is not None:
            for file in project.files:
                file_text = " ".join(
                    (
                        file.name,
                        str(file.path),
                    )
                ).lower()

                target = (interpretation.target or "").strip().lower()

                concepts = tuple(
                    concept.strip().lower()
                    for concept in interpretation.concepts
                    if concept.strip()
                )

                matches_target = bool(target and target in file_text)

                symbol_names = {
                    symbol.name.lower()
                    for symbol in project.symbols
                    if symbol.file_id == file.id
                }

                matches_concept = any(
                    concept in file_text
                    or any(concept in symbol_name for symbol_name in symbol_names)
                    for concept in concepts
                )

                key = (file.id, ContextUnitType.FILE)

                if (matches_target or matches_concept) and key not in existing:
                    candidates.append(
                        ContextCandidate(
                            entity_id=file.id,
                            unit_type=ContextUnitType.FILE,
                            score=0.8,
                            source="task_interpretation",
                            reason="Task interpretation matches file",
                        )
                    )
                    existing.add(key)

        if grounding is not None:
            self._add_grounded_candidates(
                project,
                grounding,
                candidates,
            )

        return candidates

    @staticmethod
    def _relationship_relevance(
        project: Project,
        candidate: ContextCandidate,
    ) -> tuple[float, float]:
        relationships = ProjectQuery(project).get_relationships(
            candidate.entity_id,
        )

        structural = 0.0
        dependency = 0.0

        structural_types = {
            RelationshipType.DEFINES.value,
            RelationshipType.CONTAINS.value,
        }

        dependency_types = {
            RelationshipType.IMPORTS.value,
            RelationshipType.REFERENCES.value,
            RelationshipType.INHERITS.value,
            RelationshipType.CALLS.value,
        }

        for relationship in relationships:
            relationship_type = relationship.relationship_type

            if hasattr(relationship_type, "value"):
                relationship_type = relationship_type.value

            if relationship_type in structural_types:
                structural = max(
                    structural,
                    relationship.confidence,
                )
            elif relationship_type in dependency_types:
                dependency = max(
                    dependency,
                    relationship.confidence,
                )

        return structural, dependency

    def _add_grounded_candidates(
        self,
        project: Project,
        grounding: RepositoryGrounding,
        candidates: list[ContextCandidate],
    ) -> None:
        existing = {
            (candidate.entity_id, candidate.unit_type) for candidate in candidates
        }

        for entity in grounding.task.entities:
            unit_type = ContextUnitType(entity.entity_type)
            key = (entity.entity_id, unit_type)

            if key in existing:
                continue

            candidates.append(
                ContextCandidate(
                    entity_id=entity.entity_id,
                    unit_type=unit_type,
                    score=1.0,
                    source="task_grounding",
                    reason=entity.provenance,
                )
            )

            existing.add(key)

        for entity_id in grounding.related_entity_ids:
            entity = self._get_entity(project, entity_id)

            if entity is None:
                continue

            unit_type = self._entity_type(entity)
            key = (entity_id, unit_type)

            if key in existing:
                continue

            candidates.append(
                ContextCandidate(
                    entity_id=entity_id,
                    unit_type=unit_type,
                    score=0.7,
                    source="repository_grounding",
                    reason="Repository relationship traversal",
                )
            )

            existing.add(key)

    @staticmethod
    def _get_entity(
        project: Project,
        entity_id,
    ):
        for file in project.files:
            if file.id == entity_id:
                return file

        for directory in project.directories:
            if directory.id == entity_id:
                return directory

        for symbol in project.symbols:
            if symbol.id == entity_id:
                return symbol

        return None

    @staticmethod
    def _entity_type(entity) -> ContextUnitType:
        if isinstance(entity, File):
            return ContextUnitType.FILE

        if isinstance(entity, Directory):
            return ContextUnitType.DIRECTORY

        if isinstance(entity, Symbol):
            return ContextUnitType.SYMBOL

        raise ValueError(f"Unsupported repository entity type: {type(entity).__name__}")

    @staticmethod
    def _task_relevance(
        project: Project,
        file,
        interpretation,
    ) -> float:
        if interpretation is None:
            return 0.0

        file_text = " ".join(
            (
                file.name,
                str(file.path),
            )
        ).lower()

        target = (interpretation.target or "").strip().lower()

        if target and target in file_text:
            return 1.0

        concepts = tuple(
            concept.strip().lower()
            for concept in interpretation.concepts
            if concept.strip()
        )

        if not concepts:
            return 0.0

        symbol_matches = {
            symbol.name.lower()
            for symbol in project.symbols
            if symbol.file_id == file.id
        }

        matched_concepts = sum(
            concept in file_text
            or any(concept in symbol_name for symbol_name in symbol_matches)
            for concept in concepts
        )

        return min(1.0, matched_concepts / len(concepts))

    @classmethod
    def _candidate_task_relevance(
        cls,
        project: Project,
        file: File | None,
        symbol: Symbol | None,
        interpretation,
    ) -> float:
        if interpretation is None:
            return 0.0

        if symbol is not None:
            return cls._symbol_task_relevance(
                symbol,
                interpretation,
            )

        if file is not None:
            return cls._task_relevance(
                project,
                file,
                interpretation,
            )

        return 0.0

    @staticmethod
    def _symbol_task_relevance(
        symbol: Symbol,
        interpretation,
    ) -> float:
        target = (interpretation.target or "").strip().lower()

        symbol_names = {
            symbol.name.lower(),
            (symbol.qualified_name or "").strip().lower(),
        }

        if target and target in symbol_names:
            return 1.0

        concepts = tuple(
            concept.strip().lower()
            for concept in interpretation.concepts
            if concept.strip()
        )

        if not concepts:
            return 0.0

        matched_concepts = sum(
            concept in symbol_name
            for concept in concepts
            for symbol_name in symbol_names
            if symbol_name
        )

        return min(1.0, matched_concepts / len(concepts))

    @staticmethod
    def _get_git_commits(project: Project):
        if not project.root_path.exists():
            return []

        repository = GitRepository(project.root_path)

        if not repository.is_repository():
            return []

        return repository.get_commits()

    @staticmethod
    def _lexical_relevance(candidate: ContextCandidate) -> float:
        if candidate.source != "deterministic_search":
            return 0.0

        if candidate.unit_type in (
            ContextUnitType.FILE,
            ContextUnitType.DIRECTORY,
        ):
            return candidate.score

        return 0.0

    @staticmethod
    def _symbol_relevance(candidate: ContextCandidate) -> float:
        if candidate.source != "deterministic_search":
            return 0.0

        if candidate.unit_type != ContextUnitType.SYMBOL:
            return 0.0

        return candidate.score
