# FinSight Agent Workflow

## 1. Mục tiêu

FinSight hiện là controlled Financial Research Agent. Hệ thống mở rộng chatbot truy vấn đơn giản thành agent có thể hiểu mục tiêu phân tích, lập kế hoạch nhiều bước, gọi tool, quan sát kết quả, điều chỉnh kế hoạch và tổng hợp kết luận có kiểm chứng.

Agent không phải hệ thống giao dịch tự động và không có cơ chế tự học liên tục.

## 2. Kiến trúc tổng thể

    User/Web UI
      -> NestJS API :8000
      -> FinSight FastAPI :6071
      -> FinSightApplication
           -> Fast deterministic path
           -> LangGraph Financial Research Agent
                -> interpret goal
                -> semantic resolver
                -> structured planner
                -> action validator
                -> tool executor
                -> observation/replanner
                -> critic
                -> grounded synthesis
                -> post-validation
                -> safe compose

Trust model:

    PostgreSQL / Derived Metrics = numerical truth
    Qdrant = internal qualitative knowledge
    Web = external/current context
    LLM = planning and synthesis

## 3. Fast path và Agent path

Fast path dành cho câu hỏi đơn giản:

    Doanh thu FPT năm 2024 là bao nhiêu?
      -> Intent Router
      -> FACT(net_revenue, FPT, 2024)
      -> PostgreSQL
      -> Response Composer

Fast path không gọi LLM, không gọi web và giữ tốc độ nhanh.

Agent path dành cho câu hỏi có phân tích, nhiều metric, nhiều năm, nhiều ticker, dependent reasoning hoặc thông tin hiện tại.

## 4. Các LangGraph node

- route_request: chọn fast path/LangGraph và ghi trace.
- interpret_goal: chuẩn hóa ticker, sector, period, concept và nhu cầu web.
- plan: tạo kế hoạch LLM hoặc deterministic fallback.
- validate_action: kiểm tra action, ticker, metric, sector, năm, limit và budget.
- execute_tool: gọi QueryHarness hoặc ControlledWebResearch.
- observe: lưu kết quả, compact observation và cập nhật evidence.
- decide_next: CONTINUE, REPLAN, COMPLETE, CLARIFY hoặc FAIL.
- critic: kiểm tra observation và trạng thái hoàn thành.
- synthesize: tạo kết luận grounded bằng LLM.
- validate_synthesis: kiểm tra claim; regenerate tối đa một lần rồi fallback.
- compose: tạo response cuối có kết luận, evidence, rủi ro và hạn chế.

Action được phép:

    FACT, TIME_SERIES, COMPARE, RANK,
    EVALUATION, COMPANY_KNOWLEDGE, WEB_SEARCH

## 5. Semantic concept resolver

Các khái niệm tự nhiên được chuyển thành nhóm bằng chứng:

| Khái niệm | Bằng chứng gợi ý |
|---|---|
| Khả năng sinh lời | net_profit, profit growth, margin, ROA/ROE |
| Tăng trưởng | revenue/profit growth và trend |
| Sức khỏe tài chính | growth, profitability, assets, liabilities, efficiency |
| Hiệu quả | ROA, ROE, margin |
| Quy mô | total_assets, absolute profit |
| Hiệu quả so với quy mô | profit, ROA, ROE, total_assets |
| Đòn bẩy | liabilities, assets, equity |
| Ổn định | multi-year consistency |
| Sự kiện hiện tại | controlled web research |

Đây là guidance động, không phải mapping cứng.

## 6. Tool nội bộ

### PostgreSQL / QueryHarness

- FACT: một ticker, metric và năm.
- TIME_SERIES: một ticker, metric và khoảng năm.
- COMPARE: so sánh nhiều ticker.
- RANK: xếp hạng theo metric và sector.
- EVALUATION: lấy bộ chỉ tiêu đánh giá.

### Derived Metric Engine

Tính deterministic tăng trưởng doanh thu, tăng trưởng lợi nhuận, biên lợi nhuận, ROA và ROE. LLM không được tự tính số.

### Qdrant / COMPANY_KNOWLEDGE

