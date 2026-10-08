# V6 long-term trend advisory: production serving runbook

## Scope

V6 is served as an authenticated Premium advisory that ranks long-term major
uptrend potential. It has no fixed forecast horizon and is independent from the
H120 product. No V6 field is combined with an H120 input or output.

The frozen release is `deploy/wave_v6_advisory/serving_release.json`. The Python
route verifies the CSV size, row count, date and SHA-256 before returning data.
Both Python and NestJS fail closed unless `trade_authorized` is false and
`independent_from_h120` is true.

## Endpoints

- `GET /api/wave-v6/latest?limit=1..50`
- `GET /api/wave-v6/:symbol`

Both NestJS endpoints require a Premium JWT; administrators are also allowed.
The public response contains only the long-term rank, V6 probability and model
agreement diagnostics. It does not contain `p_h120` or a cross-model score.

## Configuration

```dotenv
PYTHON_API_URL=http://python_data:6060/api
WAVE_V6_RELEASE_PATH=/app/deploy/wave_v6_advisory/serving_release.json
NEXT_PUBLIC_V6_ENABLED=true
```

`deploy/` and `reports_wave_v6/` are mounted read-only in the Python serving
container. The container health check verifies both H120 and V6 so either
advisory failing closed makes serving unhealthy. To roll back only the UI, set `NEXT_PUBLIC_V6_ENABLED=false` and
rebuild `web`. Keep the frozen release and prediction artifact as audit records.

## Smoke checks

```powershell
docker compose up -d --build python_data api web
docker compose exec python_data python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:6060/api/wave-v6/latest?limit=1').status)"
curl.exe -H "Authorization: Bearer <premium-jwt>" http://localhost:8000/api/wave-v6/latest?limit=1
```

Expected: HTTP 200, `trade_authorized: false`,
`independent_from_h120: true`, a nonempty prediction list and `as_of_date`
equal to the locked release date.
