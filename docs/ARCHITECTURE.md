# Context Forge - System Architecture

## 1. Purpose
Context Forge is a local-first project intelligence platform designed to provide AI agents with the most relevant context required to perform a task.

AI coding agents often waste tokens and time exploring entire repositories, reading irrelevant files, and reconstructing project knowledge that has already been discovered in the previous session.

Context Forge addresses this by maintaining a persistent understanding of the software project and dynamically constructing a compact task-specific context package.

The core principle is : Understand the project once. Give the agent only what it needs.

Context Forge does not modify the user's source code.

Its primary responsibility is to understand, retrieve, optimize, and package project context.

## 2. Goals

Context Forge should:

- Understand software repositories
- Maintain persistent project knowledge
- Support multiple programming languages
- Understand files, symbols, dependencies, and relationships
- Analyze Git History
- Understand User tasks
- Retrieve relevant project information
- Rank information according to task relevance
- Expand context through project relationships
- Remove irrelevant information
- Optimize context for token efficiency
- Detect uncertainty
- Ask the user for clarification when necessary
- Explain why information was selected when requested
- Generate agent-ready markdown context
- Copy generated context to clipboard
- Provide a usable web interface
- Eventually integrate directly with AI coding agents
- Eventually learn from user feedback and agent outcomes

## 3. Non-Goals

Context Forge should not initially:

- Modify the user's repository
- Automatically edit source code
- Replace an AI coding agent
- Depend entirely on a large language model for repository understanding
- Require a cloud service for core functionality
- Upload private source code to an external service by default

## 4. Core Design Principles

### 4.1 Local-first

Project source code and project knowledge should remain local whenever possible.

### 4.2 Deterministic facts before probabilistic reasoning

Facts such as file paths, imports, functions, classes, dependencies, and Git history should be obtained through deterministic analysis whenever possible.

LLMs should primarily be used for semantic reasoning and ambiguity.

### 4.3 Persistent project understanding

Context Forge should not rebuild its understanding of a project from zero for every task.

### 4.4 Task-aware retrieval

Context should be selected according to the user's current task.

### 4.5 Minimum useful context

The objective is:

> Maximum task usefulness with minimum unnecessary context.

### 4.6 Explainability

The system should be able to explain why a file, symbol, document, or historical change was selected.

### 4.7 Uncertainty awareness

Context Forge should not pretend to know something when confidence is low.

### 4.8 Modular intelligence

Repository parsing, graph construction, retrieval, ranking, LLM reasoning, and context generation should remain separate systems.

## 5. High-Level Architecture

                        USER
                        |
                        v
                    +--------------+
                    |    Web UI    |
                    +------+-------+
                        |
                        v
                    +--------------+
                    |   FastAPI    |
                    |     API      |
                    +------+-------+
                        |
            +-------------+-------------+
            |                           |
            v                           v
    Project Management          Task Management
            |                           |
            v                           v
    Project Intelligence        Task Intelligence
            |                           |
            +-------------+-------------+
                        |
                        v
                +-------------------+
                |  Project Memory   |
                +---------+---------+
                            |
                            v
                +-------------------+
                |  Context Engine   |
                +---------+---------+
                            |
            +--------------+--------------+
            |              |              |
            v              v              v
        Retrieval        Ranking       Graph Expansion
            |              |              |
            +--------------+--------------+
                            |
                            v
                +-------------------+
                | Context Optimizer |
                +---------+---------+
                            |
                            v
                +-------------------+
                | Context Validator |
                +---------+---------+
                            |
                            v
                +-------------------+
                | Context Package   |
                +---------+---------+
                            |
                            v
                    AI AGENT

## 6. Major Components

### Project Ingestion

Accepts :
- Local project folders
- GitHub repository URLs

### Repository Scanner

Walks the project filesystem and builds an initial project snapshot.

### File Classifier

Determines whether files are source code, tests, documentation, configuration, assets, generated files, and so on.

### Code Intelligence

Extracts:
- classes
- functions
- methods
- imports
- definitions
- references
- calls
- inheritance

### Project Graph

Represent relationship between project entities.

### Git Intelligence

Analyzes:
- recent commits
- changed files
- file history
- commit timestamps
- co-changed files

### Project Memory

Stores persistent project knowledge

### Task Intelligence

Converts a natural-language task into structured information

### Context Retrieval

Generates candidate project information relevant to the task.

### Relevance Engine

Ranks candidate context using multiple signals.
### Context Expansion

Follows useful relationships from highly relevant entities.

### Context Optimizer

Removes unnecessary information while preserving task-relevant information.

### Context Validator

Checks whether the selected context appears sufficient

### Local LLM

Assists with:

- task interpretation
- semantic classification
- ambiguity detection
- semantic relevance
- context synthesis
- context compression
- context validation

### Context Package Generator

Produces the final structured Markdown package containing the task, project understanding, relevant code, dependencies, tests, constraints, selection reasoning, and confidence.

The package can be copied directly to the clipboard for use with an AI agent.

## 7. Data Flow

Project
    |
    v
Scan
    |
    v
Classify
    |
    v
Parse
    |
    v
Build Project Model
    |
    v
Build Graph
    |
    v
Persist Project Memory

-> For a Task:

User Task
    |
    v
Task Analysis
    |
    v
Candidate Retrieval
    |
    v
Relevance Ranking
    |
    v
Graph Expansion
    |
    v
Context Optimization
    |
    v
Context Validation
    |
    v
Context Package

## 8. Incremental Updating

When a file changes:

File changed
    |
    v
Change detected
    |
    v
Re-analyze changed file
    |
    v
Update affected relationships
    |
    v
Update project memory

A manual full refresh should also be available

## 9. Interface strategy

The core engine should be independent from the UI.

Core Engine
    |
    +-- Web UI
    |
    +-- CLI
    |
    +-- API
    |
    +-- Future Agent Integrations

The web UI is the primary v1 Interface

## 10. Technology Strategy

Primary Language : Python
Core technologies :
- Python 3.13+
- uv
- FastAPI
- SQLite
- pytest
- Ruff

Potential technologies:
- Tree sitter
- Ollama
- local embeddings models
- lightweight frontend technologies

New dependencies should be introduced only when they solve a demonstrated problem.

## 11. Security and Privacy

Context Forge should be local-first.

Source code should not be transmitted externally unless explicitly enabled by user.

Secrets such as API Keys, credentials, and private keys should be detected and excluded from generated content by default.

## 12. Long-Term vision

Long-term research and development may include:

- learned retrieval
- learned ranking
- project-specific adaptation
- agent integrations
- global model
- agent outcome feedback
- reinforcement learning
- automatic context-budget optimization

## 14. Core Principle

Context Forge exists to solve one problem:

AI agents should not need to rediscover a software project's entire context every time they perform a task.

The system should build project understanding once, maintain it continuously, and use it to provide the smallest useful context required for each task.