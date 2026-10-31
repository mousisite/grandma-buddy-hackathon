# Grandma Buddy: the design system

Grandma Buddy should look and feel like a flagship app (the quality of the Claude app, Google Gemini, or Apple's own apps) and still be easy for an older adult with weak eyesight and shaky hands.

## The idea: "the living orb"

One memorable thing: **Buddy, a living orb of warm light.** Everything around it stays quiet and disciplined: restraint, whitespace, hairline borders, one ink accent, a real dark mode. Boldness is spent only on the orb and the moment it morphs into voice mode.

Avoid: gradients anywhere but the orb, cards inside cards, the same shadow under everything, ALL CAPS, labels above every heading, arrows on buttons, spinners, color as the only signal.

Every color, size, and timing is a custom property at the top of `static/styles.css`.

## The rules (checked by `/senior-friendly-ui`)

1. **Voice first.** "Talk to Buddy" is the main action on Home (one button, under the orb) and in the sidebar on every other screen. Everything she can tap, she can also say.
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
12. **Calm motion.** Off at first. Reduced motion (the computer's setting) or "Calm motion" in Settings (saved in her profile) turns movement into simple fades. The orb stands still but keeps its glow.

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

Buddy's colors live only in Buddy, never on words: the orb, and the halo Buddy draws in Find my things (Buddy's light around her thing). Amber `#F6B042`, peach `#F78C5B`, rose `#E1607E`, violet `#8B6CF2`.

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

- **Phones (under 768px):** content full width with 20px sides; a floating glass tab bar at the bottom: Home, Diary, Pills, Family, Settings. Its labels grow with Text size only as far as their tab allows (sized to the bar with a container query), so "Settings" never spills out on a narrow phone with Largest text, and never goes below 13px.
- **768px and up:** a slim glass sidebar (the Buddy wordmark, the same five places, and "Talk to Buddy" at the bottom, hidden on Home, which has its own); content at most 760px wide.
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
| A Memory book page is written or painted | A slow band of light (2.4s) across a soft wash of Buddy's colors, with "Writing your page…" or "Painting your picture…"; the painting fades in (560ms) once loaded. Calm motion keeps the wash, the words, and the fade, but not the band |
| Find my things finds her thing | The room dims like a spotlight (360ms), and a ring of Buddy's light draws itself around her thing once (900ms). Calm motion: both are simply there |
| Emergency, Poison Control, crisis screens | Nothing: they appear instantly |

**Chime.** An optional soft, low two-note tone (Web Audio, no sound files) when listening starts and stops. Off by default.

## Screens

All screens live on one page (`static/index.html`), each in a `<section data-screen>`. The address shows which one is open (`#/talk`, `#/pills`…), so the browser's Back button works.

**Home.** It opens on the greeting in Newsreader ("Good afternoon, Rose"), the date, and the whole orb, above the fold even on a 390 by 844 phone. Then "Talk to Buddy" (the only one on Home; the orb is a tap target, not a second button for the keyboard or screen readers), four chips (Something hurts, Check a message, Memory book: on phones, the way into the Memory book, and Find my things; on phones a 2×2 grid of tiles, icon above words, 76px tall, 16px corners, so no name is squeezed; from 768px two by two as equal pills, so none is left alone on a last row), and "Today" as a grouped list: today's weather first when her town is set up ("Sunny, with a high of 62 and a low of 48.", "From weather.gov", and "Hear it"), the daily check-in ("Not done yet" and "Start"; once done, her mood and a green check with "Done" in place of Start), the next pill ("Next: evening pill at 6:00 PM", "pills" when there are several; with "Take" when one is due; a time like "6:00 PM" never breaks over two lines), the latest diary note today, and Doctor notes.

**Today rows.** A tap anywhere on a row does what its button or link says (big targets for shaky hands), and the row darkens slightly under the mouse; keyboards use the button or link itself. Links end in a small chevron ("Pills ›"). A row's title never leaves one word alone on its last line.

**Daily check-in.** The first row of Home's Today list after the weather: "Daily check-in", "Not done yet", and **Start**. Once she has said how she feels in today's check-in: "Feeling great, at 9:00 AM" and a check with "Done" (`--success`, words and icon, nothing to tap). After "Not today": "Skipped for today", and Start stays. Start opens voice mode like "Something hurts": Buddy says its fixed opening ("Good morning, Rose. How are you feeling today?"), the button hint says "Your daily check-in", and the AI asks the other two questions one at a time. Leaving voice mode ends it. A browser can't speak before her first tap, which is why the check-in starts with a tap instead of talking on its own.

**Pill reminder card.** On every screen, at the top, while a pill is due. It rises in (the one raised card) and is calm, never red: Buddy's light spills softly onto its top from a small living orb (the same orb as on Home, 40px, so it glows while Buddy speaks), next to "Pill time" and the pill's time. Then Buddy's words with her name in Newsreader (32px, 24px on phones): "Rose, it's time for your evening Metformin." Under them each pill as on its bottle, on a tinted panel: the name, then the label word for word. Then **I took it** (ink) and **Remind me in 10 minutes** (quiet), both 56px, full width on phones, and "Say it again". Their words stay on one line down to 360px at the largest text size; on a smaller screen "Remind me in 10 minutes" takes two even lines rather than being cut off. Buddy reads it aloud with each label ("The label says: …"), once; a reminder that came before her first tap is read right after that tap. Brought into view once, and it stays until she answers. After a Poison Control screen today, its fixed message and call button come first. `?demo=reminder` in the address shows it for her next pill 2 seconds after the first tap, for the demo video; it saves nothing.

**My pills.** "Today, Wednesday" with a ring ("2 of 3"), then Morning, Afternoon, Evening, Night as grouped lists of large rows: a round check, the name, the label word for word, what it is now ("Taken at 8:05 AM", "Reminding you again at 8:40 AM", "Later today", or the fixed missed text), and the time. A pill due now has a round check button ("I took this one"). Then "Set up pills", folded away behind one "For a family member" row: Change, Remove (a sheet where the cursor starts on "Keep it"), Undo, and the Add a pill form.

**My diary.** "I'm an AI helper. I can't give medical advice." under the heading, one "Something hurts" button, then a timeline by day: the time, her words in quotes, where it hurts as a tag, and Pain and Since when she said them. A shimmer while it loads.

**Check a message.** A paste area with three ways in: "Check message", "Read it out loud" (tap, read, tap "I'm done reading"), and "Use a photo" (camera or photos, checked right away). While Buddy reads it: "Buddy is reading it…" and a shimmer. The verdict card is the screen's one raised element, read aloud, with focus on the verdict. It has:
- a status pill with words and an icon: "Likely scam" in `--warning` with a stop icon (Lucide octagon-x), "Suspicious" with a neutral outline (circle-alert), "Looks safe" in `--success` (circle-check);
- the explanation (20px), "Warning signs", and "What to do" (fixed text);
- a folded "If you already paid or shared information";
- Call {family} and Call the Elder Fraud Hotline on a likely scam;
- "Say it again" and "Check another message";
- a small thumbnail of the photo, for a photo.

**Doctor notes.** A document with Newsreader headings. On screen:
- "I'm an AI helper. I can't give medical advice." under the heading;
- a Last 7 days / 14 days / 30 days choice and **Print** (56px);
- the page itself: "Notes for Dr. Lee", "Rose, October 22 to 28".

The page's sections, in the order a doctor reads them:
- **Questions to ask**, each with a quiet **Mark as asked** just under it. An asked one stays where it is, its words in the second ink, with a green check, "Asked", and an underlined Undo; the cursor stays on it. On paper the check and "Asked" print, the buttons don't;
- **How I've been feeling**, by topic: date and time, her words in quotes, pain, since, and the emergency note;
- **My pills**, exactly as labeled: "Taken 6 of 7" and missed doses in `--warning` with an icon;
- **My mood**, one line per day;
- a footer saying it was written down by an AI helper from what she said and is not medical advice.

"Add a question" sits below the page. On paper: only the page, 10.5pt, the date beside her words, pill counts beside their names, and moods in 4 columns. A week of the demo data fits on one page (checked in the browser check).

**Family.** A document with large call buttons for her family member and doctor. Below them:
- "Today's update for Maria", with a Today / Yesterday choice;
- the update in a card, exactly the words that will be sent;
- **Send to Maria** (ink, 56px, opens her email app with it written) and **Copy** (a "Copied" toast);
- "Nothing is sent until you press Send there.";
- a note pointing to Settings when there's no email set up.

**Memory book.** "Memory book" (Newsreader display), one line on what it is, and **Tell Buddy a memory** (ink, 56px, the mic icon), which opens voice mode with "I'd love to hear one of your memories. What would you like to tell me about?". Then the pages, newest first: one column on phones, two from 768px. Each card has the painting (3:2, 16px corners, on a soft wash of Buddy's colors until it arrives), the title in Newsreader (24px, in up to two even lines), and the day. Cards side by side are the same height, with the day at the bottom, so the days line up. A card being written or painted shimmers and says so. Under the pages: "Buddy's AI writes each page from your own words and paints its picture." The empty book says "Tap 'Tell Buddy a memory' to make the first page." It is in the sidebar (book-heart icon) and opens from a Home chip on phones; the tab bar keeps its five places, because a sixth label would not fit at Large text.

**A memory page** (`#/memory/3`). "Memory book" back link, then the page like a picture book: the painting, the title in Newsreader (32px, 44px from 768px), the day, and her story in Newsreader at 20px with 1.6 line height. Then **Send to Maria** (ink, 56px, opens her email with the story written in), **Print** (quiet, 56px), and "Read it to me" (hidden when Read replies aloud is off). A note says the email holds the words only: to share the painting, Print and save it as a PDF. A painting that didn't work shows "Paint it again" on the wash. On paper: just the page, painting and all.

**Help.** "Help" (display), one line on what is here, then four sections, each a heading over a grouped list: **How Buddy works** (the 4 Meta models as cards, one column on phones and two from 520px, then each feature as a row: its name, one line, and chips for its models, or an outlined "No AI" chip for the parts that run only on this computer), **What Buddy never does** (rows with a ban icon), **Your privacy, in short**, and **Questions** (a grouped list where each question opens its answer, with a chevron that turns). Last, "Still need help?" with Call {family} (ink). Opens from the sidebar's Help (desktop) or the first row of Settings, "Help and how Buddy works", a whole row that opens a page, with a chevron (the tab bar keeps Settings lit there). Whole-row links and questions darken slightly when pressed instead of squeezing, since they are wide.

**Settings.** Help and how Buddy works first, then grouped rows: Appearance (Theme, Text size), Voice (Read replies aloud, Buddy's voice, Voice speed, Chime), Motion (Calm motion), and "Names and phone numbers", folded away for a family member. Switches and choices save at once with a "Settings saved" toast; the profile has its own "Save profile". A refused entry gets a `--warning` border and a note right under it saying how to fix it. "Buddy's voice" lists Buddy's natural voices first (Heart, the default, Bella, Nicole, Emma (British), Michael: made on this computer, the same in every browser), then the browser's own English voices best first (Edge's natural voices, Chrome's Google voices, Apple's, then the old Windows voices). It says the chosen one aloud at once and has "Try it". The choice is kept on this device. Only when there is no natural voice at all and the browser's voices are robotic does it suggest opening Buddy in Microsoft Edge. With the natural voice, the word-by-word highlight follows how far each sentence has played.

**Find my things** (`#/find`, and `#/find/glasses` from "Buddy, where are my glasses?"). One bold moment, everything around it quiet.
- **Asking:** "Find my things" (display), one line on what it does, then "What are you looking for?" (20px, semibold) over a large field, quick picks as chips (Glasses, Keys, Remote, Pill bottle, Phone; the picked one turns ink, `aria-pressed`), **Say it** (quiet, 56px) and **Take a photo** (ink, 56px, camera icon), and "Choose a photo instead" as a text button. Asking for a photo first nudges her, under the field, to say what she's looking for.
- **Looking:** her photo in a frame of its own shape (20px corners, the raised shadow, never taller than 62% of the screen), gone quiet (less color), with a small thinking orb on top and "Buddy is looking…".
- **Found:** the halo. The rest of the photo dims (a 42% ink layer with a soft, feathered hole), and an ellipse around her thing, a little bigger than it and never smaller than 6% of the photo, is drawn in Buddy's orb gradient (amber, peach, rose, violet) with a soft glow under it and a thin white edge, so it shows on any photo. Not a box: it's Buddy's light, so it uses the orb's colors (the one place outside the orb they appear, because it is Buddy). It's an SVG in the photo's own pixels, so it sits exactly on SAM's box at any size.
- **Below:** Buddy's sentence, big (24px, 32px from 768px), read aloud and given focus; it is also the photo's description for screen readers. Then **Say it again** (quiet) and **Try another photo** (ink), and "Look for something else". A button's words never wrap: when two don't fit side by side, each takes its own row (checked from 320 to 1440px at every text size).
- **Not found:** the photo as it is, no halo, Buddy's kind sentence, and Try another photo.

**Welcome** (`#/welcome`, the first time, while no name is saved). The whole screen, like voice mode: no tab bar or sidebar, and the "call 911" note stays at the bottom.
- **The stage:** Buddy's orb at the top, then where she is in words, "Step 2 of 3" (20px, semibold, `--text-2`), with three 14px dots under it that only show it (`aria-hidden`): an outline still to come, filled ink done, and a 28px ink pill for now. Then a Newsreader question and one line of help.
- **Back:** a quiet "‹ Back" text button at the top left on steps 2 and 3 (48px tall, no fill). Its row is always there (hidden on the other steps), so the orb never jumps.
- **The steps:**
  0. "Hello! I'm Buddy.", with **Let's begin**. Browsers stay silent until a first tap, so this tap lets Buddy speak.
  1. "What should I call you?": a large name field, **Say it**, and **Next**.
  2. "Who should I call when you'd like to talk to someone?": two cards, "Someone you love" and "Someone else (if you like)", each with a name and a phone number. Then Say it, Next, and Skip for now.
  3. "Would you like to set up your pills now?": **Add my pills now** (Pills with "Set up pills" open) or **Later**.
- **Voice:** each question is read aloud. "Say it" works like Tap to talk ("I'm done", then "One moment…"), fills the fields, and goes through the safety net first.
- **Refused entries:** marked under their field, saying how to fix them.

**The greeting.** "Talk to Buddy" at the start of a conversation (the first talk today, or after two hours): Buddy says "Good afternoon, Rose!" with a follow-up that is due ("Did Tom make it on Sunday?") or a warm opener, shown big and read aloud, and the microphone opens by itself once Buddy has finished (never while it speaks). Otherwise she goes straight to talking, as before.

**What Buddy has learned** (Settings, folded away under "For a family member"). One line on how far Buddy has got ("still getting to know her" or "learned from 3 days of talks"), "Nothing here is about her health", then two grouped lists: "How she likes to talk" (the notes) and "Her people, pets, and plans" (each fact, with what Buddy will ask and when). Each row has "Forget this", which asks first in the shared bottom sheet and then offers Undo.

**Safety screens.** Full-bleed, no motion, texts word for word from `docs/SAFETY.md`. Emergency and Poison Control: `--alarm` red with white words (44px title, 32px message) and one huge white call button (104px); any other call buttons are outlined. Crisis: the page color with ink words and one huge ink call button.

## Screen checklist

- `scripts/browser_checks/home.py` passes. It checks every flow, and every screen at 390, 768, and 1440px in light and dark, 360px, 200% zoom, and the largest text: no sideways scrolling, no words spilling out, every target 44px or more. Screenshots land in `test-output/`.
- `scripts/check_contrast.py` passes.
- Every action works with a keyboard, and focus is easy to see.
- Reduced motion and Calm motion stop all movement.
