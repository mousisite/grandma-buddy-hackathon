# scripts/check_read.py
# Hand-run, real check of "Read it to me" (app/reader.py) with Muse Spark.
# Three made-up papers, written here as small web pages and photographed
# with the browser into scripts/read_docs/ (the first time only): an
# electric bill, a clinic letter with test results, and a prize scam.
# Shows what Spark read and what Buddy would say after its checks, and
# saves each answer next to its photo (scripts/read_docs/<name>.json), so
# scripts/demo_screenshots.py can show the real words without calling Meta.
#
# Costs about 1 cent (3 photos read by Muse Spark).
#   .venv\Scripts\python scripts\check_read.py
#   .venv\Scripts\python scripts\check_read.py --only bill

import base64
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FOLDER = ROOT / "scripts" / "read_docs"
PROFILE = {"family_name": "Maria", "doctor_name": "Dr. Lee"}

STYLE = ("body{margin:0;background:#fff;font-family:Georgia,serif;color:#222}"
         ".page{width:760px;padding:56px 64px;box-sizing:border-box}"
         "h1{font-family:Arial,sans-serif;font-size:28px;margin:0 0 4px}.small{color:#555;font-size:15px}"
         "table{width:100%;border-collapse:collapse;margin:24px 0}td{padding:8px 0;border-bottom:1px solid #ddd;font-size:18px}"
         ".big{font-size:24px;font-weight:bold}p{font-size:18px;line-height:1.5}")

# All made up: the companies, the people, and the numbers.
PAPERS = {
    "bill": f"""<style>{STYLE}</style><div class="page">
      <h1>Riverside Power &amp; Light</h1><div class="small">PO Box 4410, Portland, OR</div>
      <p>Rose Demo<br>Account number 4417260093</p>
      <table><tr><td>Statement date</td><td>October 28, 2026</td></tr>
      <tr><td>Electricity used in October</td><td>612 kWh</td></tr>
      <tr><td class="big">Amount due</td><td class="big">$84.20</td></tr>
      <tr><td>Please pay by</td><td>November 15, 2026</td></tr></table>
      <p>Pay online, by phone, or by mail. Thank you for being our customer.</p></div>""",
    "clinic": f"""<style>{STYLE}</style><div class="page">
      <h1>Riverside Family Clinic</h1><div class="small">Dr. Lee</div>
      <p>Dear Rose Demo,</p>
      <p>Your lab results from October 20 are ready. Total cholesterol: 212 mg/dL. LDL: 141 mg/dL.
      Please call our office to talk about these results at your next visit on November 3 at 2 PM.</p>
      <p>Sincerely,<br>Riverside Family Clinic</p></div>""",
    "scam": f"""<style>{STYLE}</style><div class="page">
      <h1>NATIONAL PRIZE CENTER</h1><div class="small">Official Winner Notice</div>
      <p class="big">CONGRATULATIONS! YOU HAVE WON $5,000!</p>
      <p>To claim your prize, send a $50 processing fee in gift cards within 24 hours.
      Call 1-800-555-0142 now. Do not tell anyone until your prize arrives.</p></div>""",
}


def photos() -> dict:
    """The papers as PNG photos, made once with the browser."""
    FOLDER.mkdir(exist_ok=True)
    missing = [name for name in PAPERS if not (FOLDER / f"{name}.png").exists()]
    if missing:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={"width": 760, "height": 600})
            for name in missing:
                page.set_content(PAPERS[name])
                page.locator(".page").screenshot(path=str(FOLDER / f"{name}.png"))
            browser.close()
    return {name: "data:image/png;base64," + base64.b64encode((FOLDER / f"{name}.png").read_bytes()).decode()
            for name in PAPERS}


def main(args: list[str]) -> int:
    from app import meta_client, reader

    pictures = photos()
    names = [args[args.index("--only") + 1]] if "--only" in args else list(PAPERS)
    failures = 0
    for name in names:
        print(f"\n=== {name}")
        try:
            read = reader.read(pictures[name], PROFILE)
        except meta_client.MetaError as problem:
            print(f"FAILED: {problem}")
            failures += 1
            continue
        print(json.dumps({key: value for key, value in read.items() if key != "words"}, indent=2, ensure_ascii=False))
        (FOLDER / f"{name}.json").write_text(json.dumps(read, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"words (start): {read['words'][:160]}")
    print(f"\n{len(names)} papers read, about {len(names) * 0.3:.1f} cents.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
