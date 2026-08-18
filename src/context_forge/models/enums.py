from enum import Enum


class FileType(Enum):
    SOURCE = "source"
    TEST = "test"
    DOCUMENTATION = "documentation"
    CONFIGURATION = "configuration"
    DATA = "data"
    ASSET = "asset"
    GENERATED = "generated"
    DEPENDENCY = "dependency"
    SECRET = "secret"
    UNKNOWN = "unknown"


class DirectoryType(Enum):
    SOURCE = "source"
    TESTS = "tests"
    DOCUMENTATION = "documentation"
    CONFIGURATION = "configuration"
    ASSETS = "assets"
    GENERATED = "generated"
    DEPENDENCY = "dependency"
    UNKNOWN = "unknown"
