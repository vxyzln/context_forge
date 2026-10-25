# Context Forge

Context Forge is a deterministic, local-first repository intelligence and a memory vault for Python projects.

It helps developers understand codebases by analyzing repository structure, relationships, and code context through a command-line interface.

## Installation

### Using uv

Install Context Forge as a standalone CLI tool:

```bash
uv tool install context-forge-local
```

### Using pip

Install Context Forge inside an active Python virtual environment:

```bash
python -m pip install context-forge-local
```

**Requirements:** Python 3.13 or newer.

## Usage

Context Forge provides two command names:

```bash
cf --help
```

or

```bash
context-forge --help
```

Use the help output to explore the available commands and options.

## Design Principles

- **Local-first:** Designed to work locally with your repositories.
- **Deterministic:** Aims to produce consistent results for the same inputs and repository state.
- **Repository-aware:** Analyzes project structure and code relationships.
- **Developer-focused:** Provides command-line tools for repository intelligence and code context.

## License

See the `LICENSE` file for licensing information.
