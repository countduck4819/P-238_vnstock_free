# FinSight Financial Research Agent Specification

## 1. Thông tin tài liệu

- Tên hệ thống: FinSight Financial Research Agent
- Trạng thái: bản đặc tả theo source hiện tại
- Mục tiêu: mô tả quá trình chuyển FinSight từ chatbot hỏi–đáp sang agent nghiên cứu tài chính có kiểm soát
- Phạm vi: kiến trúc, luồng xử lý, dữ liệu, công cụ, reasoning, an toàn, kiểm thử, giới hạn và lộ trình tiếp theo
- Không thuộc phạm vi: giao dịch tự động, khuyến nghị mua/bán, dự báo giá chắc chắn hoặc tự huấn luyện mô hình trong production

## 2. Tóm tắt điều hành

FinSight ban đầu hoạt động gần với một chatbot tài chính có bộ định tuyến rule-based: nhận diện một số mẫu câu, chọn một truy vấn cố định, lấy dữ liệu rồi ghép câu trả lời. Cách làm này phù hợp với câu hỏi đơn như “Doanh thu FPT năm 2024?”, nhưng dễ sai khi gặp câu ghép, câu phân tích, câu hỏi thiếu dữ liệu, câu hỏi cần nhiều nguồn hoặc câu diễn đạt chưa từng được hard-code.

Hệ thống hiện tại đã được mở rộng thành một **bounded financial research agent** với các khả năng chính:

- Hiểu câu hỏi tự nhiên và tạo Financial Analysis Blueprint có schema.
- Lập kế hoạch bằng chứng trước khi lấy dữ liệu.
- Kiểm tra evidence nào có sẵn, có thể tính, còn thiếu hoặc cần nguồn ngoài.
- Chọn và gọi tool PostgreSQL, Calculation Engine, Qdrant hoặc Web Search.
- Quan sát kết quả, đánh giá độ đầy đủ và re-plan trong giới hạn.
- Hợp nhất bằng chứng theo thứ tự tin cậy và công khai xung đột.
- Phân biệt FACT, INFERENCE và UNKNOWN.
- Tạo financial signals, benchmark, risk review và analyst report.
- Kiểm soát số vòng lặp, số lần gọi LLM/tool/web và tổng nội dung ngoài.
- Có deterministic fallback khi LLM hoặc một nguồn dữ liệu không khả dụng.
- Có evaluation framework và golden regression dataset để chống regression.

FinSight chưa phải agent tự trị hoàn chỉnh. Planner vẫn bị giới hạn bởi ontology và tool registry hiện hữu; dữ liệu định giá, dòng tiền, benchmark ngành và dữ liệu sự kiện chưa đủ rộng; memory dài hạn, feedback learning, observability production và khả năng tự phục hồi dịch vụ vẫn còn hạn chế.

## 3. Từ chatbot sang agent

### 3.1 Chatbot trước đây

Luồng cũ chủ yếu là:

```text
User question
  -> nhận diện intent bằng từ khóa/rule
  -> tạo một query
  -> PostgreSQL hoặc Qdrant
  -> ghép template trả lời
```

Các hạn chế điển hình:

- Thường chỉ xử lý tốt một ý trong một câu hỏi.
- Câu sau có thể bị ảnh hưởng sai bởi intent hoặc context của câu trước.
- Câu hỏi ghép có thể chỉ trả lời phần xếp hạng mà bỏ phần tra cứu đơn lẻ.
- Qdrant trả đoạn gần nhất thay vì đúng loại tài liệu cần tìm.
- Không có bước xác định “cần bằng chứng gì” trước khi query.
- Không phân biệt rõ dữ liệu thiếu, tool lỗi và metric không hỗ trợ.
- Có thể lộ mã lỗi kỹ thuật như `TOOL_UNAVAILABLE` ra UI.
- LLM fallback có nguy cơ viết số hoặc nguồn không có trong dữ liệu.
- Không có cơ chế đánh giá chất lượng toàn pipeline một cách chuẩn hóa.

### 3.2 Agent hiện tại

Luồng mới ưu tiên evidence-first:

```text
User question
  -> Supervisor
  -> hiểu mục tiêu và lập blueprint
  -> lập kế hoạch evidence
  -> kiểm tra khả năng cung cấp dữ liệu
  -> lập/chỉnh kế hoạch tool
  -> thực thi và quan sát
  -> critic kiểm tra độ đầy đủ
  -> hợp nhất evidence
  -> financial reasoning
  -> interpretation / benchmark / risk
  -> analyst report
  -> grounded synthesis và validation
  -> public response
```

Khác biệt cốt lõi là agent không chỉ hỏi “câu này khớp rule nào”, mà lần lượt hỏi:

1. Người dùng thực sự muốn biết điều gì?
2. Muốn kết luận cần những bằng chứng nào?
3. Nguồn nào đáng tin nhất cho từng bằng chứng?
4. Metric có sẵn, có thể tính hay phải tìm ngoài?
5. Kết quả hiện tại đã đủ để trả lời chưa?
6. Kết luận nào là fact, inference hoặc unknown?

## 4. Nguyên tắc thiết kế

### 4.1 Evidence-first

Mọi kết luận tài chính phải bắt đầu từ evidence có cấu trúc. LLM không phải nguồn dữ liệu và không được tự tạo số.

### 4.2 Numerical truth isolation

Thứ tự tin cậy mặc định:

```text
PostgreSQL numerical truth
  > deterministic derived metric
  > external financial source
  > Qdrant qualitative knowledge
```

