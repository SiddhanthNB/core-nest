from .base_service import BaseService


class SentimentService(BaseService):
    async def dispatch(self, params, *, provider_preference: str | None = None, request=None):
        prompts = self._get_prompts("sentiment", text=params.text)
        messages = self._system_messages(
            app_system_prompt=prompts["system_prompt"],
            user_system_prompt=params.system_prompt,
        ) + [self._message("user", prompts["user_prompt"])]
        return await self._fetch_completion(
            messages=messages,
            request_params={
                "temperature": 0,
                "stream": False,
                "response_format": {"type": "json_object"},
            },
            provider_preference=provider_preference,
            request=request,
        )
