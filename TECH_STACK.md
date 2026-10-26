# Tech Stack Used

cf : Context Forge

This document lists the technologies, dependencies, and development tools used to build Context Forge (cf). So take a look at it.

## Details/Core principles kept in mind choosing these tools & dependencies:

- The cf cli tool is desiged run the cli commands like analyze on the user system only and not touch the internet.
- Users can invoke the functionality of the cf using the CLI
- cf 's strcture was divided into seprate files so that there is not just one major file
- Tests written for cf help with validating components, integration beahaviour , and CLI working.
- Standard python packaging and dev tools provide a consistent foundation for installing and developing.


## dependencies :

- **Python** : Core language
- **SQLite** : For database and persistent data storage

## Tools used to develop cf :
- **VSCODE** : primary code editor with hackatime set up in it
- **Sublime** Text : used for editing code for a brief amount of time bcz vscode was bugging out (mentioned in devlog no. &34)
- **NeoVim** : used for editng code for a brief time amount of time js like Sublime text bcz vscod was bugging out & wanted to try the best editor acc. to the Primeagen ( mentioned in devlog no. 30 & 34)
- **Ghostty** : my main terminal when developing cf.
- **Antigravity** : used for ai-assisted development (See **AI_USAGE.md** for this)
- **uv** : tool used for managing python enviroment and package management
- **Hatchling** : for Python package build backend
- **pytest** : used for running tests seamlessly (helped me a lot)
- **Ruff** : used for code  formatting and linting of code
- **Git** : version control and github repo management

To see how i used the tools and developed workflow, see **WORKFLOW.md**