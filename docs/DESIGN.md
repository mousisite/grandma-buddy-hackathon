# Grandma Buddy: design rules

Grandma has weak eyesight, finds phones confusing, and is often in pain. Every screen must be usable by someone who has never used an app like this, possibly with shaky hands.

## The golden rules

1. **Voice first.** The biggest thing on the Today screen is the "Tap to talk" voice box. Everything she can tap, she can also say.
2. **One main thing per screen.** At most 3 or 4 choices visible at once.
3. **Big everything.** Body text at least 22px, headings 32px or more, buttons at least 64px tall with at least 16px between them. No text under 18px.
4. **Words, not just icons.** Every button has a clear label ("I took it"), with an icon only as a helper.
5. **Plain language.** Short sentences, no jargon. Never show words like "error", "API", "server", "transcription", or "401".
6. **Nothing is lost by mistake.** Confirm before deleting, offer undo, no time limits, no auto-dismissing messages. Unsaved form entries stay when she moves to another screen and back.
7. **Red means emergency.** Use red only for the emergency and Poison Control screens, so red always means "act now".

## Look and feel

Buddy looks like the AI assistants people already know (ChatGPT, Perplexity, Gemini), made big and calm. The user chose this style on October 26, 2026, after trying several others. All colors and sizes live at the top of `static/styles.css`.

- **A quiet page.** White by day (6 AM to 6 PM), near-black at night. `app.js` sets `data-time="day"` or `"night"` on the page and colors the phone's top bar to match.
- **One big centered question** on Today: the date, the greeting with her name, and Buddy's words underneath, appearing word by word like an AI answer.
- **The voice box.** A wide white box with "Tap to talk" and a round black voice button, with a soft blue glow behind it. The whole box is the button.
- **Suggestion cards** under the voice box, like the cards under an AI app's input: light gray, line icon, title, and a second line.
- **A sidebar** on big screens (1000px and up): Buddy's mark, then Today, My diary, My pills, Doctor notes, Scam check, Family. On phones and upright tablets the same menu slides in from the left when she taps "Menu".
- **Other screens** look like a settings page: "Back to Today" at the top left, a big left-aligned heading, a short line under it, then light gray cards.
- **An honest note** at the bottom of every screen: Buddy is an AI helper, it can't give medical advice, and "call 911" is a real phone link.
- Almost no color. No red in the normal app. No tiny gray text, no thin fonts, no text over photos, no flashing.

### Colors

Measured October 26, 2026. If a color changes, keep the contrast at least as high: body text at least 7:1, buttons at least 4.5:1.

| Use | Name in styles.css | Day | Night |
|---|---|---|---|
| Page | `--page` | `#FFFFFF` | `#111216` |
| Cards, sidebar, voice box surround | `--soft` | `#F4F4F6` | `#1C1D22` |
| Thin lines | `--border` | `#E4E4E9` | `#2B2D34` |
| Main text | `--text` | `#0D0E12` (19.3:1) | `#ECEDEF` (16.0:1) |
| Second lines, hints, form entry borders | `--text-2` | `#4B5060` (8.0:1, 7.3:1 on cards) | `#B4B8C2` (9.4:1, 8.5:1 on cards) |
| Voice button, call buttons, Save | `--voice` | `#0D0E12`, white icon/words 19.3:1 | `#ECEDEF`, dark words 16.5:1 |
| Focus ring, small accents | `--accent` | `#2E46D9` (7.0:1) | `#9DB0FF` |
| Glow behind the voice box | `--glow-1`, `--glow-2` | soft blue and violet | a little dimmer |

**Red is only for emergency screens.** The emergency and Poison Control screens use `#B00020` with white words (7.3:1). The crisis screen is calm pale blue (`#EEF1FF`, dark words 17:1), deep blue at night.

### Font and text sizes

- **Font:** Lexend, designed to make reading easier. Self-hosted in `static/fonts/` (SIL Open Font License 1.1). Falls back to Segoe UI.
- Line height 1.5 for reading. Today's question is centered; everything else is left-aligned. Headings wrap evenly (`text-wrap: balance`).
- All sizes use `rem`, so "Bigger words" grows everything at once: normal (100%), big (115%), biggest (130%). The choice is remembered on this device only.