- Số trong PostgreSQL là numerical truth nội bộ.
- Derived metric phải được tính từ fact có nguồn bằng công thức deterministic.
- Số từ web chỉ là external evidence, không tự động thay thế hoặc ghi đè PostgreSQL.
- Qdrant dùng cho kiến thức định tính, không dùng làm nguồn số chính thức.
- Khi nguồn mâu thuẫn, hệ thống phải ghi nhận conflict thay vì âm thầm chọn một số.

### 4.3 LLM bị giới hạn vai trò

LLM được phép hỗ trợ:

- hiểu và chuẩn hóa mục tiêu;
- lập kế hoạch/re-plan;
- diễn đạt và tổng hợp câu trả lời.

LLM không được phép:

- tự chạy SQL;
- tự gọi URL ngoài tool registry;
- tạo ticker, năm hoặc metric không được grounding;
- tự tính hoặc sửa số tài chính;
- thêm nguồn không có trong evidence;
- đưa khuyến nghị mua/bán hoặc cam kết lợi nhuận.

### 4.4 Graceful degradation

Nếu LLM, PostgreSQL, Qdrant hoặc web lỗi, request phải ưu tiên fallback an toàn. Người dùng nhận giới hạn ở ngôn ngữ nghiệp vụ, không nhận stack trace, connection string hoặc lỗi kỹ thuật nội bộ.

### 4.5 Bounded autonomy

Agent được phép tự chọn tool và re-plan nhưng bị giới hạn bởi schema, validator và budget. Đây là chủ đích an toàn, không phải agent tự trị vô hạn.

## 5. Kiến trúc triển khai

```text
Next.js Web UI
  :3000 hoặc :3001
        |
        v
NestJS API
  :8000
  - xác thực người dùng
  - lưu lịch sử chat
  - proxy yêu cầu FinSight
        |
        v
FinSight FastAPI
  :6071
  - validation
  - timeout
  - rate limit
  - public error boundary
        |
        v
FinSightApplication
        |
        v
FinancialAgentSupervisor / UnifiedFinancialQueryHandler
  |                         |
  | simple query            | complex/research query
  v                         v
Deterministic path       LangGraph agent path
  |                         |
  +------------+------------+
               v
        Unified response contract

Data/tool dependencies:

- PostgreSQL: financial numerical truth
- Calculation Engine: derived metrics
- Qdrant + BGE-M3 1024: qualitative company knowledge
- Tavily/Web: controlled current/external research
- Python Data API :6060: dịch vụ dữ liệu cổ phiếu dùng bởi các phần NestJS khác
```

Lưu ý: Python Data API `:6060` và FinSight API `:6071` là hai service khác nhau. Việc `:6060` lỗi có thể ảnh hưởng cron/stock recommendation của NestJS nhưng không đồng nghĩa LangGraph của FinSight bị lỗi; ngược lại, UI hỏi FinSight cần `:6071` hoạt động và NestJS phải trỏ đúng URL.

## 6. Public API và vận hành

FastAPI hiện cung cấp:

- `GET /health`: kiểm tra process hoạt động.
- `GET /ready`: kiểm tra readiness ở mức ứng dụng.
- `POST /api/v1/finsight/query`: endpoint chính.
- `POST /api/ai-stock/ask`: endpoint tương thích với UI/NestJS hiện hữu.

Boundary hiện có:

- Pydantic request/response validation.
- Request ID cho mỗi yêu cầu.
- Timeout tối đa 120 giây.
- Sliding-window rate limit theo `user_id` hoặc IP.
- Mặc định 8 request trong 60 giây trên mỗi process.
- HTTP `429` kèm thông báo thử lại sau khi spam.
- HTTP `503/504` với thông báo công khai đã được làm sạch.

Rate limiter hiện chỉ nằm trong memory của một process. Khi scale nhiều replica, mỗi replica có bộ đếm riêng; production cần shared limiter như Redis hoặc API gateway.

## 7. Supervisor và hai execution path

### 7.1 UnifiedFinancialQueryHandler

`src/services/financial_supervisor.py` là cổng xử lý thống nhất:

- Phân loại một số intent nghiệp vụ cần contract riêng.
- Chuyển câu hỏi đơn giản sang deterministic query path để giảm latency.
- Chuyển câu hỏi phân tích/phức tạp sang LangGraph agent.
- Dùng chung `QueryHarness`, LLM client và web research dependency.

### 7.2 Deterministic path

Dùng cho câu hỏi rõ ràng, ít bước, ví dụ:

```text
Doanh thu thuần của FPT năm 2024 là bao nhiêu?
```

Luồng:

```text
intent router -> QueryHarness -> PostgreSQL -> response composer
```

Ưu điểm: nhanh, dự đoán được, không tốn LLM và ít điểm lỗi.

### 7.3 LangGraph path

Dùng cho:

- câu hỏi nhiều công ty hoặc nhiều metric;
- phân tích chuỗi thời gian;
- sức khỏe tài chính;
- chất lượng lợi nhuận;
- benchmark và risk;
- thông tin hiện tại cần web;
- câu hỏi cần nhiều bước phụ thuộc nhau.

## 8. LangGraph workflow hiện tại

Các node thực tế trong `src/services/agent_graph.py`:

```text
START
  -> route_request
  -> interpret_goal
  -> plan
  -> understand_question
  -> plan_evidence
  -> analyze_availability
  -> recover_external_data
  -> fuse_evidence
  -> validate_action
  -> execute_tool
  -> observe
  -> decide_next
       -> validate_action (CONTINUE)
       -> plan (REPLAN)
       -> critic (COMPLETE/FAIL)
       -> compose (CLARIFY)
  -> critic
  -> financial_reasoning
  -> financial_interpretation
  -> benchmark_analysis
  -> risk_review
  -> analyst_report_generator
  -> synthesize
  -> validate_synthesis
  -> compose
  -> END
```

