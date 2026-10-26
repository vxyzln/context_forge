# AI USAGE

cf : Context Forge

This document explains how AI was used in the development of the cf.

I used Antigravity to implement changes whenever AI assistance was involved. AI helped me with parts of the development, but the project was not generated entirely by AI. Some AI usage is also documented transparently in Devlogs 19 and 30.

## AI for teststests

Some Tests were generated using AI (NOT ALL).

At start, i didn't knew much about writing tests for a project like this, so I used AI to help me think of edge cases i might have missed. As i gained experience, i learned to write myself and wrote them independently and some with AI.

AI helped me identify additional test cases and improve test coverage. Tests validate the code, but they are separate from the application's actual source code and core logic.

test isn't a part of the actual source code written and logic applied by me.

## Ai to write and remove code

I've used AI for 4 times in the journey of development of cf.

### 1. Moving from Qwen3 to Qwen2.5-Coder

iInitially, I chose Qwen3 8B for my idea of Context Forge (Devlogs 1–29). However, I struggled to get it working correctly. After going deep in the issue, I found that its reasoning behaviour was not for the kind of implementation i wanted.

I decided to switch models and used AI to remove the parts that were no longer needed while keeping most of the existing foundation for Qwen2.5-Coder 7B.

### 2. Removing the Reasoning Feature

I then continued developing cf around Qwen2.5-Coder 7B,I encountered a major problem ,a feature to explain why a particular candidate was selected and etc. and qwen would reason for it but qwen was not working in that reasoning feature perfectly and i wasn't able to wrap my head around it so i had to ditch the reasoning thing and I decided to remove that feature and used AI to clean up the related code and remove unnecessary logic.

### 3. The Great Pivot

Even after switching models, I continued facing problems. the model wasn't behaving correctly like i wanted, the model was hallucinating so much that i was fed up with it
After considering the problems, I decided to change the project's direction from an AI-based context maker to a more deterministic memory vault, for me this seemed a better idea and i did the `GREATPIVOT` (devlog no. 30).
I used AI to remove code that was no longer needed. Around 8,000 lines of code were removed during this transition.

### 4. Testing, Packaging, and Final Cleanup

When it was time to test and package the project, I used AI to help with Python packaging because I had not built a package before.

I also used AI to review the repository for redundant logic and unwanted comments or docstrings. Moreover,i used Ai and AI helped me create the example projects under test_projects, which reviewers and other users can use to explore how Context Forge works.

Tests can be seen under the test-project folder.

---
so these were the times i used AI assistance for my project.

`AI usage was kept as minimal as i possibly could do so people won't call it a AI slop and genuinely see it as a good project.the project should show my own decisions and work rather than saying its all AI generated`

Keep in mind, All AI-generated changes were reviewed before committing and pushing I did not blindly accept changes because I wanted to make sure they did not break existing functionality

this is all for the AI usage in my repo and thnx for reading.