# scripts/video_cutaways.py
# The phone cutaways for the demo video's opening: full-screen shots of
# Rose's phone as the scam messages arrive. Two short clips, each
# photographed frame by frame from video/cutaways/src/phone.html with
# Playwright (so every frame is exact), with their own small sounds made
# here (a soft chime for a text, a ring for the call; no sound files from
# anywhere else), then put together by ffmpeg:
#   video/cutaways/phone-texts.mp4  4.5 s: two scam texts arrive
#   video/cutaways/phone-call.mp4   3.2 s: a call from an unknown number
#
# Run it by hand (no key, no internet):
#   .venv\Scripts\python scripts\video_cutaways.py

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.voice import wav_bytes  # noqa: E402  (the same WAV writer Buddy's voice uses)

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "video" / "cutaways" / "src" / "phone.html"
OUT = ROOT / "video" / "cutaways"
FFMPEG = shutil.which("ffmpeg") or r"C:\ProgramData\chocolatey\bin\ffmpeg.exe"
FPS = 30
RATE = 48000

SCENES = {
    # name: (seconds, the moments a sound plays, which sound)
    "texts": (4.5, [0.5, 2.3], "chime"),
    "call": (3.2, [0.3, 1.8], "ring"),
}


def tone(seconds: float, *frequencies: float, decay: float = 0.0, level: float = 0.3) -> np.ndarray:
    """A few sine waves added up, fading out exponentially when decay > 0."""
    t = np.arange(int(seconds * RATE)) / RATE
    wave = sum(np.sin(2 * np.pi * f * t) for f in frequencies) / len(frequencies)
    if decay:
        wave = wave * np.exp(-t * decay)
    edge = int(0.01 * RATE)  # a 10 ms ramp at each end, so nothing clicks
    wave[:edge] *= np.linspace(0, 1, edge)
    wave[-edge:] *= np.linspace(1, 0, edge)
    return (wave * level).astype(np.float32)


def sound(kind: str, at: list[float], seconds: float) -> bytes:
    track = np.zeros(int(seconds * RATE), dtype=np.float32)
    for moment in at:
        if kind == "chime":  # two high notes, short and soft, like a text arriving
            piece = tone(0.45, 1046.5, 1318.5, decay=7.0, level=0.28)
        else:  # the classic ring: 440 and 480 Hz together, one second long
            piece = tone(1.0, 440.0, 480.0, level=0.22)
        start = int(moment * RATE)
        end = min(len(track), start + len(piece))
        track[start:end] += piece[: end - start]
    return wav_bytes(track, RATE)


def film(page, name: str, seconds: float, frames_dir: Path) -> None:
    page.goto(SRC.as_uri() + "?scene=" + name)
    page.evaluate("document.fonts.load('17px Figtree')")
    count = round(seconds * FPS)
    for number in range(count):
        page.evaluate(f"render({number / FPS:.4f})")
        page.screenshot(path=str(frames_dir / f"{number:04d}.png"))


def main() -> int:
    if not SRC.exists():
        print(f"{SRC.relative_to(ROOT)} is missing.")
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright, tempfile.TemporaryDirectory() as temp:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
        for name, (seconds, moments, kind) in SCENES.items():
            frames = Path(temp) / name
            frames.mkdir()
            print(f"{name}: {round(seconds * FPS)} frames…")
            film(page, name, seconds, frames)
            wav = frames / "sound.wav"
            wav.write_bytes(sound(kind, moments, seconds))
            out = OUT / f"phone-{name}.mp4"
            subprocess.run([FFMPEG, "-v", "error", "-y", "-framerate", str(FPS), "-i", str(frames / "%04d.png"), "-i", str(wav),
                            "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p", "-r", str(FPS),
                            "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart", str(out)], check=True)
            print(f"  {out.relative_to(ROOT)}")
        browser.close()
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
