---
name: web-design-guidelines
description: Review Grandma Buddy's screens (HTML, CSS, and JavaScript in static/) against Vercel's Web Interface Guidelines for accessibility and UX problems. Use when asked to review the UI, check accessibility, or audit the design, and before running /senior-friendly-ui on a finished screen.
metadata:
  author: vercel (adapted for Grandma Buddy)
  version: "1.0.0-gb"
---

# Web Interface Guidelines (local copy)

Adapted from Vercel's `web-design-guidelines` skill (github.com/vercel-labs/agent-skills, MIT license). The original fetches its rules from the internet on every review. This copy reads them from `rules.md` in this folder instead, copied from github.com/vercel-labs/web-interface-guidelines in October 2026 (MIT license, see `LICENSE`).

## How to review

1. Read `rules.md` in this folder. It has every rule and the output format.
2. Read the files to review. If none were named, review everything in `static/`.
3. Check the files against every rule. This app is plain HTML, CSS, and JavaScript, not React or Tailwind, so apply each rule's intent. For example, `focus-visible:ring-*` means a clearly visible `:focus-visible` outline in CSS, and `onKeyDown` means a keyboard event listener.
4. Report findings in the `file:line` format from the end of `rules.md`, grouped by file.
5. Where `docs/DESIGN.md` is stricter than a rule (bigger text, bigger buttons, higher contrast, red only for emergencies), `docs/DESIGN.md` wins.
6. Fix the findings, then run `/senior-friendly-ui` on the same screens.
