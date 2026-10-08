Master Architecture & Execution Roadmap

VNStock → PostgreSQL + Qdrant → Query Harness → Chatbot

Tài liệu này là nguồn định hướng chính cho AI/Coding Agent trong project P-238.

Trước khi sửa code, thay kiến trúc, tạo migration, mở rộng phase, chạy batch lớn hoặc thay đổi luồng truy vấn, AI/Coding Agent phải đọc file này trước.

Nếu code hiện tại khác roadmap, phải dừng và báo khác biệt trước khi tự ý thay đổi kiến trúc.

0. Trạng thái hiện tại và quyết định đã chốt

0.1. Hướng đi chính

VNStock
   |
   +---- Financial Statements
   |         |
   |         v
   |      Raw Parquet
   |         |
   |         v
   |      Normalize
   |         |
   |         v
   |     PostgreSQL
   |
   +---- Company Data
             |
             v
           Raw JSON
             |
             v
        Build Documents
             |
             v
            Qdrant

PostgreSQL + Qdrant
        |
        v
   Query Harness
        |
        v
   Intent Router
        |
        v
   Deterministic Tools
        |
        v
   LLM / Response Composer
        |
        v
      ANSWER

0.2. Financial source hiện tại

Financial raw dùng VNStock với provider cố định:

from vnstock import Finance

finance = Finance(
    symbol=symbol,
    source="VCI",
)

df_balance_sheet = finance.balance_sheet(period="year")
df_income_statement = finance.income_statement(period="year")
df_cash_flow = finance.cash_flow(period="year")

Quyết định:

Financial provider for current MVP = VCI

Không trộn provider trong cùng một bộ raw financial của một ticker.

Ví dụ không được:

balance_sheet      = VCI
income_statement   = KBS
cash_flow          = KBS

Mục tiêu:

balance_sheet      = VCI
income_statement   = VCI
cash_flow          = VCI

0.3. Company source hiện tại

Dùng API VNStock hiện tại:

from vnstock import Reference

reference = Reference()
company = reference.company(symbol)

df_info = company.info()
df_officers = company.officers()

Raw contract hiện giữ:

data/vnstock/raw/company/{TICKER}/
├── profile.json
├── overview.json
└── officers.json

profile.json và overview.json có thể cùng được tạo từ một snapshot company.info() để giữ tương thích cấu trúc thư mục hiện tại.

Việc tách semantic profile và overview thực hiện ở bước build document cho Qdrant, không sửa raw bằng LLM.

0.4. OCR/TXT/PDF

OCR/TXT/PDF = STOPPED

Không coi OCR/TXT/PDF là:

critical path

fallback tự động

backup extraction path

nguồn numerical truth

việc cần tối ưu tiếp

Không tiếp tục:

OCR

TXT extraction

PDF parsing

Docling

RapidOCR

Gemini PDF extraction

VLM financial extraction

legacy financial parser

Code cũ có thể giữ nguyên trong repository.

Chỉ quay lại scope này khi user chủ động yêu cầu trong tương lai.

1. Mục tiêu cuối cùng

Xây dựng chatbot tài chính Việt Nam có thể trả lời nhanh, có kiểm chứng và deterministic ở phần số liệu.

Hai nhóm câu hỏi chính:

1.1. Financial / Numerical

Ví dụ:

Doanh thu FPT năm 2025 là bao nhiêu?

LNST ACB năm 2024?

Thu nhập lãi thuần MBB năm 2025?

Tổng tài sản HPG năm 2023?

LNST ACB từ 2021–2025?

So sánh lợi nhuận FPT và MWG.

Top 10 ngân hàng có LNST cao nhất.

Công ty nào tăng trưởng lợi nhuận nhanh nhất?

Tại sao lợi nhuận ngân hàng A tăng mạnh?

Nguồn trả lời:

PostgreSQL

1.2. Company Knowledge

Ví dụ:

FPT làm gì?

ACB thuộc ngành nào?

Trụ sở MWG ở đâu?

Công ty thành lập năm nào?

Ban lãnh đạo HPG gồm những ai?

Chủ tịch công ty là ai?

Nguồn trả lời:

Qdrant

2. Nguyên tắc cốt lõi

