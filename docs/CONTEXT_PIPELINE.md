# Context Forge - Context Pipeline

## 1. Purpose

The Context Pipeline transforms a user's task and a project's persistent knowledge into a compact context package designed for an AI agent.

The central objective is:

> Provide maximum useful context with minimum unnecessary context.

## 2. Input

The pipeline accepts:

- Project
- User Task
- Optional Constraints
- Optional Context Budget

Example:

Project:
~/Projects/my_app

Task:
"Fix the scrolling on the settings page."

Mode:
Automatic

Budget:
Automatic

## 3. Pipeline Overview

User Task
    |
    v
Task Understanding
    |
    v
Task Validation
    |
    v
Candidate Generation
    |
    v
Multi-Signal Retrieval
    |
    v
Relevance Ranking
    |
    v
Graph Expansion
    |
    v
Context Depth Selection
    |
    v
Context Optimization
    |
    v
Context Validation
    |
    v
Context Packaging
    |
    v
User Review
    |
    v
Copy / Export

## 4. Stage 1 - Task Understanding

Task Understanding may use:
- keyword analysis
- project structure
- symbol information
- local LLM reasoning

The output should be a structured task representation containing:
- intent
- target
- concepts
- requested action
- constraints
- ambiguity

## 5. Stage 2 - Task Validation

The system determines whether the task is sufficiently clear

Possible task states:
- clear
- ambiguous
- insufficient

## 6. Stage 3 - Candidate Generation

The system searches the Project Model for possible relevant entities.

Candidate sources include:
- files
- directories
- symbols
- functions
- classes
- documentation
- tests
- Git history

Candidate generation should prioritize recall.

## 7. Stage 4 - Multi-Signal Retrieval

Context Forge should not rely on one retrieval strategy.

### Keyword relevance

Matches:
- task words
- file names
- symbol names
- directory names
- documentation

### Semantic relevance

Determines conceptual similarity.

### Structural relevance

Uses Project structure

### Symbol relevance

Considers functions, classes, imports, and references.

### Dependency relevance

Considers dependencies of relevant entities.

### Git relevance

Considers recent relevant changes.

### Documentation relevance

Considers documentation describing relevant subsystems.

## 8. Stage 5 - Relevance Ranking

Candidates receive a relevance score.

Conceptually:
relevance =
    task_similarity
  + semantic_similarity
  + structural_relevance
  + dependency_relevance
  + symbol_relevance
  + graph_relevance
  + git_relevance
  + documentation_relevance
  + feedback_signal

Initial weights should be configurable and evaluated using benchmarks tasks.

## 9. Stage 6 - Graph Expansion

The highest-ranked entities become seeds.

Expansion should stop when:
- relevance becomes too low
- maximum graph depth is reached
- token budget is reached
- enough context has been collected

## 10. Context Depth

### Minimal

Only directly relevant information.

### Recommended

Includes:
- direct code
- important dependencies
- relevant configuration
- tests
- useful documentation

### Deep

Includes:
- broader architecture
- additional dependencies
- documentation
- Git history
- surrounding subsystems

## 11. Automatic Context Depth

The engine should normally determine the appropriate depth automatically.

Factors may include:
- task complexity
- number of candidate files
- dependency depth
- ambiguity
- project architecture
- estimated token cost
- confidence

The user may override the automatic decision.

## 12. Stage 7 - Context Optimization

The system removes unnecessary information.

Optimization may happen at:
- project level
- directory level
- file level
- section level
- symbol level
- function level
- class level

Instead of including an entire 1,000-line file, Context Forge may include only the relevant class or functions.

## 13. Token Budget

Token usage is an optimization constraint.

Possible modes:
- automatic
- minimum
- recommended
- custom budget

Objective: maximize usefulness, subject to token budget.

If the budget risks excluding important information, the system should warn the user.

## 14. Stage 8 - Context Validation

Before generating the final package, the system evaluates:
- Is the task target represented?
- Are required dependencies present?
- Are important configuration files missing?
- Is the task ambiguous?
- Are there conflicting implementations?
- Is confidence sufficiently high?

If significant uncertainty exists, the user should be asked for clarification.

## 15. Context Sufficiency

The system should distinguish between:

- sufficient context
- probably sufficient context
- insufficient context

If critical information appears to be missing, Context Forge should not silently generate a low-quality package.

It should either expand the context or ask the user for clarification.

Possible states:

High confidence:
Likely sufficient.

Medium confidence:
Possibly sufficient; some information may be missing.

Low confidence:
Ask the user before generating final context.

