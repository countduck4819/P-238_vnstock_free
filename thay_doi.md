# Thay đổi FinSight và hướng dẫn cấu hình deploy

## 1. Container được bổ sung

Phần FinSight bổ sung container mới:

### `finsight_api`

- Python FastAPI service cho Trợ lý ảo FinSight.
- Port nội bộ: `6071`.
- Build từ `Dockerfile.finsight`.
- Kết nối PostgreSQL schema `financial`.
- Truy vấn Qdrant Cloud.
- Sử dụng BGE-M3 embedding.
- Dùng volume `finsight_hf_cache` để lưu model cache.

Cấu hình Compose:

```yaml
services:
  finsight_api:
    container_name: finsight_api
    build:
      context: .
      dockerfile: Dockerfile.finsight
    working_dir: /app
    restart: unless-stopped
    env_file:
      - .env
    environment:
      FINANCIAL_DATABASE_URL: postgresql://countduck:${POSTGRES_PASSWORD}@db:5432/fireant_stock
      QDRANT_URL: ${QDRANT_URL}
      QDRANT_API_KEY: ${QDRANT_API_KEY}
    expose:
      - "6071"
    depends_on:
      db:
        condition: service_started
    volumes:
      - finsight_hf_cache:/root/.cache/huggingface

volumes:
  finsight_hf_cache:
```

Nếu PostgreSQL service có tên `fireant_db` thay vì `db`, dùng:

```ini
FINANCIAL_DATABASE_URL=postgresql://countduck:<DB_PASSWORD>@fireant_db:5432/fireant_stock
```

## 2. Container dùng lại

- `fireant_db`: PostgreSQL hiện có, không tạo database mới.
- `fireant_api`: NestJS hiện có, chỉ thêm cấu hình gọi FinSight.
- `fireant_web`: Next.js hiện có, không đổi endpoint frontend.
- `python_data`: service dữ liệu/dự báo cũ, khởi động theo stack hiện tại nếu cần.

## 3. Cấu hình NestJS

Trong container `fireant_api`:

```ini
FINSIGHT_API_URL=http://finsight_api:6071
FINSIGHT_API_TIMEOUT_MS=120000
```

NestJS tiếp tục phục vụ endpoint:

```text
/api/ai-stock/ask
```

Frontend không cần gọi trực tiếp port `6071`.

## 4. Cấu hình PostgreSQL

FinSight dùng database hiện có:

```text
Database: fireant_stock
Schema: financial
```

Kiểm tra serving facts:

```bash
docker exec fireant_db \
  psql -U countduck -d fireant_stock \
  -c "SELECT COUNT(*) FROM financial.vnstock_serving_facts;"
```

Kết quả mong đợi: `31993`.

Trong Docker phải dùng port nội bộ `5432` và hostname service (`db` hoặc `fireant_db`). Không dùng `127.0.0.1:5433` hoặc SSH tunnel trong container.

## 5. Cấu hình Qdrant Cloud

Production dùng Qdrant Cloud, không dùng Qdrant local:

```ini
QDRANT_URL=https://<QDRANT_CLOUD_ENDPOINT>
QDRANT_API_KEY=<QDRANT_API_KEY>
```

Collection yêu cầu:

```text
Name: company_knowledge_v1
Points: 3432
Dimension: 1024
Distance: cosine
```

Không cần chạy Qdrant Docker, loader hoặc nạp lại 3.432 documents nếu collection đã có đủ dữ liệu.

## 6. Khởi động deploy

Không chạy Compose project mới nếu VPS đã có stack `fireant_*`. Cập nhật Compose hiện tại để tránh trùng container, port và volume.

```bash
git checkout develop
git pull origin develop
docker compose build finsight_api
docker compose up -d finsight_api api web
```

Kiểm tra:

```bash
docker compose ps
docker compose logs --tail=100 finsight_api
docker compose logs --tail=100 api
```

Kiểm tra kết nối từ NestJS:

```bash
docker exec fireant_api \
  node -e "fetch('http://finsight_api:6071/health').then(r => r.text()).then(console.log)"
```

Kết quả mong đợi:

```json
{"status":"ok","app":"Trợ lý ảo FinSight"}
```

## 7. Bảo mật và lưu ý

- Không commit `.env`, database dump hoặc API key.
- Dùng Qdrant API key chỉ đọc cho runtime; key ghi chỉ dùng cho loader.
- Không public port `6071` ra Internet nếu không cần thiết; dùng Docker network nội bộ.
- Lần deploy đầu có thể mất thời gian tải BGE-M3.
- Volume `finsight_hf_cache` giúp không tải lại model khi recreate container.
- Các tính năng cũ có thể cần thêm artifact `runs`, `models`, `deploy` và service `python_data`.

## 8. Kiến trúc sau deploy

```text
Browser
  -> fireant_web
  -> fireant_api (NestJS)
  -> finsight_api (FastAPI:6071)
       -> fireant_db / financial schema
       -> Qdrant Cloud
```

