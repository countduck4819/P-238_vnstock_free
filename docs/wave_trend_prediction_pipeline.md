# Pipeline dự đoán xu hướng Wave

## 1. Mục tiêu và phạm vi

Pipeline này xếp hạng các cổ phiếu có khả năng hình thành và duy trì một xu
hướng tăng có thể hành động được. Hệ thống trả lời ba câu hỏi riêng biệt:

1. **Onset/H20:** cổ phiếu có đang bước vào một sóng tăng đáng chú ý không?
2. **Continuation H60/H120:** sau tín hiệu ban đầu, xu hướng có khả năng tiếp
   tục trong trung và dài hạn không?
3. **V6 pre-breakdown trend:** xu hướng lớn có khả năng tiếp tục hình thành
   trước khi một structural breakdown được xác nhận không?

Đầu ra của pipeline là xác suất xu hướng, điểm xếp hạng và danh sách Top-K.
Pipeline **không dự đoán một mức giá tương lai cụ thể**. Một mô hình dự báo
return/giá, chẳng hạn LSTM, phải là nhánh độc lập và chỉ được ghép ở tầng quyết
định sau cùng.

## 2. Luồng tổng thể

```text
OHLCV + market/sector context
            |
            v
  Data audit và quality gates
            |
            v
      Feature Store v2
            |
            v
      H20 onset detector ------------------------+
      Continuation H60/H120 ---------------------+--> Causal cascade model
      Original V6 pre-breakdown trend ------------+    trên toàn bộ universe
                                                         |
                                                         v
                                               |
                                       p_cascade probability estimate
                                       (calibration phải được audit)
                                                |
                                                v
                                  Shortlist Top-10 bằng p_cascade
                              (strength post-ranking chỉ research)
                                               |
                                               v
                                     Portfolio tối đa 3 vị thế
```

Các stage có thể dùng chung dữ liệu gốc và feature store, nhưng mỗi stage có
label, model, metric và trách nhiệm riêng. Không dùng một label chung cho toàn
bộ pipeline.

## 3. Hợp đồng dữ liệu đầu vào

Mỗi observation được định danh bằng khóa `(symbol, date)`. `date` là thời điểm
ra quyết định sau khi thị trường đóng cửa; giao dịch giả định sớm nhất tại giá
mở cửa phiên kế tiếp. Mọi feature tại ngày `t` chỉ được sử dụng thông tin có
sẵn đến hết ngày `t`.

Dữ liệu tối thiểu gồm:

- OHLCV theo ngày của từng cổ phiếu.
- Chuỗi giá và thanh khoản của benchmark thị trường.
- Phân loại ngành và chuỗi đại diện ngành khi khả dụng.
- Lịch giao dịch để đo coverage theo phiên thay vì ngày dương lịch.
- Thông tin corporate action hoặc chính sách giá đã được xác minh.

### 3.1. Chính sách giá

Toàn bộ OHLC phải dùng nhất quán một trong hai chính sách:

- `raw`: giá chưa điều chỉnh; corporate action phải được nhận diện và xử lý
  bằng quality gate/cooldown phù hợp.
- `adjusted`: lịch sử giá đã điều chỉnh nhất quán theo cùng một nguồn và cùng
  một quy tắc.

Không được train hoặc promote model khi policy vẫn là
`provider_default_unverified`. Việc sửa metadata không đồng nghĩa với việc đã
biến đổi giá; policy chỉ được đổi sau khi có bằng chứng từ provider và kiểm tra
chéo các sự kiện corporate action.

### 3.2. Data quality gates

Trước khi tạo feature, pipeline kiểm tra:

- Thiếu hoặc trùng `(symbol, date)`.
- Giá không hữu hạn, không dương hoặc OHLC không nhất quán.
- Volume âm, zero-volume kéo dài hoặc phiên stale.
- Coverage lịch sử tối thiểu cho cửa sổ 5/20/60/120 phiên.
- Gap lớn có thể liên quan corporate action.
- Dữ liệu tương lai có đủ coverage để tạo label hay không.

Không forward-fill giá hoặc volume qua các phiên thiếu. Mẫu không đủ lịch sử
giữ `NaN` và bị loại bởi eligibility gate thay vì được điền bằng thông tin có
thể gây sai lệch.

## 4. Feature Store v2

Feature store là lớp dùng chung cho các model xu hướng. Feature được tính theo
nguyên tắc point-in-time và gồm các nhóm chính:

- Return/momentum ở cửa sổ 5, 20, 60 và 120 phiên.
- Trend slope, độ bền xu hướng và `R²`.
- Volatility, true range, ATR và drawdown lịch sử.
- Volume ratio, turnover, thanh khoản và độ bất thường của volume.
- Vị trí giá so với moving average, nền giá, đỉnh/đáy và breakout.
- Relative strength so với thị trường và ngành.
- Market/sector regime và độ rộng thị trường khi khả dụng.
- Coverage, stale-session và corporate-action eligibility flags.

Feature store không tạo quyết định giao dịch. Nó chỉ tạo bảng feature đã được
version hóa cùng manifest, cấu hình, input checksum và báo cáo chất lượng.

Hợp đồng thời gian:

```text
feature cutoff  = close của ngày t
decision time   = sau close ngày t
earliest entry  = open ngày t+1
future label    = bắt đầu từ entry_lag = 1
```

## 5. Stage A — H20 onset và original V6 trend

### 5.1. Trách nhiệm

H20 phát hiện tín hiệu khởi phát ngắn hạn và cung cấp một bằng chứng onset cho
các challenger. H20 không còn là hard gate hoặc input của candidate v4 vì target
của nó là `y_entry`, không phải target continuation `y_cont_h120` của cascade.
Original V6 giải một bài toán khác: xác suất một early major wave được xác nhận
trước khi structural breakdown được xác nhận. Hai score phải được giữ riêng:

```text
p_h20       = xác suất khởi phát trong horizon H20
p_v6_trend  = bằng chứng xu hướng lớn trước structural breakdown, horizon mở
```

Không dùng tên `p_surge` cho cả hai ý nghĩa trong artifact mới. Loader vẫn chấp
nhận `p_surge` như alias legacy của `p_v6_trend` để đọc artifact cũ.

