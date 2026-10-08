#!/usr/bin/env python
# coding: utf-8

# # Hybrid Stock Forecast V4 — Reviewed
# 
# Giữ nguyên kiến trúc đã chốt:
# 
# **LSTM + Additive Prophet + Additive Holt-Winters → Dynamic Ensemble → 78 phiên**
# 
# Các cải tiến ở V4:
# 
# - Tăng yêu cầu dữ liệu tối thiểu để LSTM không train trên quá ít sequence.
# - LSTM validation trả thêm `best_epoch`; model cuối được **retrain từ đầu trên toàn bộ history** với scaler fit lại trên full history.
# - Recursive forecast dùng `model(x, training=False)` thay vì `.predict()` để giảm overhead.
# - Tính và in **MAE/RMSE của ensemble trên validation**, đồng thời so với best single model.
# - Giữ `weekly_seasonality=True` vì đây là cấu hình bám bài HUFLIT; đây không phải bug bắt buộc phải tắt.
# - Chart được tạo bằng script riêng sau khi đủ 50 forecast, tránh publish ảnh từ run dở dang.
# - Save Keras bằng `.keras` thay vì `.h5`.
# - **Schema JSON không đổi**: `predicted_on`, `last_close_price`, `chart_path`, `future[{date, predicted_close}]`.
# 
# Lưu ý: MAE của ensemble vẫn là **validation metric**, không phải final independent test metric.
# 

# In[ ]:


# Cài dependency (chạy 1 lần)
# Dependencies are installed in the dedicated Python 3.10 runtime.


# ## 1. Import

# In[1]:


import argparse
import os
import json
import random
import warnings
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.preprocessing import MinMaxScaler

import tensorflow as tf
from tensorflow.keras import Sequential
from tensorflow.keras.callbacks import EarlyStopping, ReduceLROnPlateau
from tensorflow.keras.layers import Input, LSTM, Dense, Dropout
from tensorflow.keras.optimizers import Adam

from prophet import Prophet
from statsmodels.tsa.holtwinters import ExponentialSmoothing

warnings.filterwarnings("ignore")
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2"

SEED = 42
random.seed(SEED)
np.random.seed(SEED)
tf.random.set_seed(SEED)


# ## 2. Config + danh sách ticker

# ## Cách hiểu horizon
# 
# - `LOOKBACK = 60`: LSTM nhìn lại 60 phiên gần nhất để dự đoán bước kế tiếp.
# - `FORECAST_DAYS = 78`: tạo chuỗi dự báo 78 phiên tương lai.
# - LSTM dự báo recursive: dự đoán phiên kế tiếp, đưa kết quả đó trở lại cửa sổ 60 phiên, rồi tiếp tục đến đủ 78 bước.
# - Prophet và Holt-Winters forecast trực tiếp 78 bước.
# - Ba forecast được ensemble theo trọng số MAE tính trên 78 phiên validation cuối.
# - V4 còn tính MAE/RMSE của chính ensemble trên validation để kiểm tra hybrid có thực sự tốt hơn model đơn hay không.
# 
# Lưu ý: `pd.bdate_range()` loại thứ Bảy/Chủ nhật nhưng chưa tự loại ngày nghỉ lễ của HOSE/HNX/UPCOM.
# 

# In[2]:


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train the Top-50 hybrid LSTM/Prophet/Holt price forecaster.")
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--top50-file", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--forecast-days", type=int, default=78)
    parser.add_argument("--lookback", type=int, default=120)
    parser.add_argument("--validation-days", type=int, default=78)
    parser.add_argument("--minimum-train-sequences", type=int, default=200)
    parser.add_argument("--epochs", type=int, default=80)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--patience", type=int, default=10)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--expected-symbols", type=int, default=50)
    return parser.parse_args()


ARGS = parse_args()
DATA_DIR = str(ARGS.data_dir.resolve())
TOP50_FILE = ARGS.top50_file.resolve()
MODEL_DIR = str(ARGS.model_dir.resolve())
OUTPUT_JSON = str(ARGS.output_json.resolve())

