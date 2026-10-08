# Hướng dẫn cải thiện model H120 trend ranking

> Trạng thái: tài liệu triển khai nghiên cứu, chưa phải phê duyệt production  
> Phạm vi: dự đoán và xếp hạng cổ phiếu có tiềm năng bullish continuation trong 120 phiên giao dịch  
> Nguyên tắc: ưu tiên kết quả Top-10, kiến trúc tối giản, causal validation và khả năng tái lập

## 1. Kết luận điều hành

Mục tiêu chính của model không phải dự báo giá từng phiên mà là, tại thời điểm hiện tại, tìm ra các cổ phiếu có tiềm năng hình thành xu hướng tăng/outperform trong 120 phiên tiếp theo.

Kiến trúc nên ưu tiên cho mục tiêu này là:

```text
50 stock-primitives
        |
        v
Stock-only XGBRanker
        |
        +--> rank_score ----------> xếp hạng universe ----------> Top-10
        |
        +--> causal calibration --> p_h120_calibrated ----------> risk/monitoring
```

Không đưa classifier riêng, strength regressor hoặc single-input cascade vào decision path của challenger đầu tiên. Các thành phần này chỉ được mở lại nếu một ablation độc lập chứng minh có incremental value ngoài mẫu.

Model hiện tại vẫn phải được giữ nguyên làm frozen shadow champion cho đến khi challenger vượt future holdout. Không overwrite bundle `deploy/wave_h120_shadow`.

## 2. Định nghĩa chính xác bài toán

Một tín hiệu được tạo tại ngày `t`, giả định entry tại phiên `t+1`, và outcome được đánh giá đến phiên `t+120`.

Nhãn `y_entry=1` yêu cầu đồng thời:

```text
excess_return >= max(8%, 0.5 * current_volatility * sqrt(120 / 252))
terminal_return >= 0
maximum_drawdown >= -20%
```

Vì vậy model trả lời câu hỏi:

> Trong universe đủ điều kiện tại ngày hiện tại, cổ phiếu nào có tiềm năng trở thành bullish continuation tốt trong 120 phiên tiếp theo?

Model không có trách nhiệm dự đoán:

- giá đóng cửa của từng phiên trong 120 phiên;
- thời điểm chính xác xu hướng bắt đầu hoặc kết thúc;
- đầy đủ ba trạng thái tăng, giảm và đi ngang;
- một mức lợi nhuận cụ thể hoặc cam kết giao dịch.

## 3. Kiến trúc hiện tại và các đầu ra

### 3.1. Frozen shadow champion

```text
83 features
   |
   +--> XGBClassifier --> p_entry_raw --> sigmoid --> p_h120
   |
   +--> XGBRegressor --> p_strength_conditional --x  không dùng

p_h120 --> logistic cascade --> sigmoid --> p_cascade_calibrated --> Top-10
```

Các artifact đang khóa:

- Upstream: `xgboost_continuation_h120/20260823T052814Z`.
- Cascade: `wave_cascade_v4_h120_only/20260823T170819Z`.
- Deployment status: `shadow_candidate_requires_new_holdout`.
- Trade authorization: `false`.

Điểm chưa tối ưu của kiến trúc hiện tại:

- Strength regressor vẫn chạy nhưng output bị bỏ, gây chi phí inference không cần thiết.
- Cascade chỉ nhận một biến `p_h120`; logistic và sigmoid là biến đổi đơn điệu nên gần như không bổ sung ranking power.
- Ranking vẫn dựa trên probability score của classifier, trong khi mục tiêu nghiệp vụ là Top-10 theo ngày.
- Model được train đến cutoff `2024-07-26`, đã stale so với dữ liệu hiện tại.

### 3.2. Ý nghĩa ba output đã nghiên cứu

