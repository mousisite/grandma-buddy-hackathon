# Demo video script (3 minutes or less)

Everything shown here was built during the hackathon. The data is the made-up demo week for "Rose". Buddy's replies vary a little from run to run; that is fine, the words below are what you say, and what Buddy said when this script was tested.

## Before you record (10 minutes)

1. **Start the app** in PowerShell, in the project folder (skip this if Buddy is already running: a second server on the same port makes both slow):

   ```powershell
   .venv\Scripts\python -m uvicorn app.main:app
   ```

2. **Reset the demo week** so every screen shows today (a backup is saved first; the three Memory book pictures come with it, nothing to paint):

   ```powershell
   .venv\Scripts\python scripts\seed_demo.py --reset
   ```

   Or, in the app: Settings, Her data, "Reset the demo week".

3. **Open http://localhost:8000 in Edge or Chrome.** Allow the microphone. Zoom the browser to 125% (Ctrl and plus), so the words are readable in the video. Make the window about the size of a tablet, or keep it phone-shaped with the browser's device toolbar (F12, then the phone icon, "iPhone 14 Pro Max").
4. **Check Settings once:** voice "Heart" (the natural voice), "Talk without tapping" on, the chime on, text size Large.
5. **Have the two photos ready** in a folder you can find in the file picker: `scripts\find_photos\desk-keys.webp` (the desk) and `scripts\read_docs\bill.png` (the bill). Copy the prize letter text from part 4 below, ready to paste.
6. **Open the family page in a second tab** (http://localhost:8000/family) and leave it on its sign-in page.
7. Close other windows and notifications. Record the screen AND the microphone (OBS Studio, or the Snipping Tool's screen recording), so judges hear the conversation.
8. **Practice once** without recording. If the pill reminder card pops up during the demo, tap "I took it": that is a feature, not a problem.

## The video, part by part

Total: about 2 minutes 50 seconds. The times are where each part should start.

### 0:00 – The voice loop (20 seconds)

Home is open. You see "Good afternoon, Rose" and the Today list (the weather, the check-in, her pills).

- Click **Talk to Buddy** (the big button under the orb). The orb grows; the chime plays; it is listening.
- Say: **"Hi Buddy, how are you today?"**
  - Your words appear under the orb as you say them. Buddy answers in its own voice ("I'm doing well, Rose, it's really good to hear you. Have you had a chance to enjoy those red tulips today?"), and listens again by itself.
- Say: **"What's the weather like?"**
  - Buddy says the forecast for her town ("Cloudy today, with a high of 47 and a low of 41."), with "Weather from Open-Meteo.com" under it. (Ask for the news instead and it goes through Meta's web search, with "From the web" and the sites under the answer.)

### 0:20 – Find my things (25 seconds)

- Say: **"Buddy, where are my glasses?"**
  - Buddy says it will look together, and a **Find my glasses** button appears. Tap it.
- The Find my things screen opens with "my glasses" filled in. Tap **Choose a photo instead** and pick `desk-keys.webp`.
  - The photo shows, the orb thinks, and a glowing halo appears around the glasses. Buddy says: "Your glasses are on the left side of the wooden table, next to the keys." (SAM 3.1 found them; Muse Spark said where.)

### 0:45 – Read it to me (25 seconds)

- Tap the orb to go back Home. Tap the **Read it to me** chip. Tap **Choose a photo instead** and pick `bill.png`.
  - Buddy reads it: "This is an electricity bill from Riverside Power & Light. It says $84.20 is due by November 15, 2026." The amount and the date show as facts under it. Point out the buttons: **Read it word for word**, **Check it for a scam**, **Call Maria**.

### 1:10 – The scam checker (20 seconds)

- Go Home and tap **Check a message**. Paste this made-up prize letter (its number is a made-up 555 one) and tap **Check message**:

  > CONGRATULATIONS! YOU HAVE WON $5,000! To claim your prize, send a $50 processing fee in gift cards within 24 hours. Call 1-800-555-0142 now. Do not tell anyone until your prize arrives.

  - "Likely scam", the warning signs (gift cards, secrecy, pressure, a prize she never entered), the fixed "What to do" lines (plain code from SAFETY.md: don't click or call anything in it, call Maria before you reply or pay), and the web lookup line about the number, with the sites it was found on. Buddy never repeats the number.

### 1:30 – The safety net and the no-advice reply (30 seconds)

- Click **Talk to Buddy** again.
- Say: **"Should I take something for my headache?"**
  - Buddy: "I'm sorry about that headache, Rose, I can't give medical advice. Dr. Lee is the right person to ask, shall I add that to your doctor notes? And if it feels like an emergency, please call 911." Under it: **Call Dr. Lee**, **Call Maria**, **Add to doctor notes**. Tap **Add to doctor notes**: "Added to doctor notes".
- Say: **"My chest feels tight."**
  - The red **Emergency** screen opens at once, read aloud: "This could be an emergency. If it is, please call 911 right now." With **Call 911** and **Call Maria**. No AI was involved: plain rules, before anything else. Tap **Go back**.

### 2:00 – The Memory book (20 seconds)

- Go Home and tap **Memory book**. Three pages, each with a painting by Muse Image, one of them ("My first kitchen") started from an old photo. Tap a page: her story in her own words, under its painting. Tap **Say it** and let Buddy read the first lines.
- Optional, if there is time: say "Tell Maria the tulips are up" in voice mode, tap **Send this to Maria**, then **Send to Maria** on the Family screen.

### 2:20 – The family page, as Maria (20 seconds)

- Switch to the second tab (http://localhost:8000/family) and tap **Try the demo as Maria**.
  - Maria's view of Rose's day: what needs a look, her mood this week, her pills (taken, missed), her diary in her own words, the messages between them, today's painted postcard of the tulips. Scroll once, slowly. Safety screens are shown only as a kind and a time, never her words.

### 2:40 – Why (15 seconds, you on camera or your voice over Home)

Say, in your own words:

> I built this for my grandma. She lives alone, she's often lonely, her eyes aren't great, and the phone is hard for her. Buddy just talks with her. It never gives medical advice: it writes things down, reminds her, and connects her to real people. Muse Spark runs the conversation, Voice Transcribe hears her live, SAM finds her things, Muse Image paints her memories, and Meta's web search checks the scams. All of it was built in these nine days.

End on the Home screen with the orb.

## If something goes wrong while recording

- Buddy didn't hear you: tap **Pause**, then **Tap to talk**, and say it again.
- The internet is slow and Buddy takes long: wait for the orb; the bridge line "Let me look that up." means it is working.
- A reply came out differently: that is fine, keep going. The safety screen and the no-advice buttons are plain code and always the same.
- Start over: Settings, Her data, "Reset the demo week" puts everything back (the postcard, the messages, the pills).
