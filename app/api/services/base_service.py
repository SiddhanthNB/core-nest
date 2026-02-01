from pathlib import Path
from httpx import HTTPStatusError
from fastapi import HTTPException, status
from types import SimpleNamespace
from app.config.logger import logger
from app.adapters import GoogleAdapter
from app.adapters import GroqAdapter
from app.adapters import OpenAIAdapter
from app.adapters import OpenRouterAdapter
from app.adapters import MistralAdapter
from app.adapters import CerebrasAdapter

class BaseApiService:

    def __init__(self):
        pass

    async def _generate_response(self, params):
        _providers_hash = {
            'groq': GroqAdapter,
            'google': GoogleAdapter,
            'openrouter': OpenRouterAdapter,
            'openai': OpenAIAdapter,
            'mistral': MistralAdapter,
            'cerebras': CerebrasAdapter,
        }

        if not params.provider:
            return await self._apply_fallback_mechanism('generate_response', params, _providers_hash)

        adapter_class = _providers_hash.get(params.provider)
        try:
            adapter = adapter_class()
            response = await adapter.generate_response(params)
            logger.info(f'Response generation successful with provider: {params.provider}')
            return { 'content': response, 'provider': params.provider, 'model': adapter.generation_model }
        except HTTPStatusError as e:
            logger.error(f"HTTP error during response generation for {params.provider}: {str(e)}")
            raise HTTPException(status_code=e.response.status_code, detail=f"HTTP error from {params.provider}: {e.response.text}")
        except Exception as e:
            logger.error(f"Response generation failed for {params.provider}: {str(e)}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Response generation failed for {params.provider}")

    async def _generate_embeddings(self, params):
        _providers_hash = {
            'google': GoogleAdapter,
            'openai': OpenAIAdapter,
            'mistral': MistralAdapter,
        }

        adapter_class = _providers_hash.get(params.provider)
        try:
            adapter = adapter_class()
            embeddings = await adapter.generate_embeddings(params.texts)
            logger.info(f'Embeddings generated successfully with provider: {params.provider}')
            return { 'content': embeddings, 'provider': params.provider, 'model': adapter.embedding_model }
        except HTTPStatusError as e:
            logger.error(f"HTTP error during embedding generation for {params.provider}: {str(e)}")
            raise HTTPException(status_code=e.response.status_code, detail=f"HTTP error from {params.provider}: {e.response.text}")
        except Exception as e:
            logger.error(f"Embedding generation failed for {params.provider}: {str(e)}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Embedding generation failed for {params.provider}")

    async def _apply_fallback_mechanism(self, operation, params, _providers_hash):
        if operation not in ['generate_response', 'generate_embeddings']:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported operation: {operation}")

        for provider_name, adapter_class in _providers_hash.items():
            try:
                adapter = adapter_class()

                if operation == 'generate_response':
                    result = await adapter.generate_response(params)
                    model_used = adapter.generation_model
                elif operation == 'generate_embeddings':
                    result = await adapter.generate_embeddings(params)
                    model_used = adapter.embedding_model

                logger.info(f'Operation successful with provider: {provider_name}')
                return { 'content': result, 'provider': provider_name, 'model': model_used }
            except Exception as e:
                logger.warning(f"Operation failed for {provider_name} with ERROR: {e}")
                continue

        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Operation failed: No response from any provider")

    def _get_prompts(self, prompt_type: str, **kwargs):
        base_path = Path(__file__).parent.parent.parent / "utils" / "prompts"
        system_prompts_path = base_path / "system_prompts"
        user_prompts_path = base_path / "user_prompts"

        _load_and_format = lambda file_path, **kwargs: file_path.read_text().strip().format(**kwargs)

        system_prompt = _load_and_format(system_prompts_path / f"{prompt_type}.txt", **kwargs)
        user_prompt = _load_and_format(user_prompts_path / f"{prompt_type}.txt", **kwargs)

        return { 'system_prompt': system_prompt, 'user_prompt': user_prompt }

    def _get_all_params(self, params, prompts, structured_output=False):
        return SimpleNamespace(**params.dict(), **prompts, structured_output=structured_output)
