# Kế hoạch cải thiện pipeline H120

> Trạng thái: Proposed — chưa phê duyệt production  
> Ngày lập: 2026-08-24  
> Phạm vi: giữ horizon H120; cải thiện chất lượng xếp hạng Top-10, calibration và độ tin cậy thống kê  
> Champion đang đóng băng: `xgboost_continuation_h120/20260823T052814Z` + `wave_cascade_v4_h120_only/20260823T170819Z`

## 1. Quyết định và mục tiêu

Giữ H120 làm hướng chính. Model H120 hiện tại tiếp tục là **frozen champion** để shadow và làm mốc so sánh; không sửa artifact đã khóa và không đổi `trade_authorized=false`.

Không bắt đầu bằng grid search toàn bộ hyperparameter. Thứ tự ưu tiên là:

1. sửa tính đúng đắn của label weight và evaluation;
2. tách bài toán xếp hạng cổ phiếu khỏi bài toán xác suất/regime;
3. thử nghiệm feature theo giả thuyết có kiểm soát;
4. chỉ tuning sau khi metric chính phản ánh đúng Top-10 mỗi ngày;
5. xác nhận trên future holdout chưa từng mở trước khi promotion.

### 1.1. Mục tiêu chính

- Tăng `Precision@10` trung bình theo ngày và `MAP@10` trên walk-forward OOF.
- Không còn fold mà Top-10 lift thấp hơn hoặc xấp xỉ 1 một cách có ý nghĩa thống kê.
- Xác suất H120 được calibration ổn định theo thời gian và market regime.
- Mọi cải thiện phải có paired date-block confidence interval, không kết luận từ một point estimate.
- Candidate cuối cùng phải chạy được trong shadow pipeline hiện tại mà không thay đổi contract H120.

### 1.2. Không thuộc phạm vi

- Không khôi phục H20, H60, V6 trend hoặc breakdown làm hard gate.
- Không dùng lại final test v3 để chọn feature, model hoặc hyperparameter.
- Không tự động cấp quyền giao dịch cho bất kỳ challenger nào.
- Không thay horizon 120 phiên. Các biến thể label, nếu thử, chỉ thay cách định nghĩa hurdle/utility và phải được ghi version riêng.

## 2. Baseline và bằng chứng xuất phát

Các con số dưới đây là mốc cần được tái lập trước khi thay đổi pipeline.

| Hạng mục | Baseline/quan sát hiện tại | Ý nghĩa |
|---|---:|---|
| OOF average precision | `0.228188` | Cao hơn base rate `0.169851`, nhưng chưa phản ánh trực tiếp Top-10 mỗi ngày |
| OOF daily Top-10 precision | khoảng `0.2823` | Metric gần nhất với cách dùng production |
| Validation positive rate | `4.74%` đến `24.44%` | Nhãn thay đổi rất mạnh theo năm/regime |
| Fold 2023 | AP `0.3350`, Top-10 `0.1808`, base `0.2444` | AP tốt nhưng ranking ở tail kém hơn chọn ngẫu nhiên theo base rate |
| Calibration fold 2022 | mean prediction `23.97%`, actual `4.74%` | Over-calibration nghiêm trọng |
| Final frame đã mở | mean prediction `20.48%`, actual `6.23%` | Chỉ dùng làm postmortem, không dùng để chọn model |
| Feature-ready rate | `51.4%` | Có nguy cơ selection bias dù các dòng ready sạch về mặt cơ học |
| Label sampling | mỗi 5 phiên cho horizon 120 | Các nhãn lân cận overlap khoảng 115/120 phiên |
| Effective validation dates | khoảng 25–27 ngày/fold | Không được coi hàng chục nghìn row là độc lập |
| Model training cutoff | `2024-07-26` | Model đang stale so với dữ liệu shadow 2026 |

### 2.1. Kết quả discovery đã có

Các kết quả này chỉ dùng để chọn hướng nghiên cứu, **không phải bằng chứng promotion**, vì được phát hiện trên OOF hiện có.

| Candidate discovery | Daily Top-10 | Ghi chú |
|---|---:|---|
| Classifier 83 feature hiện tại | khoảng `28.23%` | Baseline |
| Classifier với 43 stock primitives | khoảng `35.38%` | Paired delta `+7.15` điểm %, 95% CI `[+4.31, +10.08]` |
| Stock-only XGBRanker `rank:pairwise` | khoảng `36.92%` | Cải thiện 4/5 fold; worst-fold lift khoảng `1.25` |

Giả thuyết chính cần kiểm định độc lập: feature thị trường/ngành giúp ước lượng prevalence và probability, nhưng làm nhiễu thứ tự cổ phiếu trong cùng ngày.

## 3. Nguyên tắc thí nghiệm

1. **Causal only:** mọi feature, weight, label threshold và calibrator chỉ được fit từ dữ liệu có sẵn tại cutoff của fold.
2. **Một thay đổi chính mỗi experiment:** không thay đồng thời label, feature và model rồi gán nguyên nhân cho kết quả.
3. **Group theo ngày:** ranking, bootstrap và paired comparison phải giữ toàn bộ cross-section của một ngày trong cùng cluster.
4. **Không tái sử dụng final test:** `eval/runs/wave_cascade_prod_v3_final_test` chỉ là postmortem.
5. **Manifest bắt buộc:** mọi run lưu config, git commit, input checksum, feature list, fold boundaries, seed và output checksum.
6. **Không chọn bằng mean đơn lẻ:** luôn báo worst fold, dispersion và confidence interval.
7. **Ranking và calibration là hai mục tiêu khác nhau:** calibrator không được dùng để chứng minh ranking tốt hơn nếu phép biến đổi vẫn đơn điệu.

