from app.config.logger import logger
from .base_service import BaseApiService

class SentimentService(BaseApiService):

    def __init__(self):
        super().__init__()

    async def dispatch(self, params, analyzer):
        try:
            pass
        except Exception as e:
            logger.error(f'Error while creating embeddings: {str(e)}', exc_info=True)
            raise