Vai trò từng nhóm node:

| Nhóm | Node | Trách nhiệm |
|---|---|---|
| Routing | `route_request`, `interpret_goal` | Chuẩn hóa mục tiêu, ticker, sector, period và analytical concepts |
| Planning | `plan`, `understand_question`, `plan_evidence`, `analyze_availability` | Tạo tool plan và kế hoạch evidence có schema |
| Recovery | `recover_external_data`, `fuse_evidence` | Tìm evidence ngoài khi cần và hợp nhất nguồn |
| Execution | `validate_action`, `execute_tool`, `observe`, `decide_next` | Kiểm tra action, gọi tool, ghi observation và quyết định bước kế tiếp |
| Quality | `critic` | Kiểm tra đủ bằng chứng, lỗi và khả năng hoàn thành |
| Analysis | `financial_reasoning`, `financial_interpretation`, `benchmark_analysis`, `risk_review` | Tạo fact/inference/signal/benchmark/risk có reference |
| Reporting | `analyst_report_generator`, `synthesize`, `validate_synthesis`, `compose` | Tạo báo cáo, kiểm tra grounded claims và response cuối |

Hiện có một điểm cần đơn giản hóa: evidence availability/recovery/fusion chạy trước vòng tool execution, trong khi evidence thực tế còn được bổ sung ở vòng execute–observe. Về lâu dài nên thống nhất collection lifecycle để tránh hai đường evidence song song và giảm trạng thái khó hiểu.

## 9. Agent state contract

`LangGraphAgentState` là contract dùng chung giữa các node. Các nhóm field chính:

- Request: `question`, `goal`, `tickers`, `sector`, `period`, `analytical_concepts`.
- Understanding: `financial_blueprint`, `blueprint_used`.
- Planning: `evidence_plan`, `data_availability`, `plan`, `pending_action`.
- Execution: `observations`, `tool_calls`, `results`, `completed_steps` tương đương qua state thực thi.
- Evidence: `evidence`, `normalized_evidence`, `compact_observations`, `external_evidence`, `external_recovery_evidence`, `web_sources`, `source_conflicts`.
- Analysis: `evidence_package`, `financial_analysis_result`, `financial_signals`, `benchmark_result`, `risk_review`, `analyst_report`.
- Control: `decision`, `status`, `research_complete`, `missing_information`, `warnings`.
- Budget: `iteration_count`, `llm_call_count`, `tool_call_count`, `replan_count`, `web_call_count` và các giá trị tối đa.
- Output/trace: `synthesis_draft`, `synthesis_valid`, `final_answer`, `trace`, `claim_types`.

State là dữ liệu điều phối, không phải conversational memory dài hạn. Lịch sử chat đang được NestJS lưu riêng và chỉ được truyền vào một số path.

## 10. Financial Question Understanding

Module: `src/services/financial_question_understanding.py`.

Input:

```json
{"user_query": "FPT đang khỏe lên hay yếu đi?"}
```

Output là `FinancialAnalysisBlueprint` gồm:

- `intent`
- `companies`
- `sector`
- `period.start`, `period.end`
- `analysis_type`
- `required_evidence`
- `risk_flags`

Intent schema hiện hỗ trợ:

- `FACT_LOOKUP`
- `TIME_SERIES_ANALYSIS`
- `COMPANY_COMPARISON`
- `COMPANY_EVALUATION`
- `FINANCIAL_HEALTH_ANALYSIS`
- `INVESTMENT_RESEARCH`
- `RISK_ANALYSIS`
- `TREND_ANALYSIS`

Analysis type:

- `growth`
- `profitability`
- `efficiency`
- `leverage`
- `cashflow`
- `valuation`
- `business_quality`
- `industry_context`

Đặc tính an toàn:

- Không query database.
- Không gọi web.
- Không sinh số tài chính.
- Pydantic từ chối field ngoài schema.
- Kết quả LLM phải nằm trong ticker/period đã được deterministic resolver grounding.
- Nếu LLM lỗi hoặc JSON sai, dùng deterministic fallback.

## 11. Evidence Planning và Availability

### 11.1 Evidence Planning

Module: `src/services/evidence_planning.py`.

Mỗi evidence item gồm:

- tên evidence;
- category;
- priority;
- source preference;
- fallback source;
- có bắt buộc hay không.

Category:

- `NUMERIC_FACT`
- `DERIVED_METRIC`
- `QUALITATIVE_KNOWLEDGE`
- `EXTERNAL_EVENT`

Mapping nguồn mặc định:

| Evidence | Nguồn ưu tiên | Fallback |
|---|---|---|
| Numeric fact | PostgreSQL | Không tự thay bằng web |
| Derived metric | Calculation Engine | PostgreSQL nếu đã materialize |
| Qualitative knowledge | Qdrant | Web |
| External/current event | Web | Qdrant nếu có tài liệu phù hợp |

### 11.2 Data Availability Analyzer

Module: `src/services/data_availability.py`.

Output phân evidence thành:

- `available`
- `missing`
- `derivable`
- `external_required`

`MetricRegistry`, `EvidenceRegistry` và resolver cho phép thêm metric/evidence mới mà không đổi toàn bộ workflow. Missing không bao giờ được coi là `0`.

## 12. Tool layer