### 5.2. Original V6 import

V6 import gốc là stock expert ensemble XGBoost, LightGBM và CatBoost với target
`unbounded_early_major_wave_vs_confirmed_structural_breakdown`. Trọng số ensemble
được học trên snapshot; model yếu có thể nhận trọng số 0. Công thức cố định dưới
đây chỉ là legacy reproduction, không còn là mặc định production:

```text
p_v6_trend_legacy = 0.15 * p_xgb + 0.45 * p_lgb + 0.40 * p_cat
```

H1/H2/H3 (technical hard gate và logistic fusion) bị loại khỏi promotion path
vì chưa chứng minh downstream lift ổn định. Chúng chỉ được giữ làm experiment
lịch sử; original V6 được train trực tiếp bằng `train_model_6_imported_original.py` nhưng chỉ là
challenger cho đến khi có deployment artifact độc lập và vượt downstream gate.

#### Replay bản import gốc ngày 2026-08-24

Bốn file import mới đã được kiểm tra theo SHA-256. Chỉ
`check_prediction_correlation.py` trùng hoàn toàn với
`scripts/wave_v6/check_prediction_correlation.py`, nên bản ở root đã được xóa;
`docs/guide/HUONG_DAN_TRAIN_V6_IMPORTED_ORIGINAL.md`,
`scripts/wave_v6/train_model_6_imported_original.py` và
`scripts/wave_v6/vnstock_data_adapter_v3_imported_original.py` khác
nội dung nên được giữ lại để đánh giá bản import.

Đã chạy `scripts/wave_v6/train_model_6_imported_original.py` trên `data/vnstock/v6_snapshot`, policy
`adjusted`, với `--allow-stale-cache`, `--trials 15` và `--top-n 50`. Run hoàn tất
trên CPU trong khoảng `315.61` giây. Artifact nằm tại
`models_wave_v6/evaluation_bundle.joblib` và `reports_wave_v6/evaluation_report.json`.

Final holdout của run này có `13,079` dòng, `51` ngày, `ranking_k=50`, từ
`2024-08-05` đến `2025-08-06`. Ensemble (trọng số XGBoost `0.55`, CatBoost
`0.45`, LightGBM `0.0`) đạt:

| PR-AUC | ROC-AUC | Brier | Precision | Recall | F1 | Top-50 precision | Lift@50 |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.4868 | 0.7259 | 0.2014 | 0.4799 | 0.8874 | 0.6229 | 0.5655 | 1.602x |

Đây là benchmark final holdout riêng của bản import, không thay thế causal
anchor OOF tại `eval/runs/wave_v6_original_anchor_prod_v1/` và không được dùng
để chọn lại cascade. Hai kết quả không so sánh trực tiếp theo từng điểm vì
khác population, cửa sổ đánh giá và anchor export; Top-50 cũng không phải
Top-10 của cascade.

### 5.3. Candidate pool nghiên cứu

Candidate pool theo `p_h20` vẫn được đo như một policy nghiên cứu, với K ∈
{50, 100, 200}, nhưng không còn là hard gate production. Nếu cần giới hạn chi
phí inference, pool phải được bật tường minh và đánh giá recall trên
`y_cont_h120` (artifact legacy dùng alias `y_actionable`); mặc định cascade
score toàn bộ universe.

## 6. Stage B — Continuation H60/H120

### 6.1. Trách nhiệm

Continuation dự đoán xác suất xu hướng vẫn duy trì sau tín hiệu ban đầu. Model
không dự đoán giá tuyệt đối; nó phân loại một trạng thái tương lai được định
nghĩa bởi return, excess return và drawdown.

Hai horizon được giữ riêng:

- `p_h60`: continuation trung hạn trong 60 phiên.
- `p_h120`: continuation dài hạn trong 120 phiên.

H20 và V6 là hai model độc lập. Không suy diễn `p_h60` hay `p_h120` chỉ bằng
cách kéo dài xác suất H20 hoặc V6.

### 6.2. Nhãn H60

Một mẫu H60-positive phải thỏa đồng thời các ràng buộc chính:

```text
horizon                     = 60 phiên
entry_lag                   = 1 phiên
minimum_excess_return       = 5%
minimum_terminal_return     = 0%
maximum_drawdown            = -15%
minimum_future_coverage     = 90%
```

Ngưỡng excess return còn được điều chỉnh theo volatility với multiplier `0.50`.
Mẫu không đủ coverage hoặc không đủ quan sát volatility là unresolved, không
được ép thành negative.

### 6.3. Nhãn H120

Một mẫu H120-positive áp dụng logic tương tự với ngưỡng dài hạn:

```text
horizon                     = 120 phiên
entry_lag                   = 1 phiên
minimum_excess_return       = 8%
minimum_terminal_return     = 0%
maximum_drawdown            = -20%
minimum_future_coverage     = 90%
```

H120 nhiễu hơn H60 nên được đánh giá cả calibration và ranking/Top-K, không chỉ
dựa vào threshold classification.

### 6.4. Model

Baseline hiện tại dùng XGBoost riêng cho H60 và H120. Hai model có thể dùng
cùng feature store nhưng phải có artifact, calibration và OOF predictions
riêng. Việc tách model giúp mỗi horizon học pattern và base rate riêng.

## 7. Stage C — Breakdown audit (không thuộc production prediction)

### 7.1. Trách nhiệm

Breakdown chỉ còn là audit outcome để đo xem shortlist sau đó có trải qua một
sự phá vỡ cấu trúc hay không. Nó không phải input, hard gate hay probability
head của production cascade. Không continuation đủ mạnh cũng không đồng nghĩa
với breakdown nghiêm trọng.

Đầu ra audit dự kiến gồm:

- `breakdown_state`.
- `breakdown_trigger_date` và `breakdown_confirmation_date`.
- `recovery_date`, nếu trigger được xác định là false breakdown.
- `time_to_breakdown`, drawdown và recovery return.

### 7.2. Ý nghĩa “phá vỡ cấu trúc”

