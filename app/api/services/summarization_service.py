from .base_service import BaseService


class SummarizationService(BaseService):
    def _request_params(self, params) -> dict:
        return params.model_dump(exclude={"messages", "model", "provider"})

    async def dispatch(self, params, *, provider_preference: str | None = None, request=None):
        messages = self._system_messages(app_system_prompt=self._get_system_prompt("summarization", text="")) + [
            message.model_dump() for message in params.messages
        ]
        return await self._fetch_completion(
            messages=messages,
            request_params=self._request_params(params),
            provider_preference=provider_preference,
            request=request,
        )