Tool registry hiện tại nằm trong `src/services/agent_actions.py`:

| Action | Tool handler | Mục đích |
|---|---|---|
| `FACT` | `get_fact` | Một metric, một công ty, một năm |
| `TIME_SERIES` | `get_timeseries` | Chuỗi metric theo khoảng năm |
| `COMPARE` | `compare` | So sánh nhiều công ty |
| `RANK` | `rank` | Xếp hạng theo metric/sector/năm |
| `EVALUATION` | `evaluate_stock` | Thu thập nhóm chỉ tiêu đánh giá |
| `COMPANY_KNOWLEDGE` | `search_company_knowledge` | Tìm kiến thức doanh nghiệp trong Qdrant |
| `WEB_SEARCH` | `web_search` | Tìm thông tin bên ngoài có kiểm soát |

`ActionValidator` chặn:

- action không đăng ký;
- ticker không thuộc taxonomy hoặc không có trong câu hỏi;
- metric không hỗ trợ hoặc không áp dụng cho sector;
- năm không hợp lệ hoặc không được grounding;
- period đảo ngược;
- document type lạ;
- query web quá ngắn/dài;
- duplicate action;
- limit vượt phạm vi.

## 13. Dữ liệu và metric hiện được phục vụ

### 13.1 PostgreSQL numerical truth

Doanh nghiệp thông thường:

- `net_revenue`
- `net_profit`
- `profit_before_tax`
- `total_assets`
- `total_liabilities`

Ngân hàng:

- `net_interest_income`
- `net_fee_and_commission_income`
- `net_profit`
- `profit_before_tax`
- `provision_for_credit_losses`
- `total_assets`
- `total_equity`

### 13.2 Derived metrics trong query layer

- `net_revenue_yoy_growth` cho doanh nghiệp thông thường.
- `net_profit_yoy_growth` cho doanh nghiệp và ngân hàng.
- `net_profit_margin` cho doanh nghiệp thông thường.
- `roa` cho doanh nghiệp và ngân hàng.
- `roe` hiện được expose cho ngân hàng trong query registry.

### 13.3 Derived Metric Engine mở rộng

Module `src/services/derived_metrics.py` có registry/công thức deterministic cho:

- revenue growth;
- profit growth;
- gross margin;
- operating margin;
- net margin;
- ROA;
- ROE;
- debt ratio.

Engine kiểm tra input bắt buộc và mẫu số bằng `0`. Khả năng tính thực tế vẫn phụ thuộc raw facts có được collector cung cấp hay không; có công thức trong engine không đồng nghĩa database hiện đã có đủ input cho mọi công ty.

### 13.4 Qdrant qualitative knowledge

Document type hiện hỗ trợ:

- `company_profile`
- `company_history`
- `management`
- `listing_info`

Luồng retrieval:

```text
query text
  -> BGE-M3 embedding, dimension 1024
  -> filter ticker/document_type
  -> Qdrant
  -> payload text + metadata
```

Qdrant phù hợp với mô hình kinh doanh, hồ sơ, lịch sử, lãnh đạo và niêm yết. Câu hỏi chức danh cụ thể vẫn cần post-filter/rerank theo role để tránh trả toàn bộ ban lãnh đạo.

### 13.5 External research

External Recovery ưu tiên:

1. Báo cáo thường niên, BCTC kiểm toán, công bố doanh nghiệp, hồ sơ sở giao dịch.
2. Cơ sở dữ liệu tài chính đáng tin cậy.
3. Báo chí tài chính.

Mỗi nguồn cần metadata gồm URL, publisher/domain, loại nguồn, ngày công bố nếu có, thời điểm truy xuất và confidence. Web evidence không ghi đè numerical truth.

## 14. Evidence Fusion

Module: `src/services/evidence_fusion.py`.

Output `EvidencePackage` gồm:

- `facts`
- `interpretations`
- `confidence`
- `limitations`
- conflicts có cấu trúc

Các rule chính:

- Không dùng LLM để sửa số.
- Cùng metric/company/period nhưng khác value phải tạo conflict.
- Ưu tiên nguồn theo trust model, nhưng vẫn giữ dấu vết mâu thuẫn.
- Evidence thiếu source/provenance không được nâng thành fact có độ tin cậy cao.

## 15. Financial Reasoning và Interpretation

### 15.1 Financial Reasoning Engine

Module: `src/services/financial_reasoning.py`.

Kết quả phân biệt bắt buộc:

- `FACT`: bằng chứng trực tiếp.
- `INFERENCE`: nhận định suy ra từ fact, phải có evidence refs.
- `UNKNOWN`: không đủ dữ liệu.

Engine không thay đổi evidence và không tạo số mới.

### 15.2 Financial Interpretation Engine

Module: `src/services/financial_interpretation.py`.

Chuyển fact/inference thành signal:

- `GROWTH`
- `PROFITABILITY`
- `EFFICIENCY`
- `LEVERAGE`
- `CASHFLOW`
- `BUSINESS_QUALITY`

Direction:

- `POSITIVE`
- `NEGATIVE`
- `NEUTRAL`
- `UNKNOWN`

Mỗi signal có explanation và evidence references. Signal là diễn giải có kiểm soát, không phải khuyến nghị đầu tư.

## 16. Financial Decision Layer

Module: `src/services/financial_decision_layer.py`.

Lớp này cung cấp contract kết luận riêng cho các câu hỏi phân tích quan trọng và đọc evidence từ nhiều representation:

- `normalized_evidence`
- `compact_observations`
- `derived_metrics`
- raw `observations.data`

