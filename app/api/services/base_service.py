from fastapi import HTTPException
from app.config.logger import logger
from app.adapters import GoogleAdapter
from app.adapters import GroqAdapter
from app.adapters import OpenAIAdapter
from app.adapters import OpenRouterAdapter

class BaseApiService:

    def __init__(self):
        pass

    async def _generate_response_with_fallback(self, params):
        _providers_hash = {
            'grok': GroqAdapter,
            'google': GoogleAdapter,
            'openrouter': OpenRouterAdapter,
            'openai': OpenAIAdapter
        }

        for provider_name, adapter_class in _providers_hash.items():
            try:
                adapter = adapter_class()
                response = await adapter.generate_response(params)
                logger.info(f'Response generation successful with provider: {provider_name}')
                return { 'content': response, 'provider': provider_name, 'model': adapter.generation_model }
            except Exception as e:
                logger.warning(f"Response generation failed for {provider_name} with ERROR: {e}")
                continue

        raise HTTPException(status_code=503, detail="Failed to generate response: No response from any provider")

    async def _generate_embeddings_with_fallback(self, params):
        _providers_hash = {
            'google': GoogleAdapter,
            'openai': OpenAIAdapter
        }

        for provider_name, adapter_class in _providers_hash.items():
            try:
                adapter = adapter_class()
                embeddings = await adapter.generate_embeddings(params.texts)
                logger.info(f'Embeddings generated successfully with provider: {provider_name}')
                return { 'content': embeddings, 'provider': provider_name, 'model': adapter.embedding_model }
            except Exception as e:
                logger.warning(f"Embedding generation failed for {provider_name}: {str(e)}")
                continue

        raise HTTPException(status_code=503, detail="Failed to generate embeddings: No response from any provider")