| Output | Ý nghĩa | Có phải xác suất? | Vai trò phù hợp |
|---|---|---:|---|
| `p_entry_calibrated` | Xác suất đạt toàn bộ điều kiện H120 | Có, sau calibration | Risk, confidence, exposure |
| `rank_score` | Điểm ưu tiên tương đối giữa các mã cùng ngày | Không | Xếp hạng và chọn Top-10 |
| `p_strength_conditional` | Expected normalized quality nếu entry thành công | Không | Research/monitoring |

`p_strength_conditional` nên được đổi tên về mặt contract thành `q_strength_conditional` nếu được sử dụng lại, vì đây là regression score chứ không phải probability.

## 4. Bằng chứng metric hiện có

### 4.1. Các cải thiện có tín hiệu tốt

| Candidate | Daily P@10 | So sánh | Kết luận |
|---|---:|---:|---|
| E00 classifier full-83 | `0.2823` | Baseline | Frozen reference |
| E03 stock-primitives classifier, seed 238 | `0.3308` | `+0.0485`; CI 95% `[+0.0162, +0.0808]` | Feature simplification có giá trị |
| E04 stock-only Ranker, seed 238 | `0.3762` | `+0.0454` so với E03; CI `[+0.0169, +0.0716]` | Ranking objective có giá trị |
| E04 Ranker so với E00, seed 238 | `0.3762` vs `0.2823` | `+0.0938`; CI `[+0.0577, +0.1315]` | Gain all-OOF mạnh |

Qua seeds `238-242`, E04 Ranker đạt mean P@10 `0.3851`, trong khi stock-primitives classifier đạt `0.3349`. Tuy nhiên latest-fold 2024 không ổn định: ranker-minus-classifier chỉ dương ở 2/5 seed.

### 4.2. E08 chưa đủ điều kiện promotion

Trên outer fold 2024, gồm 26 ngày paired:

- Champion P@10: `0.4308`.
- E08 challenger mean P@10 qua 5 seed: `0.4554`.
- Mean delta: `+0.0246`.
- Challenger dao động từ `0.4346` đến `0.4808`.
- Không seed nào có lower bound CI 95% lớn hơn `0`.

Kết luận: point estimate tốt hơn nhưng gain nhạy theo seed; E09 refit và E10 shadow không được mở từ candidate này.

### 4.3. Những thay đổi đã bị loại

- Event uniqueness weight: P@10 `0.2823 -> 0.2954`, nhưng CI `[-0.0100, +0.0377]` và MAP@10 giảm; giữ W0.
- Strength post-ranking với weight `0.25`: P@10 `0.2603 -> 0.1962`; reject.
- Đưa strength vào meta-model: AP tăng lên `0.1508`, nhưng Top-10 precision giảm còn `0.2218`; reject.
- Feature policy F2 chỉ cải thiện nhẹ và CI cắt 0; F3 làm metric giảm.

## 5. Các vấn đề cần cải thiện theo mức ưu tiên

### P0 - Correctness và data lineage

#### 5.1. H120 purge chưa được đóng gate

Do label kéo dài 120 phiên và được lấy mẫu mỗi 5 phiên, các sample lân cận overlap mạnh. Mọi split phải purge toàn bộ H120 horizon tại boundary; embargo 5 phiên chỉ là phần bổ sung, không thay purge.

Giải pháp:

- Enforce purge tối thiểu 120 trading sessions giữa train và validation outcome.
- Viết regression test kiểm tra không có interval label nào vượt qua cutoff.
- Lưu train/calibration/validation date boundaries trong manifest.
- Không dùng row count làm effective sample size; số ngày độc lập mới là đơn vị chính.

#### 5.2. Corporate action và adjusted-price lineage

Snapshot hiện chưa đóng đầy đủ nguồn split/dividend/rights point-in-time.

Giải pháp:

- Khóa nguồn và adjustment policy theo version.
- Audit jump quanh corporate-action events trên toàn universe.
- Không để `corporate_action_recent` che lỗi điều chỉnh giá thật.
- Lưu checksum và timestamp của source.

#### 5.3. Feature-ready selection bias

Feature-ready rate khoảng `51.4%`; universe lịch sử giảm từ khoảng 1.512 mã xuống 840 mã trong dataset.

