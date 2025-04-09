from fastapi import HTTPException
from config.logger import logger
from api.controllers.api_controller import ApiController
from utils.inference_providers.services.google_service import GoogleService
from utils.inference_providers.services.groq_service import GroqService
from utils.inference_providers.services.openai_service import OpenAIService
from utils.inference_providers.services.openrouter_service import OpenRouterService

class CompletionController(ApiController):

    def __init__(self, auth):
        super().__init__()
        self.auth_token_validator(auth)
    
    async def dispatch(self, params):
        _providers_hash = {
            'grok': GroqService,
            'google': GoogleService,
            'openrouter': OpenRouterService,
            'openai': OpenAIService
        }

        for provider_name, provider_service in _providers_hash.items():
            response = None
            try:
                service = provider_service()
                response = await service.get_response(params)
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
