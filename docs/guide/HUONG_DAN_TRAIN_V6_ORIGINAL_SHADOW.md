# Hướng dẫn chạy Wave V6

## 1. Đồng bộ dữ liệu sạch

```powershell
.venv\Scripts\python.exe scripts\wave_v6\v6_data_adapter.py sync --start 2015-01-01 --end 2026-08-21 --icb-level 2 --price-policy adjusted --price-value-multiplier 1000 --force
```

### Dữ liệu local `data/vnstock`

Không dùng trực tiếp layout `daily/` hoặc `daily_full_vci/` để train V6. Tạo một
snapshot riêng từ nguồn `daily/` (không sửa dữ liệu gốc):

```powershell
.venv\Scripts\python.exe scripts\wave_v6\prepare_local_snapshot_v6.py --source-dir data\vnstock\daily --reference-dir data\vnstock\reference --output-dir data\vnstock\v6_snapshot --icb-level 2
```

Snapshot local có thể cũ so với ngày hiện tại, vì vậy chỉ dùng `--allow-stale-cache`
cho kiểm thử/research; không promote artifact đó lên production.

Nếu chưa xác nhận nguồn trả giá adjusted hay raw, dùng đúng policy thực tế. Không ghi `adjusted` chỉ để qua validation.
`price-value-multiplier=1000` vì snapshot vnstock hiện tại ghi giá cổ phiếu theo nghìn đồng
(ví dụ FPT `100.0` tương ứng khoảng 100.000 VND). Tham số này chỉ dùng để tính
thanh khoản `close * volume`, không đổi return hay indicator.

Không train strict khi thiếu ba file audit `snapshot_manifest.json`, `industry_map.csv`
và `symbols.csv`. Có thể dùng `--allow-stale-cache` để debug dữ liệu legacy, nhưng khi đó
sector feature bị bỏ chứ không được giả lập bằng một ngành `UNKNOWN`.

## 2. Train

```powershell
.venv\Scripts\python.exe scripts\wave_v6\train_v6_original_shadow.py --trials 15
```

Với snapshot local, truyền rõ từng đường dẫn và lưu artifact vào thư mục ignore:

```powershell
.venv\Scripts\python.exe scripts\wave_v6\train_v6_original_shadow.py --allow-stale-cache --trials 3 --data-dir data\vnstock\v6_snapshot --market-path data\vnstock\v6_snapshot\market\VNINDEX.csv --industry-path data\vnstock\v6_snapshot\industry_map.csv --market-cap-path data\vnstock\v6_snapshot\symbols.csv --models-dir models\wave_ignition\wave_v6_local --reports-dir eval\runs\wave_v6_local
```

Có thể thay ngưỡng strong wave:

```powershell
.venv\Scripts\python.exe scripts\wave_v6\train_v6_original_shadow.py --strong-wave-return 0.50 --lead-time-half-life 504 --trials 15
```

`--lead-time-half-life` chỉ giảm dần mức đóng góp của positive xuất hiện quá muộn;
nó **không** cắt label tại 504 phiên.

Optuna chỉ chạy sau khi feature-group ablation đã khóa nhóm feature thắng trên purged
TRAIN folds. `15` trials là mặc định cân bằng; tăng trials không sửa được target/data xấu
và có thể overfit các time folds. Dùng `--trials 3` chỉ để smoke test.

## 3. File quan trọng

Trong `reports_wave_v6/`:

- `ticker_quality.csv`: audit chất lượng từng mã.
- `data_quality_summary.json`: số mã/dòng bị loại và policy thanh khoản.
- `feature_quality.csv`: feature nào giữ/bỏ và lý do.
- `selected_features.csv`: feature thực tế dùng để train.
- `feature_group_ablation.csv`: so sánh paper continuous/binary và các nhóm mở rộng.
- `liquidity_feature_summary.csv`: phân phối các feature liquidity regime trên TRAIN.
- `label_balance_by_year.csv`: tỷ lệ positive theo năm.
- `model_metrics_calibration.csv`: điểm từng model trên calibration.
- `model_metrics_walk_forward.csv`: điểm từng model ở từng fold thời gian.
- `model_metrics_walk_forward_summary.csv`: độ ổn định trung bình qua các fold.
- `model_ensemble_admission.csv`: lý do model được/không được tham gia ensemble và weight.
- `model_metrics_final_holdout.csv`: điểm XGB/LGB/CAT/ensemble trên holdout cuối.
- `final_holdout_raw_predictions.csv`: raw class-1 probability của XGB/LGB/CAT cho từng dòng holdout.
- `prediction_correlation_final_holdout.csv`: Pearson correlation giữa prediction của ba model.
- `top50_portfolio_ranked.csv`: bảng portfolio rank 1-50 sau quality score và diversification.
- `portfolio_ranking_comparison.json`: so sánh cơ cấu Top 50 trước/sau tầng quality.
- `portfolio_ranking_holdout_before_after.csv`: kiểm tra Precision@50, Lift@50 và tỷ lệ +50%/+100% trên holdout.
- `feature_importance_aligned.csv`: importance theo từng model và ensemble.
- `feature_importance_stability_walk_forward.csv`: mean/std/selection-rate của feature qua các fold.
- `probability_reliability_calibration.csv` và `probability_reliability_final_holdout.csv`:
  predicted probability so với tỷ lệ thực tế theo bin.
- `top50_backtest_cohorts.csv`: kết quả Top 50 theo từng cohort thời gian.
- `top50_backtest_by_market_regime.csv`: tỷ lệ đạt +50%/+100% sau 6 tháng/1 năm theo BULL/BEAR/MIXED.
- `top50_strong_wave_candidates.csv`: 50 mã mạnh nhất hiện tại.
- `top50_ranked_1_to_50.csv`: bảng tóm tắt 50 mã, xếp hạng liên tục từ 1 đến 50 theo `p_ensemble`.
- `top50_actionable_entries.csv`: 50 mã ưu tiên thêm chất lượng điểm vào.
- `latest_full_universe_probabilities.csv`: toàn bộ mã đủ điều kiện hiện tại.
- `evaluation_report.json`: cấu hình, split, weights và báo cáo tổng.

