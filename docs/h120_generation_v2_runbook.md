# H120 Ranker generation v2 — local runbook

Dataset snapshot có thể nằm ở bất kỳ ổ đĩa nào. Thư mục truyền vào phải là
dataset run chứa `dataset/`, `splits/` và các partition parquet tương ứng.

## Phase C

Từ root project, chạy:

```powershell
.\scripts\run_h120_phase_c.ps1 -DatasetRun 'D:\du-lieu\wave_dataset_continuation_h120\runs\<RUN_ID>'
```

Runner dùng đúng protocol frozen: `stock_primitives`, binary H120, W0, inner
fold 2020–2023, R2 với seeds 238–242 và R3 random search. Nó không dùng fold
2024, future holdout, hay output strength để chọn config.

## Phase D

Sau khi Phase C review chọn **một** OOF rank-score artifact hợp lệ (chưa refit),
chạy C0–C2 trên chính artifact đó:

```powershell
.\.venv\Scripts\python.exe .\scripts\run_h120_ranker_calibration.py `
  --ranker-oof 'D:\path\to\oof_ranker_predictions.parquet' `
  --output .\experiments\h120_improvement\E06_generation_v2
```

Artifact sẽ có `calibrated_oof_predictions.parquet`, `calibration_by_fold.csv`
và `manifest.json`. Chọn probability mapping dựa trên Brier, log loss, ECE và
calibration slope/intercept; không ghi nhận đó là gain ranking. Nếu probability
gate fail, giữ `rank_score` cho ranking và đánh dấu probability chưa validated.

Không mở `E10_future_holdout` hoặc refit/deploy chỉ vì runner chạy thành công.
