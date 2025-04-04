import asyncio
from config.logger import logger
from api.controllers.api_controller import ApiController

class SummarizationController(ApiController):

    def __init__(self, auth):
        super().__init__()
        self.auth_token_validator(auth)

    async def dispatch(self, params, summarizer_model):
        try:
            prompt = f"Summarize: \n{params.corpus}"
            result = await asyncio.to_thread(summarizer_model, prompt, max_length=100, do_sample=False)
            return { 'success': True, 'result': result[0]["summary_text"] }
        except Exception as e:
            logger.error(f'Error while creating embeddings: {str(e)}', exc_info=True)
            raise e
