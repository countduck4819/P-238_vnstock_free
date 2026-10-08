# Nền tảng AI phân tích chứng khoán

Dự án xây dựng một nền tảng hỗ trợ nhà đầu tư theo dõi thị trường chứng khoán
Việt Nam, quản lý dữ liệu cổ phiếu, tham khảo tín hiệu xu hướng và tương tác với
trợ lý AI. Hệ thống kết hợp ứng dụng web, NestJS REST API, PostgreSQL, dịch vụ
Flask/Vnstock, FinSight FastAPI và các worker Machine Learning phục vụ advisory.

> Kết quả dự báo chỉ mang tính tham khảo, không phải khuyến nghị đầu tư. H120 và
> V6 trả về xác suất/tín hiệu xu hướng; nhánh LSTM trả về quỹ đạo giá tham khảo
> trong 78 phiên tiếp theo.

## Thành phần hệ thống

| Thành phần | Công nghệ | Cổng local | Vai trò |
| --- | --- | ---: | --- |
| Frontend | Next.js 16, React 19 | `3000` | Giao diện người dùng và trang quản trị |
| Backend chính | NestJS 11, Fastify, TypeORM | `8000` | Auth, người dùng, cổ phiếu, advisory và proxy tới các dịch vụ dữ liệu |
| Database | PostgreSQL 16 | `5000:5432` (Compose) | Lưu dữ liệu nghiệp vụ của NestJS và FinSight |
| Data service | Flask, Vnstock | `6060` | Thị trường, H120/V6 và dữ liệu JSON |
| FinSight API | FastAPI | `6071` | Phân tích tài chính, vector search và LLM workflow |
| Vector store | Qdrant | `6333` | Embedding và truy vấn tương đồng cho FinSight |
| Daily scoring worker | Python | container-only | Snapshot 480 phiên và inference H120 mỗi ngày |
| Native agent (tuỳ chọn) | FastAPI + LangGraph | `8090` | Agent độc lập, không nằm trong Compose |

Luồng ứng dụng chính:

```text
Next.js :3000  ──HTTP──>  NestJS :8000/api  ──TypeORM──>  PostgreSQL :5000
                              │                 └──> FinSight :6071 ──> Qdrant :6333
                              └──> Flask/Vnstock :6060

Daily scoring worker ── snapshot 480 phiên ──> frozen H120 inference
                     └── runs/ ──> Flask :6060 ──> NestJS ──> Next.js

V6 reviewed release ── Top 50 cohort ──> LSTM/Prophet/Holt ── 78 phiên ──> UI
```

H120, V6 và LSTM có vòng đời khác nhau. H120 chạy inference độc lập mỗi ngày và
không dùng output V6. V6 là release dài hạn đã review; LSTM chỉ làm mới khi
cohort Top 50 của V6 được promote, không chạy trong daily scoring.

## Yêu cầu hệ thống

- Git.
- Python `>= 3.11`.
- Node.js `>= 22` và npm.
- PostgreSQL 16 nếu chạy backend NestJS local.
- Docker Desktop và Docker Compose nếu chạy container.

## Cài đặt project

```powershell
git clone https://github.com/AI20K-Build-Phase-Cohort-3/P-238.git
cd P-238
```

### Python

Trên Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -e ".[dev]"
```

Trên Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -e ".[dev]"
```

Data service cần thêm Flask, scheduler và hệ sinh thái Vnstock:

```powershell
python -m pip install flask flask-cors watchdog schedule vnstock vnai
```

Mã hiện tại import trực tiếp module `vnstock_data`. Trước khi chạy data service,
kiểm tra module này đã có trong đúng virtual environment:

```powershell
python -c "import sys, vnstock_data; print(sys.executable); print(vnstock_data.__file__)"
```

Không cài `vnstock_data` bằng `pip install vnstock_data`: hiện không có distribution
tương ứng trên PyPI. Môi trường Vnstock đã được cấu hình của project phải cung cấp
module này.

### Node.js

```powershell
cd api
npm install

cd ..\web
npm install

cd ..
```

## Cấu hình môi trường

### Backend và PostgreSQL

Sao chép file mẫu tại root:

```powershell
Copy-Item .env.example .env
```

Khi NestJS và PostgreSQL cùng chạy trực tiếp trên máy, bổ sung/cập nhật các biến:

```env
PORT=8000

PGHOST=localhost
PGPORT=5000
POSTGRES_USER=<your-local-db-user>
POSTGRES_PASSWORD=<your-local-db-password>
POSTGRES_DB=<your-local-db-name>

COOKIE_SECRET=replace-with-a-local-secret
DOMAIN_WEB=http://localhost:3000
```

Các biến backend được code sử dụng:

| Biến | Bắt buộc | Giá trị local gợi ý | Mục đích |
| --- | --- | --- | --- |
| `PORT` | Có | `8000` | Cổng NestJS |
| `PGHOST` | Có | `localhost` | PostgreSQL host; dùng `db` trong Docker network |
| `PGPORT` | Có | `5000` | PostgreSQL port local; dùng `5432` trong Docker network |
| `POSTGRES_USER` | Có | `<your-local-db-user>` | Tài khoản PostgreSQL |
| `POSTGRES_PASSWORD` | Có | `<your-local-db-password>` | Mật khẩu PostgreSQL development |
| `POSTGRES_DB` | Có | `<your-local-db-name>` | Database của ứng dụng |
| `JWT_SECRET` | Có | `replace-with-a-long-random-secret` | Ký access/refresh token |
| `COOKIE_SECRET` | Có | `replace-with-a-long-random-secret` | Ký cookie Fastify |
| `DOMAIN_WEB` | Có | `http://localhost:3000` | Redirect về frontend sau authentication/payment |
| `HOST_WEB` | Có cho AI stock | `http://localhost:3000` | Tạo liên kết bài viết trả về từ AI |
| `PYTHON_API` | Có cho AI stock | `http://localhost:6060/api` | Price, finance và news API cho AI stock |
| `PYTHON_API_URL` | Có cho recommendation | `http://localhost:6060/api` | Market-data API cho recommendation scheduler |
| `GROQ_API_KEY` | Có cho AI stock | `<your-groq-key>` | Gọi mô hình Groq |

Các biến tích hợp tùy chọn:

| Nhóm | Biến |
| --- | --- |
| Google OAuth | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_CALLBACK_URL` |
| Facebook OAuth | `FACEBOOK_CLIENT_ID`, `FACEBOOK_CLIENT_SECRET`, `FACEBOOK_CALLBACK_URL` |
| PayOS | `PAYOS_CLIENT_ID`, `PAYOS_API_KEY`, `PAYOS_CHECKSUM_KEY`, `PREMIUM_PRICE`, `DOMAIN` |
| FastAPI/LLM | `OPENAI_API_KEY`, `MODEL_NAME`, `LLM_TEMPERATURE`, `APP_ENV`, `APP_HOST`, `APP_PORT`, `CORS_ORIGINS` |
| LangSmith | `LANGCHAIN_API_KEY`, `LANGCHAIN_PROJECT`, `LANGCHAIN_TRACING_V2` |
| Python app storage | `DATABASE_URL`, `QDRANT_URL`, `QDRANT_API_KEY` |

Các tính năng OAuth, Cloudinary, PayOS, Groq/OpenAI hoặc LangSmith cần thêm key
tương ứng. Không commit `.env` hoặc API key thật vào Git.

TypeORM hiện bật `synchronize: true`, vì vậy các bảng development được tạo/cập
nhật khi NestJS kết nối thành công tới PostgreSQL. Không nên dùng tùy chọn này cho
production; production cần migration riêng.

### Frontend

Tạo `web/.env.local`:

```powershell
Copy-Item web\.env.local.example web\.env.local
```

Nội dung dùng cho NestJS chạy local:

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api
NEXT_PUBLIC_API_BASE_URL_PYTHON=http://localhost:6060/api
API_BASE_URL=http://localhost:8000/api
JWT_SECRET=replace-with-the-same-jwt-secret-as-backend
```

`NEXT_PUBLIC_API_BASE_URL` dành cho NestJS, còn
`NEXT_PUBLIC_API_BASE_URL_PYTHON` dành cho Flask/Vnstock. `API_BASE_URL` được
Next.js proxy sử dụng ở phía server. Tên biến phải đúng như trên; frontend không
đọc biến `NEXT_PUBLIC_API_URL`.

## Chạy development bằng terminal

Mỗi service nên chạy trong một terminal riêng.

### 1. PostgreSQL

