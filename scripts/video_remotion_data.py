# scripts/video_remotion_data.py
# The numbers and words the Remotion opening (video/remotion/) is built from:
#   - which clip of Rose talking to use: video/heygen/rose-talking.mp4 (from
#     HeyGen, HEYGEN.md) or, until it exists, the stand-in from her photo;
#   - her words with their times, from Whisper (word timestamps), as the
#     Caption list Remotion's captions package expects;
#   - where to cut away to her phone: just after "alone." and "letters.".
# It copies the clip into video/remotion/public/media/ and writes
# video/remotion/src/data.ts. Run it by hand, then render:
#   .venv\Scripts\python scripts\video_remotion_data.py
#   cd video\remotion; npx remotion render RoseIntro ..\rose-intro.mp4
# Whisper runs on the GPU from C:\Users\mousi\.local\whisper-venv (CLAUDE.md).

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import video_intro  # noqa: E402  (the stand-in and ffprobe helpers)

ROOT = Path(__file__).resolve().parent.parent
V = ROOT / "video"
TALKING = V / "heygen" / "rose-talking.mp4"
SUBTITLES = V / "subtitles"
PUBLIC = V / "remotion" / "public" / "media"
DATA = V / "remotion" / "src" / "data.ts"
WHISPER = Path.home() / ".local" / "whisper-venv" / "Scripts" / "whisper.exe"
FFMPEG_DIR = r"C:\ProgramData\chocolatey\bin"  # whisper calls ffmpeg by name

CUT_WORDS = ("alone", "letters")  # the cutaways come right after these
AFTER_WORD = 0.25  # seconds of her pause kept before the cut


def words_of(clip: Path) -> list[dict]:
    """Whisper's words with times for this clip (transcribed once, kept in video/subtitles)."""
    out = SUBTITLES / (clip.stem + ".json")
    if clip.name == "stand-in.mp4":
        out = SUBTITLES / "rose-speech.json"  # the stand-in is her speech file exactly
    if not out.exists():
        env = dict(os.environ, PATH=FFMPEG_DIR + os.pathsep + os.environ.get("PATH", ""))
        print(f"Transcribing {clip.name} with Whisper (word timestamps)…")
        subprocess.run([str(WHISPER), str(clip), "--model", "turbo", "--device", "cuda", "--language", "en",
                        "--word_timestamps", "True", "--output_format", "json", "--output_dir", str(SUBTITLES)],
                       check=True, env=env, capture_output=True)
    data = json.loads(out.read_text(encoding="utf-8"))
    return [w for segment in data["segments"] for w in segment["words"]]


def captions_of(words: list[dict]) -> list[dict]:
    """The Caption shape (@remotion/captions): text with its leading space,
    times in ms, a page break after each sentence."""
    captions = []
    for w in words:
        text = w["word"].replace("buddy", "Buddy")
        captions.append({
            "text": text,
            "startMs": round(w["start"] * 1000),
            "endMs": round(w["end"] * 1000),
            "timestampMs": round((w["start"] + w["end"]) / 2 * 1000),
            "confidence": None,
            "pageBreakAfter": text.rstrip().endswith((".", "?", "!")),
        })
    return captions


def end_of(words: list[dict], wanted: str) -> float:
    for w in words:
        if w["word"].strip(" .,!?").lower() == wanted:
            return w["end"]
    raise SystemExit(f"Whisper didn't hear the word {wanted!r}; the cut can't be placed.")


def main() -> int:
    if TALKING.exists():
        clip = TALKING
    else:
        clip = video_intro.STAND_IN if video_intro.STAND_IN.exists() else video_intro.stand_in()
    PUBLIC.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(clip, PUBLIC / clip.name)
    words = words_of(clip)
    seconds = video_intro.seconds_of(clip)
    cuts = [end_of(words, w) + AFTER_WORD for w in CUT_WORDS]
    captions = captions_of(words)
    lines = [
        "// Written by scripts/video_remotion_data.py: do not edit by hand, run it again.",
        'import type { Caption } from "@remotion/captions";',
        "",
        f'export const CLIP = "media/{clip.name}";',
        f"export const CLIP_IS_STAND_IN = {'true' if clip.name == 'stand-in.mp4' else 'false'};",
        f"export const CLIP_SECONDS = {seconds:.3f};",
        f"export const CUT_1 = {cuts[0]:.3f}; // right after \"alone.\": the scam texts",
        f"export const CUT_2 = {cuts[1]:.3f}; // right after \"letters.\": the unknown call",
        "",
        "export const CAPTIONS: Caption[] = " + json.dumps(captions, indent=2, ensure_ascii=False) + ";",
        "",
    ]
    DATA.write_text("\n".join(lines), encoding="utf-8")
    print(f"{clip.name}: {seconds:.1f} s, {len(words)} words, cutaways after {cuts[0]:.2f} s and {cuts[1]:.2f} s")
    print(f"  wrote {DATA.relative_to(ROOT)} and copied the clip to {PUBLIC.relative_to(ROOT)}")
    if clip.name == "stand-in.mp4":
        print("  STAND-IN: Rose is a still photo. Make the HeyGen clip (video/heygen/HEYGEN.md), run this again, then render.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
