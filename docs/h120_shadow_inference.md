# H120 frozen shadow inference

Pipeline hiện được đóng gói để chạy shadow inference theo contract H120-only.
Bundle này chưa phải production approval: mọi output đều ghi
`deployment_status=shadow_candidate_requires_new_holdout` và
`trade_authorized=false`.

## Artifact được khóa

- Upstream: `xgboost_continuation_h120`, run `20260823T052814Z`.
- Cascade: `wave_cascade_v4_h120_only`, run `20260823T170819Z`.
- Feature version: `wave_ignition_v2`.
- Ranking: full universe theo `p_cascade_calibrated`, Top-10.
- Không dùng H20 hard gate, V6, H60, breakdown hoặc strength post-ranking.

Bundle manifest nằm tại:

```text
deploy/wave_h120_shadow/bundle_manifest.json
```

Loader kiểm tra SHA-256 và kích thước của toàn bộ runtime payload trước khi
deserialize model. Nó cũng kiểm tra feature schema, cascade head contract và
calibrated threshold.

## Chạy inference

```powershell
python scripts/run_h120_daily_inference.py `
  --features data/features/wave_ignition_snapshot/wave_ignition_v2/runs/<RUN_ID>
```

Có thể khóa ngày bằng `--as-of-date YYYY-MM-DD`. Mỗi run tạo:

```text
predictions/wave_h120_daily/YYYY-MM-DD/predictions.parquet
predictions/wave_h120_daily/YYYY-MM-DD/prediction_manifest.json
```

Manifest ghi bundle checksum, feature manifest, input partition checksum, model
contract, số dòng bị loại, Top-K và output checksum. Chạy lại cùng input phải tạo
`predictions.parquet` có SHA-256 giống hệt.

## Chạy toàn bộ pipeline hằng ngày

Orchestrator nối data sync, clean/audit, feature v2, frozen inference và
manifest tổng hợp:

```powershell
python scripts/run_wave_h120_shadow.py `
  --as-of-date 2026-08-24
```

Mỗi run được lưu dưới `runs/wave_h120_shadow/YYYY-MM-DD/<RUN_ID>/`, gồm:

- `snapshot/`: raw snapshot và source manifest;
- `processed/`: clean OHLCV và audit;
- `features/`: feature store v2 và quality report;
- `predictions/`: Top-10 và prediction manifest;
- `logs/`: log riêng cho sync, clean, feature và inference;
- `orchestration_manifest.json`: trạng thái toàn bộ run.

`--skip-sync` chỉ dùng cho replay một snapshot đã có manifest hợp lệ. Lock file
ngăn hai run chạy đồng thời; `--retries` cho phép retry từng bước trước khi
đánh dấu run thất bại.

Health check cho scheduler/monitoring:

```powershell
python scripts/check_wave_h120_shadow.py `
  --max-age-hours 30
```

Health check chỉ trả trạng thái healthy khi run gần nhất thành công, có đúng
Top-10 và vẫn giữ `trade_authorized=false`.

## Snapshot date versus market as-of date

`--snapshot-date` is the date on which data were downloaded. `--as-of-date`
is the requested provider cutoff and defaults to the snapshot date. The
orchestrator resolves the effective `as_of_date` from the last VNINDEX bar in
the verified snapshot before feature building or inference. This lets a Sunday
download be recorded as `snapshot_date=2026-08-23` while the model correctly
scores Friday `as_of_date=2026-08-21`.

The pipeline fails when market data are more than four calendar days behind
the requested cutoff (override only with `--max-staleness-days` after
investigation). A failed new run never overwrites a verified artifact; the API
serves the newest successful, checksum-verified run instead.

## Daily scheduler

When `python_data/server.py` is running, H120 shadow sync → audit → features
→ frozen inference runs on weekdays at `18:30` Asia/Ho_Chi_Minh. It is enabled
by default. Deployment settings:

```text
WAVE_H120_SHADOW_ENABLED=1
WAVE_H120_SHADOW_TIME=18:30
```

Set `WAVE_H120_SHADOW_ENABLED=0` to disable it. The scheduler retains the last
verified snapshot when the provider or a quality gate fails. It remains
advisory-only and records `trade_authorized=false`.

The sync is throttled to 150 per-symbol requests per minute, below the Bronze
provider limit of 180 requests per minute. Do not raise this limit unless the
provider quota changes; a rate-limited run remains failed and is never served.
Daily scoring also pins the frozen champion universe from
`data/vnstock/v6_snapshot/symbols.csv`; newly listed symbols are observed only
after an explicit universe-contract review, never silently added to demo output.

## API output

Python service expose output shadow đã verify ở dạng read-only:

```text
GET /api/wave-h120/latest?limit=10
GET /api/wave-h120/latest?date=YYYY-MM-DD&limit=10
GET /api/wave-h120/<SYMBOL>?date=YYYY-MM-DD
```

Endpoint kiểm tra trạng thái orchestration, kích thước và SHA-256 của output
trước khi trả dữ liệu. Mọi response đều ghi
`deployment_status` và `trade_authorized: false`; endpoint chỉ phục vụ hiển
thị/monitoring, không phục vụ đặt lệnh.

For product display, use `continuation_probability_h120` only. The response
includes the effective market date, download snapshot date, a fixed 120-session
horizon, and explicit advisory-only metadata; it is not a trade instruction.

## Điều kiện chuyển sang production

Không đổi bundle này thành `production_approved` bằng thao tác thủ công. Chỉ tạo
production promotion record sau khi candidate vượt calibration, Top-K và
cost-aware backtest trên một holdout tương lai chưa từng mở. Final test v3 cũ
không được tái sử dụng.
