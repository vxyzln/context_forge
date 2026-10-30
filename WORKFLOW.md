# WORKFLOW WHEN DEVELOPIG Context FORGE

cf : Context Forge

This file describes the workflow I followed when developing cf.

## Tech used
1. **VS** **Code** (Main Code editor)
2. **Ghostty** (Main Terminal for Mac)
3. **uv** (Used for managing the Python environment and installing tools like Ruff and pytest)
4. **Pytest** - to run tests
5. **Ruff**  - for linting and formatting
6. **Git** - for version control

## Main Workflow :

So i would start VScode and then ghostty. i use ghostty as my terminal of choice bcz integrated terminal of vscode sucks.

---
### uv
i used uv to make the basic first structure of the project. uv commands used :
- `uv init`
- `uv python pin version_no (eg. 3.13 or 3.14)`
- `uv venv`
- `uv add package_name`
- `uv build`

THen i would open the tp*.txt or tp*.md file where i would typically store my progress and next things. I would review them to check the current state of the project because I remember some things and forget others, so I keep notes.

then i will take a look at curent progress and then decide what i needed to do today. I used a notebook to do somethings like drawing and visulazing or sometimes i js used exaclidraw in obsidian

---
### vscode
then i started the coding in vscode and i use the extensions which are -
- Atom one Dark theme
- Hackatime Time Tracker (obv)
- Markdown All in One
- Project Manager
- Python & Pylance
- Python Ident
- Error Lens
- Prettier

After starting to code, I would work through the planned changes and implementations i had to do

After completing a code implementation let's say a simple function or a simple feature, i would then jump to writing tests. i would write tests on my own for the cases i can think of and then resolve to AI for thinking of edge cases as i am very bad thinking for edge cases. then some tests for those edge cases from AI asisstance (mentioned in *AI_USAGE.md*)

then after writing a feature and test related to it i would check that i have completed its integration or implementaton.

then i would open ghostty and use the follwoing tools

### ripgrep
i would use this to find text inside files.

---
### ruff
i would use ruff for linting and formatting & commands used for that :
- `ruff check .`
- `ruff check . --fix`
- `ruff check . --fix --unsafe-fixes`
- `ruff format .`
- `ruff format --check .`

Ruff would check the code for issues such as unused variables, unused imports, and other linting problems. It would also format the code.

---
### pytest
i run those tests using pytest using these commands :
- `pytest -q` or `pytest` for full test suite
- `pytest -q file_path` for a particluar file with tests
- `pytest -q file_path::test_name` for a particular test run

---
### git
After that, I would review the code changes once again before committing and pushing them to GitHub.

git commands used :
- `git add changes_to_stage`
- `git add -p` changes_to_stage — Stage selected parts of the changes using the hunk menu.
- `git add -A`
- `git commit -a -m "commit mesaage"`
- `git rebase`
- `git --no-pager diff`
- `git diff --stat`
- `git log -n --oneline`
- `git status`
- `git status --short`
- `git branch`
- `git switch`
- `git push origin main`

these were the main git commands used during te development of the cf

---
### Commit Style -

So after reviewing all the changes i would use commit the changes.
My commit message followed a pretty conventional style
- **feat** : when added a new feature or a integration
- **refactor** : when i simplify the existing code without changing its working
- **fix** : correction for a bug , incorrect behaviour, broken test edge case or ssues
- **test** : when added test for a feature or i improved or changes the existing tests
- **chore** : maintanance which doesnt change the main code in its working like git ignore or housekeeping etc. or removing unwanted file which were accidentally committted
- **docs** : when updating documents or guidlines or usage instructions
- **perf** : when changes were made for the perfomance improvements of the tool

this was the commit style i followed through out my project. i saw it in one of the theo3.gg 's video and liked it as it provided enough to understand what this commit is about and also i saw this style in the StarDance's guide for committing changes as an option and gave it a try in this project.

I would commit after completing a feature rather than after changing a certain number of lines of code.

then i would push to github's main branch

THEN i would continue ths cycle over & over for CF.

---

SO this would be my full worflow for the development of cf.
ik this isn't all to it as sometme it would change but the major part would be this only.

ik i made many mistakes in the code itself but yes i made a new project

THNX FOR READING THIS
