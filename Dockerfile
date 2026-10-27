FROM python:3.12-slim

WORKDIR /app

COPY app ./app
COPY import_xlsx.py .
# Bundled spreadsheet for the in-app import. Lives outside /app/data because
# the Unraid bind mount (appdata -> /app/data) would shadow it.
COPY seed/ ./seed/

RUN pip install --no-cache-dir \
    fastapi==0.162.0 \
    uvicorn[standard]==0.54.0 \
    httpx==0.28.1 \
    openpyxl==3.1.5 \
    python-multipart==0.0.32

ENV DATA_DIR=/app/data
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
