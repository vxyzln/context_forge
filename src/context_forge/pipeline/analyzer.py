from dataclasses import replace
from pathlib import Path

from context_forge.classifier.project import ProjectClassifier
from context_forge.git import GitRepository, summarize_commits
from context_forge.graph.builder import RelationshipBuilder
from context_forge.models.project import Project
from context_forge.parser import LanguageDetector, ParserRegistry
from context_forge.parser.python import PythonParser
from context_forge.parser.result import ParseResult
from context_forge.scanner.repository import RepositoryScanner
from context_forge.storage.cache import (
    RepositoryCacheMetadata,
    RepositoryIdentity,
    fingerprint_file,
)
from context_forge.storage.database import Database
from context_forge.storage.repository import ProjectRepository


def current_fingerprints(
    project: Project,
) -> dict[Path, object]:
    return {
        file.path: fingerprint_file(
            project.root_path,
            file.path,
        )
        for file in project.files
    }


class ProjectAnalyzer:
    def __init__(self, root_path: Path, database_path: Path) -> None:
        self.root_path = root_path.resolve()
        self.identity = RepositoryIdentity(self.root_path)
        self.database = Database(database_path)
        self.repository = ProjectRepository(self.database)

    def _parse_project(
        self,
        project: Project,
        detector: LanguageDetector,
        registry: ParserRegistry,
        paths: frozenset[Path] | None = None,
    ) -> None:
        files = project.files

        if paths is not None:
            files = [file for file in files if file.path in paths]

        for file in files:
            language = detector.detect(file.path)
            parser = registry.get(language)

            if parser is None:
                if language.value != "unknown":
                    project.errors.append(
                        f"{file.path}: no parser available for language "
                        f"'{language.value}'"
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
            project.references.extend(result.references)
            project.inheritance_references.extend(result.inheritance_references)

            for error in result.errors:
                project.errors.append(
                    f"{file.path}:{error.line or 0}:"
                    f"{error.column or 0}: {error.message}"
                )

    def _merge_cached_project(
        self,
        cached_project: Project,
        scanned_project: Project,
        changed_paths: frozenset[Path],
    ) -> Project:
        cached_directories = {
            directory.path: directory for directory in cached_project.directories
        }

        directories = []

        for directory in scanned_project.directories:
            cached_directory = cached_directories.get(directory.path)

            if cached_directory is not None:
                directories.append(cached_directory)
            else:
                directories.append(
                    replace(
                        directory,
                        project_id=cached_project.id,
                    )
                )

        directory_ids = {directory.path: directory.id for directory in directories}

        cached_files = {file.path: file for file in cached_project.files}

        files = []

        for file in scanned_project.files:
            cached_file = cached_files.get(file.path)

            if cached_file is not None and file.path not in changed_paths:
                files.append(cached_file)
                continue

            directory_id = None

            if file.path.parent != Path("."):
                directory_id = directory_ids.get(file.path.parent)

            files.append(
                replace(
                    file,
                    project_id=cached_project.id,
                    directory_id=directory_id,
                )
            )

        current_paths = {file.path for file in files}
        changed_or_added = changed_paths & current_paths

        cached_symbols = [
            symbol
            for symbol in cached_project.symbols
            if symbol.file_id
            in {
                file.id
                for file in cached_project.files
                if file.path not in changed_or_added and file.path in current_paths
            }
        ]

        cached_imports = [
            reference
            for reference in cached_project.imports
            if reference.file_id
            in {
                file.id
                for file in cached_project.files
                if file.path not in changed_or_added and file.path in current_paths
            }
        ]

        cached_references = [
            reference
            for reference in cached_project.references
            if reference.file_id
            in {
                file.id
                for file in cached_project.files
                if file.path not in changed_or_added and file.path in current_paths
            }
        ]

        cached_inheritance_references = [
            reference
            for reference in cached_project.inheritance_references
            if reference.file_id
            in {
                file.id
                for file in cached_project.files
                if file.path not in changed_or_added and file.path in current_paths
            }
        ]

        cached_project.directories = directories
        cached_project.files = files
        cached_project.symbols = cached_symbols
        cached_project.imports = cached_imports
        cached_project.references = cached_references
        cached_project.inheritance_references = cached_inheritance_references
        cached_project.relationships = []
        cached_project.errors = []

        cached_project.name = scanned_project.name
        cached_project.repository_url = scanned_project.repository_url
        cached_project.default_branch = scanned_project.default_branch
        cached_project.project_type = scanned_project.project_type
        cached_project.languages = scanned_project.languages
        cached_project.frameworks = scanned_project.frameworks
        cached_project.package_manager = scanned_project.package_manager
        cached_project.analysis_status = scanned_project.analysis_status

        return cached_project

    def _current_fingerprints(
        self,
        project: Project,
    ) -> dict[Path, object]:
        return current_fingerprints(project)

    def analyze(self) -> Project:
        self.database.initialize()

        scanned_project = RepositoryScanner(self.root_path).scan()

        current_fingerprints = self._current_fingerprints(
            scanned_project,
        )

        freshness = self.repository.check_cache_freshness(
            self.identity.key,
            current_fingerprints,
        )

        cached_analysis = self.repository.load_analysis(
            self.identity.key,
        )

        if freshness.is_fresh and cached_analysis is not None:
            project, _ = cached_analysis
            project.analysis_status = "analyzed"
            return project

        invalidation = self.repository.refresh_cache_state(
            self.identity.key,
            current_fingerprints,
        )

        if cached_analysis is None or invalidation.full:
            project = scanned_project
            changed_paths = frozenset(current_fingerprints)
        else:
            cached_project, _ = cached_analysis
            changed_paths = invalidation.paths
            project = self._merge_cached_project(
                cached_project,
                scanned_project,
                changed_paths,
            )

        project.analysis_status = "analyzing"

        try:
            ProjectClassifier().classify(project)

            detector = LanguageDetector()
            registry = ParserRegistry()
            registry.register(PythonParser())

            self._parse_project(
                project,
                detector,
                registry,
                paths=changed_paths,
            )

            RelationshipBuilder().build(
                project,
                project.imports,
            )

            git_repository = GitRepository(self.root_path)

            if git_repository.is_repository():
                commits = git_repository.get_commits()
                project.git_activity = summarize_commits(commits)

            project.analysis_status = "analyzed"

        except Exception:
            project.analysis_status = "failed"
            raise

        metadata = RepositoryCacheMetadata(
            repository_key=self.identity.key,
            project_id=project.id,
        )

        fingerprints = list(current_fingerprints.values())

        self.repository.save_analysis(
            project,
            metadata,
            fingerprints,
        )

        return project
