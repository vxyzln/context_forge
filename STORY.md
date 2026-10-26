# Yap of my Whole Journey By none other than Me

cf : Context Forge

THis is a development journal for cf

---

this StarDanceis my first YSWS and probably the lasrt. I found out about it on Instagram in August, registered, and immediately started brainstorming ideas. I looked at problems around my house, repetitive workflows on the internet, and things that annoyed me while using technology.

So, I came up with the idea of building a context generator for AI. had previously vibe-coded some projects, which are on GitHub but private. During those projects, I noticed that AI agents cwould lose track of context within their limited context windows(not the case for today's frontier models btw). They would sometimes make changes without properly understanding the rest of the project.Based on my understanding at the time, I decided to build Context Forge. Originally, it was meant to be an agentic context maker that would use a local language model to help prepare useful context for AI coding agents.

I started working on Context Forge in late August. I was very passionate about the project and immediately began planning its features, architecture, technology stack, data storage, and overall workflow. I wanted to figure out what tools I needed, how the different components would communicate, and how the entire system would work.

Of course, academics were also important, so I had to balance schoolwork with development. Still, I kept implementing features and improving the project. The architecture and design were not always right on the first attempt. I had to rethink parts of the design, revise my plans, and change things when my original ideas did not work as expected.

I was learning while building. Sometimes I knew what I wanted the software to do but did not know the best way to implement it. Other times, I implemented something and only discovered its limitations when I tested it.

## The First Major Problem: Qwen3 8B

My initial plan involved using Qwen3 8B, a local language model. I wanted the model to help generate context for coding agents. However, as I worked on the implementation, I realised that the reasoning-oriented approach was making the system more complicated than I wanted.

I did not want the project to become unnecessarily dependent on complicated model behaviour. I wanted something I could understand, develop, test, and maintain locally. Because of these difficulties, I moved to Qwen2.5-Coder 7B.

I then built much of the architecture around that new model. I continued implementing the features, designing the data storage, and working on the rest of the system. At that point, I had already invested considerable time in the original direction.

## The Second Major Problem: The Great Pivot

The next problem was that the model was generating reasoning and candidate responses that were too large for the kind of context output I wanted. I struggled to make the generated results consistently concise and useful.

This was an important turning point. I could have kept adding more complexity to control the model's output, but that would have made the project harder to maintain. Eventually, I decided to rethink the purpose of Context Forge itself.

This became what I refer to as the Great Pivot.

Instead of making Context Forge primarily an AI-powered context generator, I shifted it towards becoming a deterministic repository intelligence and persistent memory tool. Rather than depending on a language model to understand and summarise everything, Context Forge would analyse Python source code, build a structured representation of the repository, and make that information available through CLI commands.It was for devs and agents to use through CLI

This changed the direction of the project. The software would maintain structured information that could be queried repeatedly.

The earlier work was not completely wasted. Some of the planning, architectural thinking, and work on storing repository information provided a foundation for the new direction. However, the pivot still required substantial rethinking and implementation.I ued AI to rip of the not needed code.

## Building Memory Vault : the current product

After the pivot, Context Forge became a local repository intelligence and memory tool. It could analyse a Python repository, store information in SQLite, and provide commands for inspecting files, symbols, relationships, dependencies, architecture, and potential change impacts.

I wanted the cf to asnwer questions such as what parts of code are related to this file or thhis function etc. things or where is this particluar symbol defined and what should i see beforemaking a change. the new path felt managebale. However it wasnt esay. i still has to work through the new overhaul and plan new things and many old things are still present in the architecture. i still had to do the bug fixing, rthink design decision and make sure that diff parts worked together. u will also find old variable names as they were never changed.

## Problems & Mistakes

This is development development, sometimes a change that seemed small affecting to the project affected several other parts of the repository code. I would modify something in just one file and then discover that other modules or tests or interfaces that depend on that thing are changing and not working perfectly. The terminate software is interconnected, a change is not limited to one file. I have made projects before, but this was a new experience to work in a tool like that, a CLA tool like this

There are times when my working copy would be difficult to recover. I had to use Git to get back to a known state, like git reset, and I learned that version control is very important than this. It is also suitable to track changes, investigate mistakes, and recover from bad edits. Looking back, I see like important it is understand a git command or like having a version control, like, how is it important? And before running any commands, how is it important

The length experiments, the large language model experiments taught me another lesson that model can be useful in theory but still be poor fit for a perfect constraint. Choosing a model is not just about its capabilities, it should matter on its like output, its liability, its resource requirements, integration, complexity, all matters, like everything matters. We can't just see that this model fits on a machine and we can use that like the Quent 3 was a good model, but it couldn't I wasn't able to constrain it to a thing that I wanted

Testing was also a major part of each epidemic work once did not prove that it was correct. I had to test different cases, fix failures, check whether changes block existing behavior, and think of many edge cases. So I began to appreciate why a large attest to suit and repeatable validation maintained in a software project. I learned the main importance of the test folder, the tests that were made

## Testing beyind my own code i.e. on real repo

We should tested the tool on real Python repositories, not the projects or features I used while developing it. Some new ones from GitHub I cloned them and tested on them. This was important because I had to use it on a real repositories that contain unexpected structures, edge cases, historical data. Yes, that a control example might not expose. Testing option my own could help me evaluate whether context forge behaved as expected in a less controlled environment. Also reminded me passing test does not automatically mean a project is perfect. There can always be cases that cannot be covered Like the timestamp issue that I have mentioned in my commit

## AI Assistance

I used during parts of development process. I have written down about the AI usage in the AI_USAGE.md. You can check it out.

AI helped me with parts of work, but I had to still make major decisions about the project's direction, investigate problems, evaluate proposed changes, and like see all the changes AI made are they perfect, or do I need to change, etc. I need to determine whether the resulting software behaved as intended, the great pivot thing in the developed number 30 around reflected how understanding of project of the problem changed as I worked on the project

## WHAT I LEARNED FROM ALL THIS CODING AND WORKING ON A Project

This was a 70-hour project, and I learned far from building it than I expected. I gained practical experience with Python, CRI design, SQLite, testing, debugging, Python packaging, a Git, and the process of maintaining a growing code base. Also, learned that making a feature bug is not only a part of software development. Implementation has to fit architecture, existing behavior, and tests need to cover important cases also. Sometimes the right solution is not to add another layer of complexity but to be considered as the original approach. Working with local language models taught me to evaluate tools against real constraints. What exactly is needed for the virtual port is not assuming that a technical impressive approach is necessarily the right one. I also became more aware of the difference between software that depends on centered answers, and software's behavior can be tested deterministically.

So I'm not a professional, but I am sure there are mistakes in the code base of the whole tool and I have not noticed. I don't consider perfect, but I understand much more than what I did when I started the project about Python, about tools, about libraries, anything you say. And this is, I guess, one of the most valuable things that I can take out of this project

## Where i am now after doing the project

This came a long way from its original idea. What began as an agentic context generator now has become a deterministic depository intelligence, a memory tool, kind of there were failed experiments, changes in directions, bugs. Yes, very issues with large language models. Not every decision was right the first time, and not everything survived. But each thing taught me something that I can use in the future, and I used that also. I learned from the mistakes, I valued the practical experience of building, breaking, and debugging, testing, improving, etc. etc. A real project is much more valuable than learning theory alone. Context force is a result of that process, and I think I learned while building it are the most important to me as the final product

I believe what I learned during the development is far more valuable than the project itself or the reward itself.

## My Views on HackClub and Stardance:

What the community, hack club community is doing is very very good. They are encouraging kids to build software products, final products, tools, hardware, software, whatever you say. They are rewarding them. You cannot make a teenager do something by forcing them, to make them do something , we can be giving them a reward a gift to them. Yes, which would make them like which would encourage them to learn new things, do some things out of their comfort zone, much more things. So, whatever the stardance community, the HackClub community is doing, I think it's very great and they should do keep doing this in future. The events were very great. This isn't the first event, but I think if I was known to this event long before from a couple years ago, I would have made many more projects, learned many more things. Yes, but I think this event was a very great event for me. I give a standing ovation to them the people building this, people doing this, the reviewers, the shipwrights, the fraud squad and the community. Yes, etc. things the communities, the people behind this. I am very grateful to them for giving me such an opportunity to be a part of such a great event.

THANKS FOR HAVING ME

And that's it. This is Context Forge, my journey, my mistakes, my learnings, and the time I spent building something from an idea into a real project. It isn't perfect, and neither was the journey, but I built it, learned from it, and I'm proud of how far I've come. Whatever happens next, this experience will stay with me far longer than the project itself.
