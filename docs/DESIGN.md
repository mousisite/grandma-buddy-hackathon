# Grandma Buddy: design rules

Grandma has weak eyesight, finds phones confusing, and is often in pain. Every screen must be usable by someone who has never used an app like this, possibly with shaky hands.

## The golden rules

1. **Voice first.** The biggest thing on the home screen is the "Tap to talk" button. Everything she can tap, she can also say.
2. **One main thing per screen.** At most 3 or 4 choices visible at once.
3. **Big everything.** Body text at least 22px, headings 32px or more, buttons at least 64px tall with at least 16px between them.
4. **Words, not just icons.** Every button has a clear label ("I took it"), with an icon only as a helper.
5. **Plain language.** Short sentences, no jargon. Never show words like "error", "API", "server", "transcription", or "401".
6. **Nothing is lost by mistake.** Confirm before deleting, offer undo, no time limits, no auto-dismissing messages.
7. **Red means emergency.** Use red only for the emergency and Poison Control screens, so red always means "act now".

## Look and feel

- Calm and warm: soft off-white background, dark text, one strong friendly accent color for main buttons.
- High contrast: body text at least 7:1 against its background, buttons at least 4.5:1.
- Use the system font (Segoe UI on Windows). Line height 1.5. Left-aligned text.
- Generous spacing. Cards with large rounded corners and clear borders.
- No tiny gray text, no thin fonts, no text over photos, no animations that flash or move quickly. Respect "reduce motion".

Suggested colors (adjust with `/taste` if needed, but keep the contrast):

| Use | Color | Contrast |
|---|---|---|
| Background | `#FFFDF8` | |
| Text | `#1A1A1A` | 17.1:1 on background |
| Main buttons | `#1F4E79` with white text | 8.7:1 |
| Good or done | `#1B5E20` | 7.7:1 on background, 7.9:1 with white text |
| Heads-up | `#6B4500` | 8.3:1 on background, 8.5:1 with white text |
| Emergency only | `#B00020` with white text | 7.3:1 |

## Voice behavior

- After she taps "Tap to talk", the button changes to a large "Tap when you're done" with a clear listening indicator (gentle pulsing dot plus the word "Listening...").
- Show what she said in big text, then the reply in big text, and read the reply aloud at a slightly slow speed (`rate` about 0.9). Pick a clear, natural voice for her language.
- "Say it again" replays the last reply. A setting turns voice on or off and changes the speed.
- If the microphone is blocked, show step-by-step help with a picture of where to click "Allow".

## Home screen layout

1. Greeting: "Good morning, Rose. It's Tuesday, October 27."
2. Today's pills card (next pill, and a check mark for each one taken)
3. Giant "Tap to talk" button
4. Three big buttons: "Something hurts", "My pills", "Is this a scam?"
5. Smaller row: "My diary", "Doctor notes", "Family", "Settings"

## Screen checklist

- Works at 200% browser zoom with nothing cut off.
- Works on a tablet and at 375px wide (phone).
- Every action works with a keyboard, and focus is easy to see (thick outline).
- Spoken and new text is announced to screen readers (`aria-live="polite"`).
- Text size can be made bigger with an "A+" button.
- No horizontal scrolling.
