from context_forge.context.models import ContextUnit
from context_forge.context.retrieval import ContextRetriever
from context_forge.models.project import Project
from context_forge.query.project import ProjectQuery


class DeterministicRetriever(ContextRetriever):
    def retrieve(self, project: Project, query: str) -> list[ContextUnit]:
        results = ProjectQuery(project).search(query)

        return [
            ContextUnit(
                entity_id=result.entity_id,
                unit_type=result.result_type.value,
                relevance=result.score,
            )
            for result in results
        ]
