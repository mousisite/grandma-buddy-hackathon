# scripts/check_briefing.py
# Hand-run, real check of "what's happening today": today's weather for a
# made-up demo town from Open-Meteo (free, no key), then Meta's web search
# (Muse Spark with the built-in web_search tool) for one cheerful local
# thing and the local teams' sports, showing what came back and what Buddy
# would say after its checks (app/briefing.py: links out, no health or
# advice, at most 2 sentences).
#
# Costs under 1 cent: 2 searches ($0.0025 each) plus a few tokens.
# Uses a throwaway database, so nothing is added to her real one.
#   .venv\Scripts\python scripts\check_briefing.py
#   .venv\Scripts\python scripts\check_briefing.py --only weather

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TOWN = "Portland, Oregon"


def main(args: list[str]) -> int:
    folder = tempfile.mkdtemp(prefix="buddy-briefing-")
    os.environ["DATABASE_PATH"] = str(Path(folder) / "check.db")  # before the app reads its settings

    from app import briefing, db, meta_client, prompts, reminders

    db.init_db()
    connection = db.get_connection()
    topics = [args[args.index("--only") + 1]] if "--only" in args else list(briefing.TOPICS)
    now = reminders.current_time()
    day = f"{now:%A, %B} {now.day}"
    failures = 0
    if "weather" in topics:
        topics.remove("weather")
        print(f"\n=== weather for {TOWN}, from Open-Meteo")
        try:
            found = briefing.look_up(connection, "weather", TOWN)
        except briefing.WeatherError as problem:
            print(f"FAILED: {problem}")
            found, failures = None, failures + 1
        if found:
            print(f"Buddy says: {found['text']}  [{found['from']} {', '.join(found['sites'])}]")
        elif not failures:
            print("Open-Meteo doesn't know that town.")
            failures += 1
    for topic in topics:
        question = briefing.QUESTIONS[topic].format(town=TOWN, day=day)
        print(f"\n=== {topic}: {question}")
        try:
            raw = meta_client.search(question, prompts.BRIEFING.format(rules=prompts.BRIEFING_RULES[topic]), TOWN)
        except meta_client.MetaError as problem:
            print(f"FAILED: {problem}")
            failures += 1
            continue
        print(f"searched the web: {raw['searched']}")
        print(f"Meta's answer: {raw['text']}")
        print("sources: " + ", ".join(source["url"] for source in raw["sources"]))
        sites = [briefing.site(source["url"]) for source in raw["sources"]]
        print(f"Buddy says: {briefing.clean(raw['text']) or '(nothing left to share)'}  [from {', '.join(sites)}]")
        if not raw["searched"] or not raw["sources"]:
            failures += 1
    connection.close()
    print(f"\n{len(topics)} web searches, about {len(topics) * 0.3:.1f} cents (the weather is free).")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