Label breakdown xét kết hợp drawdown sâu, return kém và sự suy yếu có cấu trúc
của đường giá. Ví dụ cấu hình H60 hiện tại sử dụng:

```text
structural_failure_drawdown = -35%
failure_max_return_60       = -15%
failure_max_slope_60        = -0.0008
failure_min_r2_60           = 0.20
minimum_observed_ratio      = 90%
```

Mục tiêu là phân biệt biến động bình thường với một xu hướng giảm đủ sâu và đủ
có cấu trúc để làm vô hiệu giả thuyết continuation.

### 7.3. Research history

XGBoost breakdown heads H60/H120 đã được thử nhưng không nằm trong production vì
ablation làm giảm AP và Top-K precision. Artifact continuation-only hiện tại
không dùng breakdown labels để tạo target; các label này chỉ được giữ cho offline
risk audit. Outcome chưa resolved phải giữ `CENSORED_UNRESOLVED`, không ép thành
breakdown hoặc no-breakdown.

### 7.4. Redundancy audit và contract mới đề xuất

Audit trên frame aligned `63,438` dòng cho kết quả:

```text
y_cont_h120 positive                         = 10,775
y_actionable positive                        = 10,775
continuation-positive bị breakdown loại      = 0
số dòng y_cont_h120 khác y_actionable         = 0
break_h60 positive                            = 4,772
break_h120 positive                           = 10,942
break_h60 nhưng không break_h120              = 0
```

Nguyên nhân là continuation H120 đã giới hạn maximum drawdown ở `-20%`, trong
khi breakdown hiện chỉ được xác nhận từ drawdown `-35%` cùng xu hướng giảm có
cấu trúc. Vì vậy một mẫu continuation-positive không thể đồng thời là breakdown
theo contract hiện tại. Điều kiện breakdown trong `y_actionable` không thay đổi
target và chỉ làm pipeline phức tạp hơn.

Contract được đề xuất cho lần rebuild kế tiếp:

```text
target cascade chính = y_cont_h120
breakdown prediction = không dùng
breakdown labels      = chỉ dùng cho offline risk audit
```

Breakdown audit nên dùng một state machine duy nhất:

```text
NORMAL
  -> TRIGGERED
       -> CONFIRMED_BREAKDOWN
       -> RECOVERED_FALSE_BREAKDOWN
       -> CENSORED_UNRESOLVED
```

Một cú giảm chỉ là trigger. Nó chỉ thành `CONFIRMED_BREAKDOWN` khi sự phá vỡ duy
trì đủ lâu theo điều kiện point-in-time đã khóa. Nếu giá nhanh chóng lấy lại vùng
cấu trúc và hình thành xu hướng tăng, trạng thái là
`RECOVERED_FALSE_BREAKDOWN`. Nếu cổ phiếu chỉ tích lũy ở nền thấp rồi breakout
mà trước đó không phá vỡ một cấu trúc tăng hợp lệ, đó không phải breakdown giả.
Một đợt tăng xuất hiện rất lâu sau breakdown đã xác nhận được xem là một episode
/sóng mới, không hồi tố breakdown cũ thành false.

Artifact continuation-only mới `wave_cascade_prod_v3_continuation` đã ghi target
chính thức `y_cont_h120`. Artifact `wave_cascade_prod_v2` và lock cũ chỉ được giữ
làm legacy comparison; metric hai run giống hệt nhau vì hai cột target có giá trị
giống nhau trên toàn bộ frame.

## 8. Stage D — Causal cascade

### 8.1. Input

Research candidate v4 hiện chỉ nhận xác suất continuation H120 đã được tạo
point-in-time:

```text
p_h120
```

H120 vừa là anchor population vừa là head duy nhất trong contract v4. Kiến trúc
bốn head V6/H20/H60/H120 của candidate v3 được giữ làm lịch sử nhưng đã bị loại
sau causal-OOF ablation: H20 và H60 không tạo incremental lift ổn định, còn
original V6 chưa có deployment artifact đúng lineage. Khi V6 gốc có artifact
deployable độc lập, nó phải được đánh giá lại như một challenger, không tự động
đưa trở lại candidate.

### 8.2. Target tổng hợp

Target của artifact production hiện tại là `y_cont_h120`:

```text
y_cont_h120 = continuation label trong 120 phiên
```

Breakdown labels không còn là điều kiện bắt buộc của target cascade. Mẫu
`y_cont_h120` chưa resolved vẫn là unknown và bị loại khỏi cascade training;
không mặc định unknown là “an toàn”.

Redundancy audit ở mục 7.4 chứng minh migration không làm thay đổi giá trị target
hay metric; nó chỉ loại dependency breakdown khỏi contract production.

### 8.3. Meta-model

Meta-model research v4 là logistic regression (`C = 1.0`,
`positive_class_weight = 1.0`) trên duy nhất `p_h120`; vai trò chính là cung cấp
contract, calibration artifact và threshold nhất quán. Ranking vì vậy không còn
bị các head onset/continuation ngắn hạn làm nhiễu. Model không dùng phép nhân xác
suất cố định làm probability production.

`HistGradientBoosting` và các positive-class weight khác chỉ là ablation research.
Trên aligned causal OOF, HGB không vượt Logistic; positive weight `2.0` chỉ tăng
calibrated AP từ `0.1343` lên `0.1353` và Top-10 precision từ `0.2603` lên
`0.2641`, chưa đủ để thay baseline trước final holdout.

Công thức trực giác vẫn có thể hình dung là:

```text
trend evidence  = continuation H120
target          = continuation H120
breakdown risk  = offline audit, không phải input probability
p_cascade       = probability mapping(trend evidence -> continuation)
```

Logistic meta-model cho phép học trọng số và tổ hợp tuyến tính phù hợp từ
OOF data. Output là probability estimate; không được gọi là calibrated
probability nếu chưa có artifact calibrator hoặc calibration audit đủ bằng
chứng.

### 8.4. Missing head

Base heads có thể thiếu score do khác coverage/fold. Missing phải được biểu diễn
theo policy đã học từ OOF hoặc explicit missing indicator. Không được điền bằng
giá trị suy ra từ final test hay toàn bộ lịch sử.

