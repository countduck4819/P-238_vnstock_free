# Hướng dẫn deploy FinSight

Tài liệu này dành cho việc thêm FinSight vào stack P-238 đang chạy trên VPS bằng Docker Compose.

Kiến trúc production dự kiến:

```text
Browser
  -> Next.js
  -> NestJS API
  -> FinSight API
       -> PostgreSQL financial schema
       -> Qdrant Cloud
```

Browser không cần gọi trực tiếp FinSight API. NestJS đóng vai trò proxy qua endpoint chatbot hiện có.

Không đưa mật khẩu, API key hoặc file `.env` production vào Git.

## 1. Yêu cầu

VPS cần có:

- Git.
- Docker Engine.
- Docker Compose plugin.
- Kết nối Internet trong lần đầu để tải image, Python dependencies và BGE-M3.
- PostgreSQL hiện tại chứa cả dữ liệu ứng dụng và schema `financial`.
- Qdrant Cloud chứa collection `company_knowledge_v1`.

Khuyến nghị máy chủ có ít nhất 8 GB RAM để BGE-M3 chạy ổn định trên CPU. Với lưu lượng lớn nên cân nhắc nhiều CPU hơn hoặc triển khai inference riêng.

## 2. Pull source

```bash
git checkout develop
git pull origin develop
```

Không chạy một Compose project mới nếu VPS đã có các container `fireant_db`, `fireant_api` và `fireant_web`. Hãy cập nhật Compose đang được dùng để deploy nhằm tránh trùng container name, port và volume.

## 3. Kiểm tra PostgreSQL

Database production phải có schema `financial` và dữ liệu serving facts:

```bash
docker exec fireant_db \
  psql -U countduck -d fireant_stock \
  -c "SELECT COUNT(*) FROM financial.vnstock_serving_facts;"
```

Kết quả mong đợi:

```text
31993
```

Nếu schema hoặc dữ liệu chưa tồn tại, phải restore database backup hoặc chạy migration/loader được phê duyệt trước khi khởi động FinSight.

## 4. Cấu hình database cho container

Container không được dùng `127.0.0.1:5433`. Địa chỉ này chỉ dành cho máy local chạy qua SSH tunnel.

Nếu Compose dùng service name `db`:

```ini
FINANCIAL_DATABASE_URL=postgresql://countduck:<DB_PASSWORD>@db:5432/fireant_stock
```

Nếu service production được gọi là `fireant_db` và hostname này khả dụng trong Docker network:

```ini
FINANCIAL_DATABASE_URL=postgresql://countduck:<DB_PASSWORD>@fireant_db:5432/fireant_stock
```

Giữa các container phải dùng port PostgreSQL nội bộ `5432`, không dùng host port `5000`.

## 5. Cấu hình Qdrant Cloud

Thiết lập bằng deployment secrets:

```ini
QDRANT_URL=https://<QDRANT_CLOUD_ENDPOINT>
QDRANT_API_KEY=<QDRANT_READ_ONLY_API_KEY>
```

Yêu cầu:

- Collection: `company_knowledge_v1`.
- Point count: `3432`.
- Embedding: BAAI/bge-m3.
- Vector dimension: `1024`.
- Distance: cosine.

FinSight production chỉ truy vấn dữ liệu nên ưu tiên API key chỉ có quyền đọc collection. API key có quyền ghi chỉ được dùng cho loader.

## 6. Cấu hình FinSight service

Service tham khảo trong Docker Compose:

```yaml
services:
  finsight_api:
    container_name: finsight_api
    build:
      context: .
      dockerfile: Dockerfile.finsight
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

Điều chỉnh hostname `db` theo đúng service PostgreSQL của Compose production.

Volume `finsight_hf_cache` giúp giữ BGE-M3 sau khi container được recreate. Nếu không có volume, model có thể phải tải lại.

## 7. Cấu hình NestJS

Trong service NestJS:

```ini
FINSIGHT_API_URL=http://finsight_api:6071
FINSIGHT_API_TIMEOUT_MS=120000
```

Ví dụ Compose:

```yaml
services:
  api:
    environment:
      FINSIGHT_API_URL: http://finsight_api:6071
      FINSIGHT_API_TIMEOUT_MS: "120000"
    depends_on:
      finsight_api:
        condition: service_started
