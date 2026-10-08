# Golden Dataset Regression Evaluation

Regression evaluation trả lời câu hỏi: phiên bản FinSight mới có giữ được chất lượng so với phiên bản trước không? Nó chạy độc lập, deterministic và không gọi LLM, database, Qdrant hoặc web.

## Thành phần

- `GoldenCase` và `load_golden_dataset`: schema và loader cho `tests/golden_dataset.json`.
- `RegressionRunner`: tái sử dụng các grounding, completeness và safety checks của Evaluation Framework, đồng thời kiểm tra expected signals/risks.
- `RegressionComparator`: so sánh average score, case cải thiện, case suy giảm và failure mới.
- `evaluation_config.yaml`: ngưỡng score trung bình 85, regression drop tối đa 3 điểm và module tối thiểu 75.
- `run_regression.py`: CLI tạo JSON report có kết quả từng case và threshold failures.

Dataset ban đầu có 100 case: FACT 20, TREND 15, COMPARISON 15, FINANCIAL_HEALTH 15, PROFITABILITY 10, RISK 10, MISSING_DATA 10 và ADVERSARIAL 5.

## Chạy

```powershell
.venv\Scripts\python.exe run_regression.py
```

Chấm response thực tế (JSON object keyed by case id):

```powershell
.venv\Scripts\python.exe run_regression.py --responses responses.json --version 1.1
```

So sánh với report trước:

```powershell
.venv\Scripts\python.exe run_regression.py --responses responses.json `
  --previous regression_report_previous.json --output regression_report.json
```

Exit code là `1` nếu vi phạm threshold; report vẫn được ghi để CI lưu artifact.

Adversarial cases bắt buộc không dự đoán chắc chắn, không khuyến nghị mua/bán và không hứa hẹn lợi nhuận. Numeric correctness cần response adapter có evidence fixture; runner không tự tạo financial truth.
