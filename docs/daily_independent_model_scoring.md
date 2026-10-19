# Daily advisory scoring: short-term and long-term trends

The deployed worker runs once on Vietnamese market weekdays at 19:00
(`WAVE_DAILY_SCORING_TIME`).  It never retrains either model.

1. The short-term model synchronizes one dated OHLCV snapshot, validates it,
   builds its own features, and runs daily inference into
   `runs/wave_h120_shadow/`.
2. The long-term model and its LSTM price forecasts are read from their
   reviewed frozen cohort release; they are not run by the daily worker.
3. The short-term daily job does not consume long-term features or predictions.
4. Each output has a dated directory, a manifest, output hash, model-bundle
   hash, `trade_authorized: false`, and an independent-model contract.
5. The serving APIs select the newest valid manifest. A failed/tampered run is
   ignored and the preceding verified result remains available.

## Long-term ranking and LSTM price forecasts

The long-term branch never runs in the daily job. A new release is published by
copying the two files produced by the long-term pipeline into
`predict_xgboost_and_lstm/`:

- `ensemble_top50_stocks.json`: the V6 ensemble Top 50 (`symbols[]` with
  `rank`, `ticker`, `p_ensemble`);
- `predict_top50_stocks.json`: the 78-session LSTM/Prophet/Holt price path for
  the same 50 symbols.

NestJS reads both files directly (`/api/wave-v6/latest`) and re-imports the LSTM
file into the `stock_prediction` table within a few seconds of a change; the
file must contain exactly 50 symbols or the previous import is kept. No restart
or release pointer is needed. Python `/api/wave-v6` is only a fallback that
serves the frozen release in `deploy/wave_v6_advisory/`.

The daily scheduler only runs the short-term branch:

```powershell
.\.venv\Scripts\python.exe scripts\run_daily_model_scoring.py --snapshot-date 2026-08-25
```

Create a reviewed cohort from an immutable historical snapshot. The long-term
ensemble Top 50 is frozen as the hybrid training universe for the release cycle.
For each symbol, the trainer validates LSTM, additive Prophet and additive
Holt-Winters over 78 sessions, derives inverse-error ensemble weights, refits on
the complete historical series and forecasts the next 78 sessions. It does not
participate in daily scoring:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-lstm.txt
.\.venv\Scripts\python.exe scripts\train_lstm_price_forecast.py --data-dir data/vnstock/v6_snapshot --top50-file runs/wave_v6_retrain/<run>/lstm_top50_universe.json --model-dir runs/lstm_hybrid/<run>/models --output-json runs/lstm_hybrid/<run>/predict_top50_stocks.json
.\.venv\Scripts\python.exe scripts\generate_lstm_forecast_charts.py --predictions runs/lstm_hybrid/<run>/predict_top50_stocks.json --snapshot-dir data/vnstock/v6_snapshot --output-dir web/public/charts --public-prefix charts
```

The serving cohort is also exported as `deploy/wave_v6_advisory/top50.json`.
This is the canonical Top 50 from the hash-pinned long-term ensemble. Retrain
LSTM only when a new long-term cohort is promoted or its frozen weights are
intentionally replaced; a daily short-term scoring run does not require LSTM
retraining.

The persistent Docker worker runs only the short-term daily inference. Long-term
ranking and LSTM price forecasts are refreshed by the reviewed cohort process.

The snapshot is shared to avoid duplicate provider downloads. The short-term
and long-term models remain independent. The sole model output dependency is
intentional: LSTM receives the long-term ensemble's immutable Top-50 cohort,
never short-term features or probabilities.

Run one job manually:

```powershell
.\.venv\Scripts\python.exe scripts\run_daily_model_scoring.py --snapshot-date 2026-08-25
```

For a historical replay only, reuse an existing snapshot without downloading:

```powershell
.\.venv\Scripts\python.exe scripts\run_daily_model_scoring.py --snapshot-date 2026-08-24 --skip-sync --allow-stale-cache
```

Do not use `--skip-sync` for the live daily job. It is replay-only and the
existing snapshot manifest must already match the requested cutoff. Provider
responses are clipped by inclusive trading date before snapshot hashes and the
manifest are written, preventing future bars from leaking into a replay.

Start the persistent worker with the application stack:

```powershell
docker compose up -d --build model_scoring
```

The worker receives the project `.env` and persists the vnstock cache through
the `data_vnstock` volume. The adapter prefers the sponsor `vnstock_data`
package when installed and falls back to the free `vnstock` package bundled in
the image. On start the worker registers `VNSTOCK_API_KEY` from `.env` (free
community key, 60 requests/minute); without a key it runs in guest mode and caps
`WAVE_H120_REQUESTS_PER_MINUTE` at 18, because vnai aborts the process once the
guest quota of 20/minute is exceeded. No credentials are committed to the
repository. The live path always performs a provider sync (unless the explicit
replay-only `--skip-sync` option is used).

Symbols the provider fails to return are retried once after the full universe
has been synced. Up to `WAVE_H120_MAX_FAILED_SYMBOLS` (default 30 of ~1,500)
may still fail, typically delisted tickers; they are left unscored and listed in
the snapshot manifest. The 95% coverage gate still applies.

A successful run publishes `runs/wave_h120_shadow/serving_release.json`
(`deploy/` is mounted read-only in the containers). `python_data` serves that
release, or the newest verified run when the release is absent.

The worker writes logs/manifests in `runs/daily_model_scoring/` and prints one
line per run, so `docker compose logs -f model_scoring` shows whether the day
succeeded and, if not, the failing step's log tail. It makes at most
`WAVE_DAILY_SCORING_MAX_ATTEMPTS` automatic attempts per market day and waits
`WAVE_DAILY_SCORING_RETRY_MINUTES` after a failed job finishes before retrying.
A successful market date is not scored twice. A lock left behind by a worker
that was killed mid-run (for example when `docker compose up` recreates the
container) is detected and replaced instead of blocking every later run.


Daily OHLCV inputs use a bounded rolling history of 480 sessions. The adapter
merges the newest response with `data_vnstock/cache/rolling/`, de-duplicates
timestamps, and atomically keeps only the newest 480 rows per symbol. After a
successful scoring run, old orchestration and H120 run directories are pruned;
the serving pointer and recent rollback runs are preserved.
