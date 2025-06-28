from .base_service import BaseApiService

class SentimentService(BaseApiService):

    def __init__(self):
        super().__init__()

    async def dispatch(self, params):
        prompts = self._get_prompts('sentiment', text=params.text)
        params.system_prompt = prompts['system_prompt']
        params.user_prompt = prompts['user_prompt']
        params.structured_output = True
        payload = await self._generate_response_with_fallback(params)
        return { 'success': True, 'result': payload }