Nếu đã cài PostgreSQL local, tạo database và tài khoản khớp với `.env`.

Nếu Docker Desktop đang chạy, có thể chỉ khởi động database:

```powershell
docker compose up db
```

PostgreSQL được publish tại `localhost:5000`.

### 2. Data service

```powershell
cd E:\lab\P-238
.\.venv\Scripts\Activate.ps1
cd python_data
python server.py
```

Data API chạy tại `http://localhost:6060`. Một số endpoint:

- `GET /api/vnindex`
- `GET /api/listing`
- `GET /api/industries`
- `GET /api/stocks-by-industries`
- `GET /api/stocks_symbols`
- `GET /api/stock/<symbol>`
- `GET /api/finance/<symbol>`
- `GET /api/news/<symbol>`

Trong Compose, data service chỉ phục vụ dữ liệu và các artifact đã được xác minh;
daily H120 scoring chạy ở worker `model_scoring` riêng. Worker chạy vào
`WAVE_DAILY_SCORING_TIME` (mặc định 19:00, giờ Việt Nam), đồng bộ snapshot mới,
giữ rolling history tối đa 480 phiên và ghi run có manifest/hash vào `runs/`.

### 3. NestJS backend

```powershell
cd E:\lab\P-238\api
npm run start:dev
```

- API base: `http://localhost:8000/api`
- Swagger: `http://localhost:8000/api`

Các nhóm API chính gồm `auth`, `users`, `stocks`, `industries`, `news`,
`stock-recommendations`, `stock-prediction`, `ai-stock`, `premium-orders` và
`upload`.

### 4. Frontend

```powershell
cd E:\lab\P-238\web
npm run dev
```

Mở `http://localhost:3000`.

### 5. FastAPI LangGraph agent (tùy chọn, native)

```powershell
cd E:\lab\P-238
.\.venv\Scripts\Activate.ps1
uvicorn src.main:app --reload --host 0.0.0.0 --port 8090
```

Endpoints:

- `GET http://localhost:8090/health`
- `GET http://localhost:8090/api/v1/status`
- `POST http://localhost:8090/api/v1/chat`

FastAPI agent native là service độc lập; ví dụ trên dùng cổng `8090` để không
đụng cổng NestJS `8000`. FinSight API trong Compose chạy riêng trên cổng `6071`.
Frontend mặc định gọi NestJS, không gọi agent trực tiếp.

## Sample queries

Các ví dụ dưới đây dùng PowerShell và giả định các service đã chạy đúng port.

### Kiểm tra market-data service

```powershell
Invoke-RestMethod -Uri "http://localhost:6060/api/vnindex"
Invoke-RestMethod -Uri "http://localhost:6060/api/stock/FPT"
Invoke-RestMethod -Uri "http://localhost:6060/api/finance/FPT"
Invoke-RestMethod -Uri "http://localhost:6060/api/news/FPT"
```

### Truy vấn NestJS API

```powershell
# Danh sách cổ phiếu, có phân trang và tìm kiếm
Invoke-RestMethod -Uri "http://localhost:8000/api/stocks?page=1&limit=10&search=FPT"

# Danh sách ngành lấy từ dữ liệu Vnstock
Invoke-RestMethod -Uri "http://localhost:8000/api/industries/vnstock"

# Tin tức đã lưu trong database
Invoke-RestMethod -Uri "http://localhost:8000/api/news?page=1&limit=10&symbol=FPT"
```

Đăng nhập bằng tài khoản đã tồn tại:

```powershell
$loginBody = @{
    email = "user@example.com"
    password = "<your-test-password>"
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8000/api/auth/login" `
  -ContentType "application/json" `
  -Body $loginBody
```

Hỏi AI Stock; endpoint này cần `GROQ_API_KEY` và Python data service:

```powershell
$questionBody = @{
    userId = 1
    question = "Đánh giá nhanh cổ phiếu FPT dựa trên giá, tài chính và tin tức gần nhất"
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8000/api/ai-stock/ask" `
  -ContentType "application/json" `
  -Body $questionBody
```

### Truy vấn FastAPI LangGraph agent

```powershell
$chatBody = @{
    message = "Tóm tắt các yếu tố cần xem xét trước khi đánh giá xu hướng cổ phiếu FPT"
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8090/api/v1/chat" `
  -ContentType "application/json" `
  -Body $chatBody
```

