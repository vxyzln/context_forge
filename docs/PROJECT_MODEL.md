# Context Forge - Project Model

## 1. Purpose

The Project Model is the persistent representation of everything Context Forge knows about a software project.

The Project Model is the foundation of Context Forge.

THe Project Model should represent not only what files exists, but also what those files contain, how they relate to one another, how the project has changed, and what information may be relevant to future tasks.

THe core question is:

What does the Context Forge know about this project?

## 2. Project

A Project represents one software repository or local project.

Attributes:

- id
- name
- root_path
- repository_url
- created_at
- updated_at
- default_branch
- project_type
- languages
- frameworks
- package_manager
- analysis_status

A project contains:

- directories
- files
- symbols
- relationships
- documents
- tests
- Git history
- project preferences
- task history
- context history

## 3. Directory

A directory represents a folder within the project.

Attributes:

- id
- project_id
- path
- name
- parent_id
- depth
- type

Possible types:

- source
- tests
- documentation
- configuration
- assets
- generated
- dependency
- unknown

## 4. File

A file represents a file within the project.

Attributes:

- id
- project_id
- directory_id
- path
- name
- extension
- language
- file_type
- size
- hash
- created_at
- modified_at
- last_analyzed_at
- is_generated
- is_ignored

Possible file types:

- source
- test
- documentation
- configuration
- data
- asset
- generated
- dependency
- secret
- unknown

## 5. Symbol

A symbol represents a meaningful code entity.

Examples:

- function
- method
- class
- interface
- struct
- enum
- variable
- constant
- module

Attributes:

- id
- file_id
- name
- kind
- qualified_name
- start_line
- end_line
- parent_symbol_id
- signature
- visibility

The representation should be language-independent where possible.

## 6. Function

A function is a specialized type of Symbol.

Possible information:

- name
- parameters
- return_type
- parent_class
- decorators
- calls
- called_by
- documentation

## 7. Class

A class is a specialized type of Symbol.

Possible information:
- name
- methods
- attributes
- base_classes
- implemented_interfaces
- decorators
- documentation

## 8. Relationships

Relationships connect entities in the Project Model.

Attributes:

- id
- source_id
- target_id
- relationship_type
- confidence
- metadata

Possible relationship types:

- imports
- calls
- references
- defines
- contains
- inherits
- implements
- tests
- documents
- configures
- depends_on
- generated_from
- co_changes_with

## 9. Project Graph

The project graph is the collection of relationships between project entities

It is used for:
- dependency discovery
- context expansion
- relevance calculation
- architectural understanding
- impact analysis
- future agent integrations

The graph may connect:

- files
- symbols
- functions
- classes
- tests
- documentation
- configuration
- Git history

## 10. Document

A Document represents non-code information.
Examples:
- README.md
- architecture.md
- CONTRIBUTING.md
- design documents
- documentation
- comments

Documents may be connected to code entities.

## 11. Test

Tests are represented as project entities with relationships to the code they test.

Tests can reveal:
- expected behavior
- constraints
- edge cases
- intended architecture

## 12.  Git Information

Important Git entities include:
- Commit
- FileChange
- Branch

A Commit may contain:
- hash
- author
- timestamp
- message
- parent_commits

A FileChange may contain:
- commit_id
- file_id
- change_type
- lines_added
- lines_removed

Git information can help determine:
- recent activity
- recently modified areas
- related changes
- current implementation trends

## 13. Project Memory

Project Memory contains information that persists between tasks.

Categories may include:
- structural knowledge
- architectural knowledge
- historical knowledge
- user feedback
- task history
- context history
- project preferences

## 14. Task

A Task represents a user request.

Attributes may include:
- id
- project_id
- raw_text
- intent
- target
- concepts
- constraints
- created_at

## 15. Context Package

A context package represents the information selected for an individual task.

Attributes:
-id
- project_id
- task_id
- created_at
- token_count
- confidence
- depth

It contains references to selected project entities.

A package may contain:
- task
- project summary
- relevant files
- relevant symbols
- relevant code sections
- dependencies
- tests
- documentation
- Git information
- constraints
- selection explanations

## 16. Context selection

Each selected entity may contain metadata explaining why it was selected.

Possible metadata includes:

- relevance_score
- selection_reason
- retrieval_method
- supporting_relationships
- confidence


## 17. Context Exclusion

Context Forge should also represent intentionally excluded information

## 18. Confidence

Important decisions should have confidence information.

Confidence may apply to:
- file classification
- symbol extraction
- task interpretation
- relevance
- context sufficiency

Confidence may be represented numerically from 0.0 to 1.0

## 19. language Independence

Different Language parsers should convert source code into the common Project Model.

Python parser
JavaScript parser
TypeScript parser
Java parser
C++ parser
Go parser
Rust parser
       |
       v
Common Project Model

The Project Model should represent concepts such as:
- Function
- Class
- Module
- Import
- Call
- Reference
- Dependency

rather than language-specific syntax wherever possible.

## 20. Storage

SQLite is the initial persistence layer.

The storage layer should remain separate from the rest of the context Forge.

Application
    |
    v
Storage Interface
    |
    v
SQLite

## 21. Incremental Updates

When a file changes:

File change
    |
    v
Detect change
    |
    v
Re-analyze file
    |
    v
Update symbols
    |
    v
Update relationships
    |
    v
Update project memory

Unchanged Information should not be unnecessarily recomputed.

## 22. Design Rule

The Project Model should store knowledge, not simply copies of files.

The filesystem remains the source of truth for source code.

The Project Model is the structured understanding derived from that source.

## 23. Long-Term Evolution

The Project Model may eventually include:
- semantic embeddings
- architectural concepts
- project conventions
- user preferences
- agent interactions
- task outcomes
- learned relevance
- project-specific models

These should be added only when they provide measurable value.

The Project Model should remain understandable and inspectable.