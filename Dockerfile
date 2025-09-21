# Use a slim Python base
FROM python:3.11-slim

# Avoid interactive tzdata etc.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080

# System deps (add 'build-essential' only if a lib needs compiling)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Workdir
WORKDIR /app

# Install Python deps first (better caching)
COPY requirements.txt /app/
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy app
COPY . /app

# Non-root (optional but recommended)
RUN useradd -m appuser
USER appuser

EXPOSE 8080

# Start FastAPI via uvicorn; Railway sets $PORT
ENV PORT=8080
CMD ["sh","-c","uvicorn app:app --host 0.0.0.0 --port ${PORT:-8080} --log-level info"]
