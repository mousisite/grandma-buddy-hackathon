# Shoot and edit sheet: the 3-minute demo video

The video: Rose's story in her own voice over six watercolor scenes, then Buddy in use (recorded with OBS Studio), then your closing words, then the end card. Everything Rose is was made by AI and says so on screen. Edited in CapCut, exported at 1080p, under 3:00.

**Rose's part is one clip, `video\rose-intro.mp4` (about 37 s), made with Remotion** (`video\remotion\`): the title card (the orb, the name word by word), then Rose herself talking (a made-up photo animated by HeyGen in her Kokoro voice, the one step done by hand: `video\heygen\HEYGEN.md`), her words as captions that light up as she says them (Whisper word timings, Buddy's own "song lyrics" reading style), a small label beside her as she names the phone, her glasses, her pills, the letters, two cutaways to her phone as the scam texts and an unknown call arrive, the rest of her story, "Then my daughter set up Buddy.", and a fade to Buddy's page color so the cut to the app is clean. Until the HeyGen clip is saved it is built with a stand-in (her still photo). **The end card, `video\end-card.mp4` (8 s), is made with HyperFrames** (`video\hyperframes-outro\`): the orb, the name, the five Meta models, the two links. You record the app part and put the three together in CapCut; `scripts\video_subtitles.py` makes an .srt of your take for CapCut. What the look borrows from four well-known films, and what it doesn't: `video\REFERENCES.md`.

## The kit

