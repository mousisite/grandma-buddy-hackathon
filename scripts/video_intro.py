# scripts/video_intro.py
# Rose's part of the demo video, finished, as one clip to drop into CapCut
# before the app footage, put together with ffmpeg:
#
#   the title card, then Rose talking (the HeyGen clip made from her photo
#   and her voice, video/heygen/HEYGEN.md), with the "Rose is made up"
#   caption over her first seconds, cut away twice to her phone as the
#   scam messages arrive (after "so I leave it alone." and after "Odd
#   calls, odd letters."), then back to her for the rest and "Then my
#   daughter set up Buddy.", and a fade to the app's page color so the cut
#   to Buddy is clean. Also the end card as a short clip.
#
# Run it by hand (nothing leaves the computer):
#   .venv\Scripts\python scripts\video_intro.py            # with video/heygen/rose-talking.mp4
#   .venv\Scripts\python scripts\video_intro.py --scenes   # the earlier opening: her painted scenes, no talking face
# Without the HeyGen clip it builds a stand-in from her photo and her
# speech, so the cut can be checked, and says so loudly.
# Needs video/cards/*.png (scripts/video_cards.py), video/cutaways/*.mp4
# (scripts/video_cutaways.py), video/heygen/rose-speech.wav and the intro
# WAVs (scripts/video_voice.py), and ffmpeg (choco install ffmpeg -y).
# Writes video/rose-intro.mp4 and video/end-card.mp4, 1920x1080, 30 fps.

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
V = ROOT / "video"
INTRO = V / "rose-intro.mp4"
END = V / "end-card.mp4"
CARDS = V / "cards"
TALKING = V / "heygen" / "rose-talking.mp4"   # from HeyGen, saved by hand (HEYGEN.md)
STAND_IN = V / "heygen" / "stand-in.mp4"      # her photo plus her speech, only to check the cut
PHOTO = V / "heygen" / "rose-photo.png"
SPEECH = V / "heygen" / "rose-speech.wav"
CUTAWAYS = [V / "cutaways" / "phone-texts.mp4", V / "cutaways" / "phone-call.mp4"]
FFMPEG = shutil.which("ffmpeg") or r"C:\ProgramData\chocolatey\bin\ffmpeg.exe"
FPS = 30
BG = "0xF7F7F5"  # the app's page color (styles.css --bg)

TITLE_SECONDS = 4.0
CAPTION_FROM, CAPTION_TO = 0.6, 6.0   # seconds into her talking, the "Rose is made up" caption
CUT_AFTER_SENTENCE = (3, 7)           # the cutaways go after her 3rd and 7th sentences
KOKORO_CUTS = (9.36, 17.38)           # where those gaps are in rose-speech.wav, if the clip's gaps can't be read
HOLD = 0.4                            # seconds of page color at the very end

# The same picture and sound shape for every piece, so they join without a seam.
PICTURE = (f"scale=1920:1080:force_original_aspect_ratio=decrease:flags=lanczos,"
           f"pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color={BG},fps={FPS},format=yuv420p,setsar=1")
SOUND = "aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo"
ENCODE = ["-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p", "-r", str(FPS),
          "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2"]


def run(command: list[str]) -> str:
    done = subprocess.run(command, check=True, capture_output=True, text=True)
    return done.stderr