## 4. Metric contract mới

### 4.1. Metric ưu tiên

Thứ tự dùng để chọn candidate:

1. `daily_precision_at_10_mean`;
2. `MAP@10` group theo ngày;
3. `NDCG@10` group theo ngày;
4. worst-fold `lift@10`;
5. AP lift so với base rate;
6. Brier, log loss, ECE, calibration slope/intercept;
7. turnover và cost-aware return trong backtest sau cùng.

Top-10 phải được tính riêng trên từng ngày rồi mới lấy trung bình. Không được lấy Top-K trên toàn bộ frame bootstrap.

### 4.2. Confidence interval

- Resample theo **date block**, không resample từng row.
- So champion và challenger trên cùng tập ngày bằng paired bootstrap.
- Mặc định `2,000` bootstrap samples, seed cố định `238`, confidence level `95%`.
- Báo cả chênh lệch tuyệt đối theo điểm phần trăm và chênh lệch lift.
- Báo số ngày hiệu lực của từng fold; không dùng số row làm effective sample size.

### 4.3. Promotion gate nghiên cứu

Một candidate chỉ được chuyển sang shadow challenger nếu đồng thời đạt:

- lower bound 95% CI của delta `P@10` lớn hơn `0`;
- worst-fold `lift@10 >= 1.10`; mục tiêu ưu tiên `>= 1.20`;
- không fold nào có bằng chứng rõ ràng `lift@10 < 1`;
- AP lift không giảm quá `5%` tương đối so với champion;
- calibration không xấu đi đáng kể: ECE/Brier không vượt champion quá `5%` tương đối;
- feature coverage và inference failure rate không xấu hơn champion;
- kết quả tái lập với cùng seed, input và config.

Các ngưỡng trên là gate ban đầu. Nếu thay đổi, phải ghi lý do trước khi xem kết quả candidate, không sửa gate sau khi đã thấy metric.

## 5. Kế hoạch triển khai theo phase

## Phase 0 — Đóng băng baseline và tái lập kết quả

**Mục đích:** bảo đảm mọi cải thiện được so với đúng champion, không phải do khác dữ liệu hoặc khác evaluator.

### Công việc

- [x] Ghi checksum và copy reference tới champion manifests; không copy hoặc sửa model binary.
- [x] Tạo experiment registry cho chương trình H120 improvement.
- [x] Chạy lại OOF evaluator từ prediction artifact hiện có.
- [x] Tái lập AP, daily P@10, fold metrics và calibration diagnostics.
- [x] Xác nhận `final_test_used_for_selection=false` trong mọi experiment config.
- [x] Gắn cờ final test v3 là `contaminated_postmortem_only` trong registry nghiên cứu.
- [x] Viết regression test cho baseline metrics với tolerance rõ ràng.

### Artifact đầu ra

```text
experiments/h120_improvement/baseline_lock.json
reports/h120_improvement/E00_baseline/metrics.json
reports/h120_improvement/E00_baseline/fold_metrics.csv
reports/h120_improvement/E00_baseline/daily_top10.csv
reports/h120_improvement/E00_baseline/calibration_by_fold.csv
```

### Definition of done

- [x] Chênh lệch metric tái lập so với artifact gốc nhỏ hơn tolerance đã khóa (`1e-12`).
- [x] Mọi run tiếp theo tham chiếu cùng baseline ID và data checksum.

---

## Phase 1 — Audit data lineage và selection bias

**Mục đích:** phân biệt “dữ liệu sạch về mặt định dạng” với “dữ liệu đủ tin cậy cho production”.

### 1.1. Corporate action và adjusted-price lineage

- [ ] Kiểm tra split/dividend/rights events trên toàn universe, không chỉ sample vài mã.
- [ ] Xác nhận adjusted OHLC nhất quán trước/sau event và không tạo jump giả.
- [x] Lưu source, timestamp, policy và checksum để audit có thể chạy lại cho toàn bộ nguồn nội bộ. Nguồn corporate-action point-in-time vẫn chưa có.
- [ ] Tách lỗi thực sự khỏi `corporate_action_recent` cooldown hợp lệ.

**Gate:** không có unexplained jump vượt policy; mọi exception có symbol/date/reason.

### 1.2. Missing sessions

- [ ] Phân rã 948,708 missing-session records theo symbol, năm, thanh khoản và trạng thái niêm yết. Đã có mã/năm/liquidity-prior và proxy observed-span; còn thiếu lịch sử trạng thái niêm yết thực.
- [ ] Phân biệt suspended/delisted/not-yet-listed với lỗi ingest.
- [x] Không forward-fill OHLCV qua ngày không giao dịch.
- [ ] Kiểm tra các mã có missing rate cao có bị loại khỏi feature-ready hoặc khỏi Top-10 không cân xứng hay không.

**Gate:** mọi nhóm missing lớn có nguyên nhân; không còn lỗi ingest chưa giải thích.

### 1.3. Feature-ready selection bias

