from .base_service import BaseApiService

class SummarizationService(BaseApiService):

    def __init__(self):
        super().__init__()

    async def dispatch(self, params):
        prompts = self._get_prompts('summarization', text=params.text)
        params.system_prompt = prompts['system_prompt']
        params.user_prompt = prompts['user_prompt']
        payload = await self._generate_response_with_fallback(params)
        return { 'success': True, 'result': payload }
