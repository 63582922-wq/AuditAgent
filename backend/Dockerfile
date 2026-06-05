FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr tesseract-ocr-chi-sim \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV DATABASE_URL=postgresql+psycopg2://fxpg:fxpg@postgres:5432/fxpg
ENV STORAGE_PATH=/app/storage

EXPOSE 8000

RUN chmod +x docker-entrypoint.sh
CMD ["./docker-entrypoint.sh"]
