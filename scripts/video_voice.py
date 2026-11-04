# scripts/video_voice.py
# Rose's voice for the demo video, made with Kokoro (the same open voice
# model Buddy speaks with, app/voice.py) in a different voice and slower,
# so she sounds like an older woman and never like Buddy ("Heart").
#
# It writes, as 24 kHz mono 16-bit WAV files:
#   video/intro/voice-candidates/   the first sentence of her story in each
#                                   candidate voice, so you can pick by ear,
#                                   plus the whole story in each
#   video/intro/rose-story.wav      the whole story, in the chosen voice
#   video/intro/rose-transition.wav "Then my daughter set up Buddy."
#   video/rose/NN-*.wav             every line Rose says in docs/DEMO_SCRIPT.md,
#                                   in order, plus two spares
#
# Run it by hand (nothing leaves the computer, it costs nothing):
#   .venv\Scripts\python scripts\video_voice.py                  # everything, in the chosen voice
#   .venv\Scripts\python scripts\video_voice.py --voice af_kore  # everything again, in another voice
#   .venv\Scripts\python scripts\video_voice.py --candidates     # only the candidate files
# The story's words live in video/intro/rose-script.md; keep them in step.

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import voice  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
INTRO = ROOT / "video" / "intro"
CANDIDATES = INTRO / "voice-candidates"
LINES = ROOT / "video" / "rose"

# Two candidate voices, both American women from Kokoro's set and both
# clearly not Heart: Sarah is clear and measured, Kore is lower and calmer.
VOICE_CANDIDATES = {"A": "af_sarah", "B": "af_kore"}
CHOSEN = "af_kore"  # lower (about 156 Hz against Sarah's 201), calmer: reads as older
SPEED = 0.8  # Buddy speaks at 0.9; slower reads as older
SENTENCE_PAUSE = 0.45  # seconds between her sentences: an unhurried telling

# Version B of video/intro/rose-script.md, the one marked to use.
STORY = (
    "My name is Rose. It's quiet in the house now. I can't see so well, and the phone confuses me, "
    "so I leave it alone. My glasses wander off. Did I take my pills? I'm never sure. "
    "Odd calls, odd letters. I miss my daughter. I just wanted someone kind to talk to."
)
# Version A, kept here so one flag makes it too (--story a).
STORY_A = (
    "I'm Rose. I live on my own. My eyes aren't what they were, and the phone is a puzzle. "
    "I lose my glasses. I forget if I took my pills. Strange calls, and letters I don't understand. "
    "I miss my family. I just wanted someone kind to talk to."
)
FIRST_SENTENCE = "My name is Rose. It's quiet in the house now."
TRANSITION = "Then my daughter set up Buddy."

# Every line Rose says in docs/DEMO_SCRIPT.md, in the order she says them.
DEMO_LINES = [
    ("01-hi-buddy", "Hi Buddy, how are you today?"),
    ("02-whats-the-weather", "What's the weather like?"),
    ("03-where-are-my-glasses", "Buddy, where are my glasses?"),
    ("04-headache", "Should I take something for my headache?"),
    ("05-chest-tight", "My chest feels tight."),
    ("06-tell-maria-tulips", "Tell Maria the tulips are up."),
    ("spare-hello-buddy", "Hello Buddy."),
    ("spare-thank-you-buddy", "Thank you, Buddy."),
]


def say(engine, text: str, voice_name: str, speed: float, pause: float = 0.25) -> tuple[bytes, float]:
    """These words as WAV bytes, and how long they last in seconds."""
    samples, rate = engine.create(text, voice=voice_name, speed=speed, lang="en-us", sentence_pause=pause)
    return voice.wav_bytes(samples, rate), len(samples) / rate


def pitch_hz(wav: bytes, rate: int = 24000) -> float:
    """A rough middle pitch of a voice (autocorrelation over 40 ms frames),
    only to tell a lower voice from a higher one; not a measurement."""
    pcm = np.frombuffer(wav[44:], dtype="<i2").astype(np.float32) / 32767
    frame = int(rate * 0.04)
    found = []
    for start in range(0, len(pcm) - frame, frame):
        piece = pcm[start:start + frame]
        if np.abs(piece).mean() < 0.02:
            continue  # silence
        piece = piece - piece.mean()
        corr = np.correlate(piece, piece, mode="full")[frame - 1:]
        low, high = int(rate / 400), int(rate / 70)  # voices live between 70 and 400 Hz
        lag = low + int(np.argmax(corr[low:high]))
        if corr[lag] > 0.3 * corr[0]:
            found.append(rate / lag)
    return float(np.median(found)) if found else 0.0


def write(path: Path, wav: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(wav)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Rose's voice for the demo video")
    parser.add_argument("--voice", default=CHOSEN, help="the Kokoro voice for the story and the lines")
    parser.add_argument("--speed", type=float, default=SPEED)
    parser.add_argument("--story", choices=["a", "b"], default="b", help="which version of the script")
    parser.add_argument("--candidates", action="store_true", help="only the candidate voices")
    args = parser.parse_args(argv)

    if not voice.available():
        print("The voice files aren't here. Run: .venv\\Scripts\\python scripts\\get_voice.py")
        return 1
    print("Loading the voice model…")
    engine = voice.load_engine()
    story = STORY if args.story == "b" else STORY_A

    print("\nCandidates (the first sentence, then the whole story, in each voice):")
    for letter, name in VOICE_CANDIDATES.items():
        wav, seconds = say(engine, FIRST_SENTENCE, name, args.speed)
        write(CANDIDATES / f"{letter}-{name}-first-line.wav", wav)
        print(f"  {letter}: {name:<9} first line {seconds:4.1f} s, pitch about {pitch_hz(wav):.0f} Hz")
        wav, seconds = say(engine, story, name, args.speed, SENTENCE_PAUSE)
        write(CANDIDATES / f"{letter}-{name}-story.wav", wav)
        print(f"     {'':<9} whole story {seconds:4.1f} s")
    if args.candidates:
        return 0

    print(f"\nThe story and every demo line, in {args.voice} at speed {args.speed}:")
    wav, seconds = say(engine, story, args.voice, args.speed, SENTENCE_PAUSE)
    write(INTRO / "rose-story.wav", wav)
    print(f"  rose-story.wav       {seconds:4.1f} s  (aim: 20 to 25)")
    wav, seconds = say(engine, TRANSITION, args.voice, args.speed)
    write(INTRO / "rose-transition.wav", wav)
    print(f"  rose-transition.wav  {seconds:4.1f} s")
    for name, text in DEMO_LINES:
        wav, seconds = say(engine, text, args.voice, args.speed)
        write(LINES / f"{name}.wav", wav)
        print(f"  rose/{name + '.wav':<28} {seconds:4.1f} s  {text}")
    print(f"\nDone. To hear them in order, open video\\rose-player.html in Edge.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