- [ ] So sánh 925,494 dòng ready và 875,000 dòng unavailable theo năm, ngành, liquidity, listing age và market regime. Đã có theo năm; các lát cắt còn lại chưa hoàn tất.
- [x] Báo tỷ lệ từ universe 1,512 mã xuống dataset 840 mã theo từng năm.
- [ ] Kiểm tra positive rate và Top-10 coverage theo nhóm coverage/staleness.
- [ ] Không hạ quality gate chỉ để tăng row count nếu chưa có bằng chứng.

**Gate:** có report định lượng cho biết coverage gate đang loại nhóm nào và ảnh hưởng ra sao.

### 1.4. Industry point-in-time

- [x] Xác định current static ICB map có được áp ngược về quá khứ hay không.
- [x] Nếu chưa có lịch sử point-in-time, đánh dấu sector feature là lineage-risk.
- [ ] Chạy candidate không dùng sector trước khi cân nhắc giữ sector feature.

### Artifact đầu ra

```text
reports/h120_improvement/data_audit/
  corporate_action_audit.parquet
  missing_session_breakdown.csv
  feature_ready_selection_bias.csv
  universe_funnel_by_year.csv
  industry_lineage_report.json
  data_audit_summary.md
```

### Checkpoint 2026-08-24

- [x] Tạo audit tái lập tại `reports/h120_improvement/data_audit/`.
- [x] Xác nhận dữ liệu cơ học sạch sau clean gate; thiếu phiên chỉ được audit, không impute.
- [x] Xuất 11.160 dòng corporate-action jump/cooldown và funnel feature-ready theo năm.
- [ ] Đóng corporate-action lineage gate: snapshot chưa có nguồn split/dividend/rights point-in-time.
- [ ] Đóng industry lineage gate: ICB map hiện là static-current, không có effective date.

Do hai lineage gate còn mở, Phase 4 chỉ được phép dùng `stock_primitives` và không dùng sector feature cho candidate đầu tiên.

---

## Phase 2 — Sửa label overlap và sample weight

**Mục đích:** không để các nhãn overlap 120 phiên được coi như quan sát độc lập.

### 2.1. Event identity

- [x] Điền `event_id` và `event_start_date` trong `src/labels/continuation.py`.
- [x] Định nghĩa `event_id` ở cấp sample bằng hash ổn định của
  `(label_version, symbol, entry_date, label_end_date)`; đặt
  `event_start_date=entry_date`.
- [ ] Nếu cần gom các ngày liên tiếp thành một market episode, dùng cột
  `episode_id` riêng; không nhập nhằng sample identity với episode grouping.
- [ ] Thêm audit: tỷ lệ null phải bằng `0` trên labeled rows. Đã audit pass theo date; còn thiếu coverage theo fold của dataset rebuild.
- [x] Thêm test cho event boundary, start/end date và deterministic ID.

### 2.2. Uniqueness/concurrency weight

- [x] Tính concurrency `c_t` theo các interval `[entry_date, label_end_date]` của
  cùng symbol.
- [x] Tính average uniqueness cho sample `i` theo
  `u_i = mean(1 / c_t)` trên toàn interval của sample đó.
- [x] Chuẩn hóa weight để mean weight bằng 1 trên training slice được truyền vào hàm.
- [x] Tách ba thành phần, không ghi đè lẫn nhau:
  - `event_uniqueness_weight`;
  - `date_balance_weight`;
  - `class_balance_weight`.
- [x] Lưu `sample_weight_final` cùng công thức trong label manifest. Class-balance chỉ được phép fit trong training fold.

Hai hàm `event_uniqueness_weights` trong nhánh V6 legacy có thể dùng làm tài liệu
tham khảo, nhưng hiện chúng weight theo run liên tiếp của cùng class label, không
phải interval concurrency. Không copy trực tiếp sang H120 nếu chưa chứng minh hai
định nghĩa tương đương.

### 2.3. Weight ablation

Chạy cùng feature/model baseline:

| ID | Event weight | Date balance | Class weight | Mục đích |
|---|---|---|---|---|
| W0 | 1 | không | full ratio | Tái lập baseline |
| W1 | uniqueness | không | full ratio | Đo tác động overlap |
| W2 | uniqueness | có | full ratio | Mỗi ngày có khối lượng ảnh hưởng tương đương |
| W3 | uniqueness | có | sqrt ratio | Kiểm tra class-weight nhẹ hơn |
| W4 | uniqueness | có | không | Kiểm tra ranking không cần class reweight |

Không chọn weight bằng AP đơn lẻ; dùng P@10, worst fold và calibration.

### Checkpoint 2026-08-24

- [x] Build label candidate `wave_continuation_h120_v3_eventweights` với event ID SHA-256, interval concurrency và weight components tách riêng.
- [x] Audit label run `20260824T054805Z` pass: 165.875 labeled rows; event ID null/collision/boundary/hash mismatch đều bằng 0.
- [x] Chọn W1 (`event_uniqueness_weight`) làm weight artifact cho retrain candidate: effective sample size 127.887 / 165.875.
- [x] Phát hiện và loại W2 (`uniqueness × date balance`) ở mức label audit: effective sample size chỉ 1.202 và weight tối đa 1.409 do ngày có rất ít mã eligible.
- [x] Chạy lại H120 classifier với W0 và W1 trên cùng 5 annual folds/protocol. W0 tái lập P@10 `0,2823`; W1 đạt `0,2954` nhưng paired 95% CI delta `[-0,0100; +0,0377]` và MAP@10 giảm, nên giữ W0.
- [ ] Nếu cần date balance, thiết kế policy có minimum daily count/cap trong từng training fold trước khi đưa vào ablation mới.

