# Hướng dẫn chạy FinSight trên máy local

Tài liệu này dành cho thành viên chạy source trên máy cá nhân nhưng sử dụng:

- PostgreSQL dùng chung trên VPS qua SSH tunnel.
- Qdrant Cloud dùng chung.
- Next.js, NestJS và FinSight API chạy trực tiếp trên máy local.

Không đưa mật khẩu, API key hoặc file `.env` thật vào Git.

## 1. Yêu cầu

Cài đặt:

- Git.
- Node.js 22.
- Python 3.11.
- Docker Desktop nếu chạy `python_data` (Flask + vnstock bản free) bằng Docker.
- Tài khoản có quyền SSH vào VPS.

Clone source:

```powershell
git clone <repository-url>
cd P-238
git checkout develop
git pull origin develop
```

## 2. Cài dependencies

### Python và FinSight

Chạy tại thư mục gốc project:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-qdrant.txt
```

### NestJS

```powershell
cd api
npm ci
cd ..
```

### Next.js

```powershell
cd web
npm ci
cd ..
```

## 3. Mở SSH tunnel tới PostgreSQL trên VPS

Mở một terminal riêng và giữ terminal này chạy:

```powershell
ssh -N -T `
  -o ServerAliveInterval=20 `
  -o ServerAliveCountMax=6 `
  -o TCPKeepAlive=yes `
  -o ExitOnForwardFailure=yes `
  -L 127.0.0.1:5433:127.0.0.1:5000 `
  <VPS_SSH_USER>@<VPS_SSH_HOST>
```

Kiểm tra tunnel:

```powershell
Test-NetConnection 127.0.0.1 -Port 5433
```

Kết quả cần có:

```text
TcpTestSucceeded : True
```

## 4. Cấu hình `.env` cho local

Tạo `.env` từ template nếu chưa có:

```powershell
Copy-Item .env.example .env
```

Cấu hình các biến quan trọng:

```ini
DATABASE_URL=postgresql://countduck:<DB_PASSWORD>@127.0.0.1:5433/fireant_stock
FINANCIAL_DATABASE_URL=postgresql://countduck:<DB_PASSWORD>@127.0.0.1:5433/fireant_stock

PGHOST=127.0.0.1
PGPORT=5433
POSTGRES_USER=countduck
POSTGRES_PASSWORD=<DB_PASSWORD>
POSTGRES_DB=fireant_stock

QDRANT_URL=https://<QDRANT_CLOUD_ENDPOINT>
QDRANT_API_KEY=<QDRANT_READ_ONLY_API_KEY>

FINSIGHT_API_URL=http://127.0.0.1:6071
FINSIGHT_API_TIMEOUT_MS=120000

PYTHON_API_URL=http://127.0.0.1:6060/api

# API key miễn phí của vnstock (60 request/phút); để trống = chế độ khách.
VNSTOCK_API_KEY=

JWT_SECRET=<LOCAL_JWT_SECRET>
```

Qdrant Cloud phải có collection `company_knowledge_v1` với `3432` points. Không cần chạy Qdrant Docker hoặc nạp lại dữ liệu khi collection này đã sẵn sàng.

## 5. Cấu hình `web/.env.local`

Next.js chạy trong thư mục `web` không tự đọc root `.env`. Tạo file `web/.env.local`:

```ini
INTERNAL_API_BASE_URL=http://127.0.0.1:8000/api
INTERNAL_PYTHON_API_URL=http://127.0.0.1:6060/api

