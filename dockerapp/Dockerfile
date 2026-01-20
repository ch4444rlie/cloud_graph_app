FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create db directory (Kuzu needs it)
RUN mkdir -p /app/db

# Expose Flask port
EXPOSE 5000

# Production entrypoint — Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "3", "--timeout", "120", "main:app"]