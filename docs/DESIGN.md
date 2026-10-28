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

The style is called **"The Kitchen Canister Set"**: a cheerful 1950s-60s American kitchen. Her day lives on a tiled kitchen wall, with a big white plate to talk into and a solid-colored canister for each part of her day. All the colors and sizes live at the top of `static/styles.css`.

- **The tiled wall.** The page background is a wall of square glazed tiles with thin grout lines. By day (6 AM to 6 PM) it is turquoise. At night it turns deep blue. `app.js` sets `data-time="day"` or `"night"` on the page, and also colors the phone's top bar to match the wall.
- **Buddy's face.** A smiling sun on a round white plate by day, a sleepy moon at night. It is flat, because it is not a button.
- **White enamel.** Plates, reading cards, and the tab bar are white enamel. At night the white softens to a pale blue-gray so it doesn't glare.
- **Raised keys that sink (a firm promise to the user).** Everything she can tap is a raised key with a solid, darker edge underneath it, like a big-button phone. When pressed, the key moves down by the height of its edge and the edge disappears, so it looks pushed in. Things she can only read are flat cards with no edge. So "raised" always means "you can tap this".
- **Each part of her day keeps its own color.** Sunflower for talking (and the tab she is on), shamrock green for "Something hurts", cobalt blue for "Is this a scam?", lilac for pills. Use the same color every time that feature shows up.
- **Red is never used in the normal app.** Red is only for the emergency and Poison Control screens.
- **No tiny gray text, no thin fonts, no text over photos, no flashing or fast animation.** Respect "reduce motion" (see Motion below).

### Colors

Measured October 26, 2026. If a color changes, keep the contrast at least as high: body text at least 7:1, buttons at least 4.5:1.

**Day (the default):**

