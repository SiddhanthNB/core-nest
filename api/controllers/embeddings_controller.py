import asyncio
from config.logger import logger
from api.controllers.api_controller import ApiController

class EmbeddingsController(ApiController):

    def __init__(self, auth):
        super().__init__()
        self.auth_token_validator(auth)

    async def dispatch(self, params, embedding_model):
        try:
            result = await asyncio.to_thread(embedding_model.encode, params.texts)
            return { 'success': True, 'result': result.tolist() }
        except Exception as e:
            logger.error(f'Error while creating embeddings: {str(e)}', exc_info=True)
            raise e
