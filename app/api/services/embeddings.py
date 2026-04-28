from .base_service import BaseService


class EmbeddingsService(BaseService):
    async def dispatch(self, params, *, provider_preference: str | None = None, request=None):
        return await self._fetch_embedding(
            input_data=params.input,
            request_params={},
            provider_preference=provider_preference,
            request=request,
        )
