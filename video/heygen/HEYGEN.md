# Rose, talking: the HeyGen step

Rose's face in the video is a made-up photo animated by HeyGen, speaking in her Kokoro voice. HeyGen's own tools here (the HyperFrames plugin) make motion-graphics videos, not talking faces, so this one step happens in your HeyGen account on the web. Everything else is made by the scripts in this project.

## What you upload

| File | What it is |
| --- | --- |
| `video\heygen\rose-photo.png` | Rose's photo, 1024x1536, painted by Muse Image from a description (an imagined person; nobody real). Front on, lips closed, soft light: what a photo avatar wants. |
| `video\heygen\rose-speech.wav` (or `.mp3`, the same sound) | Everything she says, 25.3 seconds: her story, a short pause, then "Then my daughter set up Buddy." In Kokoro's Kore voice, the same voice as her lines in the app demo, so she sounds like one person. |

Her words, in case HeyGen asks for a script as well (use the audio for the sound, not HeyGen's voice, so the cuts land in the right places):

> My name is Rose. It's quiet in the house now. I can't see so well, and the phone confuses me, so I leave it alone. My glasses wander off. Did I take my pills? I'm never sure. Odd calls, odd letters. I miss my daughter. I just wanted someone kind to talk to. Then my daughter set up Buddy.

## In HeyGen (about 10 minutes)

The names move around between HeyGen versions; the feature is the one that turns **a photo plus your own audio** into a talking video (called Avatar IV, Photo Avatar, Talking Photo, or Photo to Video depending on the page).

1. Sign in at https://app.heygen.com. Open **Create video**, or **Avatars**, and look for making an avatar **from a photo**.
2. Upload `rose-photo.png`. If it asks you to confirm you have the rights to the picture: you do; it was painted for this project and shows nobody.
3. For the speech choose **Upload audio** (not a typed script with a HeyGen voice) and upload `rose-speech.wav` (or the `.mp3` if WAV is refused).
4. Orientation **landscape (16:9)**, and the highest resolution offered (1080p if it is there, 720p is fine).
5. Generate, wait, watch it once. Her mouth should follow the words; if the first try looks off, generate once more, it varies.
6. Download the MP4 and save it as exactly:

   `C:\Projects\grandma-buddy-hackathon\video\heygen\rose-talking.mp4`

7. Back here, in PowerShell in the project folder, two commands:

   ```powershell
   .venv\Scripts\python scripts\video_remotion_data.py
   ```

   ```powershell
   cd video\remotion; npx remotion render RoseIntro ..\rose-intro.mp4 --crf 18; cd ..\..
   ```

   The first listens to the HeyGen clip with Whisper (every word's time), places the two phone cutaways right after "alone." and "letters.", and writes the words into the Remotion project; the second renders `video\rose-intro.mp4` (about a minute). The older ffmpeg-only cut, `scripts\video_intro.py`, still works as a fallback.

Free HeyGen plans put a small watermark on the video and may limit length; 25 seconds fits the free limit. If the watermark bothers you, a one-month Creator plan removes it.

**By the API instead** (only if you have a HeyGen API key with credits): HeyGen's "Photo to Video" and "Audio to Video" endpoints take a headshot (PNG or JPEG, up to 32 MB) and an audio file and return the MP4; see https://developers.heygen.com/photo-to-video.md and https://developers.heygen.com/audio-to-video. Save the result under the same name and run the same script.

## If HeyGen can't be used

`scripts\video_intro.py --scenes` builds the earlier version of the opening instead: her painted scenes with her portrait in the corner and the same voice, no talking face.
