CoreNest
========

CoreNest is a FastAPI-powered gateway that fronts multiple LLM providers (Google, OpenAI, OpenRouter, Groq, Mistral/Minstral, Cerebras, HuggingFace) behind a single, authenticated API. It ships with provider failover, Redis-backed auth + rate limiting, Postgres-backed request logging, and prompt packs for turnkey summarization and sentiment analysis.

## Contents
- [Quick start](#quick-start)
- [Configuration](#configuration)
- [Running the API](#running-the-api)
- [Database & migrations](#database--migrations)
- [Authentication & rate limiting](#authentication--rate-limiting)
- [Endpoints](#endpoints)
- [Providers & prompts](#providers--prompts)
- [Observability](#observability)
- [Project tasks](#project-tasks)
- [Roadmap](#roadmap)

## Quick start
Prereqs: Python 3.12, Postgres, Redis, and provider API keys.

```bash
# Start from the sample env (contains all required keys)
cp .env.sample .env

# create and activate a virtualenv, then install deps
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# update .env values (see tables below)
python main.py        # runs uvicorn with reload in APP_ENV=development
```

Docs live at `/redoc`; health at `/ping`.

## Configuration
Core settings live in environment variables and `app/utils/providers.yaml` (env vars are interpolated into that file).

### Required environment
| Variable | Purpose | Example |
| --- | --- | --- |
| `APP_ENV` | `development` enables uvicorn reload and disables DB request logging. Default: `production`. | `development` |
| `PORT` | HTTP port. | `3000` |
| `WEB_CONCURRENCY` | Uvicorn workers when not in dev. | `2` |
| `SUPABASE_DB_PASSWORD` | Postgres password (used to patch into `SUPABASE_DB_URL`). | `p@ss` |
| `SUPABASE_DB_URL` | Postgres URL containing `[YOUR-PASSWORD]` placeholder. | `postgresql://user:[YOUR-PASSWORD]@host:5432/db` |
| `REDIS_PASSWORD` | Redis password (used to patch into `REDIS_URL`). | `redis-pass` |
| `REDIS_URL` | Redis URL containing `[YOUR-PASSWORD]` placeholder. | `redis://default:[YOUR-PASSWORD]@host:6379/0` |
| `GOOGLE_API_KEY` | Gemini key. | `...` |
| `OPENAI_API_KEY` | OpenAI key. | `...` |
| `HUGGINGFACE_API_KEY` | HuggingFace key. | `...` |
| `GROQ_API_KEY` | Groq key. | `...` |
| `OPENROUTER_API_KEY` | OpenRouter key. | `...` |
| `MINSTRAL_API_KEY` | Mistral key. | `...` |
| `CEREBRAS_API_KEY` | Cerebras key. | `...` |

Optional: `CLIENT_ID`, `CLIENT_SECRET` (reserved for future use).

Minimal `.env` skeleton (already stubbed in `.env.sample`):
```bash
APP_ENV=development
PORT=3000
WEB_CONCURRENCY=2
SUPABASE_DB_PASSWORD=replace-me
SUPABASE_DB_URL=postgresql://user:[YOUR-PASSWORD]@host:5432/db
REDIS_PASSWORD=replace-me
REDIS_URL=redis://default:[YOUR-PASSWORD]@host:6379/0
GOOGLE_API_KEY=replace-me
OPENAI_API_KEY=replace-me
HUGGINGFACE_API_KEY=replace-me
GROQ_API_KEY=replace-me
OPENROUTER_API_KEY=replace-me
MINSTRAL_API_KEY=replace-me
CEREBRAS_API_KEY=replace-me
```

### Provider models & endpoints
`app/utils/providers.yaml` defines default models and URLs per provider. Update this file (and restart) to switch models globally.

## Running the API
Set `APP_ENV`, `PORT`, and `WEB_CONCURRENCY` in your `.env` (or export them) first.
```bash
# dev with reload (reads env from .env)
python main.py

# or directly via uvicorn
uvicorn main:app --reload --port 3000

# production-style (APP_ENV=production, uses WEB_CONCURRENCY workers from env)
python main.py
```

## Database & migrations
- Connection: `SUPABASE_DB_URL` (converted to async psycopg URL internally).
- Migrations: Alembic lives in `app/db/migrations`.

Common commands:
```bash
# upgrade to latest
alembic -c app/db/migrations/alembic.ini upgrade head
# inspect history
alembic -c app/db/migrations/alembic.ini history
```

Tables:
- `corenest__clients`: API clients + hashed keys.
- `corenest__rate_limit_configs`: per-client rate limits.
- `corenest__api_logs`: request metadata (persisted when not in dev).

## Authentication & rate limiting
- Requests must include `Authorization: Bearer <API_KEY>`.
- API keys are generated and stored hashed. Create one via Invoke:
  ```bash
  inv one-time-tasks.create-client --name "Acme Corp"
  ```
- Client lookups are cached in Redis with sliding TTL to reduce DB load.
- Rate limiting is per client (minute/hour/day/concurrent) enforced via Redis; limits live in `corenest__rate_limit_configs`.

## Endpoints
All endpoints expect JSON and return `{ "success": true, "result": { ... } }` on success. Omit `provider` to use automatic failover.

- `POST /completions`
  ```bash
  curl -X POST http://localhost:3000/completions \
    -H "Authorization: Bearer <API_KEY>" \
    -H "Content-Type: application/json" \
    -d '{
      "user_prompt": "Write a haiku about databases",
      "system_prompt": "You are a concise assistant",
      "structured_output": false,
      "provider": "openai"
    }'
  ```
- `POST /embeddings`
  ```bash
  curl -X POST http://localhost:3000/embeddings \
    -H "Authorization: Bearer <API_KEY>" \
    -H "Content-Type: application/json" \
    -d '{ "texts": ["hello world", "bye"], "provider": "google" }'
  ```
- `POST /sentiments`
  Uses predefined prompts and structured output for sentiment classification.
  ```bash
  curl -X POST http://localhost:3000/sentiments \
    -H "Authorization: Bearer <API_KEY>" \
    -H "Content-Type: application/json" \
    -d '{ "text": "I loved the product!", "provider": "groq" }'
  ```
- `POST /summaries`
  Summarization with built-in prompts.
  ```bash
  curl -X POST http://localhost:3000/summaries \
    -H "Authorization: Bearer <API_KEY>" \
    -H "Content-Type: application/json" \
    -d '{ "text": "Long article text here" }'
  ```

Misc:
- `GET /ping` healthcheck.
- `GET /` redirects to `/redoc`.

## Providers & prompts
- Failover order (when `provider` is omitted): `groq -> google -> openrouter -> openai -> minstral -> cerebras`.
- Prompt templates live in `app/utils/prompts/{system_prompts,user_prompts}` and are loaded by services for summarization/sentiment flows.
- Set `structured_output: true` to force JSON parsing of model responses (adapters attempt to extract JSON blocks).

## Observability
- Logging: console logging configured in `app/config/logger.py`; daily rotation is wired but commented out.
- API logging: middleware in `app/utils/helpers/api_logger.py` writes request metadata to Postgres (disabled in `development`).

## Project tasks
- Invoke collection: `tasks.py` + `app/utils/tasks/one_time_tasks.py`.
  - `inv one-time-tasks.create-client --name "<client>"`: create a client + API key.
- Make targets: `make install_dependencies`, `make migration-upgrade`, etc. (see `Makefile`).
