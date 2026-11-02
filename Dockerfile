# Grandma Buddy as a public demo (docs/DEPLOY.md). One small image: Python,
# the packages, the app. No natural voice here (its model is 354 MB): the
# browser's own voice speaks. The database lives in /app/data inside the
# container, which a host may wipe on each deploy: fine for a demo that
# starts the made-up week over every night anyway (PUBLIC_DEMO=1).
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p data

# The host tells the app its port (PORT) and sits in front of it as a proxy
# (so --proxy-headers lets the app see https and the visitor's address).
ENV PORT=8000
CMD ["sh", "-c", "python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
