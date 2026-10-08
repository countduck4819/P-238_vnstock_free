# Trợ lý ảo FinSight API boundary

Trợ lý ảo FinSight is integrated additively so the existing chatbot UI and its response
contract do not need to change. The NestJS endpoint remains `/ai-stock/ask` and
continues to save chat history.

## Enable locally

Start the standalone Python boundary from the repository root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn src.finsight_api:app --host 127.0.0.1 --port 6071
```

Configure the NestJS process:

```dotenv
FINSIGHT_API_URL=http://127.0.0.1:6071
FINSIGHT_API_TIMEOUT_MS=120000
```

Configure the Python FinSight process with the dedicated financial-facts
database. This is intentionally separate from the NestJS database used for
users and chat history:

```dotenv
FINANCIAL_DATABASE_URL=postgresql://user:password@host:port/database
```

`FINSIGHT_API_URL` is the feature flag. If it is absent, or if the FinSight
boundary is temporarily unavailable, the existing Groq-backed implementation
is used without changing the frontend request or response shape.

The Python boundary defaults to deterministic composition. Set
`FINSIGHT_ENABLE_LLM=true` only when the existing configured LLM should be used.
`FINSIGHT_REQUEST_TIMEOUT_SECONDS` may be set from 1 through 120 seconds.

## Merge strategy

Most of the boundary is contained in new Python files. The only shared existing
file touched is `api/src/modules/AiStock/ai-stock.service.ts`, where a small
feature-flagged adapter runs before the legacy path. Keep that adapter as one
isolated commit when moving the work between branches; merge the new Python
files first, then apply the adapter commit. No frontend component needs to be
replaced because the current UI is already branded FinSight.