Machine calculates
→ Structured data provides evidence
→ LLM explains

Các nguyên tắc bắt buộc:

PostgreSQL là numerical truth/query engine.

Qdrant chỉ dùng cho knowledge định tính.

LLM không tự sửa số.

LLM không tự điền missing.

LLM không dùng Qdrant làm nguồn số liệu.

Derived metrics phải do backend tính.

Ranking/screening phải do backend/PostgreSQL thực hiện.

Missing != 0.

Missing != nearest year.

Missing != estimate.

Raw data là immutable source snapshot.

Mọi phase phải rerun an toàn.

Không phá dữ liệu cũ khi chưa inspect.

Query path phải ngắn nhất có thể.

Không gọi LLM khi một deterministic response/template đã đủ.

3. Kiến trúc Serving tối ưu tốc độ

Tách rõ hai đường:

3.1. Ingestion path

VNStock
   ↓
Raw Parquet / JSON
   ↓
Normalize / Build Docs
   ↓
PostgreSQL / Qdrant

Đây là pipeline offline/batch.

3.2. Serving path

USER
  ↓
Request Parser
  ↓
Ticker / Entity Resolver
  ↓
Intent Router
  ↓
Query Planner
  ├───────────────┬─────────────────┐
  ↓               ↓                 ↓
PostgreSQL       Qdrant        Hybrid Parallel
  ↓               ↓                 ↓
Structured Result / Evidence
          ↓
Response Composer
          ↓
Optional LLM
          ↓
ANSWER

Không gọi VNStock trực tiếp trong request path của chatbot.

Chatbot production phải đọc từ PostgreSQL/Qdrant local serving layer.

Lợi ích:

giảm latency

không phụ thuộc rate limit VNStock lúc user hỏi

deterministic

dễ cache

dễ kiểm thử

dễ theo dõi

query ổn định

4. Các thành phần chính của một Harness

Harness bao gồm mọi thứ xung quanh mô hình ngoại trừ bản thân trọng số của mô hình.

Trong P-238, Harness phải được coi là một thành phần kiến trúc chính, không phải chỉ là prompt.

4.1. Công cụ — Tools

Cho phép AI gọi các chức năng typed/deterministic.

Các tool tối thiểu:

resolve_ticker()
resolve_metric()
get_financial_fact()
get_financial_timeseries()
compare_financial_metrics()
rank_financial_metric()
screen_financial_metrics()
get_why_evidence()
get_company_profile()
get_company_overview()
get_company_officers()

Tool không được trả raw database dump không cần thiết.

Tool phải có:

input schema rõ ràng

output schema rõ ràng

timeout

row limit

validation

trace ID

error type rõ ràng

4.2. Bộ nhớ — Memory

Memory quản lý:

lịch sử hội thoại

referent trong session

câu hỏi nối tiếp

trạng thái task

tóm tắt context dài

Ví dụ:

User: So sánh ACB và MBB năm 2025.
User: Còn năm 2024?

Harness phải nhớ ticker và metric đang được nói tới.

Nhưng:

Memory != numerical truth

Memory không được ghi đè PostgreSQL.

Nếu memory nói một con số khác DB:

PostgreSQL wins

4.3. Môi trường thực thi — Execution Environment

Dùng cho:

chạy code

test

migration dry-run

benchmark

validation

reproduce lỗi

inspect artifacts

Bắt buộc tách:

development
test
production

Không chạy destructive command trực tiếp trên production nếu chưa có approval.

4.4. Guardrails & Permissions

Harness phải chặn:

DROP database/table

TRUNCATE production table

UPDATE numerical source từ chatbot

DELETE source facts

arbitrary SQL do LLM tự sinh

web scraping tự phát

quay lại OCR pipeline

sửa số nguồn

estimate missing

query không whitelist

context injection để bypass data policy

Chatbot production DB:

READ ONLY

Write chỉ xảy ra trong ingestion/migration jobs được kiểm soát.

4.5. Observability

Mỗi request phải có:

trace_id
timestamp
intent
ticker
metric_code
year/range
query_plan
postgres_ms
qdrant_ms
cache_status
llm_ms
total_ms
result_count
error_code

Mục tiêu:

biết request chậm ở đâu

biết tool nào fail