### Definition of done

- `event_id` không null trên mọi labeled row.
- Có distribution report của concurrency và effective sample size.
- Weight được tính chỉ từ interval metadata, không nhìn label tương lai ngoài định nghĩa sample.
- Một weight policy được khóa trước khi feature/model comparison chính thức.

---

## Phase 3 — Sửa evaluator và thiết kế validation

**Mục đích:** metric phản ánh đúng quyết định chọn 10 mã mỗi ngày và uncertainty theo thời gian.

### 3.1. Daily ranking evaluator

- [x] Thêm hàm `daily_top_k_metrics(..., k=10)` vào evaluation layer.
- [x] Tie-break deterministic: score giảm dần, sau đó symbol tăng dần.
- [x] Báo P@5/P@10/P@20/P@50, MAP@10, NDCG@10, hit-rate và lift.
- [x] Lưu một row mỗi date để paired comparison có thể kiểm tra trực tiếp.
- [x] Thêm cluster bootstrap resample date trên daily Top-10 metrics đã rank trong từng date.

### 3.2. Walk-forward folds

- [ ] Giữ annual folds hiện tại để so với baseline.
- [ ] Thêm semiannual hoặc rolling folds để tăng số điểm kiểm định regime.
- [ ] Purge tối thiểu toàn bộ H120 label horizon tại boundary; `embargo_sessions=5` là bổ sung, không thay purge.
- [ ] Tách trong mỗi fold: model-train, calibration và evaluation theo thời gian; không random split.
- [ ] Báo training cutoff, latest matured label date và số validation dates của từng fold.

### 3.3. Segment diagnostics

Mỗi candidate phải có metric theo:

- calendar year và fold;
- market momentum quintile;
- market volatility quintile;
- liquidity bucket;
- listing age/coverage bucket;
- industry, nếu industry lineage đạt yêu cầu;
- seen/unseen symbol so với training fold.

### Test bắt buộc

- [x] Unit test Top-10 trên ngày có universe nhỏ hơn, bằng và lớn hơn 10.
- [x] Unit test tie-break.
- [x] Unit test bootstrap giữ nguyên date cluster.
- [ ] Unit test purge: không có `label_end_date` của train vượt validation cutoff.
- [x] Unit test paired metric dùng đúng giao của các ngày champion/challenger.

---

## Phase 4 — Feature governance và ablation

**Mục đích:** giảm noise có bằng chứng nhưng không lọc feature theo cảm tính.

### 4.1. Sinh feature groups bằng code

Tạo file versioned, ví dụ `configs/experiments/h120_feature_groups_v1.yaml`, gồm:

- `full_83`: baseline hiện tại;
- `stock_primitives`: các feature thay đổi theo symbol trong cùng ngày;
- `stock_plus_sector_relative`: stock primitives cộng rank/z-score sector đã kiểm tra lineage;
- `no_composites`: bỏ các score tổng hợp;
- `deduplicated`: chỉ bỏ constant và duplicate chắc chắn;
- `market_regime`: feature chỉ dùng cho calibrator/exposure, không dùng cho stock ranker.

Feature group phải được sinh từ schema và audit variance/correlation; không copy tay một danh sách không có provenance.

### 4.2. Candidate loại bỏ chắc chắn

Kiểm tra lại trên từng fold trước khi loại:

- zero-use/constant hiện quan sát được: `corporate_action_jump`, `corporate_action_recent`, `coverage_5`, `is_breakout_60`, `stale_sessions`, `zero_volume_ratio_20`, `zero_volume_ratio_60`;
- duplicate đại số: một trong `volatility_ratio_10_60` và `contraction_10_60`;
- duplicate theo ngày: một trong `market_active_symbols` và `market_coverage`;
- `quality_score` sau khi đã condition trên `feature_ready`.

Nếu variance/correlation thay đổi ở fold mới, không tự động loại mà phải ghi vào audit.

### 4.3. Feature ablation matrix

| ID | Model | Feature group | Câu hỏi |
|---|---|---|---|
| F0 | classifier | full_83 | Baseline |
| F1 | classifier | deduplicated | Duplicate/constant có làm model bất ổn không? |
| F2 | classifier | no_composites | Composite score có gây double counting không? |
| F3 | classifier | stock_primitives | Market/sector có làm hại cross-sectional ranking không? |
| F4 | classifier | stock_plus_sector_relative | Sector-relative có thêm signal ổn định không? |

Không dùng global gain importance để chọn top-N. Stability report phải gồm fold-wise rank correlation và top-feature Jaccard.

### Checkpoint 2026-08-24

- [x] Tạo [config nhóm feature](../configs/experiments/h120_feature_groups_v1.yaml) và resolver theo manifest/audit, không dùng danh sách copy tay.
- [x] Audit 160.538 feature-ready rows: `full_83` (83), `stock_primitives` (50), `no_composites` (76), `deduplicated` (77), `market_regime` (12).
- [x] Xác nhận constant trong sample: `corporate_action_jump`, `corporate_action_recent`, `zero_volume_ratio_20`, `zero_volume_ratio_60`; duplicate gần hoàn hảo: `contraction_10_60`, `market_coverage`.
- [x] Gắn policy: market-regime chỉ cho calibrator/exposure; corporate-action bị loại khỏi stock primitives; `stock_plus_sector_relative` bị block bởi Phase 1.4.
- [x] Chạy F0–F3 trên cùng 5 annual folds với W0. Chỉ F1 `stock_primitives` vượt F0 với CI dương: P@10 `0,3308` vs `0,2823`, delta `+0,0485`, CI `[+0,0162; +0,0808]`.
- [x] Xác nhận F1 qua seeds 238–242: mean P@10 `0,3349` vs F0 `0,2902`; mọi seed có delta dương. Không chạy F4 cho tới khi industry lineage đóng.

