# Project TODO List

This list outlines the key architectural and development tasks for the core-nest API.

## 1. Authentication & Authorization

- [ ] **Implement Dual Authentication Dependency:**
  - Create a single FastAPI dependency (`get_current_auth`) to handle authentication.
  - The dependency should support two methods:
    1.  **Our API Keys:** Based on a `client_id` provided by our service (e.g., in `Authorization` header).
    2.  **Bring Your Own Token (BYOT):** For users providing their own keys for providers like OpenAI, Gemini, etc. (e.g., in `X-Provider-Token` headers).
  - The dependency should return a structured object (e.g., an `AuthState` Pydantic model) indicating the auth method and relevant identifiers (`client_id`).

- [ ] **Secure Client Credential Storage:**
  - Each client using our API keys must have a unique `client_id` and `client_secret`.
  - In the database, `client_secret`s must be stored as a **hash** using a strong algorithm (e.g., Bcrypt), never in plaintext.

- [ ] **Implement Authentication Caching with Redis:**
  - To improve performance and reduce database load, add a caching layer to the authentication dependency.
  - On an authentication attempt, first query Redis for the client's cached `hashed_secret`.
  - **On Cache Miss:** Query the primary PostgreSQL database, and upon successful validation, store the `hashed_secret` in the Redis cache.
  - **On Cache Hit:** Use the `hashed_secret` from Redis for verification.
  - **Expiration Policy:** Use a **sliding window** expiration. On each successful cache hit, reset the TTL of the key (e.g., to 5 minutes).
  - **Revocation:** The process for revoking a client's access must include deleting their entry from both the PostgreSQL database and the Redis cache.

## 2. Rate Limiting

- [ ] **Implement Redis-based Rate Limiter:**
  - Create a FastAPI dependency (`apply_rate_limiting`) that uses Redis to perform rate limiting.
  - This dependency must chain from the authentication dependency, using the `client_id` from the `AuthState` object.
  - Rate limiting should only be applied to requests using our API keys, not to BYOT requests.
  - Use an `asyncio`-compatible Redis client (`redis.asyncio`) to avoid blocking the server.
  - Connect to the Redis instance using an environment variable (`REDIS_URL`).

## 3. Security Hardening

- [ ] **Remove `auth_headers` from API Logs:**
  - This is a **critical security vulnerability**.
  - Modify the `_APILoggerMiddleware` to stop logging the `auth_headers` field.
  - Remove the `auth_headers` column from the `APILog` model and create a database migration to drop it from the table.

## 4. General
- [ ] Review and refactor existing code to incorporate the new dependency structure for auth and rate limiting.