biết cache có hiệu quả không

biết router có chọn đúng nguồn không

reproduce được lỗi

4.6. Orchestration / State Machine

Harness phải quyết định:

parse
→ resolve
→ route
→ retrieve
→ calculate
→ compose
→ answer

Không để LLM tự do quyết định toàn bộ luồng bằng text reasoning.

4.7. Evaluation Harness

Có bộ câu hỏi chuẩn/golden set để regression test:

fact

timeseries

compare

ranking

screening

why

profile

officers

hybrid

Mỗi lần đổi code/router/catalog phải chạy lại evaluation.

5. Cấu trúc thư mục chuẩn

P-238/
|
├── data/
│   └── vnstock/
│       |
│       ├── raw/
│       │   ├── financial/
│       │   │   └── {TICKER}/
│       │   │       ├── balance_sheet.parquet
│       │   │       ├── income_statement.parquet
│       │   │       └── cash_flow.parquet
│       │   |
│       │   └── company/
│       │       └── {TICKER}/
│       │           ├── profile.json
│       │           ├── overview.json
│       │           └── officers.json
│       |
│       ├── normalized/
│       │   ├── facts/
│       │   │   └── {TICKER}.parquet
│       │   └── qdrant/
│       │       └── {TICKER}.jsonl
│       |
│       ├── metadata/
│       │   ├── tickers.csv
│       │   ├── download_manifest.csv
│       │   ├── metric_catalog.csv
│       │   └── normalization_manifest.csv
│       |
│       └── logs/
│           ├── downloader.log
│           ├── normalizer.log
│           └── ingestion.log
|
├── scripts/
│   └── vnstock/
│       ├── download_all.py
│       ├── audit_raw.py
│       ├── normalize_financials.py
│       ├── build_metric_catalog.py
│       ├── build_qdrant_docs.py
│       ├── load_postgres.py
│       └── load_qdrant.py
|
├── src/
│   ├── harness/
│   ├── router/
│   ├── tools/
│   ├── retrieval/
│   ├── metrics/
│   ├── db/
│   └── api/
|
└── tests/
    ├── unit/
    ├── integration/
    ├── golden/
    └── performance/

6. Raw Data Policy

6.1. Financial raw

Mỗi ticker:

data/vnstock/raw/financial/{TICKER}/

Gồm:

balance_sheet.parquet
income_statement.parquet
cash_flow.parquet

Raw phải giữ đúng DataFrame VNStock/VCI trả về.

Không:

rename metric bằng suy đoán

scale số

sửa dấu

estimate

fill missing

ép schema sector khác

drop item chỉ vì chưa dùng

6.2. Company raw

data/vnstock/raw/company/{TICKER}/

Gồm:

profile.json
overview.json
officers.json

6.3. Excel

Excel chỉ dùng để kiểm tra thủ công nếu cần.

Backend source:

Parquet / JSON

7. Downloader Policy

Downloader phải:

resume

retry có giới hạn

có global rate limiter

atomic write

log success/empty/error

save manifest thường xuyên

một ticker lỗi không crash toàn batch

rerun an toàn

không normalize

không load PostgreSQL

không load Qdrant

7.1. Rate limit

Gói Community có giới hạn API.

Không chạy sát trần bằng giả định:

1 Python function call = 1 HTTP request

vì thư viện có thể phát nhiều request nội bộ.

Downloader phải hỗ trợ:

configurable calls/minute

configurable workers

retry/backoff

resume sau process termination

hạ tốc khi gặp rate-limit

Safe operational default nên ưu tiên độ ổn định hơn vài phút tốc độ download.

7.2. Manifest

Fields đề xuất:

ticker
balance_sheet
income_statement
cash_flow
financial_source
profile
overview
officers
last_error
updated_at

Có thể mở rộng:

retry_count
error_type
downloaded_at

Status:

success
exists
empty
error

empty không có nghĩa là 0.

7.3. Idempotency

valid file exists + correct source
→ SKIP

missing/error
→ RETRY

Nếu đổi provider financial:

old provider != new provider
→ refresh cả 3 financial statements

Không để một ticker chứa raw từ nhiều provider mà không ghi nhận rõ.

8. Raw Audit — bắt buộc trước normalization

