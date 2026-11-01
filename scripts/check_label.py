# scripts/check_label.py
# Hand-run, real check of a pill from a photo of its bottle (app/labels.py)
# with Muse Spark: a made-up bottle label, drawn here as a small web page
# and photographed with the browser into scripts/read_docs/label.png (the
# first time only). Prints the name and the label Spark read, which must be
# the printed words. Costs well under a cent (one photo read).
#   .venv\Scripts\python scripts\check_label.py

import base64
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FOLDER = ROOT / "scripts" / "read_docs"
# A made-up medicine and pharmacy; "Demopril" exists nowhere.
LABEL = """<style>
  body{margin:0;background:#dcd6c8}
  .label{width:520px;margin:30px;padding:26px 30px;background:#fff8e7;border:2px solid #b89b5e;border-radius:18px;
         font-family:Arial,sans-serif;color:#222;box-sizing:border-box}
  .rx{font-size:14px;color:#555}.name{font-size:30px;font-weight:bold;margin:8px 0}.dir{font-size:22px;margin:10px 0}
  .small{font-size:14px;color:#555}
</style><div class="label">
  <div class="rx">RIVERSIDE PHARMACY · RX 0018823 · ROSE DEMO</div>
  <div class="name">DEMOPRIL 10 MG TABLET</div>
  <div class="dir">TAKE 1 TABLET BY MOUTH EVERY MORNING WITH WATER</div>
  <div class="small">QTY 30 · REFILLS 2 · DR. LEE</div>
</div>"""
EXPECTED_WORDS = ["take 1 tablet", "every morning"]


def photo() -> str:
    FOLDER.mkdir(exist_ok=True)
    path = FOLDER / "label.png"
    if not path.exists():
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={"width": 600, "height": 300})
            page.set_content(LABEL)
            page.locator(".label").screenshot(path=str(path))
            browser.close()
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()


def main() -> int:
    from app import labels, meta_client

    try:
        read = labels.read_label(photo())
    except (ValueError, meta_client.MetaError) as problem:
        print(f"FAILED: {problem}")
        return 1
    print("name:", read["name"])
    print("label:", read["label"])
    problems = [words for words in EXPECTED_WORDS if words not in read["label"].lower()]
    if "demopril" not in read["name"].lower():
        problems.append("the name")
    for missing in problems:
        print(f"PROBLEM: {missing} was not read as printed")
    print("Label check:", "PROBLEMS FOUND" if problems else "OK (well under a cent)")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
