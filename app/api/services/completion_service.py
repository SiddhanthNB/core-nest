from .base_service import BaseService


class CompletionService(BaseService):
    def _request_params(self, params) -> dict:
        return {
            "temperature": params.temperature,
            "max_completion_tokens": params.max_completion_tokens,
            "max_tokens": params.max_tokens,
            "top_p": params.top_p,
            "stream": params.stream,
            "stream_options": params.stream_options,
            "stop": params.stop,
            "n": params.n,
            "presence_penalty": params.presence_penalty,
            "frequency_penalty": params.frequency_penalty,
            "functions": params.functions,
            "function_call": params.function_call,
            "logit_bias": params.logit_bias,
            "user": params.user,
            "tools": params.tools,
            "tool_choice": params.tool_choice,
            "response_format": params.response_format,
            "seed": params.seed,
            "logprobs": params.logprobs,
            "top_logprobs": params.top_logprobs,
            "extra_headers": params.extra_headers,
        }

    async def dispatch(self, params, *, provider_preference: str | None = None, request=None):
        return await self._fetch_completion(
            messages=[message.model_dump() for message in params.messages],
            request_params=self._request_params(params),
            provider_preference=provider_preference,
            request=request,
        )
