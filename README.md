CoreNest
========

CoreNest is an OpenAI-like LLM gateway for teams that want one stable API surface across multiple providers, while keeping routing, fallback, and operational policy under application control.

It is built for production use cases where you want:

- one client-facing contract
- multiple model providers behind it
- provider fallback owned by your application, not by the SDK
- Redis-backed circuit breaking and request throttling
- audit logging for request and response metadata
- opinionated endpoints for common tasks like sentiment analysis and summarization

## Why CoreNest

Most LLM integrations start simple and then become operationally messy:

- provider outages leak into application code
- request parameters drift between providers
- retry behavior becomes ambiguous
- auditing and rate limits get bolted on later

CoreNest gives you a cleaner shape:

- OpenAI-like request and response contracts
- provider abstraction via LiteLLM
- app-owned fallback and circuit-breaker behavior
- provider-pinned embeddings
- explicit operator-controlled provider enablement
- request-level provider traceability via response headers

## Quick Start

Docs are served at `/docs`. Health is `GET /ping`.

Authentication:

```http
Authorization: Bearer <API_KEY>
```

Optional provider override for completions and opinionated text endpoints:

```http
X-LLM-Provider: mistral
```

For `/embeddings`, `X-LLM-Provider` is required.

## Consumer Quickstart

### Completions

`POST /completions`

Use this when you want a flexible, OpenAI-like chat/completions endpoint.

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

Behavior:

- user supplies `messages`
- request shape is OpenAI-like
- app manages `model`, `provider`, `stream`, and `stream_options`
- if no provider is forced, CoreNest selects from enabled completion providers
- if `X-LLM-Provider` is present, only that provider is tried

### Sentiments

`POST /sentiments`

Use this when you want structured sentiment output without letting callers control the system prompt or execution policy.

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

Behavior:

- caller must not send `system` messages
- CoreNest injects the system prompt
- response format is app-owned JSON
- execution policy fields are locked by the application

### Summaries

`POST /summaries`

Use this when you want an opinionated summarization endpoint with an app-controlled prompt and execution policy.

```bash
curl -X POST http://localhost:3000/summaries \
  -H "Authorization: Bearer <API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "Summarize this article..."}
    ]
  }'
```

Behavior:

- caller must not send `system` messages
- CoreNest injects the system prompt
- provider selection follows completion routing rules

### Embeddings

`POST /embeddings`

Use this when you want embeddings from a specific provider without cross-provider fallback.

```bash
curl -X POST http://localhost:3000/embeddings \
  -H "Authorization: Bearer <API_KEY>" \
  -H "X-LLM-Provider: google" \
  -H "Content-Type: application/json" \
  -d '{
    "input": ["hello world", "bye"]
  }'
```

Behavior:

- `X-LLM-Provider` is required
- no cross-provider fallback is used
- app manages `model`

## Response Contract

Successful responses are returned without a custom success envelope.

That means:

- `/completions` returns an OpenAI-like completion payload
- `/embeddings` returns an OpenAI-like embedding payload
- opinionated endpoints also return LiteLLM/OpenAI-like payloads

CoreNest also includes response headers that tell the caller what actually served the request:

```http
X-LLM-Provider: mistral
X-LLM-Model: mistral/ministral-8b-2410
```

This matters when fallback is enabled and the final provider may vary.

## Routing and Fallback

Completion-style routes (`/completions`, `/sentiments`, `/summaries`) use application-owned routing.

Current behavior:

- enabled providers are derived from [llm_providers.yaml](https://github.com/SiddhanthNB/core-nest/blob/main/app/config/llm_providers.yaml)
- provider order follows declaration order in that config
- when no provider is forced, CoreNest rotates the starting provider via Redis-backed round robin
- fallback proceeds through the remaining providers
- open-circuit providers are skipped

If `X-LLM-Provider` is present:

- only that provider is eligible
- no cross-provider fallback is used
- provider errors are returned directly through CoreNest’s API error mapping

Embeddings are stricter:

- `X-LLM-Provider` is required
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
- `/sentiments` always expects valid JSON output
- `/completions` only enforces JSON output when the caller explicitly requests it

## Auth, Rate Limits, and Audit

CoreNest includes request-level operational controls:

- bearer-token client auth
- Redis-backed client caching
- Redis-backed rate limiting
- Redis-backed provider circuit state
- Postgres audit logging

Audit logging records request/response metadata, including provider attempt stacks. In development mode, audit persistence is skipped.

## Configuration

Primary runtime config:

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

Core runtime settings come from `.env`.

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

CoreNest uses Duo ORM as the database foundation while preserving Alembic migration history.

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