Lưu ý implementation hiện tại: `train_h120_cascade.py` loại các cột có toàn bộ
giá trị NaN trước khi fit. Vì vậy một head không overlap population sẽ bị bỏ
khỏi schema thay vì được giữ bằng missing indicator. Candidate v4 bắt buộc đúng
schema một head `p_h120`; challenger nhiều-head phải fail-closed khi thiếu head,
trùng artifact hoặc có probability columns trùng số trên batch đủ lớn.

### 8.5. Contract nhãn và ranking sau khi sửa lỗi

Canonical breakdown labels được dựng độc lập với OOF prediction tables trên
snapshot clean, với `sampling_stride=1`. Frame continuation-only hiện tại
`eval/runs/wave_cascade_prod_v2_continuation/oof_frame.parquet` có `63,438` dòng
và target `y_cont_h120`. Breakdown labels chỉ còn là metadata/audit; chúng không
được dùng làm feature hoặc dependency bắt buộc của cascade.

Các dòng chưa có nhãn vẫn có thể được score/rank trong toàn bộ universe; chỉ
những dòng có target resolved mới được dùng cho AP, precision, recall, Brier,
Top-K precision và candidate recall. Điều này ngăn metric bị thổi phồng do
lọc unknown trước khi xếp hạng.

## 9. Strength và ranking

Strength chưa được dùng để sửa `p_cascade`, vì làm vậy sẽ thay đổi calibration.
Nó chỉ được áp dụng sau cascade để sắp thứ tự shortlist:

```text
strength_rank_score = mean(strength_h60, strength_h120)

p_rank = p_cascade * (
    1 + strength_weight * (strength_rank_score - 0.5) * 2
)
```

Cấu hình production hiện tại:

```text
strength_weight = 0.0
missing strength = 0.5  # neutral
```

`strength_weight = 0.25` đã được thử trên aligned causal OOF và làm Top-10
precision giảm từ `0.2603` xuống `0.1962`, vì vậy không được promotion. Đưa
strength trực tiếp vào meta-model làm AP tăng (`0.1508`) nhưng Top-10 precision
giảm còn `0.2218`; hướng này cũng giữ ở research.

Do đó:

- `p_cascade` dùng cho PR-AUC, Brier score, calibration và threshold.
- `p_rank` chỉ dùng để sắp thứ tự cơ hội.

## 10. Quy tắc chọn Top-K

Pipeline production có một tầng cascade, một shortlist và một tầng portfolio:

1. **Full-universe cascade:** kết hợp `p_h20`, `p_h60`, `p_h120` và
   `p_v6_trend` trên toàn bộ universe đủ điều kiện.
2. **Top-10 shortlist:** xếp toàn bộ universe bằng `p_cascade` trong production.
   `p_rank`/strength adjustment chỉ được dùng cho ablation research.
3. **Tối đa 3 vị thế:** tầng portfolio áp dụng thêm giới hạn vốn, thanh khoản,
   ngành, tương quan và turnover.

Top-50 theo `p_h20` chỉ là compatibility/research audit, không được loại mã
trước cascade trong production mặc định.

Các giá trị 5, 10 và 20 được thử trên causal OOF; Top-10 là shortlist mặc định.
Không thay K dựa trên final holdout.

## 11. Training không leakage

### 11.1. Base models

Mỗi base model phải tạo OOF prediction bằng split theo thời gian. Prediction tại
một fold chỉ được tạo từ model train trên các giai đoạn trước đó. Final holdout
không được dùng để:

- chọn feature;
- chọn horizon hoặc label threshold;
- tune model/hyperparameter;
- chọn calibration/decision threshold;
- chọn Top-K;
- chọn trọng số strength.

### 11.2. Cascade

Cascade chỉ train trên OOF predictions của các base heads. Nếu cascade được
train trên in-sample prediction, nó sẽ học confidence quá mức của base models
và metric downstream bị lạc quan giả.

Threshold deployment được lấy từ causal OOF, hiện là threshold của fold causal
cuối cùng. Sau khi khóa model và threshold, final holdout chỉ được mở để báo
cáo, không dùng để selection. Nhánh nào đã từng mở holdout phải ghi
`final_holdout_observed_not_promoted` và không được coi là pristine nếu tiếp tục
tinh chỉnh.

### 11.3. Purging và embargo

Các sample gần biên fold có future-label window chồng sang validation phải bị
purge theo `label_end_date`. Config hiện tại dùng `embargo_sessions: 5` như
buffer bổ sung sau ranh giới purge; 5 phiên không thay thế cho việc purge theo
horizon H60/H120. Quy tắc này phải được giữ nhất quán ở mọi split.

## 12. Inference hằng ngày

Tại ngày giao dịch `t`, pipeline thực hiện:

1. Đồng bộ dữ liệu đến close ngày `t` và ghi source manifest.
2. Chạy OHLCV/data-quality audit.
3. Tạo feature v2 chỉ bằng dữ liệu đến `t`.
4. Loại các mã không đủ eligibility, stale hoặc nằm trong corporate-action
   cooldown theo policy.
5. H20 onset model tính `p_h20` cho toàn bộ universe đủ điều kiện.
6. Continuation models tính `p_h60` và `p_h120` cho cùng population.
7. Original V6 tính `p_v6_trend` cho cùng population.
8. Cascade kết hợp onset, continuation và V6 trend thành `p_cascade` trên
   toàn bộ universe; không áp dụng H20 hard gate.
9. Không chạy breakdown prediction heads trong production; canonical breakdown
   labels chỉ được dùng offline để audit rủi ro và state transition.
10. Production không chạy strength post-ranking; `p_rank` chỉ tồn tại trong
    research ablation và không sửa probability gốc.
11. Chọn Top-10 shortlist; portfolio layer chọn tối đa 3 vị thế.
12. Ghi predictions, feature version, model version, threshold, ranking reason
    và các quality flags để audit.

## 13. Metrics theo từng tầng

### 13.1. Onset H20 và original V6

- PR-AUC/average precision và lift so với base rate.
- Recall của `y_entry` để đánh giá đúng nhiệm vụ onset H20.
- Candidate Top-K recall của `y_cont_h120` chỉ là audit policy tùy chọn, không
  phải promotion gate production. Artifact legacy dùng `y_actionable`, có giá
  trị giống hệt trên frame hiện tại.