---

## Phase 5 — Tách ranker và probability/regime model

**Mục đích:** tối ưu đúng thứ tự Top-10 mà vẫn có xác suất dùng cho risk/exposure.

### 5.1. Stock ranker

- [x] Implement training path dùng `XGBRanker`.
- [x] Group rows theo date; sort ổn định trước khi tạo group sizes.
- [x] Objective ban đầu: `rank:pairwise`.
- [x] Early stopping: `map@10`; báo thêm `ndcg@10`.
- [x] Candidate đầu tiên chỉ dùng `stock_primitives`.
- [ ] Candidate thứ hai thêm sector-relative feature nếu Phase 1.4 đạt gate.
- [x] Không đưa date-common market features vào ranker.

### 5.2. Probability/regime calibration

- [x] Giữ raw rank score tách biệt với calibrated probability.
- [ ] Dùng market feature để ước lượng daily prevalence hoặc logit intercept.
- [x] Fit calibrator causal theo train/calibration window của từng fold.
- [ ] So sánh:
  - static Platt/sigmoid hiện tại;
  - rolling Platt với window chỉ chứa outcome đã mature;
  - regime-intercept logistic model.
- [x] Chưa ưu tiên isotonic vì số ngày độc lập thấp và dễ overfit.
- [x] Kiểm tra calibrator đơn điệu để không thay đổi stock order ngoài chủ đích.

### 5.3. Kiến trúc mục tiêu

```text
stock primitives -> cross-sectional ranker -> rank_score -> Top-10 order

market/regime -----> daily prevalence/intercept -----+
rank_score ------------------------------------------+-> p_h120_calibrated
```

Top-10 order lấy từ `rank_score`. `p_h120_calibrated` phục vụ risk, monitoring và exposure. Hai output phải có contract rõ trong manifest.

### 5.4. Model matrix

| ID | Ranking model | Probability model | Feature policy |
|---|---|---|---|
| M0 | current classifier score | current sigmoid | full_83 |
| M1 | stock-only classifier | sigmoid | stock primitives |
| M2 | stock-only XGBRanker | score-to-probability Platt | stock primitives |
| M3 | XGBRanker | regime-intercept calibration | stock + market separated |
| M4 | XGBRanker | rolling causal calibration | stock + market separated |

M3/M4 chỉ chạy sau khi M2 vượt M0 về ranking; tránh thêm complexity trước khi chứng minh ranker có giá trị.

### Checkpoint 2026-08-24

- [x] Chạy M2 `h120_ranker_stock_primitives_v1` trên 5 annual folds, dùng 50 stock-primitives và không truyền row/class weight classifier sang pairwise ranker.
- [x] M2 raw rank P@10 là 0,3762 so với M0 raw classifier 0,2823 trên cùng 130 ngày; paired delta là +0,0938, bootstrap 95% CI `[+0,0577; +0,1315]`.
- [x] Worst-fold P@10 của M2 là 0,2654, cao hơn M0 là 0,1577.
- [x] Manifest khóa contract: `rank_score` quyết định Top-10; `p_h120_calibrated` chỉ phục vụ risk/monitoring.
- [ ] So sánh calibration M2 static/rolling/regime-intercept và chỉ mở M3/M4 như experiment generation mới.

---

## Phase 6 — Hyperparameter tuning có kiểm soát

**Mục đích:** tuning sau khi objective, weight và feature policy đã khóa.

### 6.1. Không tuning meta-logistic H120-only để tăng ranking

Cascade hiện chỉ nhận `p_h120` với hệ số dương. Thay `C`, threshold hoặc sigmoid chỉ đổi thang xác suất, không đổi thứ tự Top-10. Chỉ tuning lớp này cho calibration, không ghi nhận là ranking gain.

### 6.2. Search space cho ranker

| Parameter | Search range |
|---|---|
| `max_depth` | `2, 3, 4, 5` |
| `min_child_weight` | `10–100`, log scale |
| `learning_rate` | `0.02–0.06` |
| `subsample` | `0.6–0.9` |
| `colsample_bytree` | `0.5–0.9` |
| `reg_lambda` | `2–20`, log scale |
| `reg_alpha` | `0–0.5` |
| `gamma` | `0–0.5` |
| `n_estimators` | cap `2,000`, chọn bằng early stopping |

### 6.3. Search protocol

- [x] Dùng random search nhỏ trước, không full grid.
- [x] Inner walk-forward chọn config; outer walk-forward chỉ đánh giá. E08 đã khóa config từ folds 2020–2023 trước khi mở outer fold 2024.
- [ ] Objective tổng hợp ưu tiên MAP@10/P@10, có penalty nếu worst-fold lift thấp hoặc AP/calibration giảm quá gate.
- [x] Seed chính `238`; top candidate đã chạy thêm 4 seed (`239`–`242`) để đo variance.
- [x] Lưu mọi trial, kể cả failed/pruned trial.
- [x] Khóa search space trong `h120_ranker_tuning_v1`; thay đổi sau outer evaluation phải mở experiment generation mới.

