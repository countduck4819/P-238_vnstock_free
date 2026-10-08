Tôi đang phát triển dự án:

P-238 Financial AI Platform
Financial Intelligence Chatbot từ Báo cáo tài chính doanh nghiệp Việt Nam.

Hãy đọc toàn bộ context dưới đây trước khi sửa code hoặc chạy bất kỳ pipeline nào.

==================================================
1. MỤC TIÊU CUỐI CÙNG
==================================================

Mục tiêu không chỉ là chatbot đọc PDF.

Hệ thống cần:

1. Đọc Báo cáo tài chính PDF.
2. Trích xuất số liệu tài chính có cấu trúc.
3. Lưu số liệu vào PostgreSQL.
4. Giữ source trace về PDF gốc.
5. Tính toán financial metrics bằng Python/SQL.
6. Phân tích nhiều năm.
7. So sánh doanh nghiệp.
8. Ranking / screening theo nền tảng tài chính.
9. Chatbot trả lời:
   - số liệu
   - xu hướng
   - so sánh
   - giải thích
10. Sau này dùng RAG/Vector DB cho phần thuyết minh/evidence.

Triết lý:

Machine calculates
→ Evidence proves
→ LLM explains

Tức là:

Python / SQL
→ tính toán

PDF / evidence
→ chứng minh

LLM
→ diễn giải

KHÔNG để LLM tự tính deterministic financial metrics.

==================================================
2. PHÂN VAI DỮ LIỆU
==================================================

PostgreSQL:
→ structured numerical truth
→ financial facts
→ financial validation
→ query dữ liệu số

MinIO:
→ PDF gốc
→ evidence
→ artifacts
→ audit/source trace

Vector DB / embeddings:
→ chưa làm ở phase hiện tại
→ sau này dùng cho semantic evidence / thuyết minh
→ KHÔNG dùng làm numerical truth

==================================================
3. PROJECT PATH
==================================================

Project root:

~/P-238

Financial OCR project:

~/P-238/financial_ocr_mvp

Virtualenv:

~/P-238/.venv

Batch code hiện tại ưu tiên nằm tại:

financial_ocr_mvp/batch_v1/

Baseline OCR hiện tại phải được giữ ổn định.

Không phá:

docling_pipeline/
database/
output/docling/

trừ khi có yêu cầu rõ ràng.

==================================================
4. MINIO
==================================================

MinIO hiện có dữ liệu BCTC.

Bucket:

stock-data

Structure thực tế:

financial-reports/consolidated/{ticker}/{year}/quarterly/*.pdf

financial-reports/consolidated/{ticker}/{year}/annual/*.pdf

Ví dụ:

financial-reports/consolidated/FPT/2015/quarterly/FPT_Q1_2015_consolidated_....pdf

MinIO là READ-ONLY trong phase này.

TUYỆT ĐỐI KHÔNG:

- rename object
- move object
- delete object
- overwrite object
- upload artifact thử nghiệm ngược lên MinIO

PDF gốc phải luôn được giữ nguyên.

==================================================
5. POSTGRESQL
==================================================

Không tạo database mới.

Database hiện tại:

fireant_stock_dev

Schema:

financial

Các bảng chính đã có:

financial.financial_documents
financial.financial_facts
financial.financial_validation
financial.financial_ingestion_jobs

Importer đã hỗ trợ:

- document source path
- fact_id
- raw_value
- candidate_value
- final_value
- confidence/status
- source trace

Idempotency đã được test.

Không được tạo duplicate document/fact.

==================================================
6. NGUYÊN TẮC DATA QUALITY
==================================================

Bắt buộc:

Missing != 0

Không fake VERIFIED.

Không silent repair số liệu.

raw_value là immutable.

Nếu OCR đọc:

120.816,576.677

thì raw_value phải giữ nguyên.

Nếu OCR correction có candidate:

120.816.576.677

thì lưu candidate riêng.

Không overwrite raw.

Mọi dữ liệu quan trọng phải trace:

PDF
→ original page
→ table
→ row
→ column
→ value

==================================================
7. PIPELINE BASELINE ĐÃ CÓ
==================================================

Baseline extraction từng được xây theo luồng:

PDF
→ Docling
→ physical tables
→ semantic mapper
→ review queue
→ RapidOCR cell retry
→ merge candidates
→ financial fact builder
→ financial semantic mapper
→ financial rules engine
→ canonical financial JSON
→ PostgreSQL

Các module baseline đã hoạt động.

RapidOCR được xác nhận tốt hơn Qwen 3B cho numeric cell OCR.

Không quay lại Qwen numeric OCR nếu không có lý do rất rõ ràng.

==================================================
8. CANONICAL / FINANCIAL FACTS
==================================================

Đã xây canonical schema.

Các concepts điển hình:

revenue
cost_of_goods_sold
gross_profit
financial_expense
interest_expense
operating_profit
profit_before_tax
net_income

cash_and_cash_equivalents
receivables
inventory
total_assets
liabilities
borrowings
equity

operating_cash_flow
investing_cash_flow
financing_cash_flow
ending_cash

basic_eps

Canonical giữ:

raw
candidate
final
confidence
status
source trace

==================================================
9. CLI MVP ĐÃ CHỨNG MINH KIẾN TRÚC
==================================================

financial_cli.py đã query PostgreSQL trực tiếp.

Ví dụ:

"Doanh thu FPT Q1 2015?"

→ lấy numerical fact từ PostgreSQL
→ trả value
→ confidence/status
→ source page/table/row/column

Điều này chứng minh:

Numerical chatbot
KHÔNG cần embedding để trả số chính xác.

Sau này router sẽ là:

numeric question
→ PostgreSQL

qualitative/evidence question
→ RAG / semantic retrieval

==================================================
10. BATCH V1
==================================================

Để không phá baseline đã tạo:

financial_ocr_mvp/batch_v1/

Các module hiện có/đã từng thêm:

minio_scanner.py
path_parser.py
pipeline_adapter.py
batch_runner.py
config.py
job_creator.py
run_financial_pipeline.py

và các module thử nghiệm navigation:

section_taxonomy.py
page_selector.py
pdf_page_filter.py
benchmark_page_selector.py
core_statement_locator.py
benchmark_core_locator.py

==================================================
11. BATCH END-TO-END ĐÃ PASS
==================================================

Đã test pipeline tự động từ:

MinIO
→ download PDF
→ OCR
→ canonical
→ PostgreSQL

FPT Q1/2015:

status: needs_review

download: PASS
docling: PASS
semantic_mapping: PASS_WITH_REVIEW
rapidocr: PASS
financial_facts: PASS
financial_rules: PASS
canonical: PASS
postgres_import: PASS

facts: 207
processing_seconds: 191.715

duplicate_documents: 0
duplicate_facts: 0

Source path lưu đúng MinIO path.

raw_value không bị overwrite.

==================================================
12. PILOT BENCHMARK 5 REPORT
==================================================

Đã chạy 5 report:

FPT Q1/2015
- 207 facts
- 191.715s

HPG Q1/2015
- 69 facts
- 257.631s
- peak RAM ~4615 MB

HPG Annual 2015
- 316 facts
- 709.470s
- peak RAM ~4342 MB

VNM Q1/2015
- 739 facts
- 592.437s
- peak RAM ~3224 MB

MWG Q2/2015
- 187 facts
- 250.918s
- peak RAM ~3553 MB

Average:

~400.434 seconds/report

Average peak RAM:

~3934 MB

Pipeline completed:

5/5

Failed:

0

Nhưng cả 5 đều needs_review.

==================================================
13. BOTTLENECK ĐÃ ĐƯỢC ĐO
==================================================

Profiling trung bình:

Docling:
~183.357s

RapidOCR:
~154.677s

PostgreSQL import:
~107.107s

Download:
~5.349s

Financial validation:
~1.819s

Các stage khác:
<0.1s

=> 3 bottleneck:

1. Docling
2. RapidOCR
3. PostgreSQL importer

Importer hiện execute từng fact/rule nên có thể tối ưu batch insert sau.

Nhưng bottleneck lớn nhất về kiến trúc là đang đọc quá nhiều page.

==================================================
14. PAGE SELECTOR ĐÃ THỬ VÀ THẤT BẠI
==================================================

Ý tưởng cũ:

PDF
→ classify toàn bộ page
→ KEEP core + important notes
→ Docling selected pages

Đã xây Page Selector:

- fuzzy header
- Vietnamese normalization
- taxonomy config driven
- KEEP/SKIP/UNCERTAIN
- continuation
- scan fallback OCR

Benchmark:

HPG Annual scan:
77 pages
→ selected 77
→ reduction 0%

HPG Q1 scan:
30
→ selected 30
→ reduction 0%

VNM Q1 native text:
59
→ selected 59
→ reduction 0%

Kết luận:

PAGE_SELECTOR_NOT_EFFECTIVE

Lý do:

PDF scan không có text layer.

Nếu OCR toàn bộ page chỉ để biết page nào cần giữ thì lại tốn gần bằng extraction.

KHÔNG tiếp tục đầu tư vào Page Selector full-document.

==================================================
15. CORE STATEMENT LOCATOR ĐÃ THỬ
==================================================

Sau đó đổi ý tưởng:

Không classify toàn PDF.

Thay bằng:

PDF
→ tìm 3 báo cáo chính càng sớm càng tốt
→ early-stop
→ chỉ extract core pages

Ba CORE:

1. Balance Sheet
2. Income Statement
3. Cash Flow

Benchmark:

--------------------------------------------------

HPG Annual 2015 scan

77 total pages
searched: 12 pages
time: ~30.36s

Found:

Balance Sheet:
page 4–5

Income Statement:
page 10–11

Cash Flow:
page 12–13

early_stop = true

=> trường hợp này khá tốt.

--------------------------------------------------

HPG Q1 scan

30 pages

searched:
30

time:
~75.48s

Found:

Balance Sheet:
page 2–3

Missing:

Income Statement
Cash Flow

=> locator thất bại với format này.

Nguyên nhân có thể:
heading nằm ngoài vùng top crop hiện tại.

--------------------------------------------------

VNM Q1 native-text

59 pages

searched:
2

time:
0.17s

Locator tưởng đã tìm đủ 3 CORE.

NHƯNG đây là FALSE POSITIVE.

Nguyên nhân:

Mục lục có cùng lúc:

Balance Sheet
Income Statement
Cash Flow

Locator nhầm mục lục thành báo cáo thật.

==================================================
16. KẾT LUẬN SAU CORE LOCATOR V1
==================================================

CORE_LOCATOR_NOT_EFFECTIVE

Nhưng chưa bỏ hoàn toàn hướng locator.

Có 2 lỗi khá cụ thể có thể sửa một lần cuối:

1. False positive từ mục lục.
2. Scan heading/crop chưa linh hoạt sau khi đã tìm được first anchor.

Không tiếp tục R&D locator vô hạn.

==================================================
17. SCOPE MỚI CỦA DATASET
==================================================

Scope ban đầu rất lớn:

100 mã
2015–2020
Q1/Q2/Q3/Q4/Annual

Đã quyết định giảm mạnh.

Scope mới:

50 mã

Chỉ lấy:

ANNUAL
Q2
Q3

BỎ:

Q1
Q4

Lý do:

Annual:
bắt buộc, dữ liệu cuối năm đầy đủ nhất.

Q2:
mốc giữa năm, hữu ích.

Q3:
mốc 9 tháng, hữu ích trước cuối năm.

Q4:
trùng khá nhiều với Annual.

Q1:
nếu bắt buộc bỏ một quý nữa thì giá trị thấp hơn Q2/Q3 cho mục tiêu hiện tại.

--------------------------------------------------

CHÚ Ý VỀ NĂM:

Nếu nói:

2020–2025 inclusive

thì đó là 6 năm.

Nếu thật sự muốn 5 năm thì cần chọn:

2020–2024

hoặc

2021–2025.

KHÔNG tự quyết định.
Hãy để user chốt range nếu chưa rõ.

--------------------------------------------------

Nếu 50 tickers × 5 years × 3 reports:

50 × 5 × 3
= tối đa 750 PDF

Nếu 2020–2025 inclusive:

50 × 6 × 3
= tối đa 900 PDF

Actual count có thể thấp hơn vì thiếu report.

==================================================
18. SCOPE FINANCIAL DATA MỚI
==================================================

Để cứu tốc độ extraction, phase hiện tại CHỈ ưu tiên 3 báo cáo chính.

CORE:

1. Balance Sheet
2. Income Statement
3. Cash Flow

Tạm thời KHÔNG batch extract toàn bộ thuyết minh.

PDF full vẫn giữ ở MinIO để khai thác sau bằng RAG/multimodal.

Các concept core cần đủ:

BALANCE SHEET:

cash_and_cash_equivalents
receivables
inventory
total_assets
liabilities
borrowings nếu có
equity

INCOME STATEMENT:

revenue
cost_of_goods_sold
gross_profit
financial_expense
interest_expense nếu có
operating_profit
profit_before_tax
net_income
eps

CASH FLOW:

operating_cash_flow
investing_cash_flow
financing_cash_flow
ending_cash

Dataset này đã đủ cho:

revenue growth
profit growth
gross margin
net margin
ROA
ROE
Debt/Equity
asset growth
cash analysis
operating cash flow
FCF nếu đủ dữ liệu
quality of earnings
multi-year trend
peer comparison
ranking

==================================================
19. Ý TƯỞNG MỚI NHẤT CHO CORE LOCATOR V2
==================================================

KHÔNG quay lại Page Selector toàn tài liệu.

Sửa đúng 2 vấn đề:

A. TOC REJECTION / STATEMENT VERIFICATION

B. ANCHOR-BASED NEIGHBORHOOD SEARCH

==================================================
20. A — TOC REJECTION
==================================================

Không được coi section là FOUND chỉ vì nhìn thấy heading.

Phân biệt:

CANDIDATE
vs
VERIFIED

Ví dụ thấy:

"Báo cáo lưu chuyển tiền tệ"

chỉ là:

candidate

Muốn VERIFIED phải có thêm evidence của bảng thật.

--------------------------------------------------
BALANCE SHEET VERIFY
--------------------------------------------------

Tín hiệu có thể gồm:

heading tương ứng

+

"Mã số"
"Thuyết minh"

+

"Tài sản"
"Nợ phải trả"
"Vốn chủ sở hữu"

+

numeric/table density

--------------------------------------------------
INCOME STATEMENT VERIFY
--------------------------------------------------

heading

+

"Doanh thu"
"Giá vốn"
"Lợi nhuận"

+

numeric/table structure

--------------------------------------------------
CASH FLOW VERIFY
--------------------------------------------------

heading

+

"Lưu chuyển tiền từ hoạt động kinh doanh"
"Hoạt động đầu tư"
"Hoạt động tài chính"

+

numeric/table structure

==================================================
21. TOC DETECTION
==================================================

Mục lục thường có:

"MỤC LỤC"
"CONTENTS"

hoặc:

nhiều section title trên cùng page
+
page number
+
dotted leaders
+
không có financial table thật

Một rule rất hữu ích:

Nếu cùng một page, đặc biệt ở đầu PDF,
chứa:

Balance Sheet
+
Income Statement
+
Cash Flow

thì KHÔNG được lập tức kết luận cả 3 VERIFIED.

Đây rất có thể là TOC.

Page phải được:

TOC / navigation-only

Không dùng để early-stop.

==================================================
22. B — ANCHOR-BASED NEIGHBORHOOD
==================================================

HPG Q1 đã tìm được:

Balance Sheet page 2–3.

Đây là một first anchor rất mạnh.

KHÔNG tiếp tục OCR:

page 4 → 30

theo kiểu toàn bộ.

Thay vào đó:

Balance Sheet anchor
↓
search neighborhood gần đó
↓
Income Statement
↓
Cash Flow

Ví dụ:

Balance Sheet:
page 2–3

search next:

page 4
5
6
7
8
9
10
11
12

Không scan ngay toàn bộ 30 pages.

==================================================
23. ADAPTIVE HEADING REGION
==================================================

Lỗi HPG Q1 có thể vì heading không nằm trong top crop hiện tại.

Do đó candidate page phải dùng adaptive search:

PASS 1:

OCR / inspect top 25%

Nếu không thấy:

PASS 2:

top 50%

Nếu vẫn không thấy:

PASS 3:

full page LOW-DPI OCR

NHƯNG:

PASS 3 chỉ được dùng trong neighborhood nhỏ quanh first anchor.

KHÔNG full-page OCR toàn bộ PDF.

==================================================
24. CORE LOCATOR V2 FLOW
==================================================

PDF
↓
native text available?

YES
↓
TOC detection
↓
candidate heading
↓
statement verification

NO / scanned
↓
low-cost heading OCR
↓
find first CORE anchor
↓
verify
↓
neighbor search
↓
adaptive crop
↓
verify remaining CORE

Khi:

Balance Sheet = VERIFIED
Income Statement = VERIFIED
Cash Flow = VERIFIED

→ EARLY STOP

==================================================
25. CONTINUATION
==================================================

Không chỉ giữ đúng header page.

Ví dụ:

Balance Sheet:
page 4–5

Income Statement:
page 10

Cash Flow:
page 11–12

selected pages:

4,5,10,11,12

Nếu boundary chưa chắc:

giữ thêm 1 continuation page.

Thà dư 1 page hơn mất nửa bảng.

==================================================
26. PAGE MAP
==================================================

Nếu tạo:

core_selected_pages.pdf

thì phải giữ:

working_page
→ original_page

Ví dụ:

{
  "1": 4,
  "2": 5,
  "3": 10,
  "4": 11,
  "5": 12
}

Canonical/PostgreSQL cuối cùng phải source về:

ORIGINAL PDF PAGE

Không source về page index của working PDF.

==================================================
27. TEST CUỐI CÙNG CHO LOCAL LOCATOR
==================================================

Chỉ sửa đúng:

1. TOC rejection + statement verification.
2. Anchor neighborhood + adaptive heading region.

Không thêm model phức tạp mới.

Không làm thêm full-document selector.

Benchmark lại đúng:

HPG Annual 2015 scan
HPG Q1/2015 scan
VNM Q1/2015 native text

Expected:

HPG Annual:
→ đủ 3 core
→ early stop

HPG Q1:
→ đủ 3 core
→ không scan toàn bộ 30 pages

VNM:
→ không false positive TOC
→ tìm đúng actual statement pages

==================================================
28. QUYẾT ĐỊNH SAU TEST
==================================================

Nếu Core Locator V2 PASS:

→ tích hợp vào pipeline_adapter
→ Docling chỉ xử lý 4–8 core pages
→ RapidOCR selective
→ canonical
→ PostgreSQL

Nếu HPG quarterly vẫn:

- scan gần toàn bộ PDF
hoặc
- không tìm đủ core

thì:

DỪNG LOCAL LOCATOR R&D.

Không tiếp tục vá.

Kết luận:

LOCAL_LOCATOR_NOT_SCALABLE

Sau đó cân nhắc:

Multimodal extraction provider
(Gemini / tương đương)

thay cho tầng:

locator + Docling + RapidOCR

nhưng vẫn giữ:

Canonical
Validation
PostgreSQL
MinIO
Job Queue
Source Trace
Financial engines

==================================================
29. RAPIDOCR
==================================================

RapidOCR hiện đã selective ở cell-level.

Không rewrite nếu chưa có bằng chứng cần thiết.

Logic đúng:

Docling good cell
→ dùng luôn

bad/malformed numeric cell
→ RapidOCR retry

Không OCR lại toàn table nếu chỉ một cell lỗi.

==================================================
30. POSTGRES IMPORTER
==================================================

Đã biết là bottleneck.

~107 seconds/report trung bình trong pilot.

Nguyên nhân:

nhiều execute/upsert riêng lẻ.

SAU KHI core extraction ổn:

audit importer

và chuyển sang batch insert/upsert nếu an toàn.

Target:

PostgreSQL import
<5–10 seconds/report

Nhưng chưa tối ưu importer trước khi Core Locator V2 được review.

==================================================
31. CHECKPOINT / RESUME
==================================================

Pipeline dài nên cần:

downloaded
core_located
core_pdf_created
docling_done
rapidocr_done
facts_done
canonical_done
postgres_imported

Nếu PostgreSQL lỗi:

KHÔNG Docling lại.

Nếu RapidOCR lỗi:

KHÔNG locator + Docling lại nếu artifact trước đó hợp lệ.

==================================================
32. JOB QUEUE — LAST KNOWN STATE
==================================================

Trước các thử nghiệm locator:

5 pilot jobs:
needs_review

13 jobs:
pending

failed:
0

KHÔNG chạy 13 pending jobs cho đến khi user review.

==================================================
33. SAFETY
==================================================

TUYỆT ĐỐI KHÔNG:

- chạy batch 13 pending tự động
- chạy 50 tickers tự động
- scale toàn dataset
- ghi/xóa MinIO
- tạo database mới
- phá baseline
- overwrite raw_value
- fake VERIFIED
- coi missing = 0
- bắt đầu RAG/embedding/vector DB
- tự đổi scope
- tự chạy bước tiếp theo sau benchmark

==================================================
34. VIỆC CẦN LÀM NGAY
==================================================

Bây giờ KHÔNG làm lại toàn bộ pipeline.

Chỉ:

1. Audit core_statement_locator.py hiện tại.
2. Giữ code đang PASS cho HPG Annual.
3. Thêm TOC rejection.
4. Thêm statement verification.
5. Thêm anchor-based neighborhood.
6. Thêm adaptive crop:
   - top 25%
   - top 50%
   - low-DPI full page only inside neighborhood
7. Benchmark lại đúng 3 PDF:
   - HPG Annual scan
   - HPG quarterly scan
   - VNM native-text
8. Không chạy Docling.
9. Không import PostgreSQL.
10. Không chạy pending jobs.

Output:

output/batch_v1/core_locator_v2_benchmark.json

Mỗi PDF phải báo:

total_pages
searched_pages
locator_seconds

TOC pages detected

balance_sheet:
candidate page
verified pages
confidence

income_statement:
candidate page
verified pages
confidence

cash_flow:
candidate page
verified pages
confidence

selected_pages
missing_sections
early_stop
false_positive_detected

Kết luận chỉ một trong:

CORE_LOCATOR_V2_READY

hoặc

LOCAL_LOCATOR_NOT_SCALABLE

Nếu READY:
DỪNG để user review.

Nếu NOT_SCALABLE:
DỪNG.
Không tự nghiên cứu locator V3.

==================================================
35. NGUYÊN TẮC LÀM VIỆC
==================================================

Không cố cứu một hướng chỉ vì đã viết nhiều code.

Ưu tiên:

correctness
→ scalability
→ simplicity

Nếu giải pháp local rõ ràng không khả thi,
hãy báo thẳng.

Không fake benchmark.
Không suy đoán số liệu.
Không tự an ủi.
Không mở rộng scope.

Đọc code hiện tại trước khi sửa.
Thay đổi nhỏ nhất có thể.
Bảo vệ baseline.