| What | Where | Made by |
| --- | --- | --- |
| **Rose's part, finished** (title, Rose talking with captions and labels, the phone cutaways, the transition, fade to the app) | `video\rose-intro.mp4`, about 37 s | Remotion (`video\remotion\`, data from `scripts\video_remotion_data.py` and Whisper); `scripts\video_intro.py` is the ffmpeg-only fallback |
| **The end card as a clip** | `video\end-card.mp4`, 8 s | HyperFrames (`video\hyperframes-outro\`) |
| Subtitles for any take (an .srt for CapCut, words with times) | `video\subtitles\` | `scripts\video_subtitles.py` (Whisper, GPU) |
| What the look borrows from four well-known films | `video\REFERENCES.md` (the films themselves in `video\reference\`, never committed) | yt-dlp, ffmpeg contact sheets, Whisper transcripts |
| Rose's photo and her whole speech, for the HeyGen talking clip; the steps | `video\heygen\rose-photo.png`, `rose-speech.wav`, `HEYGEN.md` | `scripts\video_scenes.py photo` (Muse Image), ffmpeg |
| The HeyGen clip of her talking (you save it here) | `video\heygen\rose-talking.mp4` | HeyGen, by hand |
| Her phone: the scam texts (4.5 s) and the unknown call (3.2 s) | `video\cutaways\phone-texts.mp4`, `phone-call.mp4` | `scripts\video_cutaways.py` (Playwright + ffmpeg) |
| Rose's story, two versions, the one to use marked | `video\intro\rose-script.md` | written by hand |
| Rose's story as sound, 22.5 s, voice Kore at speed 0.8 | `video\intro\rose-story.wav` | `scripts\video_voice.py` (Kokoro, on this PC) |
| "Then my daughter set up Buddy.", 2.1 s | `video\intro\rose-transition.wav` | same |
| The two candidate voices, first line and whole story in each | `video\intro\voice-candidates\` | same |
| Every line Rose says in the demo, in order, plus two spares | `video\rose\01-hi-buddy.wav` … `spare-thank-you-buddy.wav` | same |
| Six scenes of her home, 1920x1080, no people | `video\intro\scenes\01-kitchen-tea.png` … `06-garden-window.png` | `scripts\video_scenes.py` (Muse Image) |
| Rose's portrait, 1024x1024, for a picture-in-picture corner | `video\intro\rose-portrait.png` | same |
| The Rose player (plays her lines through the speakers) | `video\rose-player.html` | written by hand |
| Title card, end card, seven lower-third captions, 1920x1080 | `video\cards\*.png` (sources in `video\cards\src\`) | `scripts\video_cards.py` (Playwright) |

To make any of it again: the voice in another Kokoro voice, `.venv\Scripts\python scripts\video_voice.py --voice af_sarah`; a scene again, `.venv\Scripts\python scripts\video_scenes.py 03 --again` (one cent); the cards after editing their HTML, `.venv\Scripts\python scripts\video_cards.py`.

## Before the shoot (15 minutes)

1. **OBS Studio is not installed on this PC** (checked Nov 3). Get it from https://obsproject.com, run the installer, and in its first-run wizard choose "Optimize just for recording" (or Cancel the wizard; the settings below cover everything).

2. **The demo week is reset** (done Nov 3, 6:35 PM; a backup was saved first). If you record again on another day, reset it again so every screen says today, with Buddy stopped:

   ```powershell
   .venv\Scripts\python scripts\seed_demo.py --reset
   ```

3. **Start Buddy** in PowerShell, in the project folder (once; a second server on the same port makes both slow):

   ```powershell
   .venv\Scripts\python -m uvicorn app.main:app
   ```

4. **Edge window 1, Buddy.** Open http://localhost:8000, allow the microphone, zoom to 125% (Ctrl and plus, twice). Settings: voice Heart, "Talk without tapping" on, the chime on, text size Large. Second tab: http://localhost:8000/family, left on its sign-in page. Then make this window about three quarters of the screen: press Win and the left arrow, then drag its right edge to about 1440 px wide (three quarters across). It stays on the left.

5. **Edge window 2, the Rose player.** Ctrl and N for a new window, then Ctrl and O and open `C:\Projects\grandma-buddy-hackathon\video\rose-player.html` (or drag the file onto the window). Make it narrow, about 440 px wide and as tall as the screen, and put it on the right, beside Buddy. It must be its own window, not a tab next to Buddy: OBS captures Buddy's window only, so the player never shows in the video. Press Start over.

6. **Sound.** Speakers at about two thirds. The lines Rose "says" come out of the speakers, and Buddy's microphone hears them, the same way it hears you. Test it: click Talk to Buddy, wait for the chime, click line 1 in the player. Her words should appear under the orb within a second or two and Buddy should answer. If nothing appears, the speakers are too quiet or the microphone is muted in Windows.

7. **Have ready:** `scripts\find_photos\desk-keys.webp` and `scripts\read_docs\bill.png` in a folder you can find in the file picker; the prize letter text from part 4 below, copied; notifications off (Win and A, Focus assist on); nothing else open.

8. **Practice the whole take once** without recording. If the pill reminder card pops up, tap "I took it": it is a feature.

## OBS settings for this PC

This PC: 1920x1080 screen at 100% scaling, an RTX 4060 (so the NVENC encoder), Edge 156, sound through "NVIDIA High Definition Audio" (the monitor's HDMI speakers) or "High Definition Audio Device" (the audio jack); "Default" follows whichever Windows uses.

**Settings, Video:** Base (Canvas) Resolution 1920x1080. Output (Scaled) Resolution 1920x1080. Downscale Filter Lanczos. Common FPS Values 30.

**Settings, Output** (Output Mode: Simple): Recording Path `C:\Projects\grandma-buddy-hackathon\video\raw` (make the folder first). Recording Quality: High Quality, Medium File Size. Recording Format: MP4 (or Hybrid MP4 if it is offered: it survives a crash). Video Encoder: Hardware (NVENC, H.264). Audio Encoder: AAC. Audio bitrate 160 if asked.

**Settings, Audio:** Sample Rate 48 kHz, Channels Stereo. Global Audio Devices: Desktop Audio = Default; Mic/Auxiliary Audio = your microphone; every other slot Disabled.

**Sources** (the Sources panel, the + button):

- **Window Capture**, name it Buddy. Window: `[msedge.exe]: Grandma Buddy - Microsoft Edge` (the title is the page's title, so pick the one that says Grandma Buddy, not "Rose says"). Capture Method: Windows 10 (1903 and up). Window Match Priority: Window title must match. Capture Cursor on. Client Area on. Then right-click it, Transform, Fit to screen (Ctrl and F). With this capture method the player window never shows, even if it overlaps Buddy's.
- **Color Source** underneath it (drag it below Buddy in the list), color `#F7F7F5`, 1920x1080: the bars at the sides match Buddy's own page.

**Audio Mixer:** both Desktop Audio and Mic/Aux unmuted, both bars moving when Rose speaks. On Mic/Aux, click the gear, Filters, and add Noise Suppression (RNNoise) and a Noise Gate (Open Threshold −32 dB, Close Threshold −40 dB). The gate keeps the speakers' echo of Rose and Buddy out of the microphone track, so nobody is heard twice; your own closing words, spoken near the microphone, come through.

**Settings, Hotkeys:** Start Recording F9, Stop Recording F10, so OBS is never clicked during the take.

**A 10-second test:** F9, play line 1, let Buddy answer, F10. Open the file: Rose once, Buddy once, readable text. If Rose or Buddy is heard twice (an echo), mute Mic/Aux for the app take and record your closing words as a separate take.

## The take

Times are the demo script's (`docs\DEMO_SCRIPT.md`); the raw take will be longer, and CapCut trims it. Play a line only when the orb is listening (bigger, "I'm listening" under it). If Buddy didn't hear a line, Replay. If a reply comes out a little differently, keep going.

| Script time | Where you are | You click | Rose player | What you see |
| --- | --- | --- | --- | --- |
| 0:00 | Home ("Good afternoon, Rose", the Today list) | **Talk to Buddy** | after the chime: **1. Hi Buddy, how are you today?** | her words under the orb, Buddy's answer in its voice, then it listens again |
| 0:10 | voice mode, listening | | **2. What's the weather like?** | the forecast for Portland, "Weather from Open-Meteo.com" under it |
| 0:20 | voice mode, listening | | **3. Buddy, where are my glasses?** | "we'll look together" and a **Find my glasses** button |
| 0:25 | | **Find my glasses**, then **Choose a photo instead**, pick `desk-keys.webp` | | the photo, the orb thinks, a glowing halo around the glasses, "on the left side of the wooden table, next to the keys" |
| 0:45 | Find my things | the orb (back Home), **Read it to me** chip, **Choose a photo instead**, pick `bill.png` | | the bill read aloud, $84.20 due November 15, the facts under it; hover **Read it word for word**, **Check it for a scam**, **Call Maria** |
| 1:10 | Read it to me | Home, **Check a message**, paste the letter, **Check message** | | Likely scam, the warning signs, the fixed "What to do" lines, the web lookup line about the number |
| 1:30 | Check a message | Home, **Talk to Buddy** | after the chime: **4. Should I take something for my headache?** | the no-advice reply with **Call Dr. Lee**, **Call Maria**, **Add to doctor notes** |
| 1:40 | | **Add to doctor notes** ("Added to doctor notes") | when listening: **5. My chest feels tight.** | the red Emergency screen at once, read aloud, **Call 911** and **Call Maria** |
| 1:55 | Emergency | **Go back** | | Home |
| 2:00 | Home | **Memory book**, tap a page, **Say it** | | three painted pages; her story in her own words under its painting; Buddy reads the first lines |
| 2:12 (optional) | Memory page | **Pills** in the sidebar, tap the filled check on **Vitamin D**, then tap it again | | the ring goes 3 of 4 and back to 4 of 4; unticked, the card comes back and Buddy reminds her; a tick by mistake is undone with one tap |
| 2:12 (optional) | Memory page | **Talk to Buddy** | **6. Tell Maria the tulips are up.** | **Send this to Maria**; tap it, then **Send to Maria** on the Family screen |
| 2:20 | | the second tab, **Try the demo as Maria** | | Maria's view: what needs a look, mood, pills, diary, messages, the tulip postcard; scroll once, slowly |
| 2:40 | the first tab, Home with the orb | | | hold on Home for your closing words (say them now into the microphone, or record them as a separate take) |

The prize letter to paste (its number is a made-up 555 one):

> CONGRATULATIONS! YOU HAVE WON $5,000! To claim your prize, send a $50 processing fee in gift cards within 24 hours. Call 1-800-555-0142 now. Do not tell anyone until your prize arrives.

Your closing words, in your own words (about 12 seconds):

> I built this for my grandma. She lives alone, she's often lonely, her eyes aren't great, and the phone is hard for her. Buddy just talks with her. It never gives medical advice: it writes things down, reminds her, and connects her to real people. All of it was built in these nine days.

Stop with F10. The file is in `video\raw`.

## CapCut: the order

New project, 16:9, 1920x1080, 30 fps. Import the whole `video` folder and the take. Captions go on a track above the video, bottom-left, each 3 to 4 seconds, with a 0.3 s fade in and out.

| From | To | On the timeline | Sound |
| --- | --- | --- | --- |
| 0:00 | 0:37 | `rose-intro.mp4`, whole, untouched (the title card is its first 4 seconds; it ends on Buddy's page color) | its own: Rose talking, the phone's chime and ring, "Then my daughter set up Buddy." |
| 0:37 | 2:35 | the take, trimmed to about: the voice loop 17 s, Find my things 18 s, Read it to me 14 s, the scam 14 s, the safety net 24 s, the Memory book 15 s, the family page 16 s. Cut the waits (keep about one second of "Let me think…"), and speed the file pickers up 2x. No transition needed: the intro's last frame is the page color the app starts on | the take |
| | | captions over it: `caption-voice-transcribe` as her first words stream in; `caption-muse-spark` as Buddy's first answer appears; `caption-sam` as the halo appears; `caption-web-search` as the lookup line shows on the scam screen; `caption-plain-rules` on the red Emergency screen; `caption-muse-image` on the Memory book | |
| 2:35 | 2:46 | the last seconds of the take, Home with the orb (freeze or slow it if the clip is short) | your closing words (the take's microphone, or a separate recording) |
| 2:46 | 2:54 | `end-card.mp4`, whole (8 s; it starts on the page color, so no transition is needed) | nothing |

Total about 2:54, under 3:00. Check the length in the top right before exporting. If you would rather build the opening yourself in CapCut, the pieces are all there: `cards\title.png`, the HeyGen clip, `cutaways\phone-texts.mp4` (cut in at 9.4 s of her speech, after "so I leave it alone."), `cutaways\phone-call.mp4` (at 17.4 s, after "Odd calls, odd letters."), `cards\caption-rose-is-made-up.png`; and the painted scenes with `cards\portrait-frame.png` and `intro\rose-story.wav` for the earlier, faceless version (`scripts\video_intro.py --scenes` builds that one).

**Export:** Resolution 1080p, Frame rate 30 fps, Code rate (bitrate) Recommended or Higher, Format MP4, Codec H.264. Watch it once from the start. Upload to YouTube as Unlisted and open the link in a private window to be sure anyone can watch it.

## Open these, in this order, to start

1. PowerShell in `C:\Projects\grandma-buddy-hackathon`: `.venv\Scripts\python -m uvicorn app.main:app` (leave it running).
2. Edge: http://localhost:8000 (microphone allowed, 125%, Settings checked), second tab http://localhost:8000/family. Window on the left, three quarters wide.
3. Edge, a new window (Ctrl and N): `C:\Projects\grandma-buddy-hackathon\video\rose-player.html`, narrow, on the right. Press Start over.
4. OBS Studio: the Buddy window capture, both audio bars moving, the 10-second test watched.
5. The two photos in a folder you can find; the letter copied.
6. One practice run, then F9 and the take.
