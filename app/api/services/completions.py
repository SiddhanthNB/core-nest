from .base_service import BaseService


class CompletionService(BaseService):
    async def dispatch(self, params, *, provider_preference: str | None = None, request=None):
        return await self._fetch_completion(
            messages=[message.model_dump() for message in params.messages],
            request_params=self._completion_request_params(params),
            provider_preference=provider_preference,
            request=request,
        )