Tra cứu hồ sơ doanh nghiệp, mô hình kinh doanh, ban lãnh đạo, niêm yết và lịch sử doanh nghiệp.

    query text
      -> BGE-M3 embedding dimension 1024
      -> filter ticker/document_type
      -> Qdrant query_points
      -> payload text

Qdrant chỉ là qualitative evidence và không được làm numerical truth.

## 7. Controlled Web Research

WEB_SEARCH dùng cho tin tức gần đây, sự kiện doanh nghiệp, công bố chính thức, thay đổi quản trị, regulatory events và bối cảnh thị trường.

Không dùng web cho doanh thu, lợi nhuận hoặc xếp hạng đã có trong PostgreSQL.

Cấu hình:

    FINSIGHT_ENABLE_WEB=true
    WEB_SEARCH_PROVIDER=tavily
    TAVILY_API_KEY=<secret>

Nếu chưa cấu hình, tool trả TOOL_UNAVAILABLE hoặc NO_RESULTS, không làm request crash.

## 8. Chính sách nguồn web

Mỗi nguồn có source_id, title, publisher/domain, URL, publication_date, retrieval_time, summary, source_category, reliability và confidence.

- Tier 1: doanh nghiệp, cơ quan quản lý, sở giao dịch, hồ sơ chính thức.
- Tier 2: báo tài chính uy tín.
- Tier 3: nguồn thứ cấp khác.

Nguồn bị loại nếu thiếu metadata, chất lượng thấp, trùng URL, không liên quan hoặc quá cũ.

Nguồn mâu thuẫn được lưu trong source_conflicts; ưu tiên nguồn tin cậy hơn nhưng vẫn công khai khác biệt.

## 9. Observation-driven reasoning

Agent có thể thay đổi kế hoạch theo kết quả:

    RANK BANK net_profit 2024
      -> top_ticker = VCB
      -> FACT VCB roa 2024
      -> FACT VCB roe 2024
      -> FACT VCB total_assets 2024
      -> kết luận hiệu quả so với quy mô

Unsupported, missing hoặc zero denominator không bị chuyển thành số 0. Agent chọn đường thay thế nếu có hoặc trả PARTIAL.

## 10. LLM planner và synthesis

LLM dùng cho lập kế hoạch, re-plan và synthesis.

    FINSIGHT_ENABLE_LLM=true
    OPENAI_API_KEY=<valid OpenAI key>
    MODEL_NAME=gpt-4o-mini

LLM không được tự thực thi SQL, gọi URL tùy ý, tạo ticker/metric/year chưa grounding, tạo số tài chính hoặc ghi database.

LLM timeout, rate limit, JSON/schema sai hoặc claim không grounded đều được fallback an toàn.

## 11. Claim types và output

Claim types:

- NUMERICAL_FACT: PostgreSQL/Derived.
- QUALITATIVE_FACT: Qdrant.
- EXTERNAL_FACT: web có nguồn.
- INFERENCE: suy luận, phải gắn nhãn.
- LIMITATION: giới hạn dữ liệu.

Cấu trúc output:

    Kết luận
    Bằng chứng và xu hướng
    Bối cảnh bên ngoài
    Điểm cần lưu ý / Rủi ro
    Hạn chế

## 12. Numerical truth isolation

Nếu web đưa số khác PostgreSQL:

- Dùng PostgreSQL cho financial fact nội bộ.
- Web chỉ là external context nếu có nguồn.
- Không ghi số web vào PostgreSQL.
- Không trộn web number vào numerical evidence nội bộ.

## 13. Hard budgets

    MAX_AGENT_ITERATIONS=10
    MAX_LLM_CALLS_PER_REQUEST=5
    MAX_TOOL_CALLS_PER_REQUEST=10
    MAX_REPLANS_PER_REQUEST=3
    MAX_WEB_SEARCH_CALLS_PER_REQUEST=4
    MAX_WEB_SOURCES_PER_REQUEST=10
    MAX_TOTAL_EXTERNAL_CONTENT=12000

Budget chặn vòng lặp, LLM cost, tool call, re-plan, web search và external content.

## 14. Failure handling

