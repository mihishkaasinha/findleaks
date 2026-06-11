FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .

RUN mkdir -p /app/uploads /app/faiss_indexes

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UPLOAD_DIR=/app/uploads \
    FAISS_INDEX_DIR=/app/faiss_indexes

EXPOSE 8000

CMD ["/bin/sh", "-c", "uvicorn app:create_app --factory --host 0.0.0.0 --port ${PORT:-8000}"]