### 6.4. Class weight

Giữ full negative/positive ratio làm baseline classifier vì thử nghiệm sqrt/no-weight trước đây chưa thắng. Với ranker, class weight phải là một ablation riêng; không mặc định bê policy classifier sang pairwise objective.

### Checkpoint 2026-08-24

- [x] Chạy 4 random inner trials trên fold 2021–2024, dùng `stock_primitives`, `rank:pairwise`, và không áp row/class weight classifier vào ranker.
- [x] Lưu retry log thành công và log lỗi đầu tiên; không bỏ failed trial khỏi audit.
- [x] Best inner trial: mean P@10 0,4392; worst-fold P@10 0,2923. Đây là inner-selection evidence, không phải outer promotion evidence.
- [x] Chạy outer walk-forward với config inner-selected, sau đó xác nhận candidate bằng multi-seed.
- [ ] Không mở E09 refit/shadow cho tới khi lower 95% CI của delta P@10 dương ổn định theo seed.

---

## Phase 7 — Label sensitivity, giữ nguyên horizon H120

**Mục đích:** xác định base-rate drift đến từ thị trường hay từ công thức hurdle phụ thuộc volatility.

Label canonical vẫn là:

```text
horizon = 120
target = max(8%, 0.5 * current_volatility * sqrt(120 / 252))
terminal_return >= 0
maximum_drawdown >= -20%
```

### Diagnostic trước khi tạo label mới

- [x] Báo hurdle distribution theo fold/regime.
- [x] Decompose positive-rate drift theo hurdle, realized excess return và drawdown condition.
- [x] Đo mutual information/correlation giữa hurdle tại t và market regime features.
- [x] Kiểm tra tỷ lệ sample dùng floor 8% so với volatility branch.

### Candidate sensitivity

| ID | Biến thể | Quy tắc |
|---|---|---|
| L0 | canonical | Giữ nguyên label v2 |
| L1 | train-derived capped hurdle | Cap volatility hurdle bằng quantile chỉ tính trên fold-train; quantile chọn trong inner folds |
| L2 | fixed-hurdle diagnostic | Chạy một grid nhỏ được khóa trước để đo độ nhạy, không tự động promotion |
| L3 | continuous H120 utility | Dùng excess return và drawdown làm ranking target phụ, không thay ngay binary contract |

Mọi biến thể phải có `label_version` mới và rebuild toàn bộ split theo cutoff tương ứng. Chỉ đổi canonical label nếu:

- business meaning vẫn đúng;
- base rate ổn định hơn ngoài mẫu;
- ranking cải thiện trên outer folds;
- calibration và cost-aware outcome cùng cải thiện;
- quyết định đổi label được ghi riêng, không nhập nhằng với model gain.

### Checkpoint 2026-08-24

- [x] Chạy diagnostic trên canonical `wave_continuation_h120_v3_eventweights`; không thay label contract.
- [x] 25,7% labeled samples dùng floor 8%; 74,3% dùng volatility-scaled hurdle.
- [x] Hurdle có Spearman `-0,189` và mutual information `0,106` với market-regime score: có regime sensitivity, nhưng chưa đủ lý do đổi label.
- [ ] Chỉ mở L1–L3 sau khi outer evaluation của M2/tuned ranker cho thấy label canonical là bottleneck.

---

## Phase 8 — Experiment sequence và stop/go rule

Chạy theo thứ tự sau:

| Thứ tự | Experiment | Thay đổi duy nhất | Go rule |
|---:|---|---|---|
| 1 | E00 | Tái lập champion | Metric khớp baseline |
| 2 | E01 | Correct daily Top-10 evaluator | Tests pass; daily artifacts kiểm tra được |
| 3 | E02 | Event/concurrency weighting | ESS và fold metrics hợp lệ |
| 4 | E03 | Feature groups trên classifier | Chọn tối đa 2 group vượt F0 có CI |
| 5 | E04 | Stock-only ranker | Vượt M0 theo promotion gate nghiên cứu |
| 6 | E05 | Sector-relative ranker | Chỉ giữ nếu gain ổn định và lineage sạch |
| 7 | E06 | Regime calibration | Brier/ECE tốt hơn, ranking không đổi ngoài contract |
| 8 | E07 | Label sensitivity | Chỉ diagnostic nếu chưa đạt tiêu chí đổi label |
| 9 | E08 | Nested tuned challenger | Khóa config cuối |
| 10 | E09 | Refit tới latest matured cutoff | Chỉ sau khi E08 khóa |
| 11 | E10 | Shadow challenger | Không trade; monitor drift và runtime |

Stop rule:

- Dừng một nhánh nếu 95% CI của delta P@10 nằm hoàn toàn dưới 0.
- Nếu mean tăng nhưng worst fold giảm dưới lift 1, quay lại segment analysis; không cộng thêm feature để “cứu” metric.
- Nếu ranking tăng nhưng calibration giảm, giữ ranker và sửa calibrator riêng; không loại ranker chỉ vì probability scale.
- Nếu feature lineage không chứng minh được, loại feature đó khỏi production candidate dù OOF gain dương.

### Checkpoint E08 — 2026-08-24

