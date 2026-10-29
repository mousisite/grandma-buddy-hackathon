# Grandma Buddy: the design system

Grandma Buddy should look and feel like a flagship app (the quality of the Claude app, Google Gemini, or Apple's own apps) and still be easy for an older adult with weak eyesight and shaky hands.

## The idea: "the living orb"

One memorable thing: **Buddy, a living orb of warm light.** Everything around it stays quiet and disciplined: restraint, whitespace, hairline borders, one ink accent, a real dark mode. Boldness is spent only on the orb and the moment it morphs into voice mode.

Avoid: gradients anywhere but the orb, cards inside cards, the same shadow under everything, ALL CAPS, labels above every heading, arrows on buttons, spinners, color as the only signal.

Every color, size, and timing is a custom property at the top of `static/styles.css`.

## The rules (checked by `/senior-friendly-ui`)

1. **Voice first.** "Talk to Buddy" is the main action on Home and in the sidebar. Everything she can tap, she can also say.
2. **Legible.** Body text 17px or more; short labels (tabs, captions) 13px or more. "Text size" in Settings (Standard, Large, Largest: 100, 118, 135%) grows everything. It starts at Large on a first visit, and her choice is remembered on this device.
3. **Easy to tap.** Every target at least 44 by 44px; the main actions (Talk to Buddy, I took it, call buttons) 56px or more.
4. **Contrast.** Text 4.5:1 or more in light AND dark; large text, icons, and the edges of fields 3:1. Measured by `scripts/check_contrast.py`.
5. **Words, not color alone.** Every button has a text label; every state has words and an icon.
6. **Plain language.** Short, warm, specific, sentence case. Never "error", "API", "server", "transcribe", or codes.
7. **Simple first.** Her screens show only what she uses. Things only a family member sets up ("Set up pills", "Names and phone numbers") are folded away behind one row marked "For a family member".
8. **Every press shows.** A soft ring when the mouse is over something, and the moment a finger lands it squeezes, darkens, and a circle of light spreads from her finger.
9. **Nothing is lost by mistake.** Removing asks first (a bottom sheet) and offers Undo. Unsaved profile entries stay when she moves to another screen. Form problems stay inline under the entry until fixed.
10. **Red means emergency.** `--danger` and `--alarm` only on the emergency and Poison Control screens (and the Poison Control call on the pill reminder). A "Likely scam" verdict uses `--warning` with a stop icon.
11. **Keyboard and screen readers.** Visible focus ring in both themes; focus moves to each screen's heading; new text is announced (`aria-live="polite"`); a "Skip to the page" button is the first stop.
12. **Calm motion.** Reduced motion (the computer's setting) or "Calm motion" in Settings turns movement into simple fades. The orb stands still but keeps its glow.

## Color

Light is the default; Auto follows the computer's light or dark setting (and, if the computer says neither, goes dark from 7 PM to 7 AM). Settings has Auto, Light, Dark; the choice is saved in her profile and applied before the first paint from this device's last choice, so dark mode never flashes white.

| Token | Light | Dark | Use |
|---|---|---|---|
| `--bg` | `#F7F7F5` | `#131211` | the page |
| `--surface` | `#FFFFFF` | `#1D1C1A` | grouped lists, fields, documents |
| `--tint` | `#EFEEEA` | `#262522` | chips' pressed state, the segmented track, tags |
| `--border` | `rgba(28,27,25,0.08)` | `rgba(255,255,255,0.08)` | hairlines |
| `--text` | `#1C1B19` | `#F3F1EC` | words |
| `--text-2` | `#5C5953` | `#ADA89F` | second lines, captions |
| `--primary` | `#1C1B19` | `#F3F1EC` | the one ink accent: main buttons, switches |
| `--success` | `#1E7350` | `#5BC79A` | taken, looks safe |
| `--warning` | `#9A5B00` | `#F0B45A` | missed, likely scam, form problems |
| `--danger` | `#C21F3A` | `#FF6B7F` | emergency only |
| `--alarm` | `#A8162E` | `#A8162E` | emergency and Poison Control screens (white words on it) |

Buddy's colors live only inside the orb, never on words: amber `#F6B042`, peach `#F78C5B`, rose `#E1607E`, violet `#8B6CF2`.

### Contrast (from `scripts/check_contrast.py`)

| Pair | Light | Dark |
|---|---|---|
| Body text on the page | 16.0:1 | 16.6:1 |
| Secondary text on the page | 6.5:1 | 7.9:1 |
| Secondary text on cards | 7.0:1 | 7.2:1 |
| Secondary text on tags and tracks | 6.0:1 | 6.5:1 |
| Main button words | 17.2:1 | 16.6:1 |
| Toasts | 16.0:1 | 16.6:1 |
| Taken / looks safe | 5.4:1 (5.8 on cards) | 9.0:1 (8.2 on cards) |
| Missed / likely scam | 5.1:1 (5.4 on cards) | 10.1:1 (9.2 on cards) |
| Edges of fields and switches | 3.5:1 | 3.6:1 |
| White on the emergency red | 7.4:1 | 7.4:1 |

## Type

- **Figtree** (SIL Open Font License) for everything: a clear, friendly sans with open shapes.
- **Newsreader** (SIL Open Font License) only for the greeting, the wordmark, and the headings of documents (Doctor notes, Family).
- Both self-hosted in `static/fonts/`; no font CDN.
- Scale: 13 / 15 / 17 / 20 / 24 / 32 / 44 / 56px. Body 17px, line height 1.5. Headings letter-spacing −0.02em, line height 1.1. Sentence case.
- The greeting is 44px on phones and 56px on tablets and computers. Buddy's replies are 32px (24px when long) on phones, 44px (32px) on bigger screens.

## Space, shape, depth

- A 4px grid: 4, 8, 12, 16, 20, 24, 32, 40, 48, 64.
- Radii: 10px inputs, 16px cards and grouped lists, 28px sheets and the tab bar, 999px buttons, chips, and tags.
- Hairline borders separate things. At most one raised element per screen (the pill reminder card has the layered shadow).
- Glass (a 20px backdrop blur) only on the tab bar, the sidebar, and sheets.
- Icons: Lucide (ISC license), inline SVG, 24px, 1.75 stroke, always next to words.

## Layout

- **Phones (under 768px):** content full width with 20px sides; a floating glass tab bar at the bottom: Home, Diary, Pills, Family, Settings.
- **768px and up:** a slim glass sidebar (the Buddy wordmark, the same five places, and "Talk to Buddy" at the bottom); content at most 760px wide.
- Voice mode hides both, and fills the screen.
- "Check a message" and "Doctor notes" open from Home's chips and Today list.

## Buddy, the living orb

A 220px circle (272px in voice mode on phones, 300px on bigger screens). `static/buddy.js` fills each `.orb` with a glow and a core holding four blurred color blobs, a swirl, and a soft shine. The blobs drift and the whole flow turns slowly (about 12s); the core breathes 0.98 to 1.02 over 6s. One state machine drives every orb: `setBuddyState('idle' | 'listening' | 'thinking' | 'speaking')`.

| State | What she sees | Words under it (voice mode) |
|---|---|---|
| Idle | Breathes slowly; the colors flow | none |
| Listening | Brighter; swells gently with her voice (the eased microphone level) | "I'm listening" |
| Thinking | The colors flow 3× faster and a soft light sweeps around inside; the glow pulses | "Let me think…" |
| Speaking | Lifts softly with each spoken word (at most one lift every 400ms) | none |

The flow speeds up without a jump (`updatePlaybackRate`). Buddy wakes once as the app opens. Nothing ever flashes. With Calm motion the orb stands still, still glowing, and still brightens when listening.

## Voice mode (`#/talk`)

"Talk to Buddy", the orb on Home, and "Something hurts" open voice mode with a View Transition: the orb morphs larger and centered (560ms spring), the room dims a little (`--voice-bg`), and listening starts.

- The big ink button toggles between "Tap to talk" and "I'm done". Tapping the orb while she talks also finishes; tapping it otherwise, or "Done", morphs back to Home.
- Her words appear under the orb, in italics, once they are written down.
- Buddy's reply streams in word by word (each fades and un-blurs in 180ms, 25ms apart). As it is read aloud, reading progress shows like song lyrics: words not yet spoken are `--text-2`, spoken ones `--text`.
- Call buttons and "Add to doctor notes" sit under the reply; "Say it again" is always there. Earlier exchanges are listed below, newest first.
- Browsers without View Transitions, and Calm motion, just switch.

## Motion

Easing: a spring (`linear()` with a slight settle; `cubic-bezier(0.2, 0, 0, 1)` where `linear()` isn't supported). Speeds: 120ms (presses, fades out), 220ms (most changes), 360ms (things arriving); 500ms and more only for the orb's morph.

| When | What moves |
|---|---|
| The mouse is over something | A soft 4px ring appears around it (`--ring`), and quiet buttons get a tint |
| Any press (finger or mouse down) | It squeezes to 0.96 and darkens within 120ms, and a circle of light spreads from the spot she touched (650ms); it lets go with the spring. Calm motion keeps only the color; safety screens have none of it |
| The app opens | Only Buddy wakes up |
| Another screen opens | The old one fades (120ms), the new one rises 8px and fades in (220ms); the tab bar and sidebar stay put |
| Voice mode opens or closes | The orb morphs between Home and the center (560ms) |
| A reply arrives | Its words stream in |
| Something is saved | A toast slides in from the top with the spring and leaves after 4s |
| "Are you sure?" | A bottom sheet slides up (centered on bigger screens) |
| A pill is marked taken | Its check pops and draws itself; the ring fills |
| Loading | A soft shimmer, never a spinner |
| Emergency, Poison Control, crisis screens | Nothing: they appear instantly |

**Chime.** An optional soft, low two-note tone (Web Audio, no sound files) when listening starts and stops. Off by default.

## Screens

All screens live on one page (`static/index.html`), each in a `<section data-screen>`. The address shows which one is open (`#/talk`, `#/pills`…), so the browser's Back button works.

**Home.** The greeting in Newsreader ("Good afternoon, Rose"), the date, the orb, "Talk to Buddy", two chips (Something hurts, Check a message), and "Today" as a grouped list: the daily check-in (her mood once she said it, and "Start" to do it any time), the next pill (with "Take" when one is due), the latest diary note today, and Doctor notes.

**Daily check-in.** On her first visit each day, a flat card sits at the top of Home: "Your daily check-in", "Three quick questions: how you feel, anything that hurts, and your morning pills.", **Start check-in** (ink, 56px) and **Not today** (quiet). Start opens voice mode like "Something hurts": Buddy says its fixed opening ("Good morning, Rose. How are you feeling today?"), the button hint says "Your daily check-in", and the AI asks the other two questions one at a time. Leaving voice mode ends it. A browser can't speak before her first tap, which is why the check-in starts with a tap instead of talking on its own.

**Pill reminder card.** On every screen, at the top, while a pill is due: "Pill time", the words "It's time for your morning pill: …" with each label exactly as typed, "I took it", "Remind me in 10 minutes", and "Say it again". Read aloud once, brought into view once, and it stays until she answers. After a Poison Control screen today, its fixed message and call button come first.

**My pills.** "Today, Wednesday" with a ring ("2 of 3"), then Morning, Afternoon, Evening, Night as grouped lists of large rows: a round check, the name, the label word for word, what it is now ("Taken at 8:05 AM", "Reminding you again at 8:40 AM", "Later today", or the fixed missed text), and the time. A pill due now has a round check button ("I took this one"). Then "Set up pills", folded away behind one "For a family member" row: Change, Remove (a sheet where the cursor starts on "Keep it"), Undo, and the Add a pill form.

**My diary.** "I'm an AI helper. I can't give medical advice." under the heading, one "Something hurts" button, then a timeline by day: the time, her words in quotes, where it hurts as a tag, and Pain and Since when she said them. A shimmer while it loads.

**Check a message.** A paste area, "Check message", and "Use a photo". Verdicts (the next step) always have words and an icon: "Likely scam" in `--warning` with a stop icon, "Suspicious" with a neutral outline, "Looks safe" in `--success` with a check. Until then the button says message checking arrives in the next update.

**Doctor notes and Family.** Documents: Newsreader headings, a readable column, and a print stylesheet (no navigation or buttons on paper). Family has large call buttons for her family member and doctor.

**Settings.** Grouped rows: Appearance (Theme, Text size), Voice (Read replies aloud, Voice speed, Chime), Motion (Calm motion), and "Names and phone numbers", folded away for a family member. Switches and choices save at once with a "Settings saved" toast; the profile has its own "Save profile". A refused entry gets a `--warning` border and a note right under it saying how to fix it.

**Safety screens.** Full-bleed, no motion, texts word for word from `docs/SAFETY.md`. Emergency and Poison Control: `--alarm` red with white words (44px title, 32px message) and one huge white call button (104px); any other call buttons are outlined. Crisis: the page color with ink words and one huge ink call button.

## Screen checklist

- `scripts/browser_checks/home.py` passes. It checks every flow, and every screen at 390, 768, and 1440px in light and dark, 360px, 200% zoom, and the largest text: no sideways scrolling, no words spilling out, every target 44px or more. Screenshots land in `test-output/`.
- `scripts/check_contrast.py` passes.
- Every action works with a keyboard, and focus is easy to see.
- Reduced motion and Calm motion stop all movement.
