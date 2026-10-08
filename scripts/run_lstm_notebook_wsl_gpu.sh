#!/usr/bin/env bash
# Run the unchanged notebook-export script with TensorFlow GPU under WSL2.
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-/mnt/e/VinAI/P-238}"
VENV_PATH="${LSTM_WSL_VENV:-$HOME/.venvs/lstm-gpu-py311}"
NVIDIA_ROOT="$VENV_PATH/lib/python3.11/site-packages/nvidia"
HYBRID_DATA_DIR="${HYBRID_DATA_DIR:-$PROJECT_ROOT/data/vnstock/v6_snapshot}"
HYBRID_TOP50_FILE="${HYBRID_TOP50_FILE:-$PROJECT_ROOT/deploy/wave_v6_advisory/top50.json}"
HYBRID_RUN_ROOT="${HYBRID_RUN_ROOT:-$PROJECT_ROOT/runs/lstm_hybrid/manual}"

if [[ ! -x "$VENV_PATH/bin/python" || ! -d "$NVIDIA_ROOT" ]]; then
  echo "WSL GPU environment is missing: $VENV_PATH" >&2
  exit 1
fi

GPU_LIBRARIES="$(find "$NVIDIA_ROOT" -type d -name lib -print | paste -sd: -)"
export LD_LIBRARY_PATH="$GPU_LIBRARIES${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export TF_FORCE_GPU_ALLOW_GROWTH=true
export PYTHONUTF8=1

mkdir -p "$HYBRID_RUN_ROOT/models" "$HYBRID_RUN_ROOT/charts"
cd "$PROJECT_ROOT"
"$VENV_PATH/bin/python" "$PROJECT_ROOT/scripts/train_lstm_price_forecast.py" \
  --data-dir "$HYBRID_DATA_DIR" \
  --top50-file "$HYBRID_TOP50_FILE" \
  --model-dir "$HYBRID_RUN_ROOT/models" \
  --output-json "$HYBRID_RUN_ROOT/predict_top50_stocks.json"
if [[ "${HYBRID_SKIP_CHART:-0}" == "1" ]]; then
  exit 0
fi
exec "$VENV_PATH/bin/python" "$PROJECT_ROOT/scripts/generate_lstm_forecast_charts.py" \
  --predictions "$HYBRID_RUN_ROOT/predict_top50_stocks.json" \
  --snapshot-dir "$HYBRID_DATA_DIR" \
  --output-dir "$HYBRID_RUN_ROOT/charts" \
  --public-prefix charts
