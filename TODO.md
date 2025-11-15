# BYOT (Bring Your Own Token) Integration Plan

This document outlines the steps to implement a "Bring Your Own Token" (BYOT) feature, allowing users to leverage their own provider credentials while still benefiting from the CoreNest unified API.

## Phase 1: MVP Implementation

**Scope:**
- **Endpoints:** `/completions` and `/embeddings`
- **Providers:** `openai` and `google`

---

### Task 1: API Design and Schema Definition

The BYOT feature will be triggered by the presence of specific HTTP headers. CoreNest authentication is still required for all requests to track usage and prevent abuse.

- **Headers for BYOT trigger:**
    - `X-Provider`: The name of the provider (e.g., `"openai"`, `"google"`).
    - `X-Token`: The user's personal API key for the specified provider.

- **JSON Body Modifications:**
    - The schemas for `CompletionSchema` and `EmbeddingSchema` will be updated to include an optional `model` field.
    - If `model` is provided in a BYOT request, it will override the default model configured for that provider.
    - If `model` is not provided, the adapter's default model will be used.

### Task 2: Security - Prevent Token Logging

It is critical that user-provided tokens are never logged.

- **File to Modify:** `app/utils/helpers/api_logger.py`
- **Action:**
    - Update the logging middleware/utility to inspect incoming request headers.
    - Before logging the request details, check for the `X-Token` header.
    - If it exists, replace its value with a redacted placeholder (e.g., `"[REDACTED]"`).

### Task 3: Update Service Layer Logic

The service layer will be adapted to handle the new BYOT request flow.

- **Files to Modify:** `app/api/services/completion_service.py`, `app/api/services/embeddings_service.py`, and potentially `app/api/services/base_service.py`.
- **Action:**
    - In the `dispatch` method of each service, check for the presence of `X-Provider` and `X-Token` headers.
    - **If headers are present (BYOT Flow):**
        1.  Bypass the standard provider selection and fallback logic (`_generate_response_with_fallback`).
        2.  Instantiate the correct adapter (e.g., `OpenAIAdapter`) based on the `X-Provider` header value.
        3.  Call the adapter's method, passing the user's `X-Token` and the optional `model` from the request body as new arguments.
    - **If headers are absent (Managed Flow):**
        1.  The logic proceeds as it currently does.

### Task 4: Update Adapters for Credential Overriding

The adapters must be updated to accept and use the user-provided credentials.

- **Files to Modify:** `app/adapters/openai_adapter.py`, `app/adapters/google_adapter.py`.
- **Action:**
    - Modify the relevant methods (e.g., `generate_response`, `generate_embeddings`) to accept optional `api_key` and `model` arguments.
    - Inside the method, if an `api_key` is provided, use it to set the `Authorization` header for the `httpx` request, overriding the instance's default key.
    - If a `model` is provided, use it in the request payload instead of the default model.

### Task 5: Implement Specific Error Handling

Clear error messages for BYOT users are essential for a good user experience.

- **Files to Modify:** Service layer files (`completion_service.py`, etc.).
- **Action:**
    - Wrap the adapter calls in a `try...except` block that specifically catches `httpx.HTTPStatusError`.
    - Inspect the error response from the provider.
    - If the status code is `401` (Unauthorized) or `403` (Forbidden), return an `HTTP 400 Bad Request` to the end-user with a clear message like: `{"detail": "The provided token for 'openai' is invalid, expired, or has insufficient permissions."}`.
    - If the status code is `429` (Too Many Requests), return an `HTTP 429` with a message like: `{"detail": "The provided token for 'openai' has exceeded its quota. Please check your provider account."}`.

### Task 6: Create a Client Management Script

To address the inconvenience of manual database entries for new CoreNest clients.

- **New File:** `scripts/create_client.py`
- **Action:**
    - Create a standalone Python script that connects to the database.
    - The script should accept a client `name` as a command-line argument.
    - It will then:
        1.  Generate a new secure API key.
        2.  Hash the key.
        3.  Create a new `Client` record in the database with the provided name and hashed key.
        4.  Print the new, un-hashed API key to the console for the admin to share with the user.

---

## Phase 2: Future Enhancements (Post-MVP)

- [ ] Extend BYOT support to `/summaries` and `/sentiments` endpoints.
- [ ] Add BYOT support for the remaining providers: `groq`, `huggingface`, `openrouter`.
- [ ] Develop an internal-only admin API endpoint (e.g., `/admin/clients`) as a more robust alternative to the script for client management.
- [ ] Consider implementing a caching layer for BYOT requests to reduce redundant calls for identical prompts.