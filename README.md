# Context Forge

- [![Architecture diagram on Git](https://gitdiagram.com/diagram-badge.svg)](https://gitdiagram.com/vxyzln/context_forge?utm_source=readme&utm_medium=badge)

- [Context Forge on Stardance Project](https://stardance.hackclub.com/projects/52744)
- [Context Forge on PyPI](https://pypi.org/project/context-forge-local/)

**Context Forge** is a local-first command-line interface (CLI) tool built in Python that helps developers understand and navigate Python repositories. It analyzes code structure, records supported relationships between code elements, and provides commands to explore symbols, dependencies, repository architecture, and potential change impacts. Repository information is stored locally using SQLite, allowing supported commands to reuse persisted analysis data during development.

Context Forge is designed to support repository exploration and change investigation. It provides evidence to help developers make informed decisions; it does not replace code review, testing, or developer judgment.

## Table of Contents

  - [What is Context Forge :](#what-is-context-forge-)
  - [The Problem :](#the-problem-)
  - [KEY Features :](#key-features-)
  - [How IT Works :](#how-it-works-)
  - [Design Principles :](#design-principles-)
  - [Requirements :](#requirements-)
  - [Installation :](#installation-)
  - [QUICK start](#quick-start)
  - [Example Workflow](#example-workflow)
  - [USE CASES](#use-cases)
  - [Privacy and Data Storage](#privacy-and-data-storage)
  - [Limitations](#limitations)
  - [DOCUMENTATION](#documentation)
  - [TroubleShooting](#troubleshooting)
  - [AI USAGE](#ai-usage)
  - [LICENSE](#license)
  - [Acknowledgements \& Project Background](#acknowledgements--project-background)

## What is Context Forge :

Context Forge is a local-first tool that analyzes Python repositories and builds persistent information about their structure and code relationships.

A Python Repository contains files, classes, functions, imports and relationships between different parts of the code.

Understanding the project means understanding more than the individual files & classes; it also means to understand how those parts connect together and work together.

Context Forge is a tool that provides commands for examining that information. A dev can locate symbols , inspect files, explore references and relationships and examine dependencies and also see the impact of a change before doing it.

Another imp. part is persistence. Rather than treating every interaction as an entirely new, the Context-Forge Stores the repo information/data locally so supported commands can reuse it . SQLite is the piece of software used by the project for storage.

## The Problem :

When Devs open a repository they have not worked on or are new to it, they need to discover the files that are present what functions & classes are under what file or to find an important class or function and understands it where it is used.The key point is that understanding a repository requires examining relationships between its parts, not just reading isolated files.

A function or class may be referred in several places. Modules may import each other and changes to one part may affect other parts also. Manually following these connects take too much of the time that could be made useful. Context Forge provides commands for examinig the supported references, relationships etc. in a clean format.

Before modifying a class, function, or module, a developer may want to know what depends on it and what parts of the repository might be affected. the pre-change inspection and impact analysis can provide relevant evidence for that investigation. They help the developer make a more informed decision, but they cannot guarantee that every possible consequence has been identified.

## KEY Features :

#### 1. Repo Analysis

Context Forge analyzes a python repository and stores supported information about its structure and code.Users can check the state of the analysis and refresh repo information when needed.

#### 2. Persistent Repository Information

the tool stores the repository data locally in SQLite database. Supported commands can use this saved data for when needed. SO that whenever u run a command, The tool doesn't have to re-analyze the repo and can use the saved data. If the cache is stale/old, the tool would automatically refresh the data.

#### 3. Code navigation
Users can locate the place for a symbol and inspect files , symbols, relationships and dependencies and references. These help devs move from a specific question about the code to the relevant info which is elsewhere in a repository.

#### 4. Architecture and package boundaries

The architecture and package boundaries commands help devs examine how a repository is organized. this can be useful when learning a project or investigating its module structure.

#### 5. Dependency and impact analysis

Context Forge provides commands for exploring supported dependency and reference relationships. these can help developers investigate what might be affected by a change.

#### 6. Pre change inspection & Post change reporting

Before changing code, developers can inspect a target and gather relevant repository, freshness, and Git context through the supported inspection workflow .The feature helps organize the information needed for a change investigation.

After making changes, developers can use post-change reporting to review supported aspects of the repository, including structural changes and other verification findings.

## How IT Works :

#### Step 1 : Choose a repository

the users runs the cli tool against a py repository eithr from the repo root or by specifiing the path to the project

##### Step 2 : Analyze the repository

The tool processes supported source information and builds its repository intelligence. The exact information available depends on the tool's analysis capabilities and the contents of the repository.

use commands like `cf analyze` for starting the analyzing of repo

#### Step 3 : Store/save the info

The anaylsis info is automatically persisted locay i.e. stored locally using SQLite

#### Step 4 : Query the repo and the info about it stored

The user can run commands to locate symbols, inspect files, examine relationships, investigate dependencies, or understand aspects of the repository's architecture.

Different commands answer different questions about the same codebase

#### Step 5 : Investigate and review changes

When preparing to change code, the developer can inspect the relevant target and examine potential impacts. After making changes, they can use reporting commands to review what happened and then run their project's tests.

Note : the freshness of the cache and info is also handled by the tool so that we aren't querying or investigating the old data. commands can refresh stale analysis rather than implying that all information is always current automatically.

## Design Principles :

1. **Local** **First**

Designed to analyze and query repositories locally without requiring an online service during normal use. Installation and updates may require internet access.

2. **Deterministic**

Core repository analysis uses rule-based logic rather than relying on a generative model to produce repository facts. Results can still vary when the repository or analysis environment changes.

3. **Persistent**

Supported repository information is saved locally for reuse rather than being discarded after each command.

4. **Dev** **controlled**

Reports support developer decisions but do not replace code review, testing, or responsibility for changes.

5. **Inspectable**

The CLI exposes commands and reports that let developers examine supported repository information directly.

## Requirements :

To Install and use the CLI tool Context Forge, there are two prerequisites :
1. Python 3.13 or newer
2. uv or pip

## Installation :

Context Forge is Published as `context-forge-local` on PyPI.

for uv :
```
uv tool install context-forge-local
```
uv is recommended for better experience

for pip :
```
pip install context-forge-local
or
python -m pip install context-forge-local
```
When using with pip, it is prefereable to use a virtual enviroment and install the tool in it so that the system things remain intact and activate the venv before using the tool.

Context forge supports both the cli entry points :
```
cf
```
or
```
context-forge
```

To verify that the tool has installed successfully , run anyone of the following blocks:
```
cf logo
cf --help
```
or
```
context-forge logo
context-forge --help
```

[Context Forge on PyPI](https://pypi.org/project/context-forge-local/)

## QUICK start

this Shows you the smallest useful workflow. A user should be able to follow it without reading the entire CLI reference.

You should have opened a Python repository ready and run the commands from its root directory unless you explicitly supply a path.

- First analyze the repo :
```
cf analyze
```

This is the repository analysis and persists the supported information

Then check the analysis status and cache:
```
cf status
cf cache
```

These commands provide information about the analysis state and the status of the analysis and information about the saved repository data.

To explore the repository, try the following commands :
```
cf locate MyClass
cf memory search "MyClass"
```
Here, my class is an example of a target and should be replaced with the real symbol or a search term from the user's repository

You can then introduce pre-change inspection:
```
cf inspect-change MyClass
```
This command helps investigate the target before changing it.

A bit more detailed GUIDE can be accessed [GET STARTED HERE](GUIDE.md)

## Example Workflow

The quick start shows a first run.

A useful example is investigating a class before refactoring it. A developer begins by locating the relevant class and inspecting its own context. They then examine references or support dependency relationship to understand what may be affected by a change. After making the change code, developers run the appropriate post-change report, they file review its findings and run the project's own test separately. They can use commands like

```
cf locate MyClass
cf inspect-change MyClass
cf impact MyClass
cf post-change src/example.py
```

Context Forge provides the structural information at different stages of a change: before editing, during investigation, after editing. It does not automatically decide whether the change is correct. The developer reviews the report and runs the appropriate test.

## USE CASES

1. **Exploring an unfamiliar project** - Build an initial understanding of a repository's structure and supported relationships.

2. **Finding a symbol** - Locate a class or function and investigate where it is defined or referenced.

3. **Understanding dependencies** - Explore supported relationships between symbols and modules.

4. **For refactoring** - Investigate a target and its potential impact before changing it

5. **After editing the code** -  Use post-change reports as one part of the verification process.

6. **Maintaining**  - Reuse persisted information and refresh analysis as the repository evolves.

7. **Supporting AI-assisted development**- Provide structured repository information that developers can use in AI-assisted workflows.

## Privacy and Data Storage

Context forge is a local first tool.

- The repository info does not go to any cloud service or is given out on the internet.

- The repository information is stored locally using SQLite.

- The version uses `.context_forge.db` as its default database name for analysis and CLI operations & does not include the usage of internet to do it's work.

- However, updating or installing the tool may have a requiremnet for a internal connection

- The local storage is still a file on your machine, so user handle how it is handled, backed up or shared. They can share it, handle it, or back it up.

- If you use this tool to analyze private or proprietary code, the user should understand that the database would not go onto the internet unless someone does it. The author of the tool does not have any authority over the database generated by the tool.

- normal analysis is designed to run locally without sending repository information to a cloud service

## Limitations

ContextForge is designed to help develop developers understand the Python repositories, explore the code and investigate changes. However, the information and report it provides are not guaranteed to be complete, perfectly accurate or correct in every situation for a code base

- The context forge analysis supported code and repository information, but it may not identify every detail, relationship, or dependency in the project. Some information will be incomplete or unavailable

- The reported relationship and potential impacts are useful for investigation, but they may not cover every possible effect of a change, not assume that everything affected by a change will be identified by the tool

- Architecture information and package boundary reports are intended to help developers understand the repository. They should not treat as a complete or a universally correct representation of the whole code base or the repository.

- Dev/User Review is still required because Context Forge supports code infrastructure and verification but it does not replace reading the code, reviewing the results, or using appropriate testing and debugging methods

- Is still necessary. Always run the relevant test and review your changes independently. A successful context for report does not guarantee that the application will behave as expected. For that, no bugs have been introduced.

Context should be treated as a tool that provides useful information to support the development decisions, not an absolute source of truth. Devs and users remain responsible for evaluating its result and deciding whether the code is correct, ready to use, to commit, or to push

## DOCUMENTATION

Documentation for the project is divided into files as described below

1. [**GUIDE.md**](GUIDE.md) -
Provide practical instructions for installation, analysis, exploration, and common workflows as a quick start guide for a new user.

2. [**CLI_COMMANDS.md**](CLI_COMMANDS.md) -
This is a document with a detailed command syntax, arguments, options, aliases, and troubleshooting. What each command does.

1. [**TECH_STACK.md**](TECH_STACK.md) -
Provides the details about the tools that were used in the development of this CLI context forge and the prerequisites

1. [**WORKFLOW.md**](WORKFLOW.md)
Document provides the information about the workflow that was going on when developing context forge and how was everything configured, the extensions that were used in VS Code, the terminal, the tools you used, and also the commit style for this repo

1. [**AI_USAGE.md**](AI_USAGE.md)
This document is an insightful detail in how AI was used during the development of this project

1. [**STORY.md**](STORY.md)
This documents the project's development history, lessons learned, problems solved, everything about during the development of this whole tool, what were my experiences, etc.

1. [**LICENSE**](LICENSE)
This information about the license of the tool

## TroubleShooting

### `cf: command not found`

The command may not be available in your terminal's PATH, or the installation may not have completed correctly. Check your installation method and ensure that the directory containing the executable is available to your shell.

### Python version error

Context Forge requires Python 3.13 or newer. Check your active Python version and install or select a compatible version if necessary.

```bash
python --version
```

### Unable to find a symbol or file

Check that the symbol name or file path is correct and that you are analyzing the intended repository. Some symbols or relationships may not be resolvable by the analyzer.

### Repository information appears outdated

Check the repository's analysis and cache status. Run `cf refresh` if you need to refresh the saved repository information manually.

### Unsure about a command or its arguments

Use the command's help option to see its available arguments and options.

```bash
cf --help
cf COMMAND --help
```

Replace `COMMAND` with the command you want to inspect.

For more command details and troubleshooting guidance, see the [CLI Commands Reference](CLI_COMMANDS.md). For practical usage instructions, see the [Getting Started Guide](GUIDE.md).

## AI USAGE

AI has been used to Assist me during the development of the whole tool. The usage of AI is transparently mentioned in the file [AI_USAGE.md](AI_USAGE.md)

## LICENSE

This Tool is under [MIT license](LICENSE)

## Acknowledgements & Project Background

Context Forge was developed as a project for **Stardance**, a YSWS (You Ship, We Ship) event by **Hack Club**.

The original idea behind the project was to explore how AI-assisted development could retain useful context about a codebase, helping developers and AI tools understand a repository more effectively(DEVLOG 1 to 29 on SD). As development progressed, the project evolved beyond its initial concept into a local-first repository intelligence tool that analyzes Python code, stores structured repository information, and provides commands for exploring code relationships and investigating potential change impacts.

This evolution reflects the development process itself: refining the original idea, addressing practical problems, and shaping it into a tool with a clearer purpose.

I am grateful to the Stardance community, Hack Club staff, and everyone who provided support, guidance, feedback, or encouragement throughout this journey. Their contributions helped make this project and its development experience possible.
