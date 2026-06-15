FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr tesseract-ocr-chi-sim \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-postgres.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-postgres.txt

COPY . .

ENV STORAGE_PATH=/app/storage
ENV APP_ENV=production

EXPOSE 8000

RUN chmod +x docker-entrypoint.sh
CMD ["./docker-entrypoint.sh"]
