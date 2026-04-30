CoreNest
========

CoreNest is a FastAPI LLM gateway with:

- multi-provider completions
- provider-pinned embeddings
- Redis-backed auth and rate limiting
- Postgres audit logging
- Duo ORM-managed models and migrations

The public API is OpenAI-like. Successful responses are returned raw, without a custom success envelope.

## Quick Start

Prereqs:

- Python 3.12+
- Postgres
- Redis
- provider API keys for the providers you enable

```bash
cp .env.sample .env
uv sync
uv run main.py
```

Docs are served at `/docs`. Health is `GET /ping`.

## Environment

Core runtime settings come from `.env`.

Required base variables:

```bash
APP_ENV=development
PORT=3000
WEB_CONCURRENCY=2

SUPABASE_DB_PASSWORD=replace-me
SUPABASE_DB_URL=postgresql://user:[YOUR-PASSWORD]@host:5432/db

REDIS_PASSWORD=replace-me
REDIS_URL=redis://default:[YOUR-PASSWORD]@host:6379/0
```

Provider keys are only required for the providers you actually use:

```bash
GOOGLE_API_KEY=
OPENAI_API_KEY=
HUGGINGFACE_API_KEY=
GROQ_API_KEY=
OPENROUTER_API_KEY=
MISTRAL_API_KEY=
CEREBRAS_API_KEY=
```

## Startup Behavior

`uv run main.py` starts Uvicorn from Python code so reload and worker settings stay environment-driven.

Before the server starts, the app checks for pending migrations. If the database revision is behind the repo head, startup fails immediately.

## Config Files

Core config lives in:

- [providers.yaml](/home/sid/my_stuff/repos/core-nest/lib/llm/providers.yaml)
  - provider identity
  - API key env var names
  - default model IDs
- [provider_policy.yaml](/home/sid/my_stuff/repos/core-nest/app/config/provider_policy.yaml)
  - completion providers in fallback order
  - embedding providers allowlist
- [api_managed_params.yaml](/home/sid/my_stuff/repos/core-nest/app/config/api_managed_params.yaml)
  - endpoint-owned params and defaults

`providers.yaml` is explicit. Model IDs should be fully provider-prefixed where LiteLLM expects that. The app does not try to auto-prefix model names dynamically.

## API Contract

Authentication:

```http
Authorization: Bearer <API_KEY>
```

Optional routing header for completions and opinionated text endpoints:

```http
X-LLM-Provider: mistral
```

For `/embeddings`, `X-LLM-Provider` is required.

### POST /completions

Flexible OpenAI-like endpoint.

Example:

```bash
curl -X POST http://localhost:3000/completions \
  -H "Authorization: Bearer <API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "Write a haiku about databases"}
    ],
    "temperature": 0.7,
    "max_tokens": 64
  }'
```

Notes:

- user supplies `messages`
- app manages `model`, `provider`, `stream`, and `stream_options`
- supported public params are OpenAI-like and validated at the API edge
- provider-specific param support is left to LiteLLM at runtime

### POST /embeddings

Embedding-specific endpoint.

Example:

```bash
curl -X POST http://localhost:3000/embeddings \
  -H "Authorization: Bearer <API_KEY>" \
  -H "X-LLM-Provider: google" \
  -H "Content-Type: application/json" \
  -d '{
    "input": ["hello world", "bye"]
  }'
```

Notes:

- `X-LLM-Provider` is required
- no cross-provider fallback
- app manages `model`

### POST /sentiments

Opinionated sentiment endpoint.

Example:

```bash
curl -X POST http://localhost:3000/sentiments \
  -H "Authorization: Bearer <API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "I loved the product."}
    ]
  }'
```

Notes:

- user must not send `system` messages
- app injects the system prompt
- app manages `model`, `temperature`, `tools`, `tool_choice`, `stream`, `stream_options`, `response_format`
- response format is application-owned

### POST /summaries

Opinionated summarization endpoint.

Example:

```bash
curl -X POST http://localhost:3000/summaries \
  -H "Authorization: Bearer <API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "Summarize this long article..."}
    ]
  }'
```

Notes:

- user must not send `system` messages
- app injects the system prompt
- app manages execution-policy fields the same way as `/sentiments`

## Provider Routing

Completion routing is policy-driven. The current fallback order lives in [provider_policy.yaml](/home/sid/my_stuff/repos/core-nest/app/config/provider_policy.yaml).

If `X-LLM-Provider` is present:

- only that provider is tried
- no fallback is used

If `X-LLM-Provider` is absent:

- `/completions`, `/sentiments`, and `/summaries` use the configured completion provider order
- `/embeddings` does not fallback across providers

## Auth, Rate Limiting, and Audit

- router-level dependency is `rate_limiter`
- `rate_limiter` depends on `auth`
- auth reads the bearer token, resolves the client, caches it in Redis, and attaches it to `request.state`
- rate limits are enforced from the client’s `rate_limit_config`

Audit logging:

- one audit row per request/response cycle
- table: `corenest__audit_logs`
- stored metadata is compact and sanitized
- `401` auth failures do not create audit rows
- audit logging is skipped in `development`

## Database and Migrations

This repo uses Duo ORM as the database foundation while preserving the existing Alembic history.

Common commands:

```bash
uv run duo-orm migration.history
uv run duo-orm migration.upgrade
uv run duo-orm migration.downgrade
```

Low-level verification:

```bash
uv run .venv/bin/alembic -c app/db/migrations/alembic.ini current
uv run .venv/bin/alembic -c app/db/migrations/alembic.ini check
```

## Tasks

Create a client:

```bash
uv run invoke one-time-tasks.create-client --name "Acme Corp"
```

Provider health check:

```bash
uv run invoke daily-tasks.provider-health-check
```

This writes Markdown to `GITHUB_STEP_SUMMARY` when that environment variable is present.

Audit cleanup:

```bash
uv run invoke daily-tasks.cleanup-audit-logs --retention-days 60
```

## Tests

Run the test suite with:

```bash
uv run pytest
```

The current suite focuses on:

- API contract validation
- request flow
- provider policy
- middleware/audit behavior
- provider health utility behavior

Provider behavior itself is still verified manually when needed.
