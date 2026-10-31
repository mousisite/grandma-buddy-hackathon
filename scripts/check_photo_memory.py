# scripts/check_photo_memory.py
# Hand-run, real check of a Memory book page from an old photo
# (app/memories.py): the person check with SAM 3.1 and the description with
# Muse Spark, on two made-up photos:
#   - scripts/find_photos/kitchen.webp, a kitchen with no one in it;
#   - scripts/memory_photos/bench.webp, two small figures seen from behind
#     on a park bench, painted with Muse Image the first time this runs
#     (about 1 cent), so no real person is ever in a test photo.
# Prints whether SAM saw people, what Spark said, and what Buddy would say.
#
# Costs about 3 cents the first time (the painting), then about 1 cent.
#   .venv\Scripts\python scripts\check_photo_memory.py

import base64
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PHOTOS = {
    "kitchen": ROOT / "scripts" / "find_photos" / "kitchen.webp",
    "bench": ROOT / "scripts" / "memory_photos" / "bench.webp",
}
BENCH_PROMPT = ("A soft, slightly faded old color photograph of a park in autumn: two people sitting close together "
                "on a wooden bench, seen only from behind and far away, small in the frame, with no faces visible. "
                "Golden trees, fallen leaves, a path. No text anywhere.")


def data_url(path: Path) -> str:
    kind = {"webp": "image/webp", "jpg": "image/jpeg", "png": "image/png"}[path.suffix[1:]]
    return f"data:{kind};base64," + base64.b64encode(path.read_bytes()).decode()


def main() -> int:
    from app import memories, meta_client

    bench = PHOTOS["bench"]
    if not bench.exists():
        print("Painting the bench photo with Muse Image (about 1 cent)…")
        bench.parent.mkdir(exist_ok=True)
        bench.write_bytes(meta_client.paint(BENCH_PROMPT))
    failures = 0
    for name, path in PHOTOS.items():
        print(f"\n=== {name}")
        image = data_url(path)
        try:
            people = memories.has_people(image)
            scene, question = memories.described(image)
        except meta_client.MetaError as problem:
            print(f"FAILED: {problem}")
            failures += 1
            continue
        print(f"people: {people}  (expected {name == 'bench'})")
        print(f"scene: {scene or '(dropped by the checks)'}")
        print(f"question: {question or '(dropped by the checks)'}")
        print("Buddy says: " + (f"{scene} {question}" if scene else memories.PHOTO_OPENING))
        if people != (name == "bench"):
            print("UNEXPECTED: the person check disagrees with what the photo shows.")
            failures += 1
    print(f"\n2 photos looked at, about 1 cent.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
