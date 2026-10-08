#!/usr/bin/env bash
# Run the hybrid LSTM/Prophet/Holt-Winters price forecaster with TensorFlow GPU under WSL2
# using the 50 tickers from the ensemble calibrated window 11/8.
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-/mnt/e/VinAI/P-238}"
VENV_PATH="${LSTM_WSL_VENV:-$HOME/.venvs/lstm-gpu-py311}"
NVIDIA_ROOT="$VENV_PATH/lib/python3.11/site-packages/nvidia"
HYBRID_DATA_DIR="${HYBRID_DATA_DIR:-$PROJECT_ROOT/data/vnstock/v6_snapshot}"
HYBRID_TOP50_FILE="${HYBRID_TOP50_FILE:-$PROJECT_ROOT/runs/lstm_hybrid/append_only_20260827_calibration11aug/lstm_top50_universe.json}"
HYBRID_RUN_ROOT="${HYBRID_RUN_ROOT:-$PROJECT_ROOT/runs/lstm_hybrid/append_only_20260827_calibration11aug}"
WEB_CHARTS_DIR="${WEB_CHARTS_DIR:-$PROJECT_ROOT/web/public/charts}"
DEPLOY_DIR="${DEPLOY_DIR:-$PROJECT_ROOT/deploy/price_forecast_lstm}"

if [[ ! -x "$VENV_PATH/bin/python" || ! -d "$NVIDIA_ROOT" ]]; then
  echo "WSL GPU environment is missing: $VENV_PATH" >&2
  exit 1
fi

GPU_LIBRARIES="$(find "$NVIDIA_ROOT" -type d -name lib -print | paste -sd: -)"
export LD_LIBRARY_PATH="$GPU_LIBRARIES${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export TF_FORCE_GPU_ALLOW_GROWTH=true
export PYTHONUTF8=1

mkdir -p "$HYBRID_RUN_ROOT/models" "$HYBRID_RUN_ROOT/charts" "$WEB_CHARTS_DIR" "$DEPLOY_DIR"
cd "$PROJECT_ROOT"

echo "=== Step 1: Starting GPU Hybrid Training on 50 tickers from calibrated window 11/8 ==="
"$VENV_PATH/bin/python" "$PROJECT_ROOT/scripts/train_lstm_price_forecast.py" \
  --data-dir "$HYBRID_DATA_DIR" \
  --top50-file "$HYBRID_TOP50_FILE" \
  --model-dir "$HYBRID_RUN_ROOT/models" \
  --output-json "$HYBRID_RUN_ROOT/predict_top50_stocks.json"

echo "=== Step 2: Generating Chart Images into $WEB_CHARTS_DIR ==="
"$VENV_PATH/bin/python" "$PROJECT_ROOT/scripts/generate_lstm_forecast_charts.py" \
  --predictions "$HYBRID_RUN_ROOT/predict_top50_stocks.json" \
  --snapshot-dir "$HYBRID_DATA_DIR" \
  --output-dir "$WEB_CHARTS_DIR" \
  --public-prefix charts \
  --write-json "$DEPLOY_DIR/price_predictions.json"

echo "=== Step 3: Mirroring charts and predictions to run root ==="
cp -f "$DEPLOY_DIR/price_predictions.json" "$HYBRID_RUN_ROOT/predict_top50_stocks.json"
cp -f "$WEB_CHARTS_DIR"/*.png "$HYBRID_RUN_ROOT/charts/"

echo "=== Training and Chart Generation Completed Successfully! ==="
