FROM python:3.10-slim

WORKDIR /app

# Pasang dependensi sistem jika diperlukan gcc
RUN apt-get update && apt-get install -y --no-install-recommends gcc python3-dev && rm -rf /var/lib/apt/lists/*

# Salin requirements dari folder backend dan pasang
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt || true

# Salin seluruh kode dari folder backend ke dalam kontainer
COPY backend/ .

EXPOSE 8000

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
