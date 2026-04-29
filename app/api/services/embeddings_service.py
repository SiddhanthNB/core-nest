from .base_service import BaseService


class EmbeddingsService(BaseService):
    def _request_params(self, _params) -> dict:
        return {}

    async def dispatch(self, params, *, provider_preference: str | None = None, request=None):
        return await self._fetch_embedding(
            input_data=params.input,
            request_params=self._request_params(params),
            provider_preference=provider_preference,
            request=request,
        )