Sau khi bulk download hoàn tất, không đi thẳng vào PostgreSQL.

Chạy audit toàn bộ raw trước.

Tạo:

scripts/vnstock/audit_raw.py

Audit phải thống kê:

tickers_total
financial_complete
financial_partial
company_complete
company_partial

balance_success
balance_empty
balance_error

income_success
income_empty
income_error

cashflow_success
cashflow_empty
cashflow_error

profile_success
overview_success
officers_success

Ngoài ra inspect:

file tồn tại

file đọc được

row count

column count

year columns

item_id presence

duplicate item_id trong statement

schema variations theo sector

source provider

corrupt parquet/json

Không đánh giá số tài chính đúng/sai.

PASS khi:

Có report rõ ràng.

Không có corrupt file không được phát hiện.

Biết ticker nào complete/partial.

Biết các schema variation chính.

Không sửa raw.

Sau Phase Audit:

STOP → REVIEW

9. Financial Normalization

9.1. Mục tiêu

Chuyển raw wide format thành long facts.

Raw có thể dạng:

item
item_en
item_id
2025
2024
2023
2022
...

Normalized:

ticker
year
statement_type
metric_code
metric_name
metric_name_en
value
source

Ví dụ:

ACB | 2025 | income_statement | net_interest_income | ... | ... | value | vnstock_vci
ACB | 2024 | income_statement | net_interest_income | ... | ... | value | vnstock_vci

9.2. Không giả định số cột cố định

VCI có thể trả số kỳ khác nhau giữa ticker.

Normalizer phải tự phát hiện year columns:

year_columns = [
    col
    for col in df.columns
    if str(col).strip().isdigit()
]

Không assume:

luôn 8 năm
luôn 11 columns

9.3. Giữ toàn bộ item_id

KEEP ALL item_id

Không chỉ giữ vài metric phổ biến.

Nếu source không có item_id nhưng có trường định danh tương đương, phải inspect và thiết kế mapping rõ ràng trước khi tự sinh metric code.

Không dùng LLM để tự bịa metric_code.

9.4. Time scope

Raw:

giữ tất cả năm source trả về

Serving MVP ưu tiên:

2021–2025

Không xóa năm khác khỏi raw.

9.5. Missing

Nếu value null:

preserve null

Không:

null → 0
null → nearest year
null → estimate

9.6. Duplicate key

Logical key mục tiêu:

ticker
+ year
+ statement_type
+ metric_code

Nếu duplicate xảy ra:

DO NOT silently drop

Phải log và review nguyên nhân.

10. Metric Catalog

Tạo:

data/vnstock/metadata/metric_catalog.csv

Fields đề xuất:

metric_code
metric_name_vi
metric_name_en
statement_type
sector
aliases
unit_type
description
source

Mục tiêu:

resolve câu hỏi user → canonical metric

tránh hard-code alias trong nhiều nơi

sector-aware

hỗ trợ Vietnamese/English alias

query nhanh

Ví dụ alias:

LNST
lợi nhuận sau thuế
profit after tax
net profit

phải map deterministic tới metric phù hợp theo sector/source.

Catalog phát triển từ raw thực tế.

Không đoán metric không có dữ liệu.

11. PostgreSQL Strategy

11.1. Trước mọi migration

Bắt buộc:

INSPECT EXISTING DATABASE FIRST

Không assume DB rỗng.

Phải inspect:

schemas

tables

columns

indexes

constraints

row counts

existing migrations

Không được:

DROP TABLE ...
DROP SCHEMA ...
TRUNCATE ...

chỉ vì roadmap đề xuất schema mới.

Ưu tiên:

reuse
→ additive migration
→ backward compatible

11.2. Financial Facts

Logical schema:

ticker
year
statement_type
metric_code
metric_name
metric_name_en
value
source
ingested_at

Unique key mục tiêu:

ticker + year + statement_type + metric_code

11.3. Indexes

Fact lookup:

CREATE INDEX IF NOT EXISTS idx_financial_facts_lookup
ON financial_facts (
    ticker,
    year,
    metric_code
);

Time series:

CREATE INDEX IF NOT EXISTS idx_financial_facts_timeseries
ON financial_facts (
    ticker,
    metric_code,
    year
);

