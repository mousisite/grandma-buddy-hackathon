# scripts/video_scenes.py
# Rose's world in pictures, for the demo video's opening: six watercolor
# scenes painted by Muse Image in the Memory book's own style
# (app/memories.py, STYLE), with no people in them, so they stay
# consistent, plus one gentle portrait of Rose for a picture-in-picture
# corner. Everything is made up; no real person is ever painted.
#
# Writes 1920x1080 PNGs to video/intro/scenes/ and video/intro/rose-portrait.png
# (the raw pictures Meta sent back are kept in video/intro/scenes/raw/).
#
# This calls Meta's API (Muse Image, $0.01 a picture, about 8 cents for
# the lot). Run it by hand:
#   .venv\Scripts\python scripts\video_scenes.py            # everything that isn't painted yet
#   .venv\Scripts\python scripts\video_scenes.py --again    # paint them all again
#   .venv\Scripts\python scripts\video_scenes.py 03 portrait  # only these

import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import memories, meta_client  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SCENES = ROOT / "video" / "intro" / "scenes"
RAW = SCENES / "raw"
PORTRAIT = ROOT / "video" / "intro" / "rose-portrait.png"
FFMPEG = shutil.which("ffmpeg") or r"C:\ProgramData\chocolatey\bin\ffmpeg.exe"

WIDE = "1920x1080"  # asked of Meta first; if it refuses, a 3:2 page picture is painted and cropped
PAGE = meta_client.PICTURE_SIZE

# The book's style, and then: nobody in the picture at all.
STYLE = memories.STYLE + (
    " A wide, quiet scene of a home, seen as if standing in the room. There are no people in the picture, "
    "not even far away, and no faces of any kind. Calm, unhurried, lived-in."
)
PORTRAIT_STYLE = (
    "A gentle watercolor portrait, hand-painted on textured paper, with soft washes and loose, light ink lines, "
    "in a warm palette of peach, amber, rose, and soft violet with creamy white space, like a page from a beloved "
    "picture book. No text, letters, or numbers anywhere. The subject is an imagined, made-up person, not a real one."
)

SCENE_LIST = [
    ("01-kitchen-tea",
     "A small kitchen table by a window in early morning light: a cup of tea steaming on a saucer, a folded cloth "
     "napkin, a bowl of apples, a checked tablecloth with the sun falling across it."),
    ("02-glasses-windowsill",
     "A pair of reading glasses forgotten on a sunny windowsill, beside a small potted geranium, a lace curtain "
     "stirring, the garden soft and blurred outside."),
    ("03-phone-face-down",
     "A mobile phone lying face-down on a little side table next to an armchair, with a lamp with a fringed shade, "
     "a folded knitted blanket on the chair, and a ball of yarn with knitting needles."),
    ("04-pill-bottle-calendar",
     "A single amber pill bottle on a kitchen counter beside a glass of water, with a wall calendar hanging above "
     "showing only empty squares, nothing written on it, in gentle morning light."),
    ("05-letter-doormat",
     "A plain white envelope lying on a doormat inside a front door, morning light coming through the letterbox, "
     "a coat on a hook and an umbrella in a stand beside the door."),
    ("06-garden-window",
     "A window seen from inside a quiet living room, the garden outside in bloom with red tulips and a wooden "
     "bench, a small vase on the sill, warm afternoon light."),
]
PORTRAIT_SCENE = (
    "A kind older woman called Rose, imagined and made up: silver hair in a soft bun, gentle eyes behind round "
    "reading glasses, a faint warm smile, a soft cardigan, seen from the shoulders up against a plain creamy "
    "background with a hint of garden green. Painted loosely and tenderly, not photographic."
)

# A photograph-like picture of Rose for a talking "photo avatar" (HeyGen):
# a made-up person, front on, so the lip-sync has a clear face to work with.
PHOTO = ROOT / "video" / "heygen" / "rose-photo.png"
PHOTO_PROMPT = (
    "A realistic, natural photograph of a kind older woman in her late seventies, an imagined, made-up person "
    "who does not exist: soft silver hair in a loose bun, round reading glasses, a cream knitted cardigan, "
    "a gentle, warm expression with the lips closed, looking straight into the camera. Head and shoulders, "
    "face centered and well lit by soft window light, sharp focus on the eyes, a plain warm cream wall behind "
    "her, no text, no logos, no other people."
)


def paint(prompt: str, size: str) -> tuple[bytes, str]:
    """One picture at the asked size, or at the page size when Meta won't
    paint that shape. Returns the bytes and the size it was painted at."""
    try:
        return meta_client.paint(prompt, size=size), size
    except meta_client.MetaError as problem:
        if "400" not in str(problem) or size == PAGE:
            raise
        print(f"    Meta won't paint {size} ({problem}); painting {PAGE} and cropping instead")
        return meta_client.paint(prompt, size=PAGE), PAGE


def to_png(raw: Path, out: Path, width: int, height: int) -> None:
    """The raw picture as a PNG of exactly this size: scaled to cover it,
    then cropped in the middle (ffmpeg, no extra Python package)."""
    out.parent.mkdir(parents=True, exist_ok=True)
    scale = f"scale={width}:{height}:force_original_aspect_ratio=increase:flags=lanczos,crop={width}:{height}"
    subprocess.run([FFMPEG, "-v", "error", "-y", "-i", str(raw), "-vf", scale, "-frames:v", "1", str(out)], check=True)


def make(name: str, prompt: str, size: str, out: Path, width: int, height: int) -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    picture, painted_at = paint(prompt, size)
    kind = "png" if picture[:8] == b"\x89PNG\r\n\x1a\n" else "webp"
    raw = RAW / f"{name}.{kind}"
    raw.write_bytes(picture)
    to_png(raw, out, width, height)
    print(f"    {out.relative_to(ROOT)}  (painted at {painted_at}, {len(picture) // 1024} KB)")


def main(argv: list[str]) -> int:
    again = "--again" in argv
    only = [a for a in argv if not a.startswith("--")]
    if not Path(FFMPEG).exists():
        print("ffmpeg isn't here (choco install ffmpeg -y), and it's needed to make the PNGs.")
        return 1
    print("Painting with Muse Image ($0.01 a picture)…")
    for name, scene in SCENE_LIST:
        out = SCENES / f"{name}.png"
        if only and not any(name.startswith(o) for o in only):
            continue
        if out.exists() and not again:
            print(f"    {out.relative_to(ROOT)}  already painted (--again paints it anew)")
            continue
        print(f"  {name}")
        make(name, STYLE + "\n\nThe scene: " + scene, WIDE, out, 1920, 1080)
    if (not only or "portrait" in only) and (again or not PORTRAIT.exists()):
        print("  rose-portrait")
        make("rose-portrait", PORTRAIT_STYLE + "\n\nThe portrait: " + PORTRAIT_SCENE, "1024x1024", PORTRAIT, 1024, 1024)
    if "photo" in only and (again or not PHOTO.exists()):  # only when asked: it is for the talking avatar
        print("  rose-photo (for HeyGen)")
        picture, painted_at = paint(PHOTO_PROMPT, "1024x1536")
        kind = "png" if picture[:8] == b"\x89PNG\r\n\x1a\n" else "webp"
        raw = RAW / f"rose-photo.{kind}"
        raw.write_bytes(picture)
        width, height = (1024, 1536) if painted_at == "1024x1536" else (1024, 1024)
        to_png(raw, PHOTO, width, height)
        print(f"    {PHOTO.relative_to(ROOT)}  (painted at {painted_at}, {len(picture) // 1024} KB)")
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
