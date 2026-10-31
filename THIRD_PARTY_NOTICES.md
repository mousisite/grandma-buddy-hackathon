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

## Buddy's natural voice

Meta has no text-to-speech model, so Buddy speaks with an open voice model that runs on the user's own computer. None of these files are copied into this repository: the packages come from pip, and `scripts/get_voice.py` downloads the model into the git-ignored `models/` folder.

| Part | Source | License | Changes |
| --- | --- | --- | --- |
| Kokoro-82M voice model and its voices | [hexgrad/Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M); ONNX export `kokoro-v1.0.onnx` and `voices-v1.0.bin` from [thewh1teagle/kokoro-onnx](https://github.com/thewh1teagle/kokoro-onnx) (release model-files-v1.1) | Apache License 2.0 | None |
| kokoro-onnx 0.6.1 | [thewh1teagle/kokoro-onnx](https://github.com/thewh1teagle/kokoro-onnx) | MIT | None (installed with `--ignore-requires-python` on Python 3.14) |
| onnxruntime | [microsoft/onnxruntime](https://github.com/microsoft/onnxruntime) | MIT | None |
| phonemizer | [bootphon/phonemizer](https://github.com/bootphon/phonemizer) | GPL-3.0 | None (a separate package, used as is) |
| espeak-ng, through espeakng-loader | [espeak-ng/espeak-ng](https://github.com/espeak-ng/espeak-ng), [thewh1teagle/espeakng-loader](https://github.com/thewh1teagle/espeakng-loader) | GPL-3.0 | None (a separate package, used as is) |

## Test photos

`scripts/find_photos/` holds 4 photos (a living room, a kitchen counter, a sofa, and a writing desk) that `scripts/check_find.py` uses to try Find my things with the real SAM 3.1. They were painted with Meta's Muse Image for this project during the hackathon, from prompts in that script: rooms and a desk only, with no people and no writing. They are not photos of any real home.

## Fonts used by the app

| Font | Source | License | Changes |
| --- | --- | --- | --- |
| Newsreader (variable weight and optical size, upright only) | [productiontype/Newsreader](https://github.com/productiontype/Newsreader); file from the Google Fonts repository ([google/fonts](https://github.com/google/fonts/tree/main/ofl/newsreader)). Used only for the greeting and a few headlines | SIL Open Font License 1.1, Copyright 2020 The Newsreader Project Authors. Full text in `static/fonts/OFL-Newsreader.txt` | Renamed only (`[opsz,wght]` removed from the file name) |
| Figtree (variable weight, regular and italic) | [erikdkennedy/figtree](https://github.com/erikdkennedy/figtree); files from the Google Fonts repository ([google/fonts](https://github.com/google/fonts/tree/main/ofl/figtree)). Used for all other text | SIL Open Font License 1.1, Copyright 2022 The Figtree Project Authors. Full text in `static/fonts/OFL-Figtree.txt` | Renamed only (`[wght]` removed from the file names) |

## Icons used by the app

| Icons | Source | License | Changes |
| --- | --- | --- | --- |
| ban, bandage, camera, check, chevron-down, chevron-left, chevron-right, circle-alert, circle-check, circle-help, clipboard-list, house, mail, message-square-warning, mic, monitor, moon, notebook-pen, octagon-x, phone, pill, plus, scan-search, settings, shield, sun, users, volume-2, x | [Lucide](https://github.com/lucide-icons/lucide) (`icons/*.svg`), copied into the pages as inline SVG | ISC License, Copyright (c) 2026 Lucide Icons and Contributors. check, moon, and x are derived from Feather: MIT License, Copyright (c) 2013-present Cole Bemis. Full text of both in `static/LICENSE-lucide.txt` | Inlined; stroke width set to 1.75 in `static/styles.css` |
