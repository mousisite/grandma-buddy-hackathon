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
| Newsreader (variable weight and optical size, upright only) | [productiontype/Newsreader](https://github.com/productiontype/Newsreader); file from the Google Fonts repository ([google/fonts](https://github.com/google/fonts/tree/main/ofl/newsreader)). Used only for the greeting and a few headlines | SIL Open Font License 1.1, Copyright 2020 The Newsreader Project Authors. Full text in `static/fonts/OFL-Newsreader.txt` | Renamed only (`[opsz,wght]` removed from the file name) |
| Figtree (variable weight, regular and italic) | [erikdkennedy/figtree](https://github.com/erikdkennedy/figtree); files from the Google Fonts repository ([google/fonts](https://github.com/google/fonts/tree/main/ofl/figtree)). Used for all other text | SIL Open Font License 1.1, Copyright 2022 The Figtree Project Authors. Full text in `static/fonts/OFL-Figtree.txt` | Renamed only (`[wght]` removed from the file names) |

## Icons used by the app

| Icons | Source | License | Changes |
| --- | --- | --- | --- |
| bandage, camera, check, circle-alert, circle-check, clipboard-list, house, message-square-warning, mic, moon, notebook-pen, octagon-x, phone, pill, plus, settings, sun, users, volume-2, x | [Lucide](https://github.com/lucide-icons/lucide) (`icons/*.svg`), copied into the pages as inline SVG | ISC License, Copyright (c) 2026 Lucide Icons and Contributors. check, moon, and x are derived from Feather: MIT License, Copyright (c) 2013-present Cole Bemis. Full text of both in `static/LICENSE-lucide.txt` | Inlined; stroke width set to 1.75 in `static/styles.css` |