`top50_strong_wave_candidates.csv` có:

- `p_xgb_pct`
- `p_lgb_pct`
- `p_cat_pct`
- `p_ensemble_pct`
- `model_agreement`
- `entry_quality` (0-100, không phải xác suất)
- `setup_status` (`EARLY_SETUP`, `BREAKOUT`, `TRENDING`, `OVEREXTENDED`, `WEAK_SETUP`)
- `actionable_score` và `actionable_rank`

## 4. Target V6

Không dùng horizon cố định.

Từ phiên kế tiếp sau ngày feature:

- Positive chỉ khi giá đạt mức tăng tổng cấu hình (mặc định `+50%`) **và** tại ngày đó
  có xác nhận strong trend 60 phiên: return, slope, R2, drawdown và coverage đều đạt chuẩn.
- Không dùng `-25% trước +50%` làm negative. Label `0` chỉ khi có **structural breakdown**:
  mức giảm sâu (mặc định `-35%`) đồng thời xu hướng 60 phiên giảm đủ bền (return, slope,
  R2 và coverage đều xác nhận). Vì vậy một nhịp giảm/tạo nền thông thường không xóa cơ hội
  positive của base mới.
- Một cú spike/corporate action chạm `+50%` nhưng không có cấu trúc trend không còn tự động
  thành positive.
- Ngày feature đang ở trong/just-after một strong wave đã xác nhận, hoặc quá xa MA/đỉnh cũ,
  không được gán positive sớm. Live inference vẫn không hard-remove mã đó mà hạ `entry_quality`.
- Positive xuất hiện sau thời gian rất dài vẫn giữ label `1`, nhưng dùng relevance decay có
  floor để giảm nhiễu ngẫu nhiên mà không đặt horizon cứng.
- Nếu tới cuối snapshot chưa có event nào => censored, không ép thành `0`.

`label_end_time` là ngày barrier thực sự bị chạm nên vẫn purge train/calibration theo thời gian để tránh leakage.

## 5. Lưu ý khi đọc xác suất

Không lấy xác suất train làm kết quả. Chỉ tin xác suất khi `model_metrics_final_holdout.csv` vẫn cho PR-AUC/lift/calibration tốt. Nếu một model yếu trên calibration, V6 có thể cho weight của model đó về 0 trong ensemble.

Model training dùng event-uniqueness và lead-time relevance để nhiều ngày liên tiếp của cùng
một wave không lấn át dữ liệu. Calibration dùng date-balanced + relevance-weighted Platt,
vì vậy `p_ensemble` là xác suất lịch sử đã hiệu chỉnh theo mức liên quan tới trạng thái tiền
sóng, không phải cách đếm thô tất cả ngày positive. Báo cáo vẫn xuất cả raw và event-weighted
metric để audit.

Không còn hard filter GTGD 2/3 tỷ. Absolute traded value chỉ để audit; model dùng liquidity
percentile tại đúng ngày và các tỷ lệ volume/value 20/60/120. Các chốt zero-volume,
suspension, candle lỗi và corporate action vẫn được giữ chặt.

`p_ensemble` và `entry_quality` trả lời hai câu khác nhau:

- `p_ensemble`: khả năng đi vào confirmed major wave trước structural failure, theo các
  historical episode đã resolve, không có fixed label horizon.
- `entry_quality`: hiện tại còn ở vùng vào hợp lý hay đã quá xa; đây là score kỹ thuật có
  giải thích, **không phải calibrated probability**.

Không hard-remove mã ở đỉnh. Một leader thật vẫn có thể có wave probability cao nhưng được
gắn `OVEREXTENDED` và entry quality thấp để người dùng biết rủi ro timing.

Do các path chưa resolve bị right-censor và loại khỏi classifier, câu `80%` phải được hiểu là
relevance-weighted calibration trên các historical structural-event path đã resolve; không
phải bảo đảm lợi nhuận hay xác suất trọn đời vô điều kiện cho mọi mã.

## 6. Chạy lại prediction correlation mà không train model

Sau khi pipeline đã tạo `final_holdout_raw_predictions.csv`:

```powershell
.venv\Scripts\python.exe scripts\wave_v6\check_prediction_correlation.py
```

Script in Pearson matrix, lưu `prediction_correlation_final_holdout.csv` và cập nhật khóa
`prediction_correlation_final_holdout` trong `evaluation_report.json`.

## Ba bảng Top 50 khác nhau

- `top50_ranked_1_to_50.csv`: xếp theo xác suất major wave; cột `rank` luôn liên tục 1-50.
- `top50_actionable_entries.csv`: xếp theo xác suất sóng kết hợp entry quality; cột `rank` luôn liên tục 1-50 và `wave_rank` chỉ dùng đối chiếu.
- `top50_portfolio_ranked.csv`: xếp theo `final_score = 65% wave probability + 35% quality score - liquidity penalty - pump-risk penalty`, sau đó áp dụng giới hạn tập trung mềm. `liquidity_score < 20` bị trừ 15 điểm; pump-risk bị trừ tối đa 15 điểm nhưng không hard-remove mã.

`market_cap` chỉ được sử dụng khi `data_vnstock/symbols.csv` có coverage đủ. Nếu thiếu,
code ghi rõ `size_basis=LIQUIDITY_PROXY`, dùng percentile GTGD làm proxy và không gọi đó
là vốn hóa thật.