Một số câu hỏi mẫu trên giao diện AI:

- `Đánh giá nhanh xu hướng cổ phiếu FPT hiện tại.`
- `So sánh sức mạnh tương đối của FPT với VNINDEX và ngành công nghệ.`
- `Tóm tắt tình hình tài chính và tin tức gần nhất của VCB.`
- `Các rủi ro nào có thể làm tín hiệu tăng của HPG thất bại?`
- `Những yếu tố nào đang ủng hộ hoặc phủ nhận xu hướng tăng hiện tại?`

## Docker Compose

File `docker-compose.yml` khai báo `db`, `api`, `web`, `python_data`, `finsight_api`,
`qdrant`, `model_scoring` và `ngrok`. `api` là NestJS; `python_data` là Flask;
`model_scoring` là worker inference H120 độc lập.
Kiểm tra Docker Desktop engine trước khi chạy:

```powershell
docker info
docker compose config
```

Khởi động toàn bộ:

```powershell
docker compose up --build
```

Compose hiện đã thống nhất các cổng nội bộ/public: Next.js `3000`, NestJS `8000`,
Flask `6060`, FinSight `6071`, PostgreSQL `5000:5432` và Qdrant `6333`.
Container API dùng `host.docker.internal` và `VPS_DB_LOCAL_PORT` theo cấu hình
Compose; frontend dùng rewrite nội bộ tới `http://api:8000/api`. Data worker cần
credentials/provider hợp lệ trong `.env`.
`ngrok.yml` chỉ cần khi bật service `ngrok`.

## Machine Learning và advisory

H120 là mô hình ngắn hạn: mỗi ngày worker đồng bộ snapshot OHLCV, dùng 480 phiên
gần nhất để tạo feature và inference bằng frozen model. Một run thất bại hoặc
không hợp lệ bị bỏ qua; API phục vụ newest valid manifest/run trước đó, nên UI vẫn
có fallback an toàn.

V6 là mô hình dài hạn, được train/review/promote theo release độc lập. LSTM kết
hợp Prophet/Holt chỉ chạy khi cohort Top 50 của V6 thay đổi và dự báo quỹ đạo giá
78 phiên tiếp theo; nó không chạy trong daily H120 scoring. Hai nhánh H120 và V6
không truyền feature hay xác suất cho nhau.

Hướng dẫn vận hành nằm trong
[`docs/daily_independent_model_scoring.md`](docs/daily_independent_model_scoring.md);
sơ đồ tổng thể nằm trong [`ARCHITECTURE.md`](ARCHITECTURE.md) và
[`docs/architecture_diagram.md`](docs/architecture_diagram.md).

## Kiểm thử

Python:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check src tests
```

NestJS:

```powershell
cd api
npm test
npm run build
```

Frontend:

```powershell
cd web
npm run lint
npm run build
```

## Cấu trúc thư mục

```text
P-238/
├── api/                 # NestJS backend và TypeORM entities
├── web/                 # Next.js frontend
├── python_data/         # Flask/Vnstock data service và scheduler
├── src/                 # FastAPI agent và các Python package cho ML
│   ├── agents/
│   ├── api/
│   ├── evaluation/
│   ├── features/
│   ├── labels/
│   ├── models/
│   └── training/
├── scripts/             # Download, data pipeline, training và evaluation CLI
├── configs/             # Versioned configs cho feature/label/model/eval
├── data/                # Dữ liệu raw, clean, feature, label và train split
├── data_vnstock/        # Rolling cache snapshot OHLCV cho daily scoring
├── runs/                # Dated ML runs và serving manifests
├── deploy/              # Frozen model/release pointers được phục vụ
├── models/              # Model runs và frozen artifacts (không commit payload lớn)
├── eval/                # Registry và evaluation reports
├── tests/               # Python test suite
├── docs/                # Tài liệu kỹ thuật
└── docker-compose.yml
```

## Git workflow

- `main`: production/release.
- `develop`: nhánh tích hợp.
- `feature/*`: nhánh phát triển tính năng.
- Tạo Pull Request từ `feature/*` vào `develop` và yêu cầu review trước khi merge.
- Dùng Conventional Commits, ví dụ `feat(api): add stock trend endpoint`.

Chi tiết tại [GIT_WORKFLOW.md](GIT_WORKFLOW.md).

## License

MIT