# Forecast
FORECAST_DAYS = ARGS.forecast_days

# LSTM dùng 120 phiên quá khứ làm input
LOOKBACK = ARGS.lookback

# 78 phiên cuối để validation
VALIDATION_DAYS = ARGS.validation_days

# Số sequence tối thiểu dùng để train
MIN_TRAIN_SEQUENCES = ARGS.minimum_train_sequences

# Với direct multi-output:
# X = 120 phiên
# y = 78 phiên kế tiếp
MIN_ROWS = (
    LOOKBACK
    + FORECAST_DAYS
    + VALIDATION_DAYS
    + MIN_TRAIN_SEQUENCES
)

# Training
EPOCHS = ARGS.epochs
BATCH_SIZE = ARGS.batch_size
PATIENCE = ARGS.patience
LEARNING_RATE = ARGS.learning_rate

os.makedirs(MODEL_DIR, exist_ok=True)
Path(OUTPUT_JSON).parent.mkdir(parents=True, exist_ok=True)

with TOP50_FILE.open("r", encoding="utf-8") as handle:
    top50_payload = json.load(handle)
raw_tickers = top50_payload.get("symbols") if isinstance(top50_payload, dict) else top50_payload
if not isinstance(raw_tickers, list):
    raise ValueError("Top-50 JSON must be a list or contain a symbols list.")
all_tickers = [
    str(item.get("ticker", "") if isinstance(item, dict) else item).strip().upper()
    for item in raw_tickers
]
if (
    len(all_tickers) != ARGS.expected_symbols
    or len(set(all_tickers)) != len(all_tickers)
    or any(not ticker.isalnum() for ticker in all_tickers)
):
    raise ValueError(
        f"Top-50 JSON must contain exactly {ARGS.expected_symbols} unique alphanumeric symbols."
    )

print(f"Loaded {len(all_tickers)} tickers")
print(all_tickers)

print(
    f"Minimum rows required: {MIN_ROWS} "
    f"(lookback={LOOKBACK}, forecast={FORECAST_DAYS}, "
    f"validation={VALIDATION_DAYS})"
)

# ## 3. Hàm xử lý dữ liệu và mô hình

# In[3]:


def load_close_series(ticker: str) -> pd.Series:
    """Đọc CSV của một mã và trả về close series đã làm sạch, sort theo thời gian."""
    file_path = os.path.join(DATA_DIR, f"{ticker}.csv")
    if not os.path.exists(file_path):
        raise FileNotFoundError(file_path)

    df = pd.read_csv(file_path)

    if "time" not in df.columns:
        raise ValueError(f"{ticker}: thiếu cột 'time'")
    if "close" not in df.columns:
        raise ValueError(f"{ticker}: thiếu cột 'close'")

    df["time"] = pd.to_datetime(df["time"], errors="coerce")
    df["close"] = pd.to_numeric(df["close"], errors="coerce")

    df = (
        df[["time", "close"]]
        .dropna()
        .drop_duplicates(subset=["time"], keep="last")
        .sort_values("time")
        .set_index("time")
    )

    series = df["close"].astype("float32")

    if len(series) < MIN_ROWS:
        raise ValueError(
            f"{ticker}: chỉ có {len(series)} dòng, cần tối thiểu {MIN_ROWS} "
            f"để có >= {MIN_TRAIN_SEQUENCES} LSTM train sequences"
        )

    return series


def create_sequences(scaled_values: np.ndarray, lookback: int):
    """Tạo X=(samples, lookback, 1), y=(samples,) đúng dạng time-series LSTM."""
    x, y = [], []

    for i in range(lookback, len(scaled_values)):
        x.append(scaled_values[i - lookback:i, 0])
        y.append(scaled_values[i, 0])

    x = np.asarray(x, dtype=np.float32)
    y = np.asarray(y, dtype=np.float32)

    if len(x) == 0:
        return np.empty((0, lookback, 1), dtype=np.float32), y

    return x.reshape(-1, lookback, 1), y