Giải pháp:

- Báo coverage theo năm, liquidity, listing age và market regime.
- Đo positive rate và Top-10 coverage của nhóm bị loại.
- Không hạ quality gate chỉ để tăng row count.
- Thêm monitoring feature-ready/unseen-symbol rate trong shadow.

#### 5.4. Sector lineage

ICB map hiện là static-current và có nguy cơ bị áp ngược về quá khứ.

Giải pháp:

- Giữ sector feature khỏi Ranker đầu tiên.
- Chỉ thử sector-relative challenger sau khi có mapping point-in-time hoặc một policy lineage được chấp nhận trước khi xem metric.

### P1 - Validation và robustness

#### 5.5. Số ngày kiểm định thấp

Annual fold hiện chỉ có khoảng 25-27 ngày dự báo độc lập, dù số row rất lớn.

Giải pháp:

- Giữ annual folds để tương thích baseline.
- Bổ sung rolling hoặc semiannual folds.
- Resample theo complete date blocks.
- Báo số ngày, fold dispersion và worst-fold; không chỉ báo global mean.

#### 5.6. Seed instability

E04/E08 cho thấy điểm trung bình tốt nhưng latest-fold phụ thuộc seed.

Giải pháp:

- Chọn config bằng objective có penalty cho fold dispersion và seed dispersion.
- Trong inner selection, dùng ít nhất 2 seed cho candidate cuối; confirmation dùng 5 seed.
- Thử ablation giảm stochasticity bằng `subsample`/`colsample_bytree` gần `1.0`.
- Giữ tree depth nhỏ, tăng minimum child support và regularization nếu worst-fold xấu.
- Không chọn model chỉ vì một seed có điểm cao nhất.

#### 5.7. Training objective chưa tập trung hoàn toàn vào Top-10

`rank:pairwise` tối ưu nhiều positive-negative pairs, còn business chỉ quan tâm đầu danh sách.

Giải pháp:

- Giữ pairwise làm baseline mạnh.
- Mở challenger ranking objective/top-weighting ưu tiên NDCG@10 nếu implementation support được khóa rõ.
- Khóa một early-stopping metric chính; không phụ thuộc ngầm vào thứ tự của danh sách `eval_metric`.
- Dùng external deterministic daily evaluator để ra quyết định cuối.
- Không tối ưu trực tiếp trên outer/future holdout.

#### 5.8. Fold 2024 đã được xem

Fold 2024 không còn là dữ liệu sạch để chọn target, feature, hyperparameter hoặc strength weight mới.

Giải pháp:

- E04/E08 chỉ là research/postmortem evidence.
- Mở experiment generation mới.
- Đăng ký future holdout mới trước khi outcome mature.
- Không sửa gate sau khi đã nhìn metric.

### P2 - Model và calibration

#### 5.9. Kiến trúc đang dư thừa

Giải pháp cho challenger:

- Một XGBRanker duy nhất quyết định Top-10.
- Một causal sigmoid/Platt calibrator nhẹ phục vụ probability.
- Không chạy strength regressor.
- Không chạy single-input cascade.
- Không dùng probability threshold làm hard gate trừ khi một ablation riêng chứng minh lợi ích.

#### 5.10. Probability drift theo regime

Positive rate thay đổi khoảng `4.7%-24.4%` giữa các fold. Static calibration có thể không giữ được prevalence theo thời gian.

Giải pháp:

- So sánh static causal Platt, rolling causal Platt và regime-intercept calibration.
- Mọi calibrator chỉ fit từ outcome đã mature trước cutoff.
- Ranking luôn lấy từ raw `rank_score`; calibrator không được đổi thứ tự.
- Báo Brier, log loss, ECE, calibration slope/intercept theo fold và regime.
- Nếu calibration chưa đạt, vẫn có thể xuất rank nhưng không gọi score là xác suất tuyệt đối.

#### 5.11. Model stale

Giải pháp:

- Tính `latest_matured_label_date = as_of_date - 120 trading sessions` bằng VNINDEX calendar.
- Rebuild label/dataset/splits đến cutoff mature gần nhất.
- Refit chỉ sau khi config đã được khóa.
- Không gán các outcome chưa mature thành negative.

### P3 - Strength/utility, chỉ sau khi core Ranker ổn định

Strength hiện không nên nằm trong primary path. Nếu mục tiêu sau này cần phân biệt positive yếu và positive mạnh, mở experiment riêng:

```text
C0: binary Ranker hiện tại
C1: Ranker Top-30 -> rerank bằng H120 conditional strength
C2: Ranker Top-30 -> rerank bằng unconditional continuous utility
C3: graded Ranker với relevance 0/1/2/3
```

Ưu tiên C2 hoặc C3 hơn việc tái sử dụng trực tiếp `p_strength_conditional` cũ.

Một định nghĩa có thể nghiên cứu:

```text
q_strength = E[quality | y_entry=1, X]
expected_utility = P(y_entry=1 | X) * q_strength
```

Không được hiểu `expected_utility` là expected return nếu target chưa được định nghĩa theo đơn vị return.

Chỉ giữ strength nếu:

- P@10, MAP@10 và NDCG@10 không giảm;
- realized excess return hoặc drawdown-adjusted utility tăng;
- paired date-block CI của utility gain dương;
- gain ổn định theo fold và seed.

## 6. Metric contract bắt buộc

Thứ tự ưu tiên:

1. `daily_precision_at_10_mean`.
2. `MAP@10` theo ngày.
3. `NDCG@10` theo ngày.
4. Worst-fold `lift@10`.
5. AP lift so với base rate.
6. Brier, log loss, ECE, calibration slope/intercept.
7. Turnover và cost-aware return sau statistical gate.

Quy tắc tính:

- Sort score giảm dần trong từng ngày.
- Tie-break theo symbol tăng dần.
- Tính Top-10 riêng từng ngày rồi mới lấy trung bình.
- So champion/challenger trên cùng tập ngày.
- Paired bootstrap theo date block, mặc định 2.000 samples, seed 238, CI 95%.
- Báo mean, median, standard deviation, worst fold và số ngày hiệu lực.

Research promotion gate tối thiểu:

- Lower bound CI 95% của delta P@10 lớn hơn `0`.
- Worst-fold lift@10 ít nhất `1.10`, ưu tiên ít nhất `1.20`.
- Không fold nào có bằng chứng rõ ràng lift@10 dưới `1`.
- Calibration không xấu hơn đáng kể nếu candidate xuất probability.
- Feature coverage và inference failure rate không xấu hơn champion.
- Kết quả tái lập với cùng data, config, seed và checksum.

## 7. Experiment matrix đề xuất

| ID | Thay đổi duy nhất | Mục đích |
|---|---|---|
| R0 | Frozen classifier champion | Reference, không retrain |
| R1 | Default stock-only pairwise Ranker | Tái lập E04 theo evaluator khóa |
| R2 | Giảm stochasticity | Đo seed variance |
| R3 | Robust hyperparameter selection | Tối ưu mean kèm worst-fold/dispersion penalty |
| R4 | Top-focused ranking challenger | Kiểm tra gain ở đầu danh sách |
| C0 | Static causal Platt | Probability baseline |
| C1 | Rolling causal Platt | Calibration drift |
| C2 | Regime-intercept calibration | Daily prevalence |
| U0 | Ranker-only | Utility baseline tương lai |
| U1 | Continuous-utility rerank trong Top-30 | Strength challenger sau cùng |

Không thay đồng thời feature group, label, objective và calibration trong cùng một experiment.

## 8. Lộ trình triển khai

### Phase A - Khóa correctness

- [x] Hoàn thiện H120 purge implementation và regression test.
- [x] Ghi exception policy cho corporate-action/adjusted-price khi thiếu nguồn point-in-time.
- [x] Khóa contract tái lập selection-bias audit; không coi thống kê cũ là audit mới khi snapshot không có trong workspace.
- [x] Giữ sector feature ngoài Ranker cho tới khi lineage sạch.
- [x] Đồng bộ experiment registry với E00-E08 và decision artifacts.