Ranking:

CREATE INDEX IF NOT EXISTS idx_financial_facts_rank
ON financial_facts (
    year,
    metric_code,
    value
);

Có thể dùng covering/partial index sau khi benchmark query thật.

Không thêm index hàng loạt theo cảm tính vì quá nhiều index làm ingestion/write chậm.

11.4. Connection Pool

Serving backend phải dùng connection pool.

Không mở connection PostgreSQL mới cho mỗi request.

11.5. Prepared / Parameterized Query

Tool layer dùng parameterized SQL.

Không cho LLM sinh arbitrary SQL gửi thẳng DB.

12. Derived Metrics

Backend tính deterministic metrics.

Ví dụ:

net_profit_growth_yoy
revenue_growth_yoy
net_interest_income_growth_yoy
profit_before_tax_growth_yoy
fee_income_growth_yoy
provision_growth_yoy
ROA
ROE
liabilities_to_assets

Chỉ tính khi required inputs tồn tại.

Missing input:

derived metric = null/unavailable

Không estimate.

12.1. Precompute để tăng tốc

Các metric phổ biến có thể lưu trong:

financial_metrics

Logical schema:

ticker
year
metric_code
value
calculation_version
updated_at

Điều này giúp:

ranking nhanh

screening nhanh

Why Engine nhanh

giảm tính lại mỗi query

13. Sector-Aware Metrics

Không ép schema chung sai semantic.

Bank

Ví dụ:

interest_income_and_similar_income
interest_expense_and_similar_expenses
net_interest_income
net_fee_and_commission_income
operating_expenses
provision_for_credit_losses
profit_before_tax
net_profit

Corporate

Ví dụ:

net_revenue
profit_after_tax
total_assets
total_liabilities
total_equity

Securities / Insurance

Giữ item_id riêng của source.

Không map semantic sai chỉ để có tên chung.

14. Qdrant — Company Knowledge Only

Collection:

company_knowledge

Document types:

company_profile
company_overview
officer

Payload bắt buộc:

ticker
doc_type
source

Officer document:

{
  "ticker": "FPT",
  "doc_type": "officer",
  "person_name": "...",
  "position": "...",
  "text": "...",
  "source": "vnstock"
}

14.1. Filter trước vector search

Ví dụ:

ticker = FPT
doc_type = officer

sau đó mới vector search.

Không search toàn collection trước rồi mới lọc.

14.2. Qdrant performance

Để query nhanh:

payload index cho ticker

payload index cho doc_type

top_k nhỏ

document chunk ngắn, đúng semantic

không embed numeric financial statements

không lưu giant raw JSON thành một vector

reuse embedding model/version

stable document IDs

Stable IDs:

{ticker}:profile
{ticker}:overview
{ticker}:officer:{stable_person_key}

15. Intent Router

Intent chính:

FINANCIAL_FACT
FINANCIAL_TIMESERIES
FINANCIAL_COMPARE
FINANCIAL_RANK
FINANCIAL_SCREEN
FINANCIAL_WHY
COMPANY_PROFILE
COMPANY_OVERVIEW
COMPANY_OFFICERS
HYBRID

Router output nên structured:

{
  "intent": "FINANCIAL_FACT",
  "tickers": ["ACB"],
  "metric_code": "net_profit",
  "year": 2025
}

Không cần LLM nếu rule/entity resolver đã đủ chắc chắn.

LLM router chỉ dùng khi câu hỏi ambiguous.

16. Query Planner

Sau router, Query Planner quyết định tool tối thiểu.

Ví dụ:

Fact

LNST ACB 2025?
→ resolve ticker
→ resolve metric
→ PostgreSQL one-row lookup
→ template response

Không cần Qdrant.

Không cần full LLM reasoning.

Time series

LNST ACB 2021–2025?
→ PostgreSQL range query
→ structured series
→ template/optional LLM

Compare

So sánh LNST ACB và MBB năm 2025
→ one SQL query
→ structured table
→ optional LLM description

Ranking

Top 10 ngân hàng có LNST cao nhất năm 2025
→ PostgreSQL ORDER BY
→ LIMIT 10
→ response

Company

FPT làm gì?
→ Qdrant filter ticker/doc_type
→ small top_k
→ LLM summarize