def build_lstm(lookback: int) -> Sequential:
    """
    Giữ nguyên kiến trúc LSTM đã chốt:
    - 2 tầng LSTM
    - Dropout
    - Huber loss
    - Adam
    """
    model = Sequential([
        Input(shape=(lookback, 1)),
        LSTM(128, return_sequences=True),
        Dropout(0.20),
        LSTM(64, return_sequences=False),
        Dropout(0.20),
        Dense(32, activation="relu"),
        Dense(1),
    ])

    model.compile(
        optimizer=Adam(learning_rate=LEARNING_RATE),
        loss=tf.keras.losses.Huber(),
    )

    return model


def recursive_lstm_forecast(
    model: Sequential,
    scaler: MinMaxScaler,
    history_values: np.ndarray,
    steps: int,
    lookback: int,
) -> np.ndarray:
    """
    Forecast multi-step recursive cho close.

    Dùng model(x, training=False) thay vì model.predict() trong loop
    để giảm overhead cho batch size = 1.
    """
    scaled_history = scaler.transform(
        np.asarray(history_values, dtype=np.float32).reshape(-1, 1)
    )

    current = scaled_history[-lookback:].reshape(-1, 1).copy()
    preds_scaled = []

    for _ in range(steps):
        x = current.reshape(1, lookback, 1).astype(np.float32)

        next_scaled = float(
            model(
                tf.convert_to_tensor(x, dtype=tf.float32),
                training=False,
            ).numpy()[0, 0]
        )

        preds_scaled.append(next_scaled)
        current = np.vstack([current[1:], [[next_scaled]]])

    return scaler.inverse_transform(
        np.asarray(preds_scaled, dtype=np.float32).reshape(-1, 1)
    ).ravel()


