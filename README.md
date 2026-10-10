CoreNest
========

CoreNest is an OpenAI-compatible LLM gateway that sits in front of multiple providers.

It gives you:

- one client-facing contract
- app-owned routing, retries and fallback
- a few opinionated endpoints for common tasks

## Why CoreNest

Most LLM integrations start simple and then become messy:

- provider outages leak into application code
- request parameters drift between providers
- retry behavior becomes ambiguous
- auditing and rate limits get bolted on later

CoreNest gives you a cleaner shape:

- OpenAI-compatible request and response contracts
- provider abstraction via LiteLLM
- app-owned retries, fallback and circuit breaking
- stable `core-nest/*` model aliases
- explicit provider enablement
- per-request traceability via response headers and trace-aware logs

## Quick Start

Docs are served at `/docs`. Health is `GET /ping`.

Authentication:

```http
Authorization: Bearer <API_KEY>
```

Public routes:

- `/v1/chat/completions`
- `/v1/embeddings`
- `/beta/sentiments`
- `/beta/summaries`

Model aliases: `core-nest/auto` plus one `core-nest/<provider>` per enabled provider in [llm_providers.yaml](https://github.com/SiddhanthNB/core-nest/blob/main/app/config/llm_providers.yaml). Currently:

- `core-nest/auto`
- `core-nest/google`
- `core-nest/groq`
- `core-nest/mistral`
- `core-nest/openrouter`

`core-nest/auto` is only valid for chat-style endpoints.

## Consumer Quickstart

### Completions

`POST /v1/chat/completions`

```bash
curl -X POST http://localhost:3000/v1/chat/completions \
  -H "Authorization: Bearer <API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "core-nest/auto",
    "messages": [
      {"role": "user", "content": "Write a haiku about databases"}
    ],
    "temperature": 0.7,
    "max_tokens": 64
  }'
```

Behavior:

- `core-nest/auto` enables CoreNest-owned routing and fallback
- `core-nest/<provider>` locks execution to one provider
- `stream=false` is accepted; streaming is not supported

### Embeddings

`POST /v1/embeddings`

```bash
curl -X POST http://localhost:3000/v1/embeddings \
  -H "Authorization: Bearer <API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "core-nest/google",
    "input": ["hello world", "bye"]
  }'
```

Behavior:

- caller must choose a provider-specific alias
- no cross-provider fallback; `core-nest/auto` is not valid

### Sentiments

`POST /beta/sentiments`

```bash
curl -X POST http://localhost:3000/beta/sentiments \
  -H "Authorization: Bearer <API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "core-nest/auto",
    "messages": [
      {"role": "user", "content": "I loved the product."}
    ]
  }'
```

Behavior:

- no `system` messages; CoreNest injects the system prompt
- response is app-owned JSON; execution policy is locked
- routing follows chat completion rules

### Summaries

`POST /beta/summaries`

```bash
curl -X POST http://localhost:3000/beta/summaries \
  -H "Authorization: Bearer <API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "core-nest/auto",
    "messages": [
      {"role": "user", "content": "Summarize this article..."}
    ]
  }'
```

Behavior:

- no `system` messages; CoreNest injects the system prompt
- plain-text output; JSON is not supported here
- routing follows chat completion rules

## Response Contract

Successful responses are returned without a custom envelope: OpenAI-compatible completion and embedding payloads. The body keeps the alias the client requested.

Response headers:

```http
X-Request-ID: 7a9f3162-b8f5-6540-682a-4ba1fe4e02ff
X-LLM-Backend: mistral:mistral/ministral-8b-2410
```

- `X-Request-ID` is on every response; it is the request's trace id and matches the server logs and audit row
- `X-LLM-Backend` shows which provider actually served the request

## Routing and Fallback

Chat-style routes (`/v1/chat/completions`, `/beta/sentiments`, `/beta/summaries`) use application-owned routing.

With `model=core-nest/auto`:

- enabled providers come from [llm_providers.yaml](https://github.com/SiddhanthNB/core-nest/blob/main/app/config/llm_providers.yaml), in declaration order
- the starting provider rotates via Redis-backed round robin
- fallback proceeds through the remaining providers; open-circuit providers are skipped

With `model=core-nest/<provider>`:

- only that provider is eligible; no fallback
- provider errors are returned through CoreNest's API error mapping
- an open circuit returns `503`

## Reliability

- each provider gets up to 3 attempts with exponential backoff; `Retry-After` is honored, capped at 10s
- client errors (4xx) are never retried
- circuit breaker: 3 provider failures within 10 minutes open the circuit for 60s (Redis-backed); auth failures count, client errors don't
- every request has a hard 90s deadline across all providers and retries; exceeding it returns `504`
- `X-LLM-Timeout` (seconds, max 60) overrides the per-attempt timeout

## Request Validation

CoreNest validates the public contract at the edge: required fields, blocked app-managed params, message restrictions, and locked execution policy.

LiteLLM handles provider-specific support at runtime:

- params a provider doesn't support are dropped instead of erroring
- invalid JSON is treated as provider failure when JSON is required
- `stream=true` is rejected

## OpenAI Compatibility

CoreNest is OpenAI-compatible enough to power agentic workflows, not a full OpenAI clone.

- bearer-token auth works with OpenAI-style clients
- non-streaming SDK workflows work
- errors use an OpenAI-style error envelope

Intentional differences:

- `model` is a CoreNest alias
- streaming is not supported
- routing, retries and fallback stay CoreNest-owned
- beta endpoints stay opinionated

## Auth, Rate Limits, and Audit

- bearer-token client auth (keys stored hashed, cached in Redis for 5 minutes)
- Redis-backed rate limiting (per minute, hour, day, and concurrent)
- Redis-backed provider circuit state
- Postgres audit logging, including provider attempt stacks; skipped in development

## Observability

Logs are flat, single-line text to stdout and `logs/core-nest.<date>.log` (rotated daily, 7 days kept).

Every line carries OpenTelemetry trace and span ids:

```
[2026-10-10 14:34:18] [INFO] [core-nest] [pid: 146453] [trace: 7a9f…] [span: 6075…] : [name: attempt 1 groq] [parent: 0d53…] [duration_ms: 812.4] [status: OK] Span ended
```

- one span per request, per provider, and per retry attempt; each logs one line when it ends
- Redis and DB spans log at `DEBUG`; request and provider spans at `INFO`
- no exporter; spans only exist as log lines
- incoming `traceparent` headers are ignored; every request starts a new trace

## Configuration

- [llm_providers.yaml](https://github.com/SiddhanthNB/core-nest/blob/main/app/config/llm_providers.yaml): provider identity, enablement, API key env names, model IDs
- [api_managed_params.yaml](https://github.com/SiddhanthNB/core-nest/blob/main/app/config/api_managed_params.yaml): endpoint-owned params and defaults

Model IDs are stored explicitly; CoreNest does not auto-prefix them. Provider-specific quirks live in the provider's adapter under `lib/llm/adapters/`.

## Local Setup

Prereqs: Python 3.12+, Postgres, Redis, and API keys for the providers you enable.

```bash
cp .env.sample .env
uv sync
uv run main.py
```

Startup fails immediately if database migrations are pending.

## Environment

Runtime settings come from `.env`:

```bash
APP_ENV=development
PORT=3000
WEB_CONCURRENCY=2

SUPABASE_DB_PASSWORD=replace-me
SUPABASE_DB_URL=postgresql://user:[YOUR-PASSWORD]@host:5432/db

REDIS_PASSWORD=replace-me
REDIS_URL=redis://default:[YOUR-PASSWORD]@host:6379/0

# defaults to True: use LiteLLM's bundled model cost map, no network fetch at startup
LITELLM_LOCAL_MODEL_COST_MAP=True
```

Provider keys are only required for enabled providers:

```bash
GOOGLE_API_KEY=
OPENAI_API_KEY=
HUGGINGFACE_API_KEY=
GROQ_API_KEY=
OPENROUTER_API_KEY=
MISTRAL_API_KEY=
CEREBRAS_API_KEY=
```

## Database and Migrations

CoreNest uses [Duo ORM](https://github.com/SiddhanthNB/duo-orm) while preserving Alembic migration history.

```bash
uv run duo-orm migration.history
uv run duo-orm migration.upgrade
uv run duo-orm migration.downgrade
uv run duo-orm migration.current
uv run duo-orm migration.check
```

## Operational Tasks

```bash
uv run invoke one-time-tasks.create-client --name "Acme Corp"
uv run invoke daily-tasks.provider-health-check
uv run invoke daily-tasks.cleanup-audit-logs --retention-days 60
uv run invoke dev-tasks.lint
```

The health check writes Markdown to `GITHUB_STEP_SUMMARY` when set, and runs daily via GitHub Actions.

## Deployment

Deploys are triggered by pushing a version tag:

```bash
git tag v1.0.0 && git push origin v1.0.0
```

The [CI/CD workflow](https://github.com/SiddhanthNB/core-nest/blob/main/.github/workflows/ci-cd.yml) runs ruff and pytest on the tagged commit, then calls the Render deploy hook for that exact commit.

- requires the `RENDER_CORENEST_DEPLOY_URL` repository secret
- runtime env vars are set on Render, not in the workflow
- Render build command: `uv sync --locked --no-dev`
- run pending migrations before tagging a release that includes them

## Tests

```bash
uv run pytest
```

The suite covers API contracts, request flow, routing and fallback, retries and deadlines, circuit breaking, rate limiting, auth caching, middleware and audit, tracing and log format, and HTTP-level provider calls through LiteLLM (mocked with respx). Tests make no network calls.