- Brier score/calibration nếu score được dùng như probability.
- V6 được đánh giá riêng trên target pre-breakdown gốc; không trộn metric V6
  với metric H20 vì base rate và horizon khác nhau.

Nếu bật candidate pool nghiên cứu, recall của pool phải được theo dõi vì lỗi
false-negative tại pool không thể được các stage sau phục hồi. Với production
full-universe, không có bước lọc H20 trước cascade; recall được đánh giá ở
ranking Top-K cuối cùng.

### 13.2. Continuation và breakdown audit

- PR-AUC theo từng horizon.
- Brier score và calibration curve.
- Precision, recall và F1 tại threshold OOF đã khóa.
- Daily Precision@K và lift.
- Stability theo fold, năm, regime, thanh khoản và ngành.
- Tỷ lệ `CONFIRMED_BREAKDOWN` trong Top-K tại H60/H120.
- Tỷ lệ `RECOVERED_FALSE_BREAKDOWN` và thời gian reclaim cấu trúc.
- Time-to-breakdown và drawdown trước/sau trigger.

PR-AUC H120 có thể thấp hơn do horizon dài và label nhiễu. Không đánh giá model
chỉ theo độ lớn PR-AUC; luôn so với base rate và kiểm tra Top-K/lift/calibration.

### 13.3. Cascade tổng thể

- `average_precision` của `y_cont_h120`; `y_actionable` chỉ là tên target legacy
  được giữ để đối chiếu các artifact cũ.
- ROC-AUC để tham khảo, không phải metric chọn chính khi class imbalance cao.
- Brier score và reliability/calibration.
- Precision/recall/F1 tại threshold đã khóa.
- Candidate recall của Top-50.
- Shortlist precision và lift của Top-10.
- Số khuyến nghị trung bình mỗi ngày.
- Coverage và tỷ lệ unresolved bị loại.

### 13.4. Metrics kinh tế ngoài model

Sau khi xác nhận prediction metrics, backtest point-in-time cần báo cáo:

- Forward return/excess return của Top-K.
- Hit rate và payoff ratio.
- Max drawdown, Sharpe/Sortino.
- Turnover, transaction cost và slippage.
- Exposure theo ngành, thanh khoản và market regime.

Các metric kinh tế không thay thế calibration/PR-AUC; chúng kiểm tra xem khả
năng xếp hạng có chuyển thành giá trị giao dịch sau chi phí hay không.

## 14. Promotion gates

Một candidate chỉ được promote khi thỏa toàn bộ nhóm điều kiện:

- Data policy đã xác minh; không còn `provider_default_unverified`.
- Không phát hiện leakage hoặc lỗi point-in-time join.
- OOF PR-AUC/lift đạt tiêu chí so với baseline đã khóa.
- Full-universe cascade không được làm mất coverage; nếu bật candidate pool
  tùy chọn thì phải báo cáo recall@K và được kiểm tra riêng.
- Top-10 precision/lift cải thiện ổn định qua nhiều fold.
- Brier score và calibration không suy giảm vượt ngưỡng cho phép.
- Kết quả không phụ thuộc vào một năm, một regime hoặc một nhóm thanh khoản.
- Final holdout chỉ được dùng sau khi cấu hình đã đóng băng.
- Backtest sau phí không làm mất toàn bộ improvement của ranking.

Nếu một stage cải thiện metric cục bộ nhưng làm giảm candidate recall hoặc
Top-10 cascade, stage đó không được promote.

## 15. Ranh giới với mô hình dự báo giá/return

Một nhánh LSTM trong tương lai nên dự đoán phân phối return hoặc excess return,
chẳng hạn `q10/q50/q90` cho H20/H60. Nhánh đó không thay label continuation và
không sửa `p_cascade` trực tiếp.

```text
Trend branch                         Return branch
p_h20 + p_v6_trend                  expected/quantile return
p_continuation                       downside/uncertainty
       |                                      |
       +------------ Decision layer ----------+
                          |
                     final ranking
```

Trend branch trả lời “xác suất cấu trúc tiếp tục là bao nhiêu”; return branch
trả lời “upside/downside kỳ vọng là bao nhiêu”. Hai nhánh dùng chung cutoff và
split thời gian nhưng có label và metrics riêng.

## 16. Bản đồ implementation hiện tại

- Feature store: `configs/wave_ignition_features_v2.yaml`,
  `src/features/wave_ignition.py`, `scripts/build_wave_ignition_features.py`.
- Clean input builder: `scripts/build_clean_training_inputs.py`; production
  research lineage hiện dùng `data/vnstock/v6_snapshot` qua
  `--input-layout v6_snapshot`, không dùng trực tiếp baseline
  `data/vnstock/daily`.
- V6 shadow/legacy trend: `configs/wave_ignition_xgboost_v6_trend20.yaml`,
  `scripts/wave_v6/train_v6_original_shadow.py`; không ảnh hưởng ranking production.
- Continuation H120: `src/labels/continuation.py`,
  `configs/wave_continuation_labels_h120_v2.yaml`,
  `configs/wave_continuation_training_splits_h120.yaml`,
  `configs/wave_continuation_xgboost_h120.yaml`.
- Cascade frame: `scripts/build_h120_cascade_frame.py`.
- Cascade training: `scripts/train_h120_cascade.py`.
- Cascade model/evaluation: `src/models/wave_cascade.py`,
  `src/evaluation/wave_cascade.py`, `scripts/evaluate_h120_cascade.py`.
- Research candidate v4 policy:
  `configs/experiments/wave_cascade_v4_h120_only.yaml`.

Các config H60, breakdown, H1/H2/H3, multihorizon, strength, feature-ablation,
H150 và các bản legacy v1/v2 không còn nằm trong active config set; chỉ khôi
phục khi mở lại nhánh research tương ứng.

## 17. Artifact tối thiểu của mỗi run

Mỗi run phải lưu:

```text
model_manifest.json
model/<model artifact>
predictions/oof_predictions.parquet
predictions/final_test_predictions.parquet  # chỉ khi được phép mở final
audit/metrics.json
audit/fold_metrics.csv
feature/data source checksums
label, split, feature và model config versions
```

Manifest phải đủ để trả lời: dữ liệu nào, policy giá nào, cutoff nào, feature
version nào, model nào, fold nào, threshold nào và prediction được tạo theo
OOF hay final mode.

## 18. Trạng thái triển khai

Cập nhật gần nhất: **2026-08-23**.

Quy ước:

- `[x]`: đã hoàn thành và có artifact/test làm bằng chứng.
- `[~]`: đã có code hoặc run research nhưng chưa đạt promotion gate.
- `[ ]`: chưa hoàn thành.

### 18.1. Tiến độ theo stage

| Stage | Trạng thái | Bằng chứng và kết luận hiện tại |
|---|---|---|
| Data ingestion và quality gates | `[~]` | `data/vnstock/v6_snapshot` có 1,512/1,512 mã, coverage `1.0`, policy `adjusted`; clean audit snapshot loại 2,980 dòng ngoài VNINDEX calendar và không còn lỗi OHLCV. Vẫn cần report corporate-action tái lập toàn universe. |
| Feature Store v2 | `[x]` research | Snapshot run `20260823T050008Z` build 1,800,494 rows/1,512 mã, 83 features, không non-finite/duplicate; policy `adjusted`, `promotion_status: candidate_for_training`. Feature ablation B/C/D/F vẫn chưa thay baseline. |
| Stage A1 — Onset H20 | `[x]` research challenger | Snapshot XGB run `20260823T052616Z` có causal OOF/model, AP `0.08824` trên base rate `0.04142`. Anchor re-export `models/wave_ignition_snapshot/xgboost_wave_h20_anchor/xgboost_wave_v1/runs/20260823T105312Z` đạt `63,438` dòng/`130` ngày và coverage `100%` trên population H120. Head này bị loại khỏi candidate v4 sau downstream ablation; giữ làm onset challenger độc lập. |
| Stage A2 — Original V6 trend | `[~]` research | Replay bản import root ngày 2026-08-24 đã hoàn tất trên snapshot `adjusted`: final holdout `13,079` dòng/`51` ngày, ensemble PR-AUC `0.4868`, ROC-AUC `0.7259`, precision `0.4799`, recall `0.8874`, F1 `0.6229`, Top-50 precision `0.5655`, Lift@50 `1.602x`; chỉ mang tính benchmark mô tả vì là holdout riêng và không có causal OOF cùng schema. Anchor OOF production-v1 tại `eval/runs/wave_v6_original_anchor_prod_v1/anchor_oof_predictions.parquet` vẫn có `63,438` dòng/`130` ngày và `100%` `p_v6_trend`, là lineage dùng cho cascade. H1/H2/H3 đã bị loại khỏi production path. |
| Stage B — Continuation H60 | `[x]` research | Snapshot run `20260823T052724Z` có label/dataset, causal OOF và model artifact; AP `0.23166` trên base rate `0.17290`, temporal calibration audit `ok`. Không mở final holdout mới. |
| Stage B — Continuation H120 | `[x]` research | Snapshot run `20260823T052814Z` có label/dataset, causal OOF và model artifact; AP `0.22819` trên base rate `0.16985`, temporal calibration audit `ok`. Không mở final holdout mới. |
| Stage C — Breakdown H60 | `[~]` model chưa đạt | Snapshot run `20260823T053033Z` có dataset/model. AP `0.10302` trên base rate `0.09824`, ROC-AUC `0.54465`; improvement nhỏ, chưa đủ điều kiện production. |
| Stage C — Breakdown H120 | `[~]` model chưa đạt | Snapshot run `20260823T053054Z` có dataset/model. AP `0.12318` thấp hơn base rate `0.17955`, ROC-AUC `0.23703`; chưa đủ điều kiện production. |
| Stage D — Causal cascade | `[~]` research candidate, cần holdout mới | Candidate v4 tại `models/wave_ignition_snapshot/wave_cascade_research_v4_h120_only/runs/20260823T170819Z` dùng Logistic `C=1`, chỉ `p_h120`, full-universe, strength `0.0`, không breakdown. Raw causal OOF: AP `0.1942`, ROC-AUC `0.5909`, Top-10 precision `0.2864`; calibrated OOF 78 ngày: AP `0.1424`, Top-10 precision `0.2564`; audit fold 2024: AP `0.2871`, ROC-AUC `0.7011`, Top-10 precision `0.4308`, lift `2.77x`. Candidate được chọn hoàn toàn bằng causal OOF và khóa tại `experiments/baselines/wave_cascade_research_v4_h120_only_lock.json` với trạng thái `research_candidate_requires_new_holdout`; chưa được promote. Candidate v3 bốn-head bị reject và chỉ giữ làm lịch sử. |
| Cascade meta-model/head ablation | `[x]` causal-OOF selection | Đã thử HGB, positive class weight `2.0`, strength và bảy contract head. So với bốn-head, H120-only tăng raw AP `0.1930 -> 0.1942`, ROC-AUC `0.5505 -> 0.5909`, calibrated AP `0.1343 -> 0.1424`, và Top-10 fold 2024 `0.4000 -> 0.4308`. V6+H120 có calibrated Top-10 trung bình cao hơn (`0.2974`) nhưng fold 2024 thấp hơn (`0.4077`) và thiếu V6 deployment artifact đúng lineage, nên không được chọn. |
| Breakdown prediction ablation | `[x]` diagnostic | So sánh trên cùng research frame: không dùng breakdown đạt calibrated AP `0.1343`, Top-10 precision `0.2603`; thêm `p_break_h60/p_break_h120` giảm lần lượt xuống `0.1147` và `0.2487`. Trên common-support `11,322` dòng, AP `0.1387 -> 0.1130`, Top-10 precision `0.3051 -> 0.1974`. Breakdown OOF cũ chỉ phủ `23.1%` dòng/`79.2%` ngày nên chưa được promotion; cần retrain/re-export đúng population nếu muốn đánh giá lại. |
| Strength head ablation | `[~]` | Conditional-strength ablation đã chạy nhưng các candidate đều `reject_for_next_stage`. Đưa strength trực tiếp vào meta-model làm AP tăng `0.1508` nhưng Top-10 precision giảm còn `0.2218`; chưa promote. |
| Strength post-ranking | `[~]` research | Trên frame aligned mới, `strength_weight=0.25` làm Top-10 calibrated precision 78 ngày giảm từ `0.2603` xuống `0.1962`; strength adjustment hiện không được promote và production weight đã khóa `0.0`. Đây là ranking adjustment, không sửa xác suất gốc. |
| Top-50/Top-10 policy | `[x]` research policy locked | Candidate v4 dùng full-universe và xếp Top-10 bằng `p_cascade` từ H120; `p_h20` không còn là hard gate hay input v4. Candidate K `{50, 100, 200}` chỉ được audit; `p_rank`/strength bị tắt. Policy chỉ được đánh giá promotion trên một holdout tương lai chưa mở. |
| Portfolio tối đa 3 vị thế | `[~]` diagnostic reject | Đã chạy full cascade Top-10 với tối đa 3 vị thế và chi phí/slippage; chỉ có `18` giao dịch, cumulative return `-10.20%`, Sharpe `-1.18`, không đạt promotion gate. |
| Daily inference end-to-end | `[x]` shadow-ready | Frozen H120-only runner đã kiểm tra checksum/schema, lọc `feature_ready`, chạy H120 → cascade → calibration → Top-10 và ghi prediction manifest thống nhất. Smoke run ngày `2026-08-11` có 505 mã đủ điều kiện, output deterministic; chưa được phép giao dịch khi chưa promote. |
| Final holdout | `[x]` opened, không tái sử dụng | Final test v3 đã mở nhưng audit lineage phát hiện `p_v6_trend` bằng `p_h20` trên toàn bộ `28,233` dòng vì hai role trỏ tới model artifact giống hệt nhau. Vì vậy kết quả bốn-head không phải phép đánh giá trung thực của original V6; nó chỉ là diagnostic của pipeline bị miswire và không được dùng để chọn v4. Holdout này không còn pristine; promotion v4 cần một cửa sổ tương lai mới. |
| Backtest sau chi phí | `[x]` diagnostic reject | Báo cáo point-in-time full flow tại `eval/runs/wave_cascade_prod_v3_final_test/backtest/`; Top-10, tối đa 3 vị thế, holding `120` phiên, có commission/slippage/tax. Kết quả không đạt promotion gate. |
| Lineage/schema guard | `[x]` | Exporter hỗ trợ contract H120-only và fingerprint artifact theo role; nếu H20/V6 hoặc hai role khác dùng cùng model payload thì export dừng. `WaveCascadeMetaModel` cũng từ chối các probability head trùng số trên batch đủ lớn. |
| Test suite liên quan | `[x]` | Full suite hiện tại đạt `47 passed` ngày 2026-08-24, gồm integrity/schema/deterministic tests cho frozen H120 shadow runner. Các test legacy đã chuyển vào archive và không nằm trong active suite. |
| Reproducible release | `[~]` shadow bundle | Bundle manifest đã khóa 10 runtime files bằng SHA-256 tại `deploy/wave_h120_shadow/bundle_manifest.json`; worktree vẫn chưa sạch và candidate chưa vượt holdout mới nên chưa phải production release. |

