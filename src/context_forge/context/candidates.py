from context_forge.context.candidate import ContextCandidate
from context_forge.context.git_relevance import GitRelevance
from context_forge.context.signals import RelevanceSignals
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
        results = ProjectQuery(project).search(task)

        candidates = [ContextCandidate.from_search_result(result) for result in results]

        signals = self._build_signals(
            project,
            candidates,
            interpretation,
        )

        return candidates, signals

    def _build_signals(
        self,
        project: Project,
        candidates: list[ContextCandidate],
        interpretation=None,
    ) -> dict[object, RelevanceSignals]:
        git_relevance = GitRelevance(self._get_git_commits(project))

        file_by_id = {file.id: file for file in project.files}

        signals: dict[object, RelevanceSignals] = {}

        for candidate in candidates:
            file = file_by_id.get(candidate.entity_id)

            if file is None:
                continue

            signals[candidate.entity_id] = RelevanceSignals(
                git=git_relevance.score(file),
                task=self._task_relevance(file, interpretation),
            )

        return signals

    @staticmethod
    def _task_relevance(file, interpretation) -> float:
        if interpretation is None:
            return 0.0

        text = " ".join(
            (
                file.name,
                str(file.path),
            )
        ).lower()

        target = (interpretation.target or "").lower()

        if target and target in text:
            return 1.0

        concepts = tuple(
            concept.lower() for concept in interpretation.concepts if concept.strip()
        )

        if not concepts:
            return 0.0

        concept_matches = sum(concept in text for concept in concepts)

        return min(1.0, concept_matches / len(concepts))

    @staticmethod
    def _get_git_commits(project: Project):
        if not project.root_path.exists():
            return []

        repository = GitRepository(project.root_path)

        if not repository.is_repository():
            return []

        return repository.get_commits()
