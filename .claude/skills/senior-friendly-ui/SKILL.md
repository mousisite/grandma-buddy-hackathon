---
name: senior-friendly-ui
description: Check and fix any Grandma Buddy screen against pro-app standards (Apple-level legibility, touch, contrast, focus, and motion) so an older adult with weak eyesight and shaky hands can use it easily and it still looks like a flagship app. Use when creating or changing anything in static/ (HTML, CSS, or JavaScript that affects what she sees or hears).
---

# Senior-friendly screen check

Grandma Buddy must look like a flagship app and still be easy for an older adult with weak eyesight and shaky hands. Run this before marking any screen done. Fix problems instead of just listing them, then report a short pass/fail list in plain words.

## Steps

1. **Re-read `docs/DESIGN.md`.** It has the design system: tokens, type, layout, the orb, motion, and every screen.
2. **Size.** Body text at least 17px; captions and tab labels at least 13px, and only for short labels. Headings follow the type scale. "Text size" in Settings (Standard, Large, Largest) must grow everything without breaking the layout.
3. **Touch.** Every tap target at least 44 by 44px (Apple's guideline), with space between neighbors. The main actions (Talk to Buddy, Take, call buttons) are 56px or taller.
4. **Contrast.** Text at least 4.5:1 against its background, in light AND dark mode; large text (24px+) and icons at least 3:1. Measure with `scripts/check_contrast.py`, not by eye.
5. **Words.** Every button has a text label (icon-only only with an `aria-label`, and only for obvious controls like Done). No jargon, no technical words ("error", "API", "server", "transcribe", status codes). Messages are short, warm, specific, in sentence case, and say what to do next. No arrows on buttons.
6. **Choices.** One clear main action per screen. Removing something asks first (a sheet) and can be undone.
7. **Voice.** Anything she can tap, she can also say. Replies are read aloud (`static/speech.js`) and shown large, with "Say it again". Listening and thinking are obvious (the orb plus words).
8. **Red means emergency.** `--danger` only on the emergency and Poison Control screens. A warning uses `--warning` with words and an icon, never color alone.
9. **Accessibility.**
   - Every control works with the keyboard, and focus is a clearly visible ring in both themes.
   - New text uses `aria-live="polite"` (toasts, replies, Buddy's state).
   - `prefers-reduced-motion` and "Calm motion" replace movement with simple fades; the orb stays still but glowing. Nothing flashes.
10. **Sizes.** Check at 390px (phone), 768px (tablet), 1440px (desktop), and 200% browser zoom, in light and dark: nothing cut off, no horizontal scrolling.
11. **Friendly failures.** Microphone blocked, internet down, and slow AI each show a clear, kind message with what to do.

## Report format

```
Screen check: <screen name>
PASS  Text sizes (body 17px, smallest label 13px)
PASS  Contrast (light: body 16.0:1, secondary 6.5:1; dark: body 16.1:1, secondary 7.9:1)
FIXED Done was 36px tall -> 44px
PASS  Works at 390px, 768px, 1440px, and 200% zoom, light and dark
Result: PASS
```