### 18.2. Checklist trước lần train/promotion kế tiếp

- [~] Xác định provider của dữ liệu gốc là KBS qua downloader hiện tại; cần lưu
  provenance/report thay vì chỉ suy ra từ default route.
- [~] Tải lại FPT trực tiếp từ KBS và xác nhận OHLCV khớp file local trên vùng
  đối chiếu; kết quả test đã được xác nhận, nhưng report tái lập chưa được lưu
  trong repo.
- [~] Đối chiếu FPT với `exright_date`, cash dividend và stock issue từ
  `Reference().company("FPT").events()`; policy thực tế đã chốt là `adjusted`,
  nhưng provider không trả `is_adjusted`/`adjustment_factor`.
- [~] Mở rộng corporate-action audit từ FPT/một số blue-chip ra toàn universe
  và lưu report có thể tái lập.
- [~] Cập nhật provenance sang `adjusted` theo test đã xác minh; không ghi
  `provider-confirmed` vì KBS không trả `is_adjusted`/`adjustment_factor`.
- [x] Chuyển clean-builder sang hỗ trợ layout `v6_snapshot`; build processed
  input, Feature Store và metadata `adjusted` từ `data/vnstock/v6_snapshot`.
- [x] Build dataset và train snapshot XGB/causal OOF cho H20, continuation
  H60/H120 và breakdown H60/H120; original V6 import đã có benchmark riêng.
- [~] Chẩn đoán/sửa breakdown heads vì metric hiện dưới no-skill baseline.
- [x] Build shared cascade frame continuation-only để ablation `p_h20`, `p_h60`,
  `p_h120` và `p_v6_trend`; giữ breakdown labels chỉ cho offline audit, không làm
  target hay feature candidate v4.
- [x] Chạy bảy contract ablation causal OOF và chọn H120-only; train candidate
  `20260823T170819Z`, khóa K=10/strength `0.0` và checksum mà không dùng final
  holdout để selection.
- [~] Đã bổ sung cascade calibration artifact/audit causal bằng sigmoid và lưu
  threshold calibrated; chưa gọi là production-ready trước final holdout/backtest.
- [x] Cài/khóa dependency `optuna`, `catboost`, `lightgbm`; requirements đã chứa
  các dependency này. H1/H2/H3 không còn nằm trong production path.
- [x] Thống nhất phase lịch lấy mẫu V6/continuation bằng
  `supervised_sample_anchor_date=2020-01-03`, stride 5 phiên; loader cascade
  hỗ trợ exact/as-of alignment và ghi source date/lag.
- [x] Đồng bộ population/OOF support giữa H20 onset, original V6 và continuation;
  shared frame đã đạt gate H20 `100%` ngày/dòng và H60 `100%` ngày, `99.14%` dòng.
