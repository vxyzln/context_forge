from context_forge.context.candidate import ContextCandidate
from context_forge.models.project import Project
from context_forge.query.project import ProjectQuery


class CandidateGenerator:
    def generate(
        self,
        project: Project,
        task: str,
    ) -> list[ContextCandidate]:
        results = ProjectQuery(project).search(task)

        return [ContextCandidate.from_search_result(result) for result in results]