### 16.1 Financial health

Rule hiện có:

- Revenue tăng + Profit tăng + Margin không giảm → xu hướng khỏe lên.
- Revenue tăng + Profit giảm → tăng trưởng chưa chuyển hóa thành hiệu quả lợi nhuận.
- Có tín hiệu tốt và xấu → cải thiện nhưng chưa đồng nhất.
- Chỉ trả UNKNOWN khi thiếu revenue, profit hoặc không có chuỗi thời gian đủ dùng.

### 16.2 Company comparison

Framework chất lượng lợi nhuận:

- Growth quality: 30%.
- Profitability: 30%.
- Stability: 25%.
- Risk: 15%.

Kết luận không được dựa trên một metric duy nhất. Nếu thiếu operating margin, cashflow, business-cycle evidence hoặc leverage, report phải nêu limitation.

### 16.3 Risk intent

Risk được tách ở decision layer thành:

- `FINANCIAL_STATEMENT_RISK`: dùng financial database và derived metrics.
- `RECENT_EVENT_RISK`: trigger bởi “gần đây”, “hiện tại”, “mới nhất”, “tin tức”, “sự kiện” và ưu tiên web.

Nếu web không khả dụng, trạng thái nghiệp vụ phải là UNKNOWN với lời giải thích thiếu nguồn hiện tại, không phải FAILED và không lộ `TOOL_UNAVAILABLE`.

### 16.4 Valuation

Nếu thiếu price, P/E, P/B, EPS hoặc market cap, FinSight trả UNKNOWN và liệt kê dữ liệu cần bổ sung. Hệ thống không tự đoán cổ phiếu “rẻ” hay “đắt”.

## 17. Benchmark Engine

Module: `src/services/benchmark_engine.py`.

Benchmark type:

- `HISTORICAL`
- `PEER`
- `INDUSTRY`

Position:

- `ABOVE`
- `BELOW`
- `AVERAGE`
- `UNKNOWN`

Nếu không có historical/peer/industry benchmark có nguồn, kết quả bắt buộc là UNKNOWN. Registry không tự chọn peer company và không tự tạo sector median.

## 18. Risk Review Engine

Module: `src/services/risk_review.py`.

Risk type:

- `FINANCIAL`
- `EARNINGS_QUALITY`
- `GROWTH`
- `BUSINESS`
- `LEVERAGE`
- `LIQUIDITY`
- `VALUATION`

Ví dụ rule:

- Debt/liability tăng nhanh hơn asset → leverage risk.
- Profit tăng nhưng cashflow giảm → earnings-quality risk.
- Revenue growth chậm lại → growth risk.
- Company thấp hơn benchmark có nguồn → relative weakness.

Mọi risk phải có evidence refs. Thiếu evidence thì ghi UNKNOWN; không dự đoán phá sản, không đưa price target hoặc khuyến nghị mua/bán.

## 19. Analyst Report Generator

Module: `src/services/analyst_report.py`.

Output có cấu trúc:

- title;
- executive summary;
- financial assessment;
- strengths;
- weaknesses;
- risks;
- benchmark summary;
- unknowns;
- confidence;
- evidence coverage.

Report chỉ chuyển các analysis objects thành nội dung dễ đọc. LLM nếu được dùng chỉ làm nhiệm vụ viết, tổng hợp và sắp xếp; không được thêm metric hoặc evidence mới.

## 20. Response contract

Response phân tích mong muốn:

```text
Kết luận
Phân tích
Bằng chứng
Điểm tích cực
Rủi ro
Hạn chế dữ liệu
Confidence
```

Trạng thái nghiệp vụ:

- `OK`: đủ evidence cho phạm vi kết luận.
- `PARTIAL`: trả lời được một phần nhưng còn evidence thiếu/lỗi.
- `UNKNOWN`: chưa đủ evidence để kết luận an toàn.
- `NEEDS_CLARIFICATION`: thiếu ticker, năm, metric hoặc phạm vi bắt buộc.
- `FAILED`: chỉ dành cho lỗi không thể tạo response an toàn; không nên dùng cho việc đơn thuần thiếu dữ liệu.

Response public không được chứa:

- `TOOL_UNAVAILABLE`;
- stack trace;
- tên exception/driver;
- database URL;
- API key;
- prompt nội bộ;
- chain-of-thought.

## 21. Budget, retry và an toàn

Budget hiện được cấu hình qua:

```dotenv
MAX_AGENT_ITERATIONS=10
MAX_LLM_CALLS_PER_REQUEST=5
MAX_TOOL_CALLS_PER_REQUEST=10
MAX_REPLANS_PER_REQUEST=3
MAX_WEB_SEARCH_CALLS_PER_REQUEST=4
MAX_WEB_SOURCES_PER_REQUEST=10
MAX_TOTAL_EXTERNAL_CONTENT=12000
```

Các giới hạn này chặn vòng lặp vô hạn, chi phí LLM/web và context phình lớn. External recovery có timeout/retry/source ranking; synthesis có validation và deterministic fallback.

Safety rules:

- Không arbitrary SQL.
- Không database write từ agent.
- Không order execution hoặc autonomous trading.
- Không tự duyệt web ngoài controlled tool.
- Không khuyến nghị mua/bán trực tiếp.
- Không cam kết lợi nhuận hoặc dự đoán chắc chắn.
- Nội dung web/Qdrant là untrusted evidence, không phải instruction.

## 22. Trace và observability

Agent ghi trace sự kiện thay vì chain-of-thought. Các event quan trọng gồm:

