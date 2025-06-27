from fastapi import HTTPException
from app.config.logger import logger
from .base_service import BaseApiService
from app.adapters import GoogleAdapter
from app.adapters import GroqAdapter
from app.adapters import OpenAIAdapter
from app.adapters import OpenRouterAdapter

class CompletionService(BaseApiService):

    def __init__(self):
        super().__init__()

    async def dispatch(self, params):
        _providers_hash = {
            'grok': GroqAdapter,
            'google': GoogleAdapter,
            'openrouter': OpenRouterAdapter,
            'openai': OpenAIAdapter
        }

        for provider_name, provider_service in _providers_hash.items():
            response = None
            try:
                service = provider_service()
                response = await service.generate_response(params)
                if response:
                    logger.debug(f'Response generation successful with provider: {provider_name}')
                    payload = {
                        'model': service.model_name,
                        'provider': provider_name,
                        'content': response
                    }
                    return { 'success': True, 'result': payload }
                else:
                    raise HTTPException(status_code=500, detail="Did not receive expected json response from the api call")
            except Exception as e:
                logger.warning(f"Response generation failed for {provider_name} with ERROR: {e}")
                continue

        raise HTTPException(status_code=503, detail="Failed to generate response: No response from any provider!")