## 16. Stage 9 - Context Package

The final package should be structured for an AI agent.

Example:

#Context Forge — Agent Context

##Task

Fix the scrolling behavior on the settings page.

##Task Interpretation

Intent:
Bug fix

Target:
Settings page

Primary concepts:
Scrolling, overflow, container

##Project Area

frontend/settings/

##Architecture

SettingsPage
    |
    v
SettingsPanel
    |
    v
ScrollContainer

##Relevant Files

###SettingsPage.tsx

[Relevant code]

Reason:
Direct task target.

###ScrollContainer.tsx

[Relevant code]

Reason:
Contains the scrolling implementation.

###settings.css

[Relevant code]

Reason:
Contains overflow-related styling.

##Relevant Dependencies

...

##Relevant Tests

...

##Recent Git Changes

...

##Constraints

...

##Excluded Context

backend/
database/
authentication/

Reason:
No meaningful relationship to the requested task.

##Context Statistics

Files selected: 7
Estimated tokens: 6,421
Confidence: 93%

Example Over.

But in Markdown Format

## 17. Selection Explanation

Context Forge should store the reasoning behind selection.

Each selected entity should be associated with:
- relevance score
- selection reason
- retrieval signals
- supporting relationships
- confidence

The default interface may hide these details

## 18. User Feedback

Users can provide corrections.

correction becomes a project-specific feedback signal.

## 19. Context History

Generated packages should be stored.

This allows Context Forge to understand:
- what tasks were previously performed
- what context was selected
- what the user corrected
- what project areas were previously relevant

## 20. Local LLM responsibilities

The local LLM assists the pipeline rather than replacing it.

Potential uses:
- task interpretation
- semantic classification
- ambiguity detection
- semantic relevance
- context synthesis
- context compression
- context validation

The LLM should not be trusted as the sole source of structural facts.

## 21. Failure Handling

### Invalid project

Show that the project cannot be read.

### Unsupported language

Show that the language was detected but a parser is unavailable.

### Ambiguous task

Ask the user to clarify.

### Insufficient context

Warn that an important dependency may be missing.

### Token budget too small

Warn that the selected budget may exclude required information.

### Local model unavailable

Context Forge should still function using deterministic retrieval.

## 22. No-LLM Mode

Context Forge should work without an LLM.

It should still provide:
- repository scanning
- file classification
- code parsing
- graph analysis
- keyword retrieval
- structural retrieval
- Git analysis
- ranking
- context generation

The LLM should improve intelligence rather than make the application completely dependent on it.

## 23. Future Learned Retrieval

The system can eventually collect:
- task
- candidate entities
- selected entities
- user corrections
- agent outcome
- token usage

This can become training data.

A future ranking model could predict:

Task + Candidate
        |
        v
Relevance probability

## 24. Future Reinforcement Learning
A future system could model context selection as a decision process.

Task
  |
  v
Select context
  |
  v
Agent performs task
  |
  v
Observe outcome
  |
  v
Reward
  |
  v
Improve selection policy

Potential positive signals:
- successful task
- necessary context retrieved
- low token usage
- low latency

Potential negative signals:
- missing required context
- excessive irrelevant context
- failed task
- unnecessary token usage

Reinforcement learning should only be pursued if experiments show that it provides an advantage over supervised learning and ranking methods.

## 25. Evaluation
Context Forge should be evaluated using a benchmark of realistic tasks.

Measure:
- retrieval recall
- retrieval precision
- token efficiency
- latency
- context quality
- agent usefulness
- user correction rate

## 26. Baseline Comparison

Compare Context Forge against:

### Baseline 1

Entire repository supplied to the agent.
### Baseline 2

Keyword-based file search.

### Baseline 3

Semantic search.

### Baseline 4

Context Forge.
This provides measurable evidence of improvement.

## 27. Core Success Criterion

Context Forge succeeds when:

Agent receives less information
        +
Agent understands the task better
        +
Agent spends less time exploring
        +
Agent still has the information required

The ultimate objective is:
Maximum task usefulness with minimum unnecessary context.

## 28. Long-Term Pipeline

                PROJECT
                   |
                   v
          Project Understanding
                   |
                   v
            Project Memory
                   |
                USER TASK
                   |
                   v
            Task Intelligence
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
          Context Depth Model
                   |
                   v
          Context Optimization
                   |
                   v
          Context Validation
                   |
                   v
           Context Packaging
                   |
                   v
               AI AGENT
                   |
                   v
              Task Result
                   |
                   v
                Feedback
                   |
                   v
             Future Learning