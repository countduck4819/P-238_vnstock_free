# Analyst Report Generator

`AnalystReportGenerator` chuyển các kết quả phân tích đã có thành báo cáo có cấu trúc, có thể truy vết. Module nằm sau `risk_review` trong LangGraph và ghi kết quả vào `state["analyst_report"]` trước node `synthesize`.

## Nguyên tắc

- Chỉ nhận `FinancialAnalysisResult`, `FinancialSignalResult`, `BenchmarkResult` và `RiskReviewResult`.
- Không gọi PostgreSQL, Qdrant, web hay LLM; không tạo hoặc sửa số liệu.
- Nội dung được gắn nhãn `FACT`, `INTERPRETATION`, `RISK` hoặc `UNKNOWN`.
- Mỗi phát biểu giữ danh sách `evidence_refs`; thiếu bằng chứng được nêu rõ trong `unknowns`.
- Không đưa khuyến nghị mua/bán, giá mục tiêu hoặc dự báo ngoài input.

## Schema đầu ra

```json
{
  "title": "",
  "executive_summary": "",
  "financial_assessment": "",
  "strengths": [],
  "weaknesses": [],
  "risks": [],
  "benchmark_summary": "",
  "unknowns": [],
  "confidence": "HIGH|MEDIUM|LOW",
  "evidence_coverage": "COMPLETE|PARTIAL|LIMITED"
}
```

Input được kiểm tra bằng Pydantic (`extra="forbid"`). Khi LangGraph chưa có đủ bốn analysis objects, node bỏ qua an toàn và ghi trace `MISSING_INPUT`; dữ liệu gốc không bị thay đổi.

## Luồng

```text
risk_review -> analyst_report_generator -> synthesize
```

Các trường hợp full evidence, thiếu dữ liệu, rủi ro cao và input rỗng được kiểm thử trong `tests/test_api/test_analyst_report.py`.
