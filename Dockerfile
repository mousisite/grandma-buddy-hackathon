# Grandma Buddy as a public demo (docs/DEPLOY.md). One image: Python, the
# packages, Buddy's natural voice (the Kokoro model, 354 MB, downloaded at
# build time and baked in, since a host wipes the disk on every deploy), and
# the app. The database lives in /app/data inside the container: fine for a
# demo that starts the made-up week over every night anyway (PUBLIC_DEMO=1).
FROM python:3.12-slim

WORKDIR /app

# espeak-ng turns words into sounds for Kokoro (kokoro-onnx brings its own
# copy too through espeakng-loader; the system one is a safety net).
RUN apt-get update \
 && apt-get install -y --no-install-recommends espeak-ng \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
 && pip install --no-cache-dir kokoro-onnx==0.6.1 --no-deps --ignore-requires-python

# The voice model and its voices, once per image (about a minute to download;
# this layer is kept between builds while get_voice.py doesn't change).
COPY scripts/get_voice.py scripts/get_voice.py
RUN python scripts/get_voice.py

COPY . .
RUN mkdir -p data

# The host tells the app its port (PORT) and sits in front of it as a proxy
# (so --proxy-headers lets the app see https and the visitor's address).
# The model loads in the background after the start, so the health check
# (/api/ping) answers at once; the browser's voice speaks until it is ready.
# Exactly ONE worker process: the voice's cache, the head start on each
# reply's first sentence, and the per-visitor shares live in one process.
# (Uvicorn would otherwise start WEB_CONCURRENCY workers, each loading the
# model and keeping its own cache, so repeats and pre-made lines would miss.)
ENV PORT=8000 WEB_CONCURRENCY=1
CMD ["sh", "-c", "python -m uvicorn app.main:app --workers 1 --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
