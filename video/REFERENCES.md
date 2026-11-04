# What the opening borrows from (and what it doesn't)

Four well-known films were downloaded with yt-dlp into `video/reference/` (kept out of git: they are other people's work), looked at as 12-frame contact sheets (ffmpeg) and read as Whisper transcripts. Nothing from them is in our video: no footage, no music, no words. What follows is what each one taught, and the choice it led to in `video/remotion/`.

| Film | What it does well | What we took from it |
| --- | --- | --- |
| Google, "Loretta" (Super Bowl 2020) | Builds a whole life out of plain words on a white screen: a search box, "Ok, I'll remember that", one remembered line at a time with a small date under it. No faces until the photos. Calm, slow, devastating. | Rose's words carry the opening. Her captions are large, plain, one short line at a time on the app's own page color, and they arrive word by word with her voice, the way Buddy's own replies light up "like song lyrics" (docs/DESIGN.md). No boxes, no karaoke colors. |
| Apple, "Zac" (iPhone 16 Pro, Apple Intelligence, 2024) | One person, one problem, and the phone's notification at real size is the hero shot. Warm wood interiors. The small print stays small. | The scam messages are shown as full-screen cutaways to her phone, at real notification size, with the lock screen's time and date, not as a graphic. The honesty line ("Rose is made up…") stays a small pill in a corner. |
| ElliQ, "Your AI sidekick for happier, healthier aging" (review by RoboPhil) | Older adults with the device at home; feature words appear as small labels with a hairline beside the person as they are mentioned. | While Rose talks, a small label rises beside her at the moment she says "phone", "glasses", "pills", "letters": the four troubles the app answers later. Hairline, Figtree, text-2 color, gone in three seconds. |
| Meta, "Introducing Meta Ray-Ban Display" (2025) | UI floats over the world as a layer; beauty shots; cuts every one to three seconds; a dark, cinematic grade. | Only the discipline: one framing while something happens, a cut when the subject changes, nothing moving just to move. Our look stays light, because Buddy is light. |

## Rules we set from this

- The first three seconds: the orb and the name, then Rose is already talking. No logo sting, no music swell.
- Captions are the product's own reading style, not a social-media caption preset: Figtree, ink on the page color, upcoming words in `--text-2`, spoken words in `--text`.
- Cutaways are motivated: the phone appears only right after she mentions it, and the call right after "odd calls".
- Titles land and stay still (HyperFrames' own motion notes say the same): per-word blur-in for the name, nothing sliding after it has landed.
- Everything made up says so on screen within the first six seconds.
