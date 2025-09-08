from .base_service import BaseApiService

class SummarizationService(BaseApiService):

    def __init__(self):
        super().__init__()

    async def dispatch(self, params):
        prompts = self._get_prompts('summarization', text=params.text)
        all_params = self._get_all_params(params=params, prompts=prompts)
        payload = await self._generate_response(all_params)
        return { 'success': True, 'result': payload }