- fast path hoặc LangGraph được chọn;
- LLM plan/re-plan được dùng hay fallback;
- tool được gọi và observation nhận được;
- web source được chấp nhận hoặc loại;
- source conflict;
- critic pass/fail;
- synthesis bị từ chối hoặc fallback.

Trace giúp debug request mà không lộ suy luận riêng tư. Hiện trace chủ yếu ở phạm vi request; production vẫn cần metrics, centralized logs, distributed tracing, dashboard và alert.

## 23. Evaluation Framework

### 23.1 Deterministic evaluator

Module: `src/services/evaluation_framework.py`.

Đánh giá:

- correctness;
- evidence grounding;
- hallucination;
- completeness;
- safety;
- module quality.

Evaluator không dùng LLM và không đánh giá văn phong. Nó kiểm tra evidence reference, evidence coverage và forbidden claims.

Dataset `tests/evaluation_cases.json` có các nhóm fact, trend, comparison, risk, external research và missing data.

CLI:

```powershell
.venv\Scripts\python.exe evaluate_agent.py
```

### 23.2 Golden regression

Các thành phần:

- `src/services/regression_runner.py`
- `tests/golden_dataset.json`
- `evaluation_config.yaml`
- `run_regression.py`
- `regression_evaluation.md`

Golden dataset hiện được thiết kế với 100 case thuộc các nhóm fact, trend, comparison, financial health, profitability, risk, missing data và adversarial.

CLI:

```powershell
.venv\Scripts\python.exe run_regression.py
```

Framework hiện chấm response đã có; để trở thành end-to-end production gate, CI cần khởi chạy agent với fixture/test database ổn định rồi đưa response thật vào evaluator.

## 24. Ví dụ execution trace nghiệp vụ

Câu hỏi:

```text
FPT đang khỏe lên hay yếu đi trong giai đoạn 2021-2024?
```

Trace kỳ vọng:

```text
1. Supervisor chọn LANGGRAPH_AGENT.
2. Question Understanding:
   - intent = FINANCIAL_HEALTH_ANALYSIS
   - company = FPT
   - period = 2021..2024
   - analysis = growth, profitability, efficiency
3. Evidence Planning yêu cầu:
   - revenue/profit time series
   - revenue/profit growth
   - net margin
   - assets/liabilities nếu có
   - business driver nếu cần giải thích
4. Availability Resolver:
   - raw metrics -> PostgreSQL
   - growth/margin -> Calculation Engine
   - business driver -> Qdrant
5. Planner tạo TIME_SERIES/COMPANY_KNOWLEDGE actions.
6. Validator chặn ticker, year hoặc metric không grounded.
7. Executor gọi tool; observe chuẩn hóa result và provenance.
8. Critic kiểm tra đủ revenue/profit/time series.
9. Evidence Fusion tạo package và conflict nếu cần.
10. Reasoning tạo FACT/INFERENCE/UNKNOWN có refs.
11. Interpretation tạo growth/profitability signals.
12. Decision layer kết luận khỏe lên, yếu đi hoặc cải thiện chưa đồng nhất.
13. Report/synthesis diễn đạt; validator chặn claim không grounded.
14. Composer trả kết luận trước, sau đó evidence, risk, limitation và confidence.
```

## 25. Những gì agent hiện có thể làm

- Tra cứu một chỉ tiêu tài chính theo mã và năm.
- Lấy chuỗi thời gian và tính tăng trưởng khi có đủ năm.
- So sánh nhiều công ty theo metric hỗ trợ.
- Xếp hạng doanh nghiệp/ngân hàng theo sector và metric phù hợp.
- Đánh giá một mã bằng bộ metric hiện có.
- Phân tích sức khỏe tài chính theo nhiều evidence thay vì một số duy nhất.
- Phân tích chất lượng lợi nhuận có growth, margin, stability và risk framework.
- Tra cứu mô hình kinh doanh, hồ sơ, lịch sử, lãnh đạo và niêm yết từ Qdrant.
- Tìm sự kiện/rủi ro gần đây qua nguồn web nếu cấu hình và network hoạt động.
- Tính derived metrics deterministic.
- Nêu rõ dữ liệu thiếu và từ chối kết luận định giá khi thiếu inputs.
- Tạo báo cáo có evidence references, confidence và limitations.
- Tự fallback khi LLM lỗi mà không làm mất toàn bộ khả năng tra cứu deterministic.

## 26. Giới hạn hiện tại

### 26.1 Giới hạn dữ liệu

- Financial truth mới bao phủ một tập metric tương đối hẹp.
- Cashflow chưa được phục vụ nhất quán cho toàn universe.
- Thiếu price, market cap, EPS, P/E, P/B và valuation history để đánh giá định giá.
- ROE doanh nghiệp thường chưa đồng nhất với registry của ngân hàng.
- Peer/industry median chưa được materialize và version hóa đầy đủ.
- Qualitative documents có thể thiếu đúng role/year hoặc metadata cập nhật.
- External news phụ thuộc Tavily, network, timeout và chất lượng kết quả tìm kiếm.

### 26.2 Giới hạn reasoning

- Một phần intent/concept mapping vẫn dựa trên từ khóa và ontology cố định.
- Planner có tính động nhưng chỉ được chọn action/metric đã đăng ký.
- Reasoning chủ yếu là rule-based có cấu trúc; chưa có model tài chính sâu theo ngành.
- Không có causal model đủ mạnh để khẳng định “tại sao” nếu chỉ có tương quan số liệu.
- Benchmark không tự tạo peer group; cần dataset hoặc quy tắc peer được quản trị.
- Câu hỏi ghép nhiều ý vẫn cần decomposition contract chặt và test rộng hơn.

