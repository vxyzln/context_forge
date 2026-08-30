from context_forge.context.candidate import ContextCandidate
from context_forge.context.git_relevance import GitRelevance
from context_forge.context.signals import RelevanceSignals
from context_forge.context.types import ContextUnitType
from context_forge.git.repository import GitRepository
from context_forge.models.project import Project
from context_forge.query.project import ProjectQuery


class CandidateGenerator:
    def generate(
        self,
        project: Project,
        task: str,
        interpretation=None,
    ) -> tuple[list[ContextCandidate], dict[object, RelevanceSignals]]:
        candidates = self._generate_candidates(project, task, interpretation)

        git_relevance = GitRelevance(self._get_git_commits(project))

        file_by_id = {file.id: file for file in project.files}

        signals: dict[object, RelevanceSignals] = {}

        for candidate in candidates:
            file = file_by_id.get(candidate.entity_id)

            if file is None:
                continue

            signals[candidate.entity_id] = RelevanceSignals(
                git=git_relevance.score(file),
                task=self._task_relevance(
                    project,
                    file,
                    interpretation,
                ),
            )

        return candidates, signals

    def _generate_candidates(
        self,
        project: Project,
        task: str,
        interpretation=None,
    ) -> list[ContextCandidate]:
        results = ProjectQuery(project).search(task)

        candidates = [ContextCandidate.from_search_result(result) for result in results]

        if interpretation is None:
            return candidates

        existing = {
            (candidate.entity_id, candidate.unit_type) for candidate in candidates
        }

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

            if (matches_target or matches_concept) and (
                file.id,
                ContextUnitType.FILE,
            ) not in existing:
                candidates.append(
                    ContextCandidate(
                        entity_id=file.id,
                        unit_type=ContextUnitType.FILE,
                        score=0.8,
                        source="task_interpretation",
                        reason="Task interpretation matches file",
                    )
                )

        return candidates

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

    @staticmethod
    def _get_git_commits(project: Project):
        if not project.root_path.exists():
            return []

        repository = GitRepository(project.root_path)

        if not repository.is_repository():
            return []

        return repository.get_commits()
