from context_forge.models.enums import FileType
from context_forge.models.project import Project

LANGUAGE_BY_EXTENSION = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".java": "Java",
    ".cpp": "C++",
    ".cc": "C++",
    ".hpp": "C++",
    ".c": "C",
    ".h": "C",
    ".go": "Go",
    ".rs": "Rust",
    ".rb": "Ruby",
    ".swift": "Swift",
    ".kt": "Kotlin",
    ".php": "PHP",
}

DOCUMENTATION_EXTENSIONS = {".md", ".rst", ".txt"}

CONFIGURATION_FILES = {
    "pyproject.toml",
    "package.json",
    "package-lock.json",
    "uv.lock",
    "Cargo.toml",
    "go.mod",
    "requirements.txt",
    "Makefile",
    ".gitignore",
}

FRAMEWORK_INDICATORS = {
    "fastapi": "FASTAPI",
    "django": "Django",
    "flask": "Flask",
    "react": "React",
    "next": "Next.js",
}


class ProjectClassifier:
    def classify(self, project: Project) -> Project:
        self._classify_files(project)
        self._detect_languages(project)
        self._detect_project_types(project)
        self._detect_package_manager(project)
        self._detect_frameworks(project)

        return project

    def _detect_project_types(self, project: Project) -> None:
        file_names = {file.name for file in project.files}

        if "pyproject.toml" in file_names:
            project.project_type = "python_project"
        elif "package.json" in file_names:
            project.project_type = "javascript_project"
        elif "Cargo.toml" in file_names:
            project.project_type = "rust_project"
        elif "go.mod" in file_names:
            project.project_type = "go_project"
        elif "pom.xml" in file_names:
            project.project_type = "java_project"
        else:
            project.project_type = "unknown"

    def _classify_files(self, project: Project) -> None:
        for file in project.files:
            if file.name in CONFIGURATION_FILES:
                file.file_type = FileType.CONFIGURATION
            elif file.extension in DOCUMENTATION_EXTENSIONS:
                file.file_type = FileType.DOCUMENTATION
            elif file.path.parts and "tests" in file.path.parts:
                file.file_type = FileType.TEST
            elif file.extension in LANGUAGE_BY_EXTENSION:
                file.file_type = FileType.SOURCE
            else:
                file.file_type = FileType.UNKNOWN

    def _detect_languages(self, project: Project):
        languages = {
            LANGUAGE_BY_EXTENSION[file.extension]
            for file in project.files
            if file.extension in LANGUAGE_BY_EXTENSION
        }

        project.languages = sorted(languages)

    def _detect_package_manager(self, project: Project) -> None:
        file_names = {file.name for file in project.files}

        if "uv.lock" in file_names:
            project.package_manager = "uv"
        elif "requirements.txt" in file_names:
            project.package_manager = "pip"
        elif "package-lock.json" in file_names:
            project.package_manager = "npm"
        elif "pnpm-lock.yaml" in file_names:
            project.package_manager = "pnpm"
        elif "yarn.lock" in file_names:
            project.package_manager = "yarn"
        elif "Cargo.toml" in file_names:
            project.package_manager = "cargo"
        elif "go.mod" in file_names:
            project.package_manager = "go"

    def _detect_frameworks(self, project: Project) -> None:
        detected: set[str] = set()

        for file in project.files:
            if file.extension != ".py":
                continue

            try:
                content = (project.root_path / file.path).read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

            content_lower = content.lower()

            for indicator, framework in FRAMEWORK_INDICATORS.items():
                if f"import {indicator}" in content_lower:
                    detected.add(framework)

        project.frameworks = sorted(detected)