| Use | Name in styles.css | Color | Contrast |
|---|---|---|---|
| Tiled wall (page background) | `--wall` | `#5EC4BE` turquoise | |
| Shadow side of things on the wall (the Talk plate's edge) | `--wall-edge` | `#3A9E98` | |
| Words sitting right on the wall | `--on-wall` | `#0E2422` | 7.8:1 on the wall |
| Plates, cards, tab bar | `--enamel` | `#FFFFFF` | |
| White keys sitting on white (tabs) | `--enamel-key` | `#EEF4F3` | |
| Edge under a white key | `--enamel-edge` | `#B7CDCA` | |
| Words on light colors | `--ink` | `#0E2422` | 16.2:1 on white |
| Second lines on white cards | `--ink-soft` | `#3A4F4D` | 8.7:1 on white |
| Talk plate well, the open tab, text highlight | `--sun` | `#F7C23E` sunflower, ink text | 9.9:1 |
| Edge under sunflower | `--sun-edge` | `#C99220` | |
| "Something hurts" canister | `--shamrock` | `#8DD39A`, ink text | 9.2:1 |
| Edge and lid of the green canister | `--shamrock-edge` | `#4F9B5C` | |
| "Is this a scam?" canister, the "A+" letters | `--cobalt` | `#2A4A9C`, white text | 8.2:1 |
| Edge under the cobalt canister | `--cobalt-edge` | `#172F6B` | |
| Pills (the disc behind the pill drawing) | `--lilac` | `#CDB6EE`, ink drawing | 8.9:1 |
| Voice ring while listening | `--ring` | `#FFD866` light sunflower | |
| Keyboard focus ring | `--focus` | `#0E2422` | |
| Soft shadow under raised things | `--drop` | ink at 22% | |

**Night (`data-time="night"`)** changes only these. Everything else stays the same:

| Use | Name | Color | Contrast |
|---|---|---|---|
| Tiled wall | `--wall` | `#1B2A55` deep blue | |
| Shadow side of things on the wall | `--wall-edge` | `#0E1838` | |
| Words on the wall | `--on-wall` | `#FFFFFF` | 13.9:1 |
| Plates, cards, tab bar | `--enamel` | `#E9EDF6` soft white | ink 13.8:1 |
| White keys on white | `--enamel-key` | `#D9DFEC` | |
| Edge under a white key | `--enamel-edge` | `#8E9AB8` | |
| Keyboard focus ring | `--focus` | `#F7C23E` sunflower (shows on the dark wall) | |
| Soft shadow | `--drop` | black at 40% | |

**Red is only for emergency screens.** The colors above contain no red. The emergency and Poison Control screens keep their own red (`#B00020` with white text, 7.3:1) and nothing else may use it.

### Font and text sizes

- **Font:** Atkinson Hyperlegible Next, made by the Braille Institute for readers with low vision. It is stored in `static/fonts/` (self-hosted, license SIL Open Font License 1.1). If it can't load, the page falls back to Segoe UI.
- Line height 1.5 for reading text. Left-aligned text, except the Talk plate and the message under it, which are centered.
- All sizes use `rem`, so the "Bigger words" key can grow everything at once: normal (100%), big (115%), biggest (130%).

| What | Size | Weight |
|---|---|---|
| Greeting ("Good morning!") | 40px | extra bold (800), tight lines (1.1) |
| Words on the Talk plate | 36px ("Tap when you're done": 30px), shrinks on narrow phones so it always fits in the circle | extra bold |
| Card headings ("Today's pills") | 32px | extra bold |
| What she said | 28px | regular |
| Canister names | 24px (26px on big screens) | extra bold |
| Message under the plate | 24px | bold (700) |
| Body text, the date, the "Bigger words" key | 22px | regular; date and keys bold |
| Tab names | 19px, never under 18px on narrow phones | extra bold |

Every button's words are extra bold (800). Tab names are smaller than the 22px body rule only so four tabs fit across a phone; don't use 19px anywhere else.

### Shapes and spacing

- **Round pills** for single keys like "Bigger words" (fully rounded, at least 64px tall).
- **Circles** for Buddy's face plate and the Talk plate.
- **Reading cards:** 24px rounded corners, 18 to 22px inside padding.
- **Canisters:** 20px corners at the top, 28px at the bottom, like a real canister.
- **Tabs:** 20px corners. The tab bar itself has 28px rounded top corners.
- **Spacing:** 16px between keys and between sections (the golden rule minimum). Page padding 20px. 56px between the two columns on big screens.
- **Edges:** small keys and tabs have a 5 to 7px edge, the Talk plate a 10px edge. Each edge is a darker shade of the key's own color.
- **Drawings:** simple line drawings, same color as the words, sized with the text (1.2 times the letter size) so they grow with "Bigger words". Always next to a word, never alone.

### The parts

| Part | What it looks like |
|---|---|
| **Talk plate** | The biggest thing on screen: a white plate (about 19rem wide, 60% of a phone's width) with a sunflower well in the middle holding a microphone drawing and "Tap to talk". Its edge is the wall's shadow color. Sinks 10px when pressed. |
| **Key** | A white rounded pill with a pale edge underneath, like "A+ Bigger words". The "A+" is in cobalt. |
| **Canister** | A tappable block in its feature's color, with a darker "lid" band across the top and a thin seam below it. The drawing sits at the top left and the name at the bottom left, so two canisters side by side line up. Sinks 7px when pressed. |
| **Reading card** | A flat white card with rounded corners, a big heading, and second lines in the softer ink. No edge, because it is not a button. A small colored disc behind a heading's drawing shows which feature it belongs to (lilac for pills). |
| **Tab bar** | A white bar fixed at the bottom of every screen, with four tab keys: Home, Pills, Diary, Family. Each tab has a drawing on top and its name below. The tab she is on is sunflower with a darker sunflower edge; the others are pale white keys. |
| **Focus ring** | A thick 5px outline, 5px away from the key, following its shape. Dark ink by day, sunflower at night. |

### Motion

Every movement must tell her something: the app is ready, a key was pressed, it is listening, it is working, or her words arrived. Nothing flashes, and nothing moves fast. One easing everywhere (`--ease`: a quick start that slows down gently). The main moment is **talking**; everything else is quiet support.

| When | What moves | How long |
|---|---|---|
| The app opens | Buddy's face pops in, the greeting slides in, the plate rises, the canisters follow one after another, the pills card rises, the tab bar slides up. Content is never hidden if the animation can't run. | under 1 second in all |
| Waiting for her | A thin sunflower ring gently breathes behind the Talk plate, inviting a tap. The sun's rays turn very slowly and its face floats; at night the moon gently rocks. | 3.6 s breath, 40 s per ray turn |
| Listening | The ring grows and shrinks with her voice; a dark dot pulses; everything else fades back to 30%. | live; 1.4 s pulse |
| Writing it down ("One moment…") | A sunflower arc sweeps around the plate like a kitchen timer. | 1.6 s per turn |
| Her words arrived | The plate gives one small happy settle, and the "You said" card rises into place. | 0.45 s |
| Any tap | Keys sink by their edge height; a canister's lid lifts a little; a new message eases in. | 0.1 to 0.3 s |
| Bigger words | The text grows smoothly instead of jumping. | 0.25 s |

- Rings sit behind the plate (the Talk area has its own layer, `isolation: isolate`), so the plate's raised edge stays in front of them.
- Mouse users see a key dim slightly when they point at it. Touch screens don't, so a key never stays dim after a tap.
- Animate only position, size, rotation, and fading (`transform` and `opacity`), so it stays smooth on tablets.
- **Reduced motion:** if her device asks for less motion, nothing slides, spins, grows, or breathes. Fades and color changes that show what changed still happen. The voice ring still appears while listening (at one fixed size) and the timer arc still shows while working (standing still).

## Voice behavior

- After she taps "Tap to talk", the plate's label changes to "Tap when you're done". A gently pulsing dark dot replaces the microphone, and the message under the plate says "Listening…". A solid light-sunflower ring around the plate grows and shrinks with her voice, and everything else on the screen fades back.
- Show what she said in big text, then the reply in big text, and read the reply aloud at a slightly slow speed (`rate` about 0.9). Pick a clear, natural voice for her language.
- "Say it again" replays the last reply. A setting turns voice on or off and changes the speed.
- If the microphone is blocked, show step-by-step help with a picture of where to click "Allow".

## Home screen layout

On a phone, from top to bottom:

1. **Hello:** Buddy's face (sun or moon) on the left, the greeting ("Good morning!") and the date ("It's Monday, October 26.") beside it.
2. **"A+ Bigger words" key**, right under the date, so she can grow the words before reading anything else. It always says what it will do next ("Bigger words", "Even bigger", "Smaller words") and remembers her choice.
3. **The Talk plate**, centered and the biggest thing on screen, with a kind message under it ("How are you today?"). After she talks, a card shows "You said:" and her words.
4. **Two canisters side by side:** "Something hurts" (shamrock) and "Is this a scam?" (cobalt). With bigger words, or when they don't fit, they stack one per line.
5. **Today's pills card** (flat, for reading).
6. **The tab bar**, always at the bottom: Home, Pills, Diary, Family. The page leaves room at the bottom so the tab bar never covers the last card or the keyboard focus.

Doctor notes are no longer a home-screen button: they live under the **Diary** tab. Settings live under the **Family** tab.

**Tablets lying sideways and computers (900px wide and up):** two columns, at most 1040px wide. The greeting and "Bigger words" run across the top. The Talk plate is on the left. The canisters and the pills card are on the right, and the canisters get taller with bigger names (26px). The tab bar's keys stay centered, at most 720px wide.

**Phones and upright tablets (under 900px):** one column, at most 560px wide, centered.

## Screen checklist

- Works at 200% browser zoom with nothing cut off.
- Works on a tablet and at 375px wide (phone).
- Every action works with a keyboard, and focus is easy to see (thick outline).
- Spoken and new text is announced to screen readers (`aria-live="polite"`).
- Text size can be made bigger with an "A+" button.
- No horizontal scrolling.
