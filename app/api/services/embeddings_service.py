import asyncio
from fastapi import HTTPException
from app.config.logger import logger
from .base_service import BaseApiService
from app.adapters import GoogleAdapter, OpenAIAdapter

class EmbeddingsService(BaseApiService):

    def __init__(self):
        super().__init__()

    async def dispatch(self, params):
        """Generate embeddings with fallback between Google (free) and OpenAI"""
        providers = [
            ('google', GoogleAdapter),
            ('openai', OpenAIAdapter)
        ]
        
        for provider_name, adapter_class in providers:
            try:
                adapter = adapter_class()
                embeddings = await adapter.generate_embeddings(params.texts)
                logger.info(f'Embeddings generated successfully with provider: {provider_name}')
                return {
                    'success': True, 
                    'result': embeddings,
                    'provider': provider_name,
                    'model': 'text-embedding-004' if provider_name == 'google' else 'text-embedding-3-small'
                }
            except Exception as e:
                logger.warning(f"Embedding generation failed for {provider_name}: {str(e)}")
                continue
        
        raise HTTPException(status_code=503, detail="Failed to generate embeddings: No response from any provider")