```

NestJS tiếp tục phục vụ endpoint frontend hiện tại:

```text
/api/ai-stock/ask
```

Không cần thay frontend sang gọi trực tiếp FinSight API.

## 8. Không public port FinSight nếu không cần thiết

Production nên dùng Docker network nội bộ:

```yaml
expose:
  - "6071"
```

Nếu cần debug trực tiếp từ VPS, chỉ bind vào loopback:

```yaml
ports:
  - "127.0.0.1:6071:6071"
```

Không nên public `0.0.0.0:6071` ra Internet khi không có authentication hoặc reverse proxy bảo vệ.

## 9. Build và khởi động

```bash
docker compose build finsight_api
docker compose up -d finsight_api api web
```

`python_data` (Flask + vnstock bản free) nằm trong cùng compose; `api` chờ nó
healthy rồi mới chạy. Chạy cả stack bằng `docker compose -f docker-compose.prod.yml up -d --build`.
Flask được publish ở `127.0.0.1:6060` để nginx phục vụ `/python_api/` (xem `file.nginx`).

Kiểm tra:

```bash
docker compose ps
docker compose logs --tail=100 finsight_api
docker compose logs --tail=100 api
```

Lần khởi động đầu có thể lâu hơn do tải BGE-M3. Không restart liên tục trong khi model đang được tải.

## 10. Kiểm tra kết nối nội bộ

Từ container NestJS:

```bash
docker exec fireant_api \
  node -e "fetch('http://finsight_api:6071/health').then(r => r.text()).then(console.log)"
```

Kết quả mong đợi:

```json
{"status":"ok","app":"FinSight"}
```

Kiểm tra Qdrant collection bằng Qdrant Cloud UI:

```text
company_knowledge_v1: 3432 points
```

Kiểm tra database:

```bash
docker exec fireant_db \
  psql -U countduck -d fireant_stock \
  -c "SELECT COUNT(*) FROM financial.vnstock_serving_facts;"
```

## 11. Kiểm tra end-to-end

Sau khi UI và API đã chạy, kiểm tra:

1. Đăng nhập bằng tài khoản đã tồn tại trong database production.
2. Mở Trợ lý ảo FinSight.
3. Hỏi `Doanh thu FPT năm 2024 là bao nhiêu?`.
4. Hỏi `FPT kinh doanh gì?`.
5. Hỏi `So sánh lợi nhuận sau thuế của FPT và HPG năm 2024.`.
6. Hỏi `Xếp hạng 5 ngân hàng theo tổng tài sản năm 2024.`.

Theo dõi log trong lúc test:

```bash
docker compose logs -f finsight_api api
```

## 12. Biến môi trường production tối thiểu

```ini
POSTGRES_USER=countduck
POSTGRES_PASSWORD=<DB_PASSWORD>
POSTGRES_DB=fireant_stock

FINANCIAL_DATABASE_URL=postgresql://countduck:<DB_PASSWORD>@db:5432/fireant_stock

QDRANT_URL=https://<QDRANT_CLOUD_ENDPOINT>
QDRANT_API_KEY=<QDRANT_READ_ONLY_API_KEY>

FINSIGHT_API_URL=http://finsight_api:6071
FINSIGHT_API_TIMEOUT_MS=120000

JWT_SECRET=<PRODUCTION_JWT_SECRET>
```

Các dịch vụ Google OAuth, Cloudinary, PayOS, VNStock và ngrok cần secrets riêng nếu được bật trên production.

## 13. Lỗi thường gặp

### FinSight kết nối `127.0.0.1` và bị từ chối

Trong container, `127.0.0.1` là chính container FinSight. Hãy dùng service name PostgreSQL như `db` hoặc `fireant_db`.

### NestJS báo FinSight timeout

Kiểm tra:

- `FINSIGHT_API_URL=http://finsight_api:6071`.
- Hai container cùng Docker network.
- FinSight đã tải xong BGE-M3.
- Qdrant Cloud đang hoạt động.
- PostgreSQL trả lời truy vấn bình thường.

### Qdrant Cloud không truy vấn được

Kiểm tra cluster còn hoạt động, API key chưa hết hạn và collection vẫn có đủ `3432` points. Free-tier cluster có thể bị suspend khi không hoạt động trong một thời gian.

### Login lỗi dù FinSight hoạt động

Login sử dụng schema ứng dụng cũ trong PostgreSQL, không phải Qdrant. Kiểm tra NestJS database config, user data và `JWT_SECRET`.

