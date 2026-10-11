# InvoiceDesk on Google Cloud Run (or any container host).
FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY app/ app/
COPY data/seed.json data/extraction_cache.json data/
COPY fixtures/ fixtures/
# Cloud Run sets PORT (8080 by default).
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}
