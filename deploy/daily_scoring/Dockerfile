FROM python:3.11-slim

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates libgomp1 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
RUN pip install --default-timeout=1000 --retries 10 --no-cache-dir -r requirements.txt --extra-index-url https://vnstocks.com/api/packages --extra-index-url https://vnstocks.com/api/simple 'vnstock>=4.0.9'
COPY . .
CMD ["python", "scripts/run_daily_model_scoring_service.py"]
