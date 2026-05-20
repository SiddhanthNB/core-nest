CoreNest
========

CoreNest is an OpenAI-compatible LLM gateway that sits in front of multiple providers.

It gives you:

- one client-facing contract
- app-owned routing and fallback
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
- app-owned fallback and circuit-breaker behavior
- stable `core-nest/*` model aliases
- explicit provider enablement
- request-level provider traceability via response headers

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

Public model aliases:

- `core-nest/auto`
- `core-nest/google`
- `core-nest/groq`
- `core-nest/cerebras`
- `core-nest/mistral`
- `core-nest/huggingface`
- `core-nest/openrouter`

`core-nest/auto` is only valid for chat-style endpoints. It enables CoreNest-owned provider routing and fallback.

## Consumer Quickstart

### Completions

`POST /v1/chat/completions`

Use this when you want an OpenAI-compatible chat/completions endpoint that can power agentic workflows while keeping provider routing under CoreNest control.

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

- user supplies `messages`
- request shape is OpenAI-compatible
- caller supplies a CoreNest model alias via `model`
- `core-nest/auto` enables CoreNest-owned provider routing and fallback
- `core-nest/<provider>` locks execution to a specific provider
- `stream=false` is accepted, but streaming is not supported

### Embeddings

`POST /v1/embeddings`

Use this when you want an OpenAI-compatible embeddings endpoint without cross-provider fallback.

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

- caller must choose a provider-specific CoreNest model alias
- no cross-provider fallback is used
- `core-nest/auto` is not valid for embeddings

### Sentiments

`POST /beta/sentiments`

Use this when you want structured sentiment output without letting callers control the system prompt or execution policy.

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

- caller must not send `system` messages
- CoreNest injects the system prompt
- response format is app-owned JSON
- execution policy fields are locked by the application
- provider routing follows the same model-alias rules as chat completions

### Summaries

`POST /beta/summaries`

Use this when you want an opinionated summarization endpoint with an app-controlled prompt and execution policy.

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

- caller must not send `system` messages
- CoreNest injects the system prompt
- provider selection follows completion routing rules
- summaries are plain-text oriented; JSON output is not app-supported here

## Response Contract

Successful responses are returned without a custom success envelope.

That means:

- `/v1/chat/completions` returns an OpenAI-compatible completion payload
- `/v1/embeddings` returns an OpenAI-compatible embedding payload
- opinionated endpoints return the same payload family while preserving their app-owned execution rules

The response body keeps the public CoreNest model alias the client requested. CoreNest also includes a response header that tells the caller what actually served the request:

```http
X-LLM-Backend: mistral:mistral/ministral-8b-2410
```

This matters when fallback is enabled and the final provider may vary from one request to the next.

## Routing and Fallback

Chat-style routes (`/v1/chat/completions`, `/beta/sentiments`, `/beta/summaries`) use application-owned routing.

Current behavior:

- enabled providers are derived from [llm_providers.yaml](https://github.com/SiddhanthNB/core-nest/blob/main/app/config/llm_providers.yaml)
- provider order follows declaration order in that config
- when `model=core-nest/auto`, CoreNest rotates the starting provider via Redis-backed round robin
- fallback proceeds through the remaining providers
- open-circuit providers are skipped

If `model=core-nest/<provider>` is used:

- only that provider is eligible
- no cross-provider fallback is used
- provider errors are returned directly through CoreNest’s API error mapping

Embeddings are stricter:

- caller must choose a provider-specific model alias
- no cross-provider fallback is allowed

## Request Validation

CoreNest validates the public API contract at the edge.

That means it owns:

- required fields
- blocked app-managed params
- message restrictions on opinionated endpoints
- endpoint-specific locked execution policy

LiteLLM then handles provider-specific request support at runtime.

Examples:

- unsupported provider-specific params become runtime provider errors
- invalid JSON from a provider is treated as provider failure when JSON is required
- `/beta/sentiments` always expects valid JSON output
- `/beta/summaries` does not support JSON output as an app-level contract
- `/v1/chat/completions` accepts common OpenAI client fields like `stream=false`, but rejects unsupported active behavior like `stream=true`

## OpenAI Compatibility

CoreNest is designed to be OpenAI-compatible enough to power agentic workflows, not to be a full OpenAI feature clone.

That means:

- standard bearer-token auth works with OpenAI-style clients
- `/v1/chat/completions` and `/v1/embeddings` follow an OpenAI-compatible HTTP surface
- request and response bodies are compatible enough for non-streaming SDK workflows
- error responses use an OpenAI-style error envelope

Intentional differences:

- `model` is a CoreNest alias such as `core-nest/auto` or `core-nest/google`
- streaming is not supported
- provider switching, circuit breaking, and fallback remain CoreNest-owned behavior
- beta endpoints stay opinionated even though they use the same general payload family

## Auth, Rate Limits, and Audit

CoreNest includes request-level controls:

- bearer-token client auth
- Redis-backed client caching
- Redis-backed rate limiting
- Redis-backed provider circuit state
- Postgres audit logging

Audit logging records request/response metadata, including provider attempt stacks. In development mode, audit persistence is skipped.

## Configuration

Main config:

- [llm_providers.yaml](https://github.com/SiddhanthNB/core-nest/blob/main/app/config/llm_providers.yaml)
  - provider identity
  - provider enablement
  - API key env variable names
  - default model IDs
- [api_managed_params.yaml](https://github.com/SiddhanthNB/core-nest/blob/main/app/config/api_managed_params.yaml)
  - endpoint-owned params and defaults

Model IDs are stored explicitly. CoreNest does not auto-prefix provider model names dynamically.

## Local Setup

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

Before the server starts, CoreNest checks for pending migrations. If the database revision is behind the repo head, startup fails immediately.

## Environment

Runtime settings come from `.env`.

Base variables:

```bash
APP_ENV=development
PORT=3000
WEB_CONCURRENCY=2

SUPABASE_DB_PASSWORD=replace-me
SUPABASE_DB_URL=postgresql://user:[YOUR-PASSWORD]@host:5432/db

REDIS_PASSWORD=replace-me
REDIS_URL=redis://default:[YOUR-PASSWORD]@host:6379/0
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

CoreNest uses [Duo ORM](https://github.com/SiddhanthNB/duo-orm) as the database foundation while preserving Alembic migration history.

Common commands:

```bash
uv run duo-orm migration.history
uv run duo-orm migration.upgrade
uv run duo-orm migration.downgrade
```

Verification:

```bash
uv run duo-orm migration.current
uv run duo-orm migration.check
```

## Operational Tasks

Create a client:

```bash
uv run invoke one-time-tasks.create-client --name "Acme Corp"
```

Run provider health checks:

```bash
uv run invoke daily-tasks.provider-health-check
```

This writes Markdown to `GITHUB_STEP_SUMMARY` when that environment variable is present.

Clean up old audit rows:

```bash
uv run invoke daily-tasks.cleanup-audit-logs --retention-days 60
```

Lint the repo:

```bash
uv run invoke dev-tasks.lint
```

## Tests

Run the test suite with:

```bash
uv run pytest
```

The current suite focuses on:

- API contract validation
- request flow
- provider routing policy
- middleware and audit behavior
- provider health utilities
- Redis-backed provider ordering behavior
