# FinSight Evaluation Framework

`src/services/evaluation_framework.py` là bộ chấm điểm deterministic, chạy độc lập với pipeline agent. Framework không gọi LLM, database, Qdrant hoặc web và không đánh giá văn phong.

## Thành phần

- `EvaluationCase`: schema dataset với category, intent, evidence bắt buộc, claim cấm và hành vi kỳ vọng.
- `EvaluationRunner`: chấm một response hoặc cả suite.
- `GroundingChecker`: FACT/INFERENCE có số liệu hoặc nhãn phải có `[Evidence: ...]`; thiếu reference bị đánh dấu `HALLUCINATION`.
- `EvidenceCoverageChecker`: tính completeness theo tỷ lệ required evidence xuất hiện trong response.
- `ForbiddenClaimDetector`: chặn mua/bán, khuyến nghị đầu tư, giá mục tiêu và cam kết lợi nhuận.
- `EvaluationReport`: tổng điểm, case lỗi, nhóm vấn đề phổ biến và điểm theo module (có thể bổ sung khi tích hợp telemetry).

## Chạy

Dataset mẫu có 20 case tại `tests/evaluation_cases.json`. Có thể chấm baseline (response rỗng):

```powershell
.venv\Scripts\python.exe evaluate_agent.py
```

Để chấm response thực tế, tạo JSON object keyed by case id rồi chạy:

```powershell
.venv\Scripts\python.exe evaluate_agent.py --responses responses.json --output evaluation_report.json
```

CLI in summary và ghi đầy đủ `results` vào report output. Những điểm số là 0–100; case chỉ pass khi đạt tối thiểu 80, không có lỗi grounding hoặc safety.

## Giới hạn có chủ ý

Không có expected numerical values trong `EvaluationCase`, vì vậy framework không tự xác minh con số đúng/sai theo thị trường. Nó xác minh phạm vi, traceability và coverage. Muốn kiểm tra numerical correctness, thêm evidence fixture có source vào response adapter hoặc một validator dữ liệu riêng; tuyệt đối không để evaluator tự tạo financial truth.
