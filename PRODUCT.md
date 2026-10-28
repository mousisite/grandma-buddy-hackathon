# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

- **Grandma (main user).** An older adult who lives alone in the United States. Often lonely, deals with a lot of pain, has weak eyesight and possibly shaky hands, and finds phones hard to use. She talks to the app instead of typing. She uses it all day long: a check-in in the morning, pill reminders through the day, company in the evening.
- **A family member (helper).** Sets up her medications and contacts once, and receives a short daily update.
- **Hackathon judges.** Watch a 3-minute demo video and open the code and live product (Meta Global AI Developer Hackathon, Indie track, judged on creativity, technical ambition, and whether it works).

## Product Purpose

A voice companion that checks in every day, reminds her about her pills, keeps a symptom diary for her doctor, keeps her company, keeps her family in the loop, and spots scams. Success: she uses it every day by voice without help, and her family and doctor know how she is doing.

## Positioning

It never gives medical, mental-health, or food advice. It listens, writes things down, reminds, and connects her with real people (family, doctor, emergency services). A plain-rules safety net (not AI) shows fixed emergency, crisis, and Poison Control screens.

## Operating Context

- Runs as a web page on a tablet or phone (held or propped up), in a browser, for one person. No accounts, no login.
- Used throughout the day, in daylight and in lamp light.
- Voice first: one big "Tap to talk" button; replies are shown in big text and read aloud.

## Capabilities and Constraints

- Features (see docs/SPEC.md): voice conversation, emergency safety net, symptom diary, pill reminders, daily check-in, companion chat, scam checker, doctor visit notes, family updates.
- Plain HTML, CSS, and JavaScript served by FastAPI. No framework, no build step.
- Uses Meta's Muse Spark 1.3 and Muse Voice Transcribe. No other AI provider.
- All code written during the hackathon (Oct 26 to Nov 4, 2026). Public repository, so no secrets or real personal data.

## Brand Commitments

- Name: Grandma Buddy.
- The sky matches the time of day: a smiling sun by day, a sleepy moon at night (user asked to keep this, Oct 26, 2026).
- Buttons are raised keys that sink when pressed, like a big-button phone (user asked to keep this, Oct 26, 2026).
- Must look and feel like a real, finished app, not a demo page (user, Oct 26, 2026).

## Evidence on Hand

- No real photos, logos, or testimonials. Demo data must be made up (the demo user is "Rose").
- Never use real health information anywhere.

## Product Principles

1. Record, remind, connect. Never advise.
2. Voice first: everything she can tap, she can also say.
3. One main thing at a time, in big words she can read without glasses.
4. Real people matter most: always point to family, doctor, and help lines.
5. Red means emergency, and nothing else.

## Accessibility & Inclusion

Rules in docs/DESIGN.md: body text 22px or more, headings 32px or more, buttons at least 64px tall with 16px between them, body contrast at least 7:1, words on every button, no time limits, keyboard focus easy to see, screen-reader announcements, reduced motion respected, works at 375px and 200% zoom.