| What | Size |
|---|---|
| Greeting, screen headings, Buddy's short answers | 40px |
| Section headings ("Set up Buddy") | 32px |
| Buddy's long answers (over 12 words), safety screen words | 28px |
| "Tap to talk", what she said | 26px |
| Body text, form labels and entries, card titles | 22px |
| Menu items, call buttons, Save | 20px |
| Second lines, "Back to Today", "Bigger words", hints, the honest note | 18px (the smallest allowed) |

### Shapes and spacing

- **Round pills** for single buttons: "Bigger words", "Menu", call buttons, Save. At least 64px tall.
- **Cards** have 24px rounded corners and 20 to 22px inside padding. Form entries and choices have 16px corners.
- **Form entries** have a 2px border in `--text-2`, so they're easy to find. An entry the server sent back gets a 4px dark border and a note right under it saying how to fix it (never red).
- **Spacing:** 16px between tap targets, 20px page padding on phones.
- **Icons:** simple line drawings, same color as the words, sized with the text so they grow with "Bigger words". Always next to a word.
- **Focus ring:** a 4px outline in `--accent`, 4px away from the button.

### Motion

Every movement tells her something: the app is ready, it's listening, it's working, or her words arrived. One easing everywhere (`--ease`: a quick start that slows down gently).

| When | What moves | How long |
|---|---|---|
| The app opens | The question, voice box, and cards rise in one after another | under 1 second |
| Waiting for her | The glow behind the voice box breathes; a soft ring pulses out of the voice button | 6 s breath, 2.8 s pulse |
| Listening | Live bars in the voice button and the glow follow her voice; a colored ring runs around the box; everything else fades to 30% | live |
| Working | Buddy's words shimmer; a small spinner turns | 1.6 s |
| Her words arrived | The voice button nods; "You said" rises in; Buddy's answer appears word by word | under 1.2 s |
| Another screen opens | It rises in gently; the phone menu slides in from the left | 0.3 to 0.4 s |
| Bigger words | Text grows smoothly | 0.3 s |

- Animate only `transform` and `opacity`, so it stays smooth on tablets.
- Mouse users see a soft outline or lift when pointing at something. Touch screens don't, so nothing stays highlighted after a tap.
- **Reduced motion:** if her device asks for less motion, nothing slides, spins, grows, or breathes. Fades and color changes still happen.

## Voice behavior

- After she taps "Tap to talk", the label changes to "Tap when you're done", Buddy's words say "Listening…", and the bars move with her voice.
- Show what she said in big text, then the reply in big text, and read the reply aloud at a slightly slow speed (about 0.9). Pick a clear, natural English voice.
- "Say it again" replays the last reply. On the Family screen, a family member can turn reading aloud off and pick Slower, Normal, or Faster. Emergency messages are always read aloud.
- If the microphone is blocked, say where to click "Allow". Whatever goes wrong, Call 911 and Call family appear.

## Screens and moving between them

All screens live on one page (`static/index.html`), each in a `<section data-screen>`. The address shows which one is open (`#/diary`, `#/family`…), so the browser's Back button works. When she opens a screen, it starts at the top, and keyboard and screen-reader focus moves to its heading. A "Skip to the page" button is the first keyboard stop.

**Today, on a phone, from top to bottom:** Menu and Bigger words; the date, greeting, and Buddy's question; "Say it again"; what she said (after she talks); the voice box; the cards (Something hurts, Is this a scam?, My pills, Family), one per row; the honest note.

**Tablets lying sideways and computers (1000px and up):** the sidebar sits on the left; the cards form a two-by-two grid (from 640px up); the page column is at most 820px wide.

**Family:** big call buttons for her family member and doctor at the top, then "Set up Buddy" for a family member: her names, family name, phone and email, doctor name and phone, and Buddy's voice. One Save button.

## Screen checklist

- Works at 200% browser zoom with nothing cut off.
- Works at 360px and 375px (phones), 768px (upright tablet), and 1280px.
- Every action works with a keyboard, and focus is easy to see.
- Spoken and new text is announced to screen readers (`aria-live="polite"`).
- "Bigger words" works on every screen.
- No horizontal scrolling. Words never spill out of a button (`scripts/browser_checks/home.py` checks this).