Trạng thái: Phase A đóng cho **research-only**. Corporate-action và industry
point-in-time lineage vẫn là production gate mở; xem
`reports/h120_improvement/data_audit/phase_a_closure.md`.

### Phase B - Tạo experiment generation mới

- [x] Khóa feature group `stock_primitives` (50 features, không market/sector/corporate-action).
- [x] Khóa binary H120 label; chưa thay bằng utility label hay conditional strength target.
- [x] Khóa folds, seeds, metrics và promotion gates trước khi train.
- [x] Cấm dùng fold 2024 để chọn config mới bằng protocol validator.
- [x] Đăng ký future holdout mới, outcome niêm phong.

Protocol: `configs/experiments/h120_ranker_generation_v2.yaml`; holdout:
`experiments/h120_improvement/E10_future_holdout/registration.json`. Chỉ Phase C
được chọn cấu hình trên các inner fold đã khóa; không được mở holdout để tuning.

### Phase C - Robust Ranker

- [~] Tái lập R1 — chờ snapshot dataset/feature đã pin.
- [~] Chạy R2 để giảm seed variance — pipeline tổng hợp đã sẵn sàng.
- [~] Chạy random search nhỏ cho R3 trên inner folds — tuner đã bị khóa protocol.
- [x] Báo mean/worst-fold/seed SD cho P@10, MAP@10, NDCG@10 và lift bằng artifact contract.
- [ ] Freeze config trước khi refit (chỉ sau R1–R3 hợp lệ).

Không dùng E04/E08 cũ để freeze cấu hình mới: chúng đã nhìn fold 2024. Runbook
và trạng thái input nằm ở `experiments/h120_improvement/E08_generation_v2/README.md`.

#### Checkpoint rerun 2026-08-24

- [x] R1/R2 đã chạy lại trên dataset `wave_dataset_continuation_h120_v3`, run
  `20260824T114000Z`, sử dụng `wave_continuation_h120_v3_eventweights`.
- [x] R2 seeds 238–242: mean daily P@10 `0.3731`, seed SD `0.0057`,
  worst-fold lift `1.3417`.
- [x] R3 hoàn tất 20 trials trên inner folds 2020–2023; trial 14 là candidate
  research: P@10 `0.3923`, paired delta `+0.1471`, bootstrap 95% CI
  `[+0.1019, +0.1914]`, worst-fold lift `1.5105`.
- [ ] Freeze config/refit vẫn chờ review quyết định nghiên cứu; không cấp
  quyền Phase E tự động.

Artifact: `experiments/h120_improvement/E08_generation_v2/rerun_summary.md`,
`R2/seed_summary.json`, `R3/summary.json` và
`R3_trial14_candidate/evaluation/metrics.json`.

#### Confirmation and freeze 2026-08-24

- [x] Trial 14 xác nhận lại trên seeds 238–242: mean P@10 `0.3915`, seed SD
  `0.0052`, worst-fold lift `1.3342`.
- [x] Lower bound 95% moving date-block CI của delta P@10 dương ở cả năm seed:
  `+0.0442` đến `+0.0673`.
- [x] Freeze config cho research-only Phase E tại
  `phase_c_selection_frozen.json`; một delta fold nhỏ nhất là `-0.0148`
  (seed 239/fold 2020), nhưng challenger không có fold lift dưới 1.
- [ ] Không xem confirmation này là outer/future promotion evidence vì toàn bộ
  phép chọn và xác nhận vẫn ở inner folds.

Artifact: `R3_trial14_candidate/seed_confirmation.json`.

### Phase D - Probability calibration

- [x] Fit calibrator chỉ bằng prior causal OOF folds (C0/C1/C2 đều có guard).
- [x] Chuẩn bị so C0-C2 trên cùng prediction artifact.
- [x] Khóa contract: rank từ `rank_score`, probability chỉ phục vụ risk/monitoring.
- [x] Nếu probability gate fail, giữ output ranking và đánh dấu probability chưa validated.

