# scripts/get_voice.py
# Downloads Buddy's natural voice: the Kokoro voice model (Apache-2.0, by
# hexgrad), exported for kokoro-onnx by thewh1teagle, from GitHub. About
# 354 MB, into models/ (git-ignored). Run it once by hand:
#   .venv\Scripts\python scripts\get_voice.py
# Without these files Buddy still talks, with the browser's own voice.

import sys
import urllib.request
from pathlib import Path

RELEASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/"
FILES = ["kokoro-v1.0.onnx", "voices-v1.0.bin"]  # the voice model (326 MB) and its 54 voices (28 MB)
MODELS = Path(__file__).resolve().parent.parent / "models"


def main() -> int:
    MODELS.mkdir(exist_ok=True)
    for name in FILES:
        target = MODELS / name
        if target.exists():
            print(f"{name}: already here")
            continue
        print(f"Downloading {name}…")
        partial = target.with_suffix(target.suffix + ".part")
        urllib.request.urlretrieve(RELEASE + name, partial)
        partial.rename(target)  # only a complete file gets the real name
        print(f"{name}: {target.stat().st_size // (1024 * 1024)} MB")
    print("Done. Restart the app, and Buddy speaks with the natural voice.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