Hybrid

FPT làm gì và doanh thu 2025 bao nhiêu?

Chạy song song:

Qdrant --------┐
               ├→ merge
PostgreSQL ----┘

17. Why Engine

Không để LLM tự duyệt toàn bộ facts.

Backend chuẩn bị evidence theo sector.

Bank example:

net_profit_growth_yoy
net_interest_income_growth_yoy
net_fee_and_commission_income_growth_yoy
operating_expenses_growth_yoy
provision_for_credit_losses_growth_yoy
profit_before_tax_growth_yoy

Output backend:

{
  "ticker": "ACB",
  "year": 2025,
  "target_metric": "...",
  "related_metrics": []
}

LLM chỉ:

diễn giải

mô tả biến động

nêu evidence

Không khẳng định causal relationship tuyệt đối nếu dữ liệu chỉ cho thấy đồng biến/nghịch biến.

18. Query Performance — ưu tiên tốc độ tối đa

18.1. Rule số 1

Fastest valid path wins.

Không đi qua Qdrant/LLM nếu SQL direct lookup đủ.

18.2. Simple facts không bắt buộc LLM

Ví dụ:

LNST ACB 2025 bao nhiêu?

Backend có thể trả trực tiếp template:

LNST ACB năm 2025 là X.

LLM chỉ cần nếu user yêu cầu giải thích/phân tích.

18.3. Cache

Cache các thành phần ít thay đổi:

ticker resolver
metric catalog
aliases
sector map
company profile hot queries
popular ranking

Có thể bắt đầu bằng in-process LRU.

Redis chỉ thêm khi cần multi-instance hoặc cache distributed.

Không thêm Redis chỉ vì kiến trúc “trông production”.

18.4. Parallelism

Hybrid request:

PostgreSQL || Qdrant

chạy song song.

Không tuần tự nếu hai nhánh độc lập.

18.5. Context minimization

LLM chỉ nhận:

câu hỏi

structured result cần thiết

vài evidence rows

company snippets top-k nhỏ

Không đưa toàn report vào context.

18.6. Latency Targets

Mục tiêu sau warm-up, cần benchmark thật:

Backend direct fact       < 300 ms
Backend timeseries        < 500 ms
Backend compare/rank      < 800 ms
Qdrant retrieval          < 500 ms
Hybrid retrieval          < 1 s

End-to-end:

simple fact without LLM   < 1 s
fact with LLM formatting  ~1–2 s
company info              ~1–3 s
why/hybrid                ~2–5 s

Đây là target, không phải guarantee.

18.7. Performance Benchmark

Tạo test:

tests/performance/

Benchmark ít nhất:

100 fact queries

50 time-series queries

20 compare

20 rank

20 company

20 hybrid

Theo dõi:

P50
P95
P99

Không tối ưu dựa trên một request đơn lẻ.

19. Security / SQL Guardrails

Chatbot production role:

SELECT ONLY

Không:

INSERT
UPDATE
DELETE
DROP
ALTER
TRUNCATE

SQL tool phải:

whitelist schema

whitelist table

parameterized query

query timeout

row limit

no multiple statements

no arbitrary identifier injection

metric resolution qua catalog

20. Data Validation Philosophy

Chỉ kiểm tra kỹ thuật:

file tồn tại

parquet/json đọc được

schema parse được

year parse được

value lưu được

item_id

duplicate key

null

API error

source mismatch

Không:

sửa số

estimate

nearest year

“giá trị này có vẻ sai nên sửa”

so sánh web rồi overwrite source

Nếu source trả value:

preserve value

Nếu source trả null:

preserve null

21. Memory Policy

Conversation memory dùng cho:

follow-up

referent

user formatting preference

session state

Không dùng memory làm fact database.

Ví dụ:

User: LNST ACB 2025?
Assistant: ...
User: Còn MBB?

Memory giúp resolve:

metric = LNST
year = 2025
ticker = MBB

Sau đó vẫn query PostgreSQL.

22. Observability Standard

Mỗi request tạo trace:

{
  "trace_id": "...",
  "intent": "...",
  "ticker": ["..."],
  "metric_code": "...",
  "postgres_ms": 0,
  "qdrant_ms": 0,
  "llm_ms": 0,
  "total_ms": 0,
  "cache": "hit|miss",
  "status": "success|error"
}