Được xử lý an toàn:

- LLM timeout/rate limit/empty response/invalid JSON.
- Planner hoặc synthesis malformed.
- PostgreSQL, Qdrant hoặc web unavailable.
- Metric unsupported, missing hoặc zero denominator.
- Duplicate action.
- Ticker/year không grounding.
- Chạm iteration/tool/replan/web budget.

Exception public chỉ giữ tên loại lỗi, không giữ password, connection string, API key hoặc prompt.

## 15. Trạng thái response

- OK: đủ evidence.
- PARTIAL: một phần tool/evidence lỗi hoặc thiếu.
- FAILED: không có evidence đủ an toàn.
- NEEDS_CLARIFICATION: thiếu thông tin bắt buộc.

## 16. Trace

Các event chính:

    FAST_PATH_USED
    LANGGRAPH_USED
    LLM_PLAN_USED
    LLM_REPLAN_USED
    TOOL_EXECUTED
    OBSERVATION_RECEIVED
    WEB_SEARCH_USED
    WEB_SOURCE_ACCEPTED
    WEB_SOURCE_REJECTED
    SOURCE_CONFLICT
    LLM_SYNTHESIS_USED
    SYNTHESIS_REJECTED
    DETERMINISTIC_FALLBACK
    CRITIC_PASS
    CRITIC_FAIL

Trace chỉ mô tả sự kiện, không chứa chain-of-thought.

## 17. Bảo mật và phạm vi

Agent không hỗ trợ arbitrary SQL, database write, order execution, autonomous trading, autonomous browser, nghiên cứu vô hạn, tự sửa metric mapping hoặc tự học lâu dài.

Web và Qdrant content được xem là untrusted data. Prompt injection không được thực thi.

## 18. Local và Docker

Local:

    SSH tunnel database :5433
    Python Data API :6060 (tùy chọn)
    FinSight API :6071
    NestJS API :8000
    Next.js web :3001

FinSight local:

    .venv\\Scripts\\python.exe -m uvicorn src.finsight_api:app --host 127.0.0.1 --port 6071 --env-file .env

Docker:

    docker compose up -d --build --force-recreate finsight_api api web

Database cùng Docker network dùng hostname service database, ví dụ db:5432.

## 19. Ví dụ câu hỏi

Fast path:

- Doanh thu FPT năm 2024 là bao nhiêu?
- LNST MBB năm 2024 là bao nhiêu?
- Top 5 ngân hàng theo tổng tài sản năm 2024?

Agent semantic:

- Phân tích khả năng sinh lời của MBB từ 2020 đến 2024.
- Phân tích sức khỏe tài chính FPT trong 5 năm gần nhất.
- FPT đang khỏe lên hay yếu đi trong 5 năm gần đây?

Dependent:

- Tìm ngân hàng có lợi nhuận cao nhất năm 2024 rồi đánh giá ngân hàng đó có hiệu quả hay chỉ có quy mô lớn.

Web/hybrid:

- FPT gần đây có sự kiện nào đáng chú ý có thể ảnh hưởng hoạt động kinh doanh?
- Kết hợp tình hình tài chính FPT 5 năm gần đây và thông tin mới nhất để đánh giá rủi ro.

## 20. Khả năng và giới hạn

Agent làm được:

- FACT, TIME_SERIES, COMPARE, RANK, EVALUATION.
- Phân tích nhiều metric/nhiều năm.
- Hiểu analytical concept.
- Dependent reasoning và observation-driven re-plan.
- Qdrant qualitative retrieval.
- Controlled web research.
- Grounded synthesis và safe fallback.

Agent chưa làm:

- Tự học liên tục.
- Tự thay đổi schema hoặc mapping.
- Tự bổ sung dữ liệu thiếu.
- Tự giao dịch.
- Nghiên cứu vô hạn.
- Thay thế chuyên gia đầu tư.

Mọi mở rộng phải giữ nguyên nguyên tắc: PostgreSQL là numerical truth, Derived Engine tính deterministic, Qdrant là qualitative evidence, web có source policy/budget và LLM chỉ lập kế hoạch/tổng hợp.