JWT_SECRET=<GIỐNG_JWT_SECRET_CỦA_NESTJS>
```

File này đã được `.gitignore` bảo vệ và không được commit. Trình duyệt gọi
`/api/*` (NestJS) và `/python_api/*` (Flask) cùng origin; Next.js rewrite theo hai
biến trên nên không cần biến `NEXT_PUBLIC_*` cho địa chỉ API.

## 6. Khởi động các service

### Terminal 1: SSH tunnel

Giữ lệnh SSH tunnel tại bước 3 tiếp tục chạy.

### Terminal 2: FinSight API

Chạy tại thư mục gốc project:

```powershell
.\.venv\Scripts\python.exe -m uvicorn src.finsight_api:app `
  --host 127.0.0.1 `
  --port 6071
```

Lần chạy đầu có thể mất thời gian tải BGE-M3. Các lần sau sẽ sử dụng model trong local cache.

### Terminal 3: NestJS

NestJS hiện không tự động đọc root `.env` khi chạy trực tiếp. Nạp các biến cần thiết trong terminal rồi khởi động:

```powershell
cd api

$env:PGHOST="127.0.0.1"
$env:PGPORT="5433"
$env:POSTGRES_USER="countduck"
$env:POSTGRES_PASSWORD="<DB_PASSWORD>"
$env:POSTGRES_DB="fireant_stock"
$env:FINSIGHT_API_URL="http://127.0.0.1:6071"
$env:FINSIGHT_API_TIMEOUT_MS="120000"
$env:PYTHON_API="http://127.0.0.1:6060/api"
$env:PYTHON_API_URL="http://127.0.0.1:6060/api"
$env:JWT_SECRET="<LOCAL_JWT_SECRET>"

npm run start:dev
```

NestJS mặc định chạy tại `http://127.0.0.1:8000`.

### Terminal 4: Next.js

```powershell
cd web
npm run dev
```

Mở giao diện:

```text
http://localhost:3000
```

### Data service `python_data` tại port 6060

Giá, chỉ số tài chính, tin tức, ngành và danh sách mã lấy từ `python_data`
(vnstock bản free). Chạy bằng Docker:

```powershell
docker compose up -d --build python_data
```

hoặc chạy trực tiếp:

```powershell
.\.venv\Scripts\python.exe -m pip install -r python_data\requirements.txt
cd python_data
..\.venv\Scripts\python.exe server.py
```

Kiểm tra: `http://127.0.0.1:6060/api/health`. FinSight facts và company RAG không dùng `python_data`.

Muốn chạy toàn bộ hệ thống bằng một lệnh thì dùng `docker compose up --build` ở thư mục gốc.

## 7. Kiểm tra

Kiểm tra các port:

```powershell
Test-NetConnection 127.0.0.1 -Port 5433
Test-NetConnection 127.0.0.1 -Port 6071
Test-NetConnection 127.0.0.1 -Port 8000
Test-NetConnection 127.0.0.1 -Port 3000
```

Kiểm tra FinSight:

```powershell
Invoke-RestMethod http://127.0.0.1:6071/health
```

Kết quả mong đợi:

```text
status : ok
app    : FinSight
```

Các câu hỏi test:

1. `Doanh thu FPT năm 2024 là bao nhiêu?`
2. `FPT kinh doanh gì?`
3. `So sánh lợi nhuận sau thuế của FPT và HPG năm 2024.`
4. `Xếp hạng 5 ngân hàng theo tổng tài sản năm 2024.`

## 8. Những service không cần chạy local

Khi sử dụng DB VPS và Qdrant Cloud:

- Không cần chạy `fireant_db` local.
- Không cần chạy Qdrant Docker local.
- Không cần chạy Qdrant loader.
- Không cần tải raw company documents từ Git.

## 9. Lỗi thường gặp

### `ECONNREFUSED 127.0.0.1:5000`

NestJS đang dùng sai port. Khi chạy native qua SSH tunnel phải dùng `127.0.0.1:5433`.

### `password authentication failed`

Kiểm tra `POSTGRES_USER`, `POSTGRES_PASSWORD` và chắc chắn tunnel đang kết nối đúng VPS.

### FinSight timeout

Kiểm tra:

- FinSight API đang chạy tại port `6071`.
- `QDRANT_URL` và `QDRANT_API_KEY` hợp lệ.
- VPS database còn kết nối được qua tunnel.
- BGE-M3 đã tải xong trong lần chạy đầu.

