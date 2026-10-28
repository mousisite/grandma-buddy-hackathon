# Third-party notices

Grandma Buddy's coding agent uses some skills written by other people. Each one keeps its license file in its folder under `.claude/skills/`. They are instructions and helper scripts for the coding agent, not part of the app itself.

| Skill | Source | License | Changes |
| --- | --- | --- | --- |
| systematic-debugging | [obra/superpowers](https://github.com/obra/superpowers) v7.0.1 | MIT, Copyright (c) 2025 Jesse Vincent | None |
| test-driven-development | [obra/superpowers](https://github.com/obra/superpowers) v7.0.1 | MIT, Copyright (c) 2025 Jesse Vincent | None |
| verification-before-completion | [obra/superpowers](https://github.com/obra/superpowers) v7.0.1 | MIT, Copyright (c) 2025 Jesse Vincent | None |
| requesting-code-review | [obra/superpowers](https://github.com/obra/superpowers) v7.0.1 | MIT, Copyright (c) 2025 Jesse Vincent | None |
| receiving-code-review | [obra/superpowers](https://github.com/obra/superpowers) v7.0.1 | MIT, Copyright (c) 2025 Jesse Vincent | None |
| webapp-testing | [anthropics/skills](https://github.com/anthropics/skills) | Apache License 2.0 | `scripts/with_server.py` changed for Windows (busy-port check, server output to a log file, stopping the whole server process tree); a "Windows and this project" section added to `SKILL.md` |
| web-design-guidelines | Skill: [vercel-labs/agent-skills](https://github.com/vercel-labs/agent-skills) (MIT). Rules: [vercel-labs/web-interface-guidelines](https://github.com/vercel-labs/web-interface-guidelines) | MIT, Copyright (c) 2025 Vercel Labs | `SKILL.md` rewritten to read the rules from a local `rules.md` instead of fetching them, and adapted to plain HTML, CSS, and JavaScript |

The skills `meta-model-api`, `safety-check`, `senior-friendly-ui`, and `demo-prep` were written for this project.

## Fonts used by the app

| Font | Source | License | Changes |
| --- | --- | --- | --- |
| Lexend (Latin subset, variable weight 300 to 800) | [googlefonts/lexend](https://github.com/googlefonts/lexend), a typeface designed to make reading easier; file from Google Fonts | SIL Open Font License 1.1, Copyright 2018 The Lexend Project Authors, Reserved Font Name "RevReading Lexend". Full text in `static/fonts/OFL-Lexend.txt` | None |