Runner: `scripts/run_h120_ranker_calibration.py`; config:
`configs/experiments/h120_ranker_calibration_generation_v2.yaml`. Việc chạy và
chọn calibrator chờ R1/R2/R3 có snapshot hợp lệ; không có ranking credit cho
calibration gain.

Hướng dẫn chạy snapshot local: `docs/h120_generation_v2_runbook.md`.

#### Checkpoint rerun 2026-08-24

- [x] Đã so C0–C2 trên OOF artifact của R3 trial 14.
- [x] C2 (`regime_intercept`) tốt nhất trong ba candidate: mean Brier `0.1621`,
  log loss `0.6918`, ECE `0.1465` trên 3 fold có prior causal outcomes.
- [x] Contract không đổi: C2 chỉ phục vụ probability/risk/monitoring; Top-10
  vẫn lấy duy nhất từ `rank_score`.

Artifact: `experiments/h120_improvement/E06_generation_v2/manifest.json`.

### Phase E - Refit và shadow

- [ ] Rebuild đến latest matured cutoff.
- [ ] Train final Ranker bằng config đã khóa.
- [ ] Xuất model manifest, feature schema, config/input/output checksum.
- [ ] Tích hợp daily batch scoring toàn universe.
- [ ] Chạy song song frozen champion và challenger; không trade.

**Trạng thái 2026-08-24: blocked đúng gate.** Evidence đã được ghi tại
`experiments/h120_improvement/E08_generation_v2/phase_c_decision_pending.json`,
nhưng candidate chưa được review/freeze. Preflight
`scripts/validate_h120_phase_e.py` fail-closed; chưa refit, chưa daily scoring,
chưa shadow challenger và không trade.

#### Checkpoint Phase E 2026-08-24

- [x] Refit frozen candidate với `110` boosted rounds trên 165,875 label rows
  mature; latest decision date `2026-02-09`, latest label-end `2026-08-06`.
- [x] Bundle có feature schema, config/input checksum và contract
  `rank_score_only`: `models/wave_ignition/h120_ranker_generation_v2_phase_e/`.
- [x] Chạy paired shadow snapshot 2026-08-11: challenger có 498 rows eligible,
  champion 505; Top-10 overlap `8/10`. Đây chỉ là monitoring không có label.
- [ ] Probability vẫn unvalidated, không được dùng ngoài risk/monitoring.
- [ ] Cần pin runtime champion về scikit-learn `1.7.0` hoặc export artifact
  portable; runtime `1.9.0` hiện cảnh báo khi unpickle LogisticRegression.

#### Demo operations checkpoint 2026-08-24

- [x] Frozen champion runtime pinned to `scikit-learn==1.7.0`; deterministic
  replay has identical probabilities, ranks and prediction-file SHA-256.
- [x] H120 orchestration now records both `snapshot_date` (download date) and
  effective `as_of_date` (last VNINDEX bar), and rejects stale source data.
- [x] Daily weekday scheduler runs sync → quality gates → features → frozen
  inference. A failed run retains the latest successful checksum-verified API
  artifact; API output is probability/advisory-only and trade-disabled.
- [x] Snapshot demo completed: `snapshot_date=2026-08-23`, effective market
  `as_of_date=2026-08-21`, frozen universe `1,512/1,512` (100% coverage),
  501 eligible rows and Top-10 output. Orchestration manifest:
  `runs/wave_h120_shadow/2026-08-23_20260824T141201Z/`;
  prediction SHA-256 `0f580360ca50db0539c36170e48fbd97ee353c39cfc53d9600b5ab286d139bfe`.
  This does not alter Phase F gates.

### Phase F - Future validation

- [ ] Chờ đủ 120 trading sessions cho label mature.
- [ ] Mở holdout đúng một lần bằng script có manifest.
- [ ] Chạy paired daily evaluation.
- [ ] Chỉ sau statistical gate mới chạy cost-aware backtest.
- [ ] Chỉ promotion khi statistical, calibration, cost và runtime gates cùng pass.