- [x] Chọn config bằng 4 trial trên inner folds 2020–2023; fold 2024 không tham gia selection.
- [x] Đánh giá outer fold 2024 (26 ngày paired) và xác nhận seeds 238–242; toàn bộ artifact nằm tại `experiments/h120_improvement/E08_outer_evaluation_2024/`.
- [x] Stop rule không bị kích hoạt: không CI nào nằm hoàn toàn dưới 0.
- [x] Không đạt research promotion gate: mean delta P@10 qua 5 seed `+0,0246`, nhưng không seed nào có lower 95% CI > 0; P@10 dao động `0,4346–0,4808` so với champion `0,4308`.
- [ ] E09 refit và shadow monitoring — blocked bởi E08 no-go, không phải bởi compute.

## 6. Refit, holdout và production promotion

### 6.1. Refit challenger

- [ ] Tính `latest_matured_label_date = as_of_date - 120 trading sessions` bằng VNINDEX calendar.
- [ ] Train tới cutoff mature gần nhất sau khi config E08 đã khóa.
- [ ] Không dùng dữ liệu chưa mature làm negative label.
- [ ] Lưu model card, schema, config checksum và training interval.

Champion cũ vẫn được giữ nguyên để có comparison trung thực; không overwrite bundle `deploy/wave_h120_shadow`.

### 6.2. Future holdout

- [ ] Chọn holdout bắt đầu sau thời điểm khóa experiment protocol.
- [ ] Đăng ký start/end/cutoff trước khi outcome mature.
- [ ] Không mở label hoặc aggregate metric trong lúc tuning.
- [ ] Chờ đủ 120 trading sessions cho outcome mature, cộng data-quality grace period.
- [ ] Mở holdout đúng một lần qua script có manifest.

Vì horizon là 120 phiên, production approval có độ trễ tự nhiên khoảng sáu tháng giao dịch sau khi khóa holdout. Shadow monitoring có thể chạy ngay, nhưng không thay thế future-label evidence.

### 6.3. Cost-aware backtest

Chỉ chạy sau khi candidate đã qua statistical gate:

- Top-10 portfolio construction cố định trước khi mở holdout;
- transaction cost, slippage, liquidity cap và turnover policy versioned;
- không sửa holding/rebalance rule sau khi nhìn PnL;
- báo return, drawdown, turnover, capacity và sensitivity theo cost;
- so champion/challenger trên cùng ngày và cùng execution assumptions.

### 6.4. Production gate cuối

- [ ] Future holdout P@10 delta có lower 95% CI > 0.
- [ ] Worst regime/fold lift đạt gate đã khóa.
- [ ] Calibration đạt Brier/ECE và slope/intercept gate.
- [ ] Cost-aware backtest tốt hơn champion và không vi phạm drawdown/capacity policy.
- [ ] Inference latency, checksum, deterministic ranking và missing-feature policy đạt test.
- [ ] Shadow run ổn định liên tục trong khoảng thời gian vận hành đã định trước.
- [ ] Có approval record riêng; không sửa tay `deployment_status`.

## 7. Thay đổi code dự kiến

| Khu vực | File hiện tại/đề xuất | Thay đổi |
|---|---|---|
| Label | `src/labels/continuation.py` | Event ID, interval metadata, uniqueness weight |
| Label tests | `tests/test_labels/test_continuation.py` | Event/weight determinism và overlap tests |
| Split | `src/training/splits.py` | Full H120 purge, rolling/semiannual fold support |
| Training | `src/training/xgboost_pipeline.py` | Weight components, ranker path hoặc shared utilities |
| Ranking | `src/training/xgboost_ranker_pipeline.py` | Đề xuất file mới cho XGBRanker, group-by-date contract |
| Evaluation | `src/evaluation/wave_model.py` | Exact daily Top-K, MAP/NDCG, paired date bootstrap |
| Evaluation tests | `tests/test_evaluation/test_wave_model_evaluation.py` | Top-K/tie/bootstrap/pair tests |
| Feature groups | `configs/experiments/h120_feature_groups_v1.yaml` | Versioned feature policies |
| Ranker config | `configs/experiments/h120_xgboost_ranker_v1.yaml` | Objective, search space, metric contract |
| Experiment runner | `scripts/run_h120_improvement_experiment.py` | Một entry point tái lập cho E00–E10 |
| Comparison | `scripts/compare_h120_candidates.py` | Paired CI và promotion gates |
| Shadow | `scripts/run_wave_h120_shadow.py` | Chạy champion/challenger song song, không đổi trade authorization |

Tên file mới là đề xuất; khi implement phải giữ backward compatibility với frozen bundle.

## 8. Artifact contract cho mỗi experiment

```text
experiments/h120_improvement/<EXPERIMENT_ID>/
  experiment.yaml
  manifest.json
  feature_list.json
  fold_boundaries.csv
  predictions/
    oof_predictions.parquet
  audit/
    metrics.json
    fold_metrics.csv
    daily_topk.csv
    segment_metrics.csv
    calibration_by_fold.csv
    feature_stability.csv
    paired_vs_champion.json
    data_quality.json
  model/
    ...
```

`manifest.json` tối thiểu phải có:

- experiment ID và parent ID;
- git commit và dirty-worktree flag;
- data/feature/label/split/config checksums;
- training and validation date boundaries;
- latest matured label date;
- feature group/version;
- weight formula/version;
- random seed và package versions;
- final test access flag;
- promotion gate result và lý do pass/fail.

## 9. Monitoring trong shadow

### Không cần chờ nhãn H120

