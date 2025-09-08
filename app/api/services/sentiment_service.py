from .base_service import BaseApiService

class SentimentService(BaseApiService):

    def __init__(self):
        super().__init__()

    async def dispatch(self, params):
        prompts = self._get_prompts('sentiment', text=params.text)
        all_params = self._get_all_params(params=params, prompts=prompts, structured_output=True)
        payload = await self._generate_response(all_params)
        return { 'success': True, 'result': payload }
