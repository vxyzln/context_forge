from pathlib import Path

from context_forge.classifier.project import ProjectClassifier
from context_forge.graph.builder import RelationshipBuilder
from context_forge.models.project import Project
from context_forge.parser import LanguageDetector, ParserRegistry
from context_forge.parser.python import PythonParser
from context_forge.scanner.repository import RepositoryScanner
from context_forge.storage.database import Database
from context_forge.storage.repository import ProjectRepository


class ProjectAnalyzer:
    def __init__(self, root_path: Path, database_path: Path) -> None:
        self.root_path = root_path.resolve()
        self.database = Database(database_path)
        self.repository = ProjectRepository(self.database)

    def analyze(self) -> Project:
        self.database.initialize()

        project = RepositoryScanner(self.root_path).scan()

        ProjectClassifier().classify(project)

        detector = LanguageDetector()
        registry = ParserRegistry()
        registry.register(PythonParser())

        for file in project.files:
            language = detector.detect(file.path)
            parser = registry.get(language)

            if parser is None:
                continue

            source = (project.root_path / file.path).read_text(encoding="utf-8")
            result = parser.parse(source, file)

            for symbol in result.symbols:
                project.add_symbol(symbol)

            for relationship in result.relationships:
                project.add_relationship(relationship)

        RelationshipBuilder().build(project)

        self.repository.save(project)

        return project