def seconds_of(path: Path) -> float:
    probe = FFMPEG.replace("ffmpeg", "ffprobe")
    out = subprocess.run([probe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         check=True, capture_output=True, text=True).stdout
    return float(out.strip())


def silences(path: Path) -> list[tuple[float, float]]:
    """The quiet stretches (a quarter second or more) in a clip's sound."""
    log = subprocess.run([FFMPEG, "-i", str(path), "-af", "silencedetect=n=-40dB:d=0.22", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    starts = [float(m) for m in re.findall(r"silence_start: ([\d.]+)", log)]
    ends = [float(m) for m in re.findall(r"silence_end: ([\d.]+)", log)]
    return list(zip(starts, ends))


def cut_points(clip: Path) -> tuple[float, float]:
    """Where to cut away: the middle of the gap after her 3rd and 7th
    sentences, read from the clip's own sound (HeyGen may add a little
    silence at the start). Falls back to the Kokoro timings if the gaps
    can't be told apart."""
    quiet = silences(clip)
    lead = quiet[0][1] if quiet and quiet[0][0] < 0.05 else 0.0
    length = seconds_of(clip)
    gaps = [(a, b) for a, b in quiet if a > lead + 0.3 and b < length - 0.3]
    if len(gaps) >= 8:
        first, second = (gaps[n - 1] for n in CUT_AFTER_SENTENCE)
        return (first[0] + first[1]) / 2, (second[0] + second[1]) / 2
    print(f"  (found {len(gaps)} gaps between sentences, expected 9: using the Kokoro timings plus {lead:.2f} s)")
    return lead + KOKORO_CUTS[0], lead + KOKORO_CUTS[1]


def stand_in() -> Path:
    print("No video/heygen/rose-talking.mp4 yet: building a STAND-IN from her photo (HEYGEN.md says how to make the real one).")
    run([FFMPEG, "-v", "error", "-y", "-loop", "1", "-framerate", str(FPS), "-i", str(PHOTO), "-i", str(SPEECH),
         "-vf", PICTURE, "-af", SOUND, "-t", f"{seconds_of(SPEECH):.3f}", *ENCODE, "-movflags", "+faststart", str(STAND_IN)])
    return STAND_IN


def piece(out: Path, inputs: list[str], video: str, audio: str, extra: list[str] | None = None) -> Path:
    run([FFMPEG, "-v", "error", "-y", *inputs, "-filter_complex", f"{video};{audio}", "-map", "[v]", "-map", "[a]",
         *(extra or []), *ENCODE, str(out)])
    return out


def talking_intro() -> None:
    source = TALKING if TALKING.exists() else stand_in()
    length = seconds_of(source)
    first, second = cut_points(source)
    print(f"Rose's part: {source.name} ({length:.1f} s), cutaways at {first:.2f} s and {second:.2f} s…")
    with tempfile.TemporaryDirectory() as temp:
        T = Path(temp)
        pieces = []
        # 1. The title card: in from black, out to the page color.
        pieces.append(piece(T / "1-title.mp4",
                            ["-loop", "1", "-framerate", str(FPS), "-t", f"{TITLE_SECONDS}", "-i", str(CARDS / "title.png"),
                             "-f", "lavfi", "-t", f"{TITLE_SECONDS}", "-i", "anullsrc=r=48000:cl=stereo"],
                            f"[0:v]{PICTURE},fade=t=in:st=0:d=0.4,fade=t=out:st={TITLE_SECONDS - 0.4}:d=0.4:c={BG}[v]",
                            "[1:a]anull[a]"))
        # 2. Rose, up to the first cut, in from the page color, with the caption over her first seconds.
        caption = CARDS / "caption-rose-is-made-up.png"
        pieces.append(piece(T / "2-rose-a.mp4",
                            ["-i", str(source), "-loop", "1", "-framerate", str(FPS), "-t", f"{first:.3f}", "-i", str(caption)],
                            f"[0:v]trim=0:{first:.3f},setpts=PTS-STARTPTS,{PICTURE},fade=t=in:st=0:d=0.4:c={BG}[r];"
                            f"[1:v]format=rgba,fade=t=in:st={CAPTION_FROM}:d=0.4:alpha=1,fade=t=out:st={CAPTION_TO}:d=0.4:alpha=1[c];"
                            f"[r][c]overlay=0:0:enable='between(t,{CAPTION_FROM},{CAPTION_TO + 0.4})'[v]",
                            f"[0:a]atrim=0:{first:.3f},asetpts=PTS-STARTPTS,{SOUND}[a]"))
        # 3. Her phone: the scam texts.
        pieces.append(piece(T / "3-texts.mp4", ["-i", str(CUTAWAYS[0])], f"[0:v]{PICTURE}[v]", f"[0:a]{SOUND}[a]"))
        # 4. Rose, between the cuts.
        pieces.append(piece(T / "4-rose-b.mp4", ["-i", str(source)],
                            f"[0:v]trim={first:.3f}:{second:.3f},setpts=PTS-STARTPTS,{PICTURE}[v]",
                            f"[0:a]atrim={first:.3f}:{second:.3f},asetpts=PTS-STARTPTS,{SOUND}[a]"))
        # 5. Her phone: the unknown call.
        pieces.append(piece(T / "5-call.mp4", ["-i", str(CUTAWAYS[1])], f"[0:v]{PICTURE}[v]", f"[0:a]{SOUND}[a]"))
        # 6. Rose to the end, then the fade to the page color and a short hold.
        rest = length - second
        pieces.append(piece(T / "6-rose-c.mp4", ["-i", str(source)],
                            f"[0:v]trim={second:.3f},setpts=PTS-STARTPTS,{PICTURE},fade=t=out:st={rest - 0.6:.3f}:d=0.6:c={BG},"
                            f"tpad=stop_mode=add:stop_duration={HOLD}:color={BG}[v]",
                            f"[0:a]atrim={second:.3f},asetpts=PTS-STARTPTS,{SOUND},apad=pad_dur={HOLD}[a]"))
        # All six, one after the other.
        listing = T / "list.txt"
        listing.write_text("".join(f"file '{p.as_posix()}'\n" for p in pieces), encoding="utf-8")
        run([FFMPEG, "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing), *ENCODE, "-movflags", "+faststart", str(INTRO)])
    print(f"  {INTRO.relative_to(ROOT)}  ({seconds_of(INTRO):.1f} s)")
    if source == STAND_IN:
        print("  STAND-IN: Rose is a still photo here. Make the HeyGen clip (video/heygen/HEYGEN.md) and run this again.")


# ---------- The earlier opening: her painted scenes (--scenes) ----------

SCENE_SECONDS, LAST_SECONDS, DISSOLVE, ZOOM = 4.7, 5.5, 0.5, 0.06
STORY_AT, STORY_SECONDS, TRANSITION_AT, FADE_OUT_AT, SCENES_TOTAL = 4.0, 22.5, 26.8, 29.2, 30.0


def scenes_intro() -> None:
    scenes = sorted((V / "intro" / "scenes").glob("0*.png"))
    clips = [(CARDS / "title.png", TITLE_SECONDS)] + [(s, SCENE_SECONDS) for s in scenes[:-1]] + [(scenes[-1], LAST_SECONDS)]
    command = [FFMPEG, "-v", "error", "-y", "-loop", "1", "-framerate", str(FPS), "-t", f"{TITLE_SECONDS}", "-i", str(clips[0][0])]
    for scene, _ in clips[1:]:
        command += ["-i", str(scene)]
    for picture in [CARDS / "portrait-frame.png", CARDS / "caption-rose-is-made-up.png"]:
        command += ["-loop", "1", "-framerate", str(FPS), "-t", f"{SCENES_TOTAL}", "-i", str(picture)]
    command += ["-i", str(V / "intro" / "rose-story.wav"), "-i", str(V / "intro" / "rose-transition.wav")]
    portrait, caption, story, transition = range(len(clips), len(clips) + 4)
    graph = ["[0:v]format=yuv420p,setsar=1,setpts=PTS-STARTPTS[c0]"]
    for number, (_, seconds) in enumerate(clips[1:], start=1):
        frames = round(seconds * FPS)
        graph.append(f"[{number}:v]scale=3840:2160:flags=lanczos,"
                     f"zoompan=z='1+{ZOOM}*on/{frames - 1}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s=1920x1080:fps={FPS},"
                     f"format=yuv420p,setsar=1,setpts=PTS-STARTPTS[c{number}]")
    total, last = clips[0][1], "c0"
    for number in range(1, len(clips)):
        graph.append(f"[{last}][c{number}]xfade=transition=fade:duration={DISSOLVE}:offset={total - DISSOLVE:.2f}[x{number}]")
        last = f"x{number}"
        total += clips[number][1] - DISSOLVE
    p_in, p_out = STORY_AT + 0.5, FADE_OUT_AT - 1.2
    c_in, c_out = STORY_AT + 0.2, STORY_AT + STORY_SECONDS - 0.4
    graph.append(f"[{portrait}:v]format=rgba,fade=t=in:st={p_in}:d=0.5:alpha=1,fade=t=out:st={p_out}:d=0.5:alpha=1[pf]")
    graph.append(f"[{last}][pf]overlay=0:0:enable='between(t,{p_in},{p_out + 0.5})'[v1]")
    graph.append(f"[{caption}:v]format=rgba,fade=t=in:st={c_in}:d=0.4:alpha=1,fade=t=out:st={c_out}:d=0.4:alpha=1[cf]")
    graph.append(f"[v1][cf]overlay=0:0:enable='between(t,{c_in},{c_out + 0.4})'[v2]")
    graph.append(f"[v2]fade=t=in:st=0:d=0.4,fade=t=out:st={FADE_OUT_AT}:d=0.6:c={BG}[video]")
    graph.append(f"[{story}:a]adelay={int(STORY_AT * 1000)}:all=1[s]")
    graph.append(f"[{transition}:a]adelay={int(TRANSITION_AT * 1000)}:all=1[t]")
    graph.append(f"[s][t]amix=inputs=2:duration=longest:normalize=0,apad,{SOUND}[audio]")
    command += ["-filter_complex", ";".join(graph), "-map", "[video]", "-map", "[audio]", "-t", f"{SCENES_TOTAL}",
                *ENCODE, "-movflags", "+faststart", str(INTRO)]
    print(f"Rose's part from her painted scenes: {SCENES_TOTAL:.0f} s…")
    run(command)
    print(f"  {INTRO.relative_to(ROOT)}")


def end_card() -> None:
    seconds = 6.0
    run([FFMPEG, "-v", "error", "-y", "-loop", "1", "-framerate", str(FPS), "-t", f"{seconds}", "-i", str(CARDS / "end.png"),
         "-f", "lavfi", "-t", f"{seconds}", "-i", "anullsrc=r=48000:cl=stereo",
         "-vf", f"{PICTURE},fade=t=in:st=0:d=0.5:c={BG},fade=t=out:st={seconds - 0.8}:d=0.8",
         "-shortest", *ENCODE, "-movflags", "+faststart", str(END)])
    print(f"  {END.relative_to(ROOT)}  (the end card, 6 s)")


def main(argv: list[str]) -> int:
    if not Path(FFMPEG).exists():
        print("ffmpeg isn't here (choco install ffmpeg -y).")
        return 1
    needed = [CARDS / "title.png", CARDS / "end.png", CARDS / "caption-rose-is-made-up.png"]
    needed += [V / "intro" / "rose-story.wav", V / "intro" / "rose-transition.wav"] if "--scenes" in argv else [PHOTO, SPEECH, *CUTAWAYS]
    missing = [p.relative_to(ROOT) for p in needed if not p.exists()]
    if missing:
        print("Missing:", ", ".join(map(str, missing)))
        return 1
    scenes_intro() if "--scenes" in argv else talking_intro()
    end_card()
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
