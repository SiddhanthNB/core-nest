import asyncio
from app.config.logger import logger
from .base_service import BaseApiService

class SummarizationService(BaseApiService):

    def __init__(self):
        super().__init__()

    async def dispatch(self, params, summarizer_model):
        try:
            prompt = f"Summarize: \n{params.corpus}"
            result = await asyncio.to_thread(summarizer_model, prompt, max_length=100, do_sample=False)
            return { 'success': True, 'result': result[0]["summary_text"] }
        except Exception as e:
            logger.error(f'Error while creating embeddings: {str(e)}', exc_info=True)
            raise