**Trạng thái 2026-08-24: blocked đúng gate.** Holdout đã đăng ký chỉ bắt đầu từ
phiên 2026-08-25, chưa có đủ 120 phiên mature. Preflight
`scripts/validate_h120_phase_f.py` xác nhận holdout vẫn sealed; không có nhãn
hay metric future holdout nào được mở.

## 9. Shadow monitoring

Trước khi label mature:

- input rows và số symbols;
- feature-ready, missing/non-finite/default counts;
- feature PSI so với training/recent window;
- rank-score distribution và concentration;
- Top-10 turnover và overlap với champion;
- unseen-symbol rate;
- inference latency, model checksum và deterministic replay.

Sau khi label mature:

- rolling P@10, MAP@10 và NDCG@10;
- base rate và lift;
- paired champion-challenger delta;
- Brier/ECE/calibration slope nếu có probability;
- segment metrics theo regime, liquidity và coverage.

## 10. Artifact contract cho challenger

```text
experiments/h120_improvement/<GENERATION>/<EXPERIMENT_ID>/
  experiment.yaml
  manifest.json
  feature_list.json
  fold_boundaries.csv
  model/
    ranker.json
    calibration.json
  predictions/
    oof_predictions.parquet
  audit/
    metrics.json
    fold_metrics.csv
    daily_top10.csv
    calibration_by_fold.csv
    segment_metrics.csv
    paired_vs_champion.json
    data_quality.json
```

Manifest tối thiểu phải ghi:

- experiment/parent IDs;
- git commit và dirty-worktree flag;
- data, feature, label, split và config checksums;
- train/calibration/validation boundaries;
- latest matured label date;
- feature group và model parameters;
- seeds và package versions;
- final-test access flag;
- promotion result và lý do pass/fail.

## 11. Những việc chưa nên làm

- Không thêm LSTM/trajectory model vào core H120 screening ở giai đoạn này.
- Không bật strength weight chỉ vì strength score có vẻ hợp lý về trực giác.
- Không ensemble classifier, Ranker và strength khi chưa có joint OOF evidence.
- Không dùng lại final test v3 hoặc fold 2024 để chọn model.
- Không mở full grid search trước khi evaluator/splits được khóa.
- Không thêm static sector features khi point-in-time lineage chưa sạch.
- Không gọi raw `rank_score` hoặc sigmoid đơn thuần là xác suất.
- Không overwrite frozen champion trước production approval.

## 12. Tiêu chí hoàn tất cuối cùng

Challenger chỉ được coi là đáp ứng mục tiêu khi:

- tạo Top-10 hằng ngày từ dữ liệu chỉ có tại thời điểm inference;
- vượt frozen champion trên future H120 holdout;
- lower CI 95% của paired delta P@10 dương;
- worst-regime/fold lift đạt gate;
- probability calibration đạt gate nếu được công bố;
- cost-aware outcome tốt hơn champion;
- inference deterministic, feature coverage và latency đạt yêu cầu;
- shadow ổn định trong thời gian đã đăng ký;
- có production approval record riêng.

## 13. Tài liệu và artifact tham chiếu

- `docs/h120_improvement_execution_plan.md`
- `docs/h120_shadow_inference.md`
- `docs/wave_trend_prediction_pipeline.md`
- `experiments/h120_improvement/baseline_lock.json`
- `experiments/h120_improvement/E03_feature_ablation/F1_stock_primitives/metrics.json`
- `experiments/h120_improvement/E04_ranker_vs_f1/decision.md`
- `experiments/h120_improvement/E08_outer_evaluation_2024/decision.md`
- `configs/experiments/h120_ranker_stock_primitives_v1.yaml`
- `configs/experiments/h120_ranker_stock_primitives_e08_outer2024_v1.yaml`
- `src/training/h120_ranker.py`
- `src/evaluation/wave_model.py`
