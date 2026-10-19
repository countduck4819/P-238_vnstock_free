FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# core/paths.py lấy thư mục cha của python_data làm gốc: dữ liệu ở /app/data.
WORKDIR /app/python

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade -r requirements.txt

COPY . .

EXPOSE 6060

CMD ["sh", "start.sh"]