- [x] Đã chuyển metadata/config/frame/model cascade sang target chính thức
  `y_cont_h120`, tạo lại manifest và lock continuation-only. Breakdown labels
  chỉ còn là offline risk audit và breakdown predictions không nằm trong feature schema.
- [x] Đã tách coverage khỏi ranking loss; frame aligned hiện tại có `100%`
  canonical-label coverage và metric ranking chạy trên toàn bộ scored universe.
- [x] Candidate Top-50 recall sau khi sửa target contract đã được ghi nhận như
  diagnostic: `p_h20` `0.0641`, cascade `0.1649`; đây không còn là gate vì
  production dùng full-universe cascade.
- [x] Khóa candidate target contract bằng cách bỏ H20 hard gate và loại H20 khỏi
  candidate v4 sau ablation; H20 vẫn học `y_entry` đúng nhiệm vụ onset và được
  giữ làm challenger độc lập. Target cascade là `y_cont_h120`; `y_actionable`
  chỉ là alias legacy.
- [x] Diagnostic aligned cùng population đã đo candidate recall@{50,100,200};
  `p_h20` đạt `{0.0641, 0.1368, 0.3101}`, còn `p_cascade_calibrated` đạt
  `{0.1649, 0.3083, 0.5410}`. Đây là audit chi phí, không phải production gate.
- [x] Chạy downstream causal-OOF ablation cho strength post-ranking (`p_rank`)
  trên Top-K precision/lift; frame aligned mới cho kết quả giảm precision nên
  không promote strength adjustment.
- [x] Chạy ablation meta-model causal trên cùng aligned frame; giữ Logistic
  `C=1.0`, positive weight `1.0` và strength post-ranking `0.0` làm baseline
  production vì HGB/strength-feature không đạt Top-10 promotion gate, còn weight
  `2.0` chỉ cải thiện biên.
- [x] So sánh cascade có và không có `p_break_h60/p_break_h120`; breakdown
  predictions hiện làm giảm AP và Top-10 precision cả trên full research frame
  lẫn common-support. Không đưa breakdown vào production cascade; chỉ retrain
  đúng population nếu sau này cần một risk head độc lập.
- [x] Audit redundancy của target: `y_actionable` và `y_cont_h120` giống nhau
  trên toàn bộ `63,438` dòng; breakdown không loại continuation-positive nào.
- [x] Rebuild frame/config/manifest với target chính thức `y_cont_h120`, chuyển
  breakdown labels sang offline risk audit và retrain cascade. Run mới là
  `models/wave_ignition_snapshot/wave_cascade_prod_v3_continuation/runs/20260823T155411Z`.
- [x] Lock pre-holdout continuation-only tại
  `experiments/baselines/wave_cascade_prod_v3_continuation_lock.json`; lock v2
  vẫn được giữ để đối chiếu artifact legacy.
- [x] Xuất final-test predictions cùng population cho V6/H20/H60/H120, sau đó
  mở full-cascade final holdout đúng một lần. Manifest tại
  `eval/runs/wave_cascade_prod_v3_final_test/manifest.json`.
- [x] Audit lại lineage final export: artifact gắn role `v6_trend` thực tế trùng
  model H20 và hai score giống nhau tuyệt đối. Đánh dấu kết quả bốn-head là
  diagnostic không hợp lệ cho original V6; thêm fingerprint/schema guard để lỗi
  này không lặp lại.
- [x] Chạy backtest sau transaction cost/slippage cho Top-10 và portfolio tối
  đa 3 vị thế; kết quả không đạt promotion gate nên candidate chưa được promote.
- [x] Đã đóng gói frozen H120 shadow bundle, daily inference runner và prediction
  manifest thống nhất; loader fail-closed khi checksum, feature version hoặc schema lệch.
- [ ] Commit/freeze một worktree sạch trước khi xem candidate là reproducible
  release.

### 18.3. Thứ tự công việc đề xuất

1. `[x]` Chuyển metadata/config sang `adjusted` theo test mã đã xác minh; vẫn
   cần lưu provenance report tái lập.
2. `[x]` Rebuild clean input và Feature Store v2 trực tiếp từ
   `data/vnstock/v6_snapshot` với `promotion_status: candidate_for_training`.
3. `[x]` Rebuild dataset/model snapshot H20, continuation H60/H120 và
   breakdown H60/H120; breakdown vẫn cần cải thiện trước promotion.
4. `[x]` Loại H1/H2/H3 khỏi đường train/promotion chính; original V6 chỉ còn là
   challenger cho đến khi có deployment artifact độc lập, đúng lineage.
5. `[x]` Khóa phase sampling bằng anchor chung và thêm coverage/audit guard;
   diagnostic cascade đã chạy nhưng bị chặn promotion vì population coverage.
6. `[x]` Re-export OOF H20 và original V6 trên cùng population/date support,
   build shared frame và chạy causal head ablation.
7. `[x]` Đã migrate metadata target sang `y_cont_h120`, retrain cascade
   continuation-only và tạo lại lock checksum trước final holdout.
8. `[x]` Đã chạy full-universe cascade final holdout đúng một lần và backtest sau phí
   cho portfolio tối đa ba vị thế; kết quả không đạt promotion gate nên candidate bị
   giữ ở research/rejected. Audit sau đó còn phát hiện V6 final bị miswire với H20.
9. `[x]` Chọn và khóa research candidate v4 H120-only hoàn toàn từ causal OOF;
   thêm artifact fingerprint và duplicate-head guard.
10. `[x]` Full active test suite đạt `47 passed`; frozen bundle và daily inference
    runner/manifest H120-only đã chạy smoke test deterministic. Runner vẫn ghi
    `trade_authorized=false` cho đến khi có promotion record hợp lệ.
11. `[ ]` Chỉ promotion sau khi candidate v4 vượt calibration, Top-K và backtest
    cost-aware trên holdout mới; không tái sử dụng final test v3.
12. `[x]` Import lại và replay bản V6 gốc; lưu metric tại
    `reports_wave_v6/`. Chỉ xoá file root trùng SHA-256 với bản keeper trong
    `scripts/wave_v6/`; các file import khác được giữ vì khác nội dung.
