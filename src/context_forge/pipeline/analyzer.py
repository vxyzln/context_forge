from pathlib import Path

from context_forge.classifier.project import ProjectClassifier
from context_forge.graph.builder import RelationshipBuilder
from context_forge.models.project import Project
from context_forge.parser import LanguageDetector, ParserRegistry
from context_forge.parser.python import PythonParser
from context_forge.parser.result import ParseResult
from context_forge.scanner.repository import RepositoryScanner
from context_forge.storage.database import Database
from context_forge.storage.repository import ProjectRepository


class ProjectAnalyzer:
    def __init__(self, root_path: Path, database_path: Path) -> None:
        self.root_path = root_path.resolve()
        self.database = Database(database_path)
        self.repository = ProjectRepository(self.database)

    def _parse_project(
        self,
        project: Project,
        detector: LanguageDetector,
        registry: ParserRegistry,
    ) -> None:
        for file in project.files:
            language = detector.detect(file.path)
            parser = registry.get(language)

            if parser is None:
                if language.value != "unknown":
                    project.errors.append(
                        f"{file.path}: no parser available for language '{language.value}'"
                    )
                continue

            try:
                source = (project.root_path / file.path).read_text(encoding="utf-8")
                result: ParseResult = parser.parse(source, file)
            except (OSError, UnicodeDecodeError) as error:
                project.errors.append(f"{file.path}: {error}")
                continue

            for symbol in result.symbols:
                project.add_symbol(symbol)

            project.imports.extend(result.imports)
            project.relationships.extend(result.relationships)

            for error in result.errors:
                project.errors.append(
                    f"{file.path}:{error.line or 0}:"
                    f"{error.column or 0}: {error.message}"
                )

    def analyze(self) -> Project:
        self.database.initialize()

        project = RepositoryScanner(self.root_path).scan()
        project.analysis_status = "analyzing"

        try:
            ProjectClassifier().classify(project)

            detector = LanguageDetector()
            registry = ParserRegistry()
            registry.register(PythonParser())

            self._parse_project(project, detector, registry)
            RelationshipBuilder().build(project)

            project.analysis_status = "analyzed"

        except Exception:
            project.analysis_status = "failed"
            raise

        self.repository.save(project)

        return project
