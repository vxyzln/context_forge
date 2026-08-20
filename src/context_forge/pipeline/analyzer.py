from pathlib import Path

from context_forge.classifier.project import ProjectClassifier
from context_forge.extractor.python import PythonExtractor
from context_forge.graph.builder import RelationshipBuilder
from context_forge.models.project import Project
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

        PythonExtractor().extract(project)

        RelationshipBuilder().build(project)

        self.repository.save(project)

        return project
