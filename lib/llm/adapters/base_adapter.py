import json
import httpx
from app.config.logger import logger
from fastapi import HTTPException, status as HTTPStatus
from tenacity import AsyncRetrying, retry_if_exception, stop_after_attempt, wait_exponential

class BaseAdapter:

    def __init__(self):
        self._request_timeout = httpx.Timeout(30.0)

    async def _request_with_retries(self, client, method, url, **kwargs):
        timeout = kwargs.pop("timeout", self._request_timeout)

        def _is_retryable_exception(exc):
            retryable_status = {429, 500, 502, 503, 504}
            if isinstance(exc, (httpx.ReadTimeout, httpx.ConnectError)):
                return True
            if isinstance(exc, httpx.HTTPStatusError):
                return exc.response.status_code in retryable_status
            return False

        def _log_before_sleep(retry_state):
            exc = retry_state.outcome.exception()
            sleep = retry_state.next_action.sleep if retry_state.next_action else 0
            logger.warning(f"[retry attempt {retry_state.attempt_number}] Request to {url} with HTTP method {method} failed; retrying in {sleep:.1f}s due to: {exc}")

        async for attempt in AsyncRetrying(
            wait=wait_exponential(multiplier=1, min=1, max=8),
            stop=stop_after_attempt(4),
            retry=retry_if_exception(_is_retryable_exception),
            before_sleep=_log_before_sleep,
            reraise=True,
        ):
            with attempt:
                response = await client.request(method, url, timeout=timeout, **kwargs)
                response.raise_for_status()
                return response

    def response_parser(self, response):
        def _extract_json_block(text):
            text = text.strip()
            start_marker = "```json"
            end_marker = "```"

            start_idx = text.index(start_marker) + len(start_marker)
            end_idx = text.index(end_marker, start_idx)
            json_str = text[start_idx:end_idx].strip()

            return json.loads(json_str)

        if response.startswith('{') and response.endswith('}'):
            return json.loads(response)
        elif '```json' in response and '```' in response:
            return _extract_json_block(response)
        else:
            raise HTTPException(status_code=HTTPStatus.HTTP_500_INTERNAL_SERVER_ERROR, detail="No JSON block found in response")