### 26.3 Giới hạn autonomy

- Không tự học trực tuyến từ hội thoại.
- Không tự thêm tool, metric, schema hoặc nguồn dữ liệu.
- Không tự chạy tác vụ dài hạn/background research sau khi trả lời.
- Không có durable checkpoint để resume một research job sau restart.
- Không có human approval workflow cho hành động có tác động bên ngoài.
- Không thực hiện giao dịch hay thay đổi dữ liệu nguồn.

### 26.4 Giới hạn vận hành

- Rate limiting chưa dùng shared store.
- Health/ready endpoint chưa chứng minh toàn bộ dependency đều usable.
- Native local và Docker dùng hostname khác nhau; cấu hình sai dễ tạo `ECONNREFUSED`.
- Proxy hệ điều hành có thể làm Tavily/LLM timeout dù key hợp lệ.
- API key sai/hết hạn khiến LLM fallback và response có thể mang trạng thái PARTIAL.
- Timeout đồng bộ dài có thể làm UI cảm giác lag.
- Một số chuỗi tiếng Việt trong source cần được kiểm tra UTF-8 để tránh mojibake.
- Lịch sử chat trong NestJS chưa phải agent memory có cấu trúc.

## 27. Vì sao đây chưa phải “agent thực sự” hoàn chỉnh

Không có một định nghĩa duy nhất cho “agent thực sự”. Theo tiêu chuẩn production financial agent, FinSight đã có bốn thuộc tính agentic quan trọng: goal understanding, planning, tool use và feedback/re-plan. Tuy nhiên nó còn thiếu các năng lực sau để đạt mức trưởng thành cao:

1. **Coverage:** đủ dữ liệu để planner có lựa chọn thực tế, không chỉ lập kế hoạch rồi trả UNKNOWN.
2. **Dynamic decomposition:** chia câu hỏi mới thành sub-goal độc lập và theo dõi quan hệ phụ thuộc rõ ràng.
3. **Durable memory:** lưu facts đã xác minh, preference và research state theo phiên nhưng không làm nhiễm numerical truth.
4. **Reliable external research:** search, fetch, parse, deduplicate, rank, cache và cite nguồn ổn định.
5. **Evidence-level provenance:** mọi claim public liên kết được tới metric/company/period/source cụ thể.
6. **Recovery:** circuit breaker, retry theo loại lỗi, timeout riêng từng tool và fallback semantic.
7. **Production evaluation:** end-to-end regression trên test database cố định trước mỗi deploy.
8. **Human oversight:** approval cho báo cáo nhạy cảm hoặc thay đổi cấu hình/data registry.
9. **Learning loop an toàn:** học offline từ feedback/evaluation, review rồi mới release; không tự sửa production dựa trên một cuộc chat.

Thiếu data là một nguyên nhân lớn nhưng không phải nguyên nhân duy nhất. Agent còn cần tool contract tốt, planner đáng tin, evidence validation, memory, observability, evaluation và cơ chế vận hành production.

## 28. Lộ trình cải thiện

### P0 — Ổn định và đúng trước khi deploy

1. Chuẩn hóa cấu hình theo môi trường:
   - `.env.local` cho native;
   - `.env.docker` hoặc Compose interpolation cho container;
   - không dùng `host.docker.internal` trong native process;
   - không dùng `127.0.0.1` để gọi container khác từ trong container.
2. Rotate mọi secret từng bị hiển thị và đảm bảo `.env` không được commit.
3. Thêm dependency readiness cho PostgreSQL, Qdrant, embedding, LLM và web.
4. Sanitize toàn bộ technical code khỏi response public.
5. Sửa/kiểm tra UTF-8 tiếng Việt trong source và snapshot UI.
6. Tách trạng thái `UNKNOWN`, `PARTIAL`, `FAILED` nhất quán từ Python tới NestJS/UI.
7. Thêm regression cho năm thiếu, tool timeout, invalid key, proxy lỗi và multi-intent.

Acceptance criteria P0:

- Fact query có dữ liệu trả HTTP 200 và đúng source.
- Thiếu dữ liệu trả UNKNOWN/PARTIAL, không HTTP 503.
- Không xuất hiện `TOOL_UNAVAILABLE`, stack trace hoặc secret trên UI.
- LLM/web/Qdrant lỗi không làm hỏng PostgreSQL fact path.
- Bộ unit/regression test chạy ổn định trên Windows và CI.

### P1 — Mở rộng năng lực nghiên cứu

1. Bổ sung cashflow statements và quality-of-earnings metrics.
2. Bổ sung market data/valuation facts: price, shares, market cap, EPS, P/E, P/B.
3. Xây peer registry và industry benchmark có version/source.
4. Nâng Qdrant retrieval:
   - filter document type bắt buộc;
   - role/year-aware management lookup;
   - reranking;
   - chunk stitching có giới hạn;
   - freshness/version metadata.
5. Nâng external research:
   - query expansion tiếng Việt/tiếng Anh;
   - domain allowlist theo Tier;
   - fetch nội dung gốc;
   - cache theo query/source/date;
   - retry/backoff và circuit breaker;
   - citation URL hiển thị được trên UI.
6. Tách câu ghép thành sub-questions có thứ tự và merge answer theo từng phần.
7. Thêm industry-specific reasoning cho bank, manufacturing, retail và real estate.

Acceptance criteria P1:

- Các câu hỏi health/comparison/risk có evidence coverage đạt ngưỡng quy định.
- Câu định giá trả phân tích khi đủ dữ liệu, UNKNOWN khi thiếu.
- Câu sự kiện gần đây có ít nhất một nguồn hợp lệ hoặc limitation chính xác.
- Câu hỏi ghép 2–3 ý trả đủ từng ý, không dùng context sai.

### P2 — Agent production-grade

1. Durable LangGraph checkpoint và resumable research jobs.
2. Structured conversation memory với entity/period/metric slots và cơ chế reset context.
3. Distributed tracing, latency/cost metrics và dashboard theo node/tool.
4. Shared rate limit, queue, concurrency control và cancellation.
5. Human-in-the-loop cho báo cáo quan trọng và nguồn xung đột.
6. Offline learning loop:
   - thu feedback có consent;
   - phân loại failure;
   - bổ sung golden cases;
   - review ontology/tool mapping;
   - benchmark trước khi release.
7. Planner policy evaluation: tool precision, unnecessary-call rate, re-plan success, token/cost budget.
8. Version hóa schema, prompts, metric registry, source policy và evidence package.

Acceptance criteria P2:

- Có thể resume request dài sau restart.
- Có audit trail từ câu trả lời tới từng evidence/tool/source.
- Có SLO latency/availability và alert theo dependency.
- Mọi release phải vượt quality gate và không tạo regression nghiêm trọng.

## 29. Definition of Done cho Financial Research Agent

FinSight được coi là đạt mức agent nghiên cứu tài chính production khi:

- Nhận câu hỏi tự nhiên mới mà không cần user chọn workflow.
- Tự phân rã mục tiêu thành evidence requirements và tool actions hợp lệ.
- Chọn đúng nguồn theo loại bằng chứng.
- Có thể re-plan khi dữ liệu thiếu hoặc tool lỗi.
- Không tạo số, nguồn hoặc kết luận không có provenance.
- Phân biệt rõ fact, inference, risk và unknown.
- Trả lời đa ý đầy đủ, có thứ tự.
- Cung cấp citation/evidence reference có thể kiểm tra.
- Không lộ lỗi kỹ thuật hoặc bí mật.
- Không đưa lời khuyên giao dịch trái policy.
- Hoạt động ổn định khi một dependency bị lỗi.
- Có end-to-end evaluation, regression gate, monitoring và audit.
- Có human oversight và quy trình cập nhật ontology/data/tool an toàn.

## 30. Cấu hình bắt buộc và tùy chọn

Không ghi secret thật trong tài liệu hoặc Git.

Nhóm bắt buộc cho numerical path:

```dotenv
FINANCIAL_DATABASE_URL=<postgresql-url>
FINSIGHT_API_URL=<url-NestJS-goi-FinSight>
```

Nhóm Qdrant:

```dotenv
QDRANT_URL=<qdrant-url>
QDRANT_API_KEY=<secret>
```

BGE-M3 phải tương thích collection vector dimension 1024 và embedding config trong metadata.

Nhóm LLM, có thể tắt để dùng deterministic fallback:

```dotenv
FINSIGHT_ENABLE_LLM=true
OPENAI_API_KEY=<secret>
MODEL_NAME=gpt-4o-mini
LLM_TEMPERATURE=0.2
```

Nhóm web, có thể tắt nếu không cần current-event research:

```dotenv
FINSIGHT_ENABLE_WEB=true
WEB_SEARCH_PROVIDER=tavily
TAVILY_API_KEY=<secret>
```

Khi chạy native local:

- PostgreSQL VPS cần SSH tunnel hoạt động và URL trỏ `127.0.0.1:<local-forward-port>`.
- NestJS phải trỏ FinSight về `http://127.0.0.1:6071`.
- Web proxy phải trỏ NestJS về `http://127.0.0.1:8000`.
- `PYTHON_API_URL` cho service `:6060` phải dùng `127.0.0.1`, không dùng hostname Docker.

Khi chạy Compose:

- Service gọi nhau bằng Compose service name.
- Chỉ trình duyệt/host dùng published localhost ports.
- Không dùng giá trị native và Docker lẫn nhau trong cùng một env contract.

## 31. Quy tắc phát triển tiếp theo

- Không thêm node nếu trách nhiệm có thể đặt trong module hiện hữu.
- Mỗi tool/action mới phải có schema, validator, timeout, provenance và unit test.
- Mỗi metric mới phải khai báo raw inputs, sector applicability, formula, unit và zero-denominator policy.
- Mỗi inference/risk rule mới phải nêu evidence tối thiểu và UNKNOWN behavior.
- Mỗi bug production phải tạo regression case trước hoặc cùng patch.
- Không dùng LLM để che lấp thiếu dữ liệu hoặc sửa kết quả tool.
- Không commit `.env`, key, token, raw credential hoặc log chứa secret.
- Không coi một response “hay” là đúng nếu không trace được evidence.

## 32. Kết luận

FinSight hiện đã có nền tảng của một financial research agent: supervisor, schema-driven understanding, evidence planning, multi-tool execution, observation/re-plan, evidence fusion, bounded reasoning, benchmark, risk review, report generation và deterministic evaluation.

Bước quan trọng tiếp theo không phải thêm nhiều node hơn, mà là làm pipeline hiện có đáng tin và nhất quán hơn: mở rộng dữ liệu, chuẩn hóa evidence contract, tăng chất lượng retrieval, củng cố failure recovery, đưa evaluation vào CI và hoàn thiện observability. Khi các tiêu chí này đạt được, FinSight mới chuyển từ một agent prototype có kiểm soát thành một financial research agent production-grade.
