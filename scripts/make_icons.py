# scripts/make_icons.py
# The app's icons, drawn from Buddy's own orb (the CSS in static/styles.css
# and the markup buddy.js makes), so the home-screen icon is Buddy itself.
# Writes static/icons/: buddy-192.png and buddy-512.png (the orb on a clear
# background), buddy-maskable-512.png (on the page color, with room around
# it, for phones that cut icons into circles), and buddy-180.png (Apple's
# touch icon, on the page color). No AI, no sound files, nothing downloaded.
#   .venv\Scripts\python scripts\make_icons.py

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "static" / "icons"
ORB = ('<span class="orb-glow"></span><span class="orb-core"><span class="orb-flow">'
       '<span class="orb-blob orb-blob--amber"></span><span class="orb-blob orb-blob--peach"></span>'
       '<span class="orb-blob orb-blob--rose"></span><span class="orb-blob orb-blob--violet"></span>'
       '</span><span class="orb-swirl"></span><span class="orb-shine"></span></span>')
# (name, box size, orb size, background or None for clear)
ICONS = [
    ("buddy-512.png", 512, 400, None),
    ("buddy-192.png", 192, 150, None),
    ("buddy-maskable-512.png", 512, 300, "#F7F7F5"),
    ("buddy-180.png", 180, 128, "#F7F7F5"),
]


def page(size: int, orb: int, background: str | None) -> str:
    styles = (ROOT / "static" / "styles.css").read_text(encoding="utf-8")
    return f"""<!doctype html><html data-theme="light" data-calm><head><style>{styles}</style><style>
      html, body {{ margin: 0; background: transparent; }}
      #box {{ display: grid; place-items: center; width: {size}px; height: {size}px;
              background: {background or "transparent"}; }}
      .orb {{ --orb-size: {orb}px; view-transition-name: none; }}
    </style></head><body><div id="box"><div class="orb" data-buddy="idle">{ORB}</div></div></body></html>"""


def main() -> int:
    from playwright.sync_api import sync_playwright

    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        for name, size, orb, background in ICONS:
            tab = browser.new_page(viewport={"width": size, "height": size}, device_scale_factor=1)
            tab.set_content(page(size, orb, background))
            tab.wait_for_timeout(300)
            tab.locator("#box").screenshot(path=str(OUT / name), omit_background=background is None)
            tab.close()
        browser.close()
    favicon()
    print("Icons drawn: " + ", ".join(name for name, *_ in ICONS) + ", favicon.ico")
    return 0


def favicon() -> None:
    """/favicon.ico, with no new package: an ICO container holding the 192px
    PNG of the orb (browsers accept a PNG inside an ICO)."""
    import struct

    png = (OUT / "buddy-192.png").read_bytes()
    header = struct.pack("<HHH", 0, 1, 1)  # reserved, type 1 (icon), one picture
    entry = struct.pack("<BBBBHHII", 192, 192, 0, 0, 1, 32, len(png), 6 + 16)  # size, colors, planes, bits, bytes, offset
    (OUT / "favicon.ico").write_bytes(header + entry + png)


if __name__ == "__main__":
    sys.exit(main())