def fit_lstm_for_validation(series: pd.Series):
    """
    Outer validation:
    - 78 phiên cuối KHÔNG tham gia train.
    - Scaler chỉ fit trên phần train.
    - validation_split=10% nằm bên trong train để EarlyStopping.

    Trả thêm best_epoch để dùng khi retrain final LSTM trên full history.
    """
    train = series.iloc[:-VALIDATION_DAYS]
    valid = series.iloc[-VALIDATION_DAYS:]

    scaler = MinMaxScaler(feature_range=(0, 1))
    train_scaled = scaler.fit_transform(
        train.to_numpy(dtype=np.float32).reshape(-1, 1)
    )

    x_train, y_train = create_sequences(train_scaled, LOOKBACK)

    if len(x_train) < MIN_TRAIN_SEQUENCES:
        raise ValueError(
            f"Chỉ có {len(x_train)} LSTM train sequences, "
            f"cần tối thiểu {MIN_TRAIN_SEQUENCES}"
        )

    model = build_lstm(LOOKBACK)

    callbacks = [
        EarlyStopping(
            monitor="val_loss",
            patience=PATIENCE,
            restore_best_weights=True,
            mode="min",
            verbose=0,
        ),
        ReduceLROnPlateau(
            monitor="val_loss",
            factor=0.5,
            patience=max(3, PATIENCE // 2),
            min_lr=1e-5,
            verbose=0,
        ),
    ]

    history = model.fit(
        x_train,
        y_train,
        epochs=EPOCHS,
        batch_size=BATCH_SIZE,
        validation_split=0.10,
        callbacks=callbacks,
        shuffle=False,
        verbose=0,
    )

    val_loss_history = history.history.get("val_loss", [])
    if val_loss_history:
        best_epoch = int(np.argmin(val_loss_history) + 1)
    else:
        best_epoch = int(len(history.history.get("loss", [])) or EPOCHS)

    valid_pred = recursive_lstm_forecast(
        model=model,
        scaler=scaler,
        history_values=train.to_numpy(),
        steps=VALIDATION_DAYS,
        lookback=LOOKBACK,
    )

    mae = mean_absolute_error(valid.to_numpy(), valid_pred)
    rmse = np.sqrt(
        mean_squared_error(valid.to_numpy(), valid_pred)
    )

    return (
        model,
        scaler,
        valid_pred,
        float(mae),
        float(rmse),
        best_epoch,
    )


def train_final_lstm_on_full_series(
    series: pd.Series,
    epochs: int,
):
    """
    Retrain final LSTM từ đầu trên toàn bộ history.

    Đây là bước final refit sau khi validation đã dùng để:
    - đánh giá model family/config,
    - xác định ensemble weights,
    - ước lượng số epoch phù hợp.

    Scaler final được fit lại trên TOÀN BỘ history đã biết.
    Điều này không phải leakage vì target cần dự đoán nằm ở tương lai.
    """
    final_scaler = MinMaxScaler(feature_range=(0, 1))

    full_scaled = final_scaler.fit_transform(
        series.to_numpy(dtype=np.float32).reshape(-1, 1)
    )

    x_full, y_full = create_sequences(full_scaled, LOOKBACK)

    if len(x_full) < MIN_TRAIN_SEQUENCES:
        raise ValueError(
            f"Không đủ full-history sequences cho final LSTM: {len(x_full)}"
        )

    final_model = build_lstm(LOOKBACK)

    final_epochs = max(1, min(int(epochs), EPOCHS))

    final_model.fit(
        x_full,
        y_full,
        epochs=final_epochs,
        batch_size=BATCH_SIZE,
        shuffle=False,
        verbose=0,
    )

    return final_model, final_scaler


def prophet_forecast_from_train(
    train: pd.Series,
    dates_to_predict: pd.DatetimeIndex,
) -> np.ndarray:
    """
    Additive Prophet bám cấu hình bài HUFLIT:
    - changepoint_prior_scale = 0.05
    - seasonality_prior_scale = 10
    - weekly seasonality
    - yearly seasonality
    - monthly seasonality ~30 ngày

    weekly_seasonality=True được GIỮ LẠI có chủ đích.
    Việc dữ liệu chỉ có phiên giao dịch không tự động làm weekly seasonality sai;
    nên đánh giá bằng validation nếu muốn làm ablation riêng.
    """
    train_df = pd.DataFrame({
        "ds": train.index,
        "y": train.to_numpy(dtype=float),
    })

    model = Prophet(
        seasonality_mode="additive",
        changepoint_prior_scale=0.05,
        seasonality_prior_scale=10.0,
        daily_seasonality=False,
        weekly_seasonality=True,
        yearly_seasonality=True,
    )

    model.add_seasonality(
        name="monthly",
        period=30.5,
        fourier_order=5,
    )

    model.fit(train_df)

    future_df = pd.DataFrame({
        "ds": pd.DatetimeIndex(dates_to_predict)
    })

    return model.predict(future_df)["yhat"].to_numpy(dtype=float)


def holt_forecast_from_train(
    train: pd.Series,
    steps: int,
) -> np.ndarray:
    """Additive Holt-Winters dùng như baseline mùa vụ."""
    model = ExponentialSmoothing(
        train.to_numpy(dtype=float),
        trend="add",
        seasonal="add",
        seasonal_periods=5,
        initialization_method="estimated",
    ).fit(
        optimized=True,
        use_brute=True,
    )

    return np.asarray(
        model.forecast(steps),
        dtype=float,
    )


def safe_mae(y_true, y_pred) -> float:
    return float(
        mean_absolute_error(
            np.asarray(y_true, dtype=float),
            np.asarray(y_pred, dtype=float),
        )
    )


def safe_rmse(y_true, y_pred) -> float:
    return float(
        np.sqrt(
            mean_squared_error(
                np.asarray(y_true, dtype=float),
                np.asarray(y_pred, dtype=float),
            )
        )
    )


def inverse_error_weights(
    model_mae: dict,
    eps: float = 1e-8,
) -> dict:
    """
    Dynamic ensemble:
    model có MAE validation thấp hơn sẽ được trọng số cao hơn.
    """
    inv = {
        name: 1.0 / max(float(mae), eps)
        for name, mae in model_mae.items()
        if np.isfinite(mae)
    }

    if not inv:
        return {}

    total = sum(inv.values())

    raw = {
        name: value / total
        for name, value in inv.items()
    }

    clipped = {
        name: min(max(weight, 0.10), 0.70)
        for name, weight in raw.items()
    }

    clipped_total = sum(clipped.values())

    return {
        name: weight / clipped_total
        for name, weight in clipped.items()
    }


def weighted_ensemble(
    forecasts: dict,
    weights: dict,
) -> np.ndarray:
    names = [
        name
        for name in forecasts
        if name in weights
    ]

    if not names:
        raise ValueError("Không có model hợp lệ để ensemble")

    result = np.zeros_like(
        np.asarray(forecasts[names[0]], dtype=float),
        dtype=float,
    )

    for name in names:
        result += (
            np.asarray(forecasts[name], dtype=float)
            * float(weights[name])
        )

    return result


def positive_price_guard(
    pred: np.ndarray,
    last_close: float,
) -> np.ndarray:
    """Chặn giá âm/vô lý nhưng không bóp biên forecast."""
    floor = max(
        float(last_close) * 0.01,
        1e-6,
    )

    return np.maximum(
        np.asarray(pred, dtype=float),
        floor,
    )


# ## 4. Pipeline dự báo cho một ticker

# In[4]:


def forecast_one_ticker(ticker: str):
    print(f"\n{'=' * 72}")
    print(f"▶ {ticker}")

    series = load_close_series(ticker)
    last_close_price = float(series.iloc[-1])

    # ------------------------------------------------------
    # 1) Validation 78 phiên cuối để chấm điểm từng model
    # ------------------------------------------------------
    train = series.iloc[:-VALIDATION_DAYS]
    valid = series.iloc[-VALIDATION_DAYS:]
    valid_dates = valid.index

    validation_mae = {}
    validation_forecasts = {}

    # LSTM
    (
        lstm_validation_model,
        lstm_validation_scaler,
        lstm_valid_pred,
        lstm_mae,
        lstm_rmse,
        lstm_best_epoch,
    ) = fit_lstm_for_validation(series)

    validation_mae["lstm"] = lstm_mae
    validation_forecasts["lstm"] = lstm_valid_pred

    # Additive Prophet
    try:
        prophet_valid_pred = prophet_forecast_from_train(
            train,
            valid_dates,
        )

        validation_forecasts["prophet"] = prophet_valid_pred

        validation_mae["prophet"] = safe_mae(
            valid.to_numpy(),
            prophet_valid_pred,
        )

    except Exception as exc:
        print(
            f"⚠ {ticker} Prophet validation lỗi: {exc}"
        )

    # Additive Holt-Winters
    try:
        holt_valid_pred = holt_forecast_from_train(
            train,
            VALIDATION_DAYS,
        )

        validation_forecasts["holt"] = holt_valid_pred

        validation_mae["holt"] = safe_mae(
            valid.to_numpy(),
            holt_valid_pred,
        )

    except Exception as exc:
        print(
            f"⚠ {ticker} Holt-Winters validation lỗi: {exc}"
        )

    # Dynamic weights dựa trên MAE validation
    weights = inverse_error_weights(validation_mae)

    if not weights:
        weights = {"lstm": 1.0}

    # ------------------------------------------------------
    # 1.1) Đánh giá chính ensemble trên validation
    # ------------------------------------------------------
    active_validation_forecasts = {
        name: pred
        for name, pred in validation_forecasts.items()
        if name in weights
    }

    active_validation_weights = {
        name: weight
        for name, weight in weights.items()
        if name in active_validation_forecasts
    }

    val_weight_total = sum(
        active_validation_weights.values()
    )

    active_validation_weights = {
        name: weight / val_weight_total
        for name, weight in active_validation_weights.items()
    }

    ensemble_valid_pred = weighted_ensemble(
        active_validation_forecasts,
        active_validation_weights,
    )

    ensemble_valid_mae = safe_mae(
        valid.to_numpy(),
        ensemble_valid_pred,
    )

    ensemble_valid_rmse = safe_rmse(
        valid.to_numpy(),
        ensemble_valid_pred,
    )

    best_single_name = min(
        validation_mae,
        key=validation_mae.get,
    )
    best_single_mae = validation_mae[best_single_name]

    if best_single_mae > 0:
        ensemble_gain_pct = (
            (best_single_mae - ensemble_valid_mae)
            / best_single_mae
            * 100.0
        )
    else:
        ensemble_gain_pct = 0.0

    print(
        "Validation MAE:",
        {
            name: round(value, 4)
            for name, value in validation_mae.items()
        },
    )

    print(
        "Ensemble weights:",
        {
            name: round(value, 4)
            for name, value in weights.items()
        },
    )

    print(
        f"LSTM validation RMSE: {lstm_rmse:.4f}"
    )

    print(
        f"LSTM best epoch: {lstm_best_epoch}"
    )

    print(
        f"Ensemble validation MAE: "
        f"{ensemble_valid_mae:.4f}"
    )

    print(
        f"Ensemble validation RMSE: "
        f"{ensemble_valid_rmse:.4f}"
    )

    print(
        f"Best single model: {best_single_name} "
        f"(MAE={best_single_mae:.4f})"
    )

    print(
        f"Ensemble gain vs best single: "
        f"{ensemble_gain_pct:+.2f}%"
    )

    # ------------------------------------------------------
    # 2) Forecast 78 phiên giao dịch tương lai
    # ------------------------------------------------------
    future_dates = pd.bdate_range(
        start=series.index[-1] + pd.Timedelta(days=1),
        periods=FORECAST_DAYS,
    )

    future_forecasts = {}

    # Final LSTM:
    # retrain từ đầu trên full history, dùng best_epoch từ validation
    lstm_model, lstm_scaler = train_final_lstm_on_full_series(
        series=series,
        epochs=lstm_best_epoch,
    )

    future_forecasts["lstm"] = recursive_lstm_forecast(
        model=lstm_model,
        scaler=lstm_scaler,
        history_values=series.to_numpy(),
        steps=FORECAST_DAYS,
        lookback=LOOKBACK,
    )

    # Prophet: refit full history
    if "prophet" in weights:
        try:
            future_forecasts["prophet"] = (
                prophet_forecast_from_train(
                    series,
                    future_dates,
                )
            )
        except Exception as exc:
            print(
                f"⚠ {ticker} Prophet future lỗi: {exc}"
            )
            weights.pop("prophet", None)

    # Holt-Winters: refit full history
    if "holt" in weights:
        try:
            future_forecasts["holt"] = (
                holt_forecast_from_train(
                    series,
                    FORECAST_DAYS,
                )
            )
        except Exception as exc:
            print(
                f"⚠ {ticker} Holt-Winters future lỗi: {exc}"
            )
            weights.pop("holt", None)

    # Normalize lại weights nếu model nào fail ở future stage
    active = {
        name: weight
        for name, weight in weights.items()
        if name in future_forecasts
    }

    if not active:
        active = {"lstm": 1.0}

    total_weight = sum(active.values())

    active = {
        name: weight / total_weight
        for name, weight in active.items()
    }

    predicted_prices = weighted_ensemble(
        future_forecasts,
        active,
    )

    predicted_prices = positive_price_guard(
        predicted_prices,
        last_close_price,
    )

    # ------------------------------------------------------
    # 3) Lưu final LSTM + final scaler
    # ------------------------------------------------------
    lstm_model.save(
        os.path.join(
            MODEL_DIR,
            f"{ticker}_lstm_model.keras",
        )
    )

    joblib.dump(
        lstm_scaler,
        os.path.join(
            MODEL_DIR,
            f"{ticker}_lstm_scaler.pkl",
        ),
    )

    # Charts are generated in a separate step only after all 50 forecasts
    # complete. A partial training run must never replace web-served images.
    now = datetime.now()

    print(
        f"{ticker} - Giá close gần nhất: "
        f"{last_close_price:.2f}"
    )

    print(
        f"{ticker} - Giá close dự đoán phiên thứ "
        f"{FORECAST_DAYS}: "
        f"{float(predicted_prices[-1]):.4f}"
    )

    # ------------------------------------------------------
    # 5) Schema output GIỮ NGUYÊN như file thứ 3
    # ------------------------------------------------------
    result = {
        "predicted_on": now.strftime(
            "%Y-%m-%d %H:%M:%S"
        ),
        "last_close_price": float(
            last_close_price
        ),
        "chart_path": None,
        "future": [
            {
                "date": str(
                    future_dates[i].date()
                ),
                "predicted_close": float(
                    predicted_prices[i]
                ),
            }
            for i in range(FORECAST_DAYS)
        ],
    }

    return result


# ## 5. Chạy toàn bộ Top 50 và lưu JSON (78 phiên/mã)

# In[ ]:


result_json = {}
if Path(OUTPUT_JSON).is_file():
    try:
        with open(OUTPUT_JSON, "r", encoding="utf-8") as handle:
            existing = json.load(handle)
        if isinstance(existing, dict):
            result_json = {
                ticker: value
                for ticker, value in existing.items()
                if ticker in all_tickers
                and isinstance(value, dict)
                and isinstance(value.get("future"), list)
                and len(value["future"]) == FORECAST_DAYS
            }
            print(f"Loaded {len(result_json)} valid cached forecasts from {OUTPUT_JSON}")
    except Exception as exc:
        print(f"Notice: Could not load existing {OUTPUT_JSON}: {exc}")

failed_tickers = {}

for position, ticker in enumerate(all_tickers, 1):
    if ticker in result_json:
        print(f"[{position}/{len(all_tickers)}] CACHED {ticker}", flush=True)
        continue
    print(f"[{position}/{len(all_tickers)}] Training hybrid forecast for {ticker}", flush=True)
    try:
        result_json[ticker] = forecast_one_ticker(ticker)

        # Save incremental để job dừng giữa chừng vẫn giữ kết quả đã chạy.
        with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
            json.dump(result_json, f, indent=4, ensure_ascii=False)

        print(f"[{position}/{len(all_tickers)}] PASS {ticker}", flush=True)

    except Exception as exc:
        failed_tickers[ticker] = str(exc)
        print(f"❌ {ticker}: {exc}")
    finally:
        tf.keras.backend.clear_session()

print("\n✅ Hoàn tất")
print(f"Saved JSON: {OUTPUT_JSON}")
print(f"Success: {len(result_json)}/{len(all_tickers)}")

if failed_tickers:
    print("Failed:", failed_tickers)
    failure_path = Path(OUTPUT_JSON).with_name(Path(OUTPUT_JSON).stem + "_failures.json")
    failure_path.write_text(
        json.dumps(failed_tickers, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

if failed_tickers or len(result_json) != ARGS.expected_symbols:
    raise RuntimeError(
        f"Hybrid training incomplete: success={len(result_json)}, "
        f"failed={len(failed_tickers)}, expected={ARGS.expected_symbols}."
    )


# ## 6. Kiểm tra schema output

# In[ ]:


# Kiểm tra compatibility với file thứ 3
if result_json:
    sample_ticker = next(iter(result_json))
    sample = result_json[sample_ticker]

    assert set(sample.keys()) == {
        "predicted_on",
        "last_close_price",
        "chart_path",
        "future",
    }
    assert len(sample["future"]) == FORECAST_DAYS
    assert set(sample["future"][0].keys()) == {
        "date",
        "predicted_close",
    }

    print("✅ Output schema tương thích file thứ 3")
    print(
        json.dumps(
            {sample_ticker: sample},
            ensure_ascii=False,
            indent=2,
        )[:2500]
    )

