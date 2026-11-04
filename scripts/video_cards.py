# scripts/video_cards.py
# The demo video's cards for CapCut, as 1920x1080 PNGs rendered from HTML
# (video/cards/src/) in Buddy's own fonts and colors, with Playwright:
#   video/cards/title.png         the title card
#   video/cards/end.png           the end card (the live demo and the code)
#   video/cards/caption-*.png     lower-third captions, transparent except
#                                 the pill, to lay over the app footage
#
# Run it by hand (no key, no internet; the browser is the one the checks use):
#   .venv\Scripts\python scripts\video_cards.py
# If Playwright says the browser is missing: .venv\Scripts\python -m playwright install chromium

import sys
from pathlib import Path
from urllib.parse import quote

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "video" / "cards" / "src"
OUT = ROOT / "video" / "cards"

CAPTIONS = [
    ("caption-rose-is-made-up", "Rose is made up. Her voice and pictures are AI."),
    ("caption-voice-transcribe", "Muse Voice Transcribe, live"),
    ("caption-muse-spark", "Muse Spark 1.3"),
    ("caption-sam", "SAM 3.1 found them"),
    ("caption-muse-image", "Muse Image"),
    ("caption-web-search", "Meta web search"),
    ("caption-plain-rules", "Plain rules, no AI"),
]


def shoot(page, url: str, out: Path, transparent: bool = False) -> None:
    page.goto(url)
    # Both fonts, loaded for sure before the picture is taken (a face only
    # loads by itself once some text uses it; the captions use just one).
    page.evaluate("Promise.all([document.fonts.load('17px Figtree'), document.fonts.load('17px Newsreader')])")
    if not page.evaluate("document.fonts.check('17px Figtree')"):
        raise RuntimeError("Figtree didn't load; is static/fonts/Figtree.ttf there?")
    page.screenshot(path=str(out), omit_background=transparent, full_page=False)
    print(f"  {out.relative_to(ROOT)}")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
        print("Rendering the cards:")
        shoot(page, (SRC / "title.html").as_uri(), OUT / "title.png")
        shoot(page, (SRC / "end.html").as_uri(), OUT / "end.png")
        for name, text in CAPTIONS:
            shoot(page, (SRC / "caption.html").as_uri() + "?text=" + quote(text), OUT / f"{name}.png", transparent=True)
        # Rose's portrait in its corner frame, for the story (scripts/video_intro.py lays it over the scenes).
        if (ROOT / "video" / "intro" / "rose-portrait.png").exists():
            shoot(page, (SRC / "portrait.html").as_uri(), OUT / "portrait-frame.png", transparent=True)
        browser.close()
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
