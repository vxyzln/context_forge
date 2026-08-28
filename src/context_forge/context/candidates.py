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
    ) -> tuple[list[ContextCandidate], dict[object, RelevanceSignals]]:
        results = ProjectQuery(project).search(task)

        candidates = [ContextCandidate.from_search_result(result) for result in results]

        signals = self._build_signals(project, candidates)

        return candidates, signals

    def _build_signals(
        self,
        project: Project,
        candidates: list[ContextCandidate],
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
            )

        return signals

    @staticmethod
    def _get_git_commits(project: Project):
        if not project.root_path.exists():
            return []

        repository = GitRepository(project.root_path)

        if not repository.is_repository():
            return []

        return repository.get_commits()
