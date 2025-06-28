from .base_service import BaseApiService

class CompletionService(BaseApiService):

    def __init__(self):
        super().__init__()

    async def dispatch(self, params):
        payload = await self._generate_response_with_fallback(params)
        return { 'success': True, 'result': payload }
