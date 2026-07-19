FROM python:3.11-slim

WORKDIR /app

# Salin file requirements dan install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Salin seluruh source code backend
COPY . .

# Ganti 8000 sesuai dengan port aplikasi Python Anda
EXPOSE 8000

# Ganti perintah ini sesuai cara Anda menjalankan aplikasi (Contoh untuk FastAPI/Uvicorn)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]