Batch ingestion cũng phải report:

started_at
finished_at
runtime
tickers_total
tickers_success
tickers_failed
resources_downloaded
resources_skipped
resources_empty
resources_error

23. Test Strategy

Unit

Test:

year detection

wide → long

metric resolver

ticker resolver

derived metrics

missing handling

query planner

Integration

Test:

normalized → PostgreSQL

Qdrant build/load

PostgreSQL tool

Qdrant tool

router → tool

hybrid parallel

Golden Questions

Tạo fixed test set:

LNST ACB 2025?
Thu nhập lãi thuần MBB 2024?
Doanh thu FPT 2025?
LNST ACB 2021–2025?
So sánh LNST ACB và MBB.
Top ngân hàng theo LNST.
FPT làm gì?
Ban lãnh đạo HPG gồm ai?
FPT làm gì và doanh thu 2025 bao nhiêu?

Mỗi test phải kiểm:

route đúng

data source đúng

metric đúng

year đúng

deterministic value đúng với DB

missing behavior đúng

24. Phase Plan mới — hướng đi tiếp theo

PHASE 0 — Finish / Resume Bulk Raw Download

Mục tiêu:

hoàn tất downloader

resume ticker còn thiếu

không xóa dữ liệu đã tải

giảm rate nếu cần

bảo toàn manifest

PASS khi:

process hoàn thành

không corrupt artifact

manifest được lưu

các failure còn lại có danh sách rõ ràng

Sau đó:

STOP → REVIEW

PHASE 1 — Raw Audit

Tạo:

audit_raw.py

Output:

raw_audit_report.csv/json

PASS khi:

biết chính xác số ticker complete/partial

biết schema variation

biết empty/error resources

biết years available

biết item_id coverage

raw unchanged

Sau đó:

STOP → REVIEW

PHASE 2 — Freeze Downloader Contract

Sau audit:

chốt financial provider = VCI

chốt raw schema contract

chốt manifest fields

chốt retry/resume policy

chỉ sửa downloader nếu có bug

Mục tiêu:

Không tiếp tục thay downloader khi đã sang normalization,
trừ bug nghiêm trọng.

PHASE 3 — Normalization Pilot

Pilot đại diện:

FPT
HPG
MWG
GAS
ACB
MBB
SSI
BVH

Mục tiêu:

wide → long

Giữ:

ticker
year
statement_type
metric_code/item_id
metric_name
metric_name_en
value
source

PASS khi:

raw unchanged

không mất item_id

2021–2025 query được

variable year columns xử lý đúng

duplicate được phát hiện

bank/corporate/securities/insurance không bị ép sai schema

Sau đó:

STOP → REVIEW NORMALIZED ARTIFACTS

PHASE 4 — Inspect Existing PostgreSQL

Trước khi viết migration/load:

inspect schema hiện có

inspect table hiện có

inspect indexes

inspect constraints

xác định phần nào tái sử dụng

Output:

postgres_schema_report.md

Không migration destructive.

PASS khi:

có kế hoạch schema rõ ràng

biết table nào reuse

biết migration additive nào cần thiết

PHASE 5 — PostgreSQL Pilot Load

Load normalized pilot.

Dùng:

UPSERT

hoặc deterministic replace theo phạm vi pilot nếu đã được review.

Test:

fact

time series

compare

ranking

sector metric

PASS khi query deterministic hoạt động.

PHASE 6 — Metric Catalog + Derived Metrics

Tạo/finalize:

metric_catalog.csv

Implement:

aliases

sector awareness

derived metrics phổ biến

unit metadata

Benchmark query.

PHASE 7 — Qdrant Pilot

Build:

company_profile
company_overview
officer

Load:

company_knowledge

Test filter:

ticker
doc_type

PASS khi company lookup ổn định.

PHASE 8 — Query Tools + Harness Core

Implement typed tools:

get_financial_fact
get_financial_timeseries
compare
rank
screen
why_evidence
company_profile
company_officers

Thêm:

guardrails

timeout

observability

trace_id

memory policy

PHASE 9 — Intent Router + Query Planner

