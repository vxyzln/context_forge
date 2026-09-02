from context_forge.context.models import ContextUnit, Evidence, Fact
from context_forge.context.types import ContextUnitType
from context_forge.models.project import Project


class FileContextEnricher:
    def enrich(self, project: Project, unit: ContextUnit) -> ContextUnit:
        if unit.unit_type != ContextUnitType.FILE:
            return unit

        file = next(
            (item for item in project.files if item.id == unit.entity_id),
            None,
        )

        if file is None:
            return unit
        source_path = project.root_path / file.path
        content = source_path.read_text(encoding="utf-8")

        evidence = Evidence(
            source_id=file.id,
            description=f"file metadata: {file.path.as_posix()}",
        )

        facts = (
            Fact(
                fact_type="file_path",
                value=file.path.as_posix(),
                evidence=(evidence,),
            ),
            Fact(
                fact_type="file_type",
                value=file.file_type.value,
                evidence=(evidence,),
            ),
            Fact(
                fact_type="extension",
                value=file.extension,
                evidence=(evidence,),
            ),
            Fact(
                fact_type="size",
                value=str(file.size),
                evidence=(evidence,),
            ),
            Fact(
                fact_type="generated",
                value=str(file.is_generated),
                evidence=(evidence,),
            ),
            Fact(
                fact_type="ignored",
                value=str(file.is_ignored),
                evidence=(evidence,),
            ),
        )

        return ContextUnit(
            entity_id=unit.entity_id,
            unit_type=unit.unit_type,
            relevance=unit.relevance,
            content=content,
            signals=unit.signals,
            facts=unit.facts + facts,
            inferences=unit.inferences,
        )
