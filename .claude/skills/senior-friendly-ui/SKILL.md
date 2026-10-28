---
name: senior-friendly-ui
description: Check and fix any Grandma Buddy screen so an older adult with weak eyesight, shaky hands, and little tech experience can use it easily. Use when creating or changing anything in static/ (HTML, CSS, or JavaScript that affects what she sees or hears).
---

# Senior-friendly screen check

Grandma struggles with phones and has weak eyesight. Run this before marking any screen done. Fix problems instead of just listing them, then report a short pass/fail list in plain words.

## Steps

1. **Re-read `docs/DESIGN.md`.** It has the golden rules, colors, sizes, and home screen layout.
2. **Size and spacing.** Body text 22px or more, headings 32px or more, buttons at least 64px tall with at least 16px between tap targets. No text smaller than 18px anywhere.
3. **Contrast.** Body text at least 7:1 against its background, button text at least 4.5:1. Check the actual colors in `static/styles.css`, not guesses.
4. **Words.** Every button has a text label. No jargon, no technical words ("error", "API", "server", "transcribe", status codes). Messages are short, kind, and say what to do next.
5. **Choices.** One main action per screen, at most 3 or 4 choices visible. Destructive actions ask "Are you sure?" and can be undone.
6. **Voice.** Anything she can tap, she can also say. New replies are read aloud (`static/speech.js`) and shown in big text, with a "Say it again" button. The listening state is obvious ("Listening..." plus a gentle indicator).
7. **Red means emergency.** Red is used only on the emergency and Poison Control screens.
8. **Accessibility.**
   - Every control works with the keyboard, and focus is a thick, visible outline.
   - New text uses `aria-live="polite"`. Images have `alt` text.
   - Respect `prefers-reduced-motion`. Nothing flashes.
9. **Sizes.** Check at 375px wide (phone), a tablet width, and 200% browser zoom: nothing cut off, no horizontal scrolling.
10. **Friendly failures.** Microphone blocked, internet down, and slow AI each show a clear, kind message with what to do.
11. **Polish.** Run `/taste` on the screen and apply its suggestions only if they keep every rule above.

## Report format

```
Screen check: <screen name>
PASS  Text sizes (smallest is 20px)
PASS  Contrast (body 17.1:1, buttons 8.7:1)
FIXED "Error 500" message -> "Sorry, something went wrong. Please try again."
PASS  Works at 375px and 200% zoom
Result: PASS
```