- input row count, symbols và feature-ready rate;
- missing/non-finite/defaulted feature counts;
- feature PSI so với training và recent reference window;
- rank-score distribution, concentration và Top-10 turnover;
- unseen-symbol rate;
- calibration output distribution;
- inference latency, artifact checksum và deterministic replay.

### Khi nhãn mature

- rolling P@10/MAP@10 với confidence interval;
- base rate và lift;
- Brier/ECE/calibration slope;
- metrics theo regime/liquidity/coverage;
- champion–challenger paired daily delta.

Alert ban đầu:

- feature PSI > `0.25` ở nhiều feature trọng yếu;
- mean predicted prevalence lệch actual mature rate quá ngưỡng calibration đã khóa;
- rolling lift@10 dưới `1` đủ số ngày tối thiểu;
- feature-ready/unseen-symbol rate ra ngoài training envelope;
- output không đủ 10 mã khi universe đủ điều kiện lớn hơn hoặc bằng 10.

Ngưỡng alert cụ thể phải được fit từ train/OOF distribution trước khi bật shadow challenger.

## 10. Tiến độ dự kiến

Đây là effort estimate cho một người, chưa tính thời gian chờ label future holdout mature.

| Giai đoạn | Effort | Phụ thuộc |
|---|---:|---|
| Phase 0: baseline lock | 0.5–1 ngày | Artifact hiện có |
| Phase 1: data/lineage audit | 2–4 ngày | Raw snapshot và corporate-action source |
| Phase 2: event weighting | 2–3 ngày | Label code/tests |
| Phase 3: evaluator/folds | 2–4 ngày | OOF predictions |
| Phase 4: feature governance | 1–2 ngày | Evaluator đúng |
| Phase 5: ranker/calibrator | 3–5 ngày | Weight + feature groups |
| Phase 6–8: nested experiments/refit | 3–7 ngày + compute | Các phase trước pass |
| Shadow integration | 2–3 ngày | Candidate khóa |
| Future holdout | >=120 phiên giao dịch | Protocol khóa trước |

Không chạy tuning lớn song song với việc sửa evaluator; nếu evaluator thay đổi, mọi trial cũ phải được đánh dấu incompatible.

## 11. Checklist theo dõi tổng

### P0 — Correctness

- [ ] E00 tái lập champion.
- [ ] Daily Top-10 evaluator đúng và có unit tests.
- [ ] Date-block paired bootstrap đúng.
- [ ] H120 purge test pass.
- [ ] `event_id`/uniqueness weights hoàn chỉnh.

### P1 — Evidence

- [ ] Data lineage report hoàn chỉnh.
- [ ] Feature-ready selection-bias report hoàn chỉnh.
- [ ] Weight policy được khóa.
- [ ] Feature groups được version hóa.
- [ ] Stock-only ranker được đánh giá nested walk-forward.
- [ ] Regime calibrator được đánh giá riêng.

### P2 — Candidate

- [ ] Candidate vượt research promotion gate.
- [ ] Config/hyperparameter khóa trước refit.
- [ ] Refit dùng latest matured cutoff.
- [ ] Champion và challenger chạy shadow song song.
- [ ] Future holdout được đăng ký và niêm phong.

### P3 — Production

- [ ] Future holdout đã mature và chỉ mở một lần.
- [ ] Statistical gate pass.
- [ ] Calibration gate pass.
- [ ] Cost-aware backtest gate pass.
- [ ] Runtime/monitoring gate pass.
- [ ] Có production approval record.

## 12. Decision log

Mỗi quyết định điền thêm một dòng, không sửa kết quả lịch sử.

| Ngày | Decision ID | Quyết định | Bằng chứng | Người duyệt |
|---|---|---|---|---|
| 2026-08-24 | H120-PLAN-001 | Giữ H120; frozen champion; ưu tiên stock ranker + regime calibration | OOF audit và causal ablations hiện có | Pending |
| 2026-08-24 | H120-E00-001 | Khóa và tái lập H120 shadow champion; final test v3 chỉ postmortem | `experiments/h120_improvement/baseline_lock.json`, E00 report và regression test | Pending |

## 13. Tài liệu và artifact tham chiếu

- `docs/h120_shadow_inference.md`
- `configs/experiments/wave_cascade_v4_h120_only.yaml`
- `configs/wave_continuation_labels_h120_v2.yaml`
- `configs/wave_continuation_training_splits_h120.yaml`
- `configs/wave_continuation_xgboost_h120.yaml`
- `data/processed/wave_ignition_v6_snapshot/audit/quality_summary.json`
- `data/features/wave_ignition_snapshot/wave_ignition_v2/runs/20260823T050008Z/audit/feature_quality_report.json`
- `data/labels/wave_ignition_snapshot/wave_continuation_h120_v2/runs/20260823T050546Z/audit/label_quality_report.json`
- `data/training/wave_ignition_snapshot/wave_dataset_continuation_h120/runs/20260823T050830Z/audit/dataset_quality_report.json`
- `data/training/wave_ignition_snapshot/wave_dataset_continuation_h120/runs/20260823T050830Z/audit/split_summary.csv`
- `models/wave_ignition_snapshot/xgboost_continuation_h120/runs/20260823T052814Z/audit/oof_metrics.json`
- `models/wave_ignition_snapshot/xgboost_continuation_h120/runs/20260823T052814Z/audit/fold_metrics.csv`
- `models/wave_ignition_snapshot/xgboost_continuation_h120/runs/20260823T052814Z/model_manifest.json`
