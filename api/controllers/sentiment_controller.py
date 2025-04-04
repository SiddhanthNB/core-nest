import asyncio
from config.logger import logger
from api.controllers.api_controller import ApiController

class SentimentController(ApiController):

    def __init__(self, auth):
        super().__init__()
        self.auth_token_validator(auth)

    async def dispatch(self, params, analyzer):
        try:
            text = params.text.strip()
            scores = await asyncio.to_thread(analyzer.polarity_scores, text)
            compound_score = scores['compound']

            if scores['compound'] >= 0.05:
                sentiment = 'positive'
            elif scores['compound'] <= -0.05:
                sentiment = 'negative'
            else:
                sentiment = 'neutral'

            return { 'success': True, 'result': {'sentiment': sentiment, 'score': compound_score} }
        except Exception as e:
            logger.error(f'Error while creating embeddings: {str(e)}', exc_info=True)
            raise e
