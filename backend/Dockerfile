FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Uploaded documents live here and are deleted after processing (ADR-005).
RUN mkdir -p /app/.workspace

EXPOSE 8000
# Hosts such as Render inject $PORT; 8000 locally. Shell form so it expands.
# One worker on purpose: jobs, documents and the duplicate-analysis guard live
# in process memory (README "What the in-process runner is not"), so a second
# worker would not see them.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