Implement intent routing.

Ưu tiên:

rule/deterministic resolver first
LLM fallback only when ambiguous

Test golden set.

PHASE 10 — End-to-End Chatbot

Kết nối:

User
→ Harness
→ Router
→ Planner
→ Tools
→ Structured Evidence
→ Response Composer
→ Optional LLM
→ Answer

PASS khi:

số liệu đến từ PostgreSQL

company knowledge đến từ Qdrant

hybrid chạy song song

missing trả đúng

không hallucinate numerical value

performance đạt target thực dụng

PHASE 11 — Scale Normalized + Serving Data

Sau pilot end-to-end PASS:

normalize toàn universe

load toàn PostgreSQL

build/load Qdrant toàn universe

build derived metrics

benchmark

audit lại

PHASE 12 — Production Hardening

Thêm khi cần:

read-only DB role

connection pooling

caching

retry

structured tracing

performance dashboard

backup

health checks

deployment config

regression suite

25. Stop Conditions

AI/Coding Agent phải STOP nếu:

Cần DROP/TRUNCATE production data.

Existing PostgreSQL schema khác giả định.

Raw schema có biến thể chưa xử lý.

Duplicate key chưa hiểu nguyên nhân.

item_id bị mất trong normalize.

VCI provider trả schema mới chưa được review.

Router gửi numerical question sang Qdrant.

LLM được yêu cầu tự tính ranking có thể làm bằng SQL.

Missing bị biến thành 0.

Phase chưa PASS nhưng code chuẩn bị chạy phase sau.

26. Những việc AI không được tự làm

Không được tự:

quay lại OCR/TXT/PDF

thay VNStock khỏi source chính

thay VCI provider financial mà không review

thêm web scraping

sửa numerical raw data

estimate missing

nearest-year substitution

đưa financial facts vào Qdrant

dùng Qdrant làm numerical truth

cho LLM tự ranking/growth khi backend làm được

arbitrary SQL

destructive migration

bypass audit

bypass phase gate

27. Definition of MVP Done

MVP hoàn thành khi:

Raw VNStock universe đã được audit.

Financial statements được normalize.

PostgreSQL chứa structured financial facts.

Company knowledge được index Qdrant.

Metric resolver hoạt động.

Router phân biệt numerical vs qualitative.

Chatbot trả được:

fact

time series

compare

ranking

screening

why

company profile

officers

hybrid

Derived metrics do backend tính.

Missing được xử lý đúng.

Numerical response không phụ thuộc Qdrant.

Simple fact path có thể trả lời không cần LLM.

Harness có tools, memory policy, execution environment, guardrails và observability.

Golden tests PASS.

Latency đạt mức thực dụng.

Không cần OCR/TXT/PDF cho MVP.

28. Immediate Next Step

Tại thời điểm roadmap này:

CURRENT STEP
=
FINISH/RESUME BULK RAW DOWNLOAD
→ RAW AUDIT
→ FREEZE DOWNLOADER
→ NORMALIZATION PILOT

Không đi thẳng vào:

PostgreSQL
Qdrant
Router
LLM integration

trước khi raw audit và normalization pilot được review.

Thứ tự ngay sau downloader:

1. Hoàn thành/resume bulk raw download.
2. Audit manifest + raw artifacts.
3. Review complete/partial/empty/error.
4. Inspect representative VCI schemas.
5. Freeze downloader contract.
6. Build normalize_financials.py.
7. Normalize pilot sectors.
8. Review normalized artifacts.
9. Inspect PostgreSQL hiện có.
10. Load PostgreSQL pilot.
11. Build metric catalog/derived metrics.
12. Build Qdrant company docs.
13. Implement query tools + harness.
14. Implement router/planner.
15. End-to-end tests.
16. Scale serving dataset.

29. Final Principle

Structured source first.

Raw is immutable.

PostgreSQL answers numbers.

Qdrant answers company knowledge.

Harness controls execution.

Machine calculates.

LLM explains.

Fastest valid query path wins.

Do not guess.

Do not repair source values.

Do not estimate missing.

Route before retrieve.

Filter before vector search.

Inspect before migrate.

Audit before normalize.

Pilot serving path before production scale.

Observe everything important.

Stop when assumptions break.