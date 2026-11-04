# scripts/video_subtitles.py
# Subtitles for any take of the demo video (the OBS recording of the app,
# your closing words, a HeyGen clip), made with Whisper on this PC's GPU:
# an .srt to import into CapCut (Text, Import subtitles) and a .json with
# every word's time. Nothing leaves the computer.
#
# Run it by hand:
#   .venv\Scripts\python scripts\video_subtitles.py video\raw\take.mp4
#   .venv\Scripts\python scripts\video_subtitles.py video\raw\take.mp4 --model large-v3-turbo
# Writes video\subtitles\<name>.srt, .vtt, .txt, .json. Whisper lives in
# C:\Users\mousi\.local\whisper-venv (CLAUDE.md); the first run of a model
# downloads it once.

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "video" / "subtitles"
WHISPER = Path.home() / ".local" / "whisper-venv" / "Scripts" / "whisper.exe"
FFMPEG_DIR = r"C:\ProgramData\chocolatey\bin"  # whisper calls ffmpeg by name


def main(argv: list[str]) -> int:
    files = [a for a in argv if not a.startswith("--")]
    if not files:
        print("Which file? For example: .venv\\Scripts\\python scripts\\video_subtitles.py video\\raw\\take.mp4")
        return 1
    model = argv[argv.index("--model") + 1] if "--model" in argv else "turbo"
    if not WHISPER.exists():
        print(f"Whisper isn't at {WHISPER}. See CLAUDE.md for how it was installed.")
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, PATH=FFMPEG_DIR + os.pathsep + os.environ.get("PATH", ""))
    for name in files:
        path = Path(name)
        if not path.exists():
            print(f"{path} isn't there.")
            return 1
        print(f"{path.name}: listening with Whisper ({model}, GPU)…")
        subprocess.run([str(WHISPER), str(path), "--model", model, "--device", "cuda", "--language", "en",
                        "--word_timestamps", "True", "--output_format", "all", "--output_dir", str(OUT)],
                       check=True, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        srt = OUT / (path.stem + ".srt")
        print(f"  {srt.relative_to(ROOT)}  (import it in CapCut: Text, then Import subtitles)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
