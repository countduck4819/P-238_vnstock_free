# H120 trend advisory: production serving runbook

## Scope and safety boundary

This release serves the frozen H120 continuation probability to authenticated
Premium users and administrators. It is an **advisory-only** product surface:

- it exposes `continuation_probability_h120` over a 120-session horizon;
- it does not create orders, portfolio actions, or buy/sell instructions;
- the upstream manifest must contain `trade_authorized: false` or serving fails;
- it is not a trade-approved model. Promotion still requires a new untouched
  holdout and a cost-aware backtest.

Each successful daily run of the `model_scoring` worker publishes the release
lock `runs/wave_h120_shadow/serving_release.json`, pinning that run's
prediction parquet by path, size and SHA-256. The frozen model bundle stays in
[bundle_manifest.json](../deploy/wave_h120_shadow/bundle_manifest.json).

## Service contract

Browser requests go only through NestJS, so the Python service is never exposed
as an unauthenticated product API:

```
Premium browser -> GET /api/wave-h120/latest -> NestJS -> Python /api/wave-h120/latest -> verified parquet
```

Available endpoints:

- `GET /api/wave-h120/latest?limit=1..10`
- `GET /api/wave-h120/:symbol`

Both require a JWT and a Premium account; administrators are also allowed. The
local `WaveH120PremiumGuard` is deliberate defense in depth because the legacy
global role guard is shared by unrelated endpoints.

## Configuration and rollout

The compose configuration supplies:

```dotenv
PYTHON_API_URL=http://python_data:6060/api
WAVE_H120_RUN_ROOT=/app/runs/wave_h120_shadow
INTERNAL_API_BASE_URL=http://api:8000/api
NEXT_PUBLIC_H120_ENABLED=true
```

`runs/` is mounted read-only into `python_data`. The browser uses the same-origin
`/api` path; Next.js rewrites it server-side to `INTERNAL_API_BASE_URL`, so an
external product domain never points users at `localhost`. `pyarrow` is included because
the product endpoint reads the verified parquet file. The serving
container never runs the pipeline: the frozen production image must not train
or mutate artifacts. The daily run belongs to the separate `model_scoring`
worker.

Before rollout, build and start the services, then check the Python endpoint
inside its container and the authenticated NestJS endpoint with a Premium JWT:

```powershell
docker compose up -d --build python_data api web
docker compose exec python_data python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:6060/api/wave-h120/latest?limit=1').status)"
curl.exe -H "Authorization: Bearer <premium-jwt>" http://localhost:8000/api/wave-h120/latest?limit=1
```

Expected properties: HTTP 200, `trade_authorized: false`, 120-session advisory
metadata, a nonempty `predictions` list, and data dates matching the release
lock. A non-Premium token must receive HTTP 403.

## Monitoring and rollback

- Docker health checks the read-only Python H120 endpoint every 30 seconds.
- NestJS returns 503 if the upstream service is unreachable, its data is
  malformed, or `trade_authorized` is anything other than `false`.
- The Python route verifies the prediction file's size and SHA-256, and falls
  back to the latest valid successful run if a newer artifact is invalid.

For an immediate presentation rollback, set
`NEXT_PUBLIC_H120_ENABLED=false`, rebuild/redeploy `web`; the tab disappears.
For an API rollback, remove `WaveH120Module` from `AppModule` and redeploy the
API. Do not delete the frozen artifact; it is the audit record.

## Next data refresh

When the dedicated worker is packaged, it may run
`scripts/run_wave_h120_shadow.py --snapshot-date YYYY-MM-DD` after market close.
It must retain the current artifact when any quality check fails. Each fresh run
must still be `trade_authorized: false` until Phase F's untouched holdout and
cost-aware backtest have passed.
