from fastapi import APIRouter, Request

from app.api.controllers._helpers import _error_response, _success_response
from app.api.services.embeddings_service import EmbeddingsService
from app.api.validators import Embeddings

router = APIRouter(tags=["embeddings"])


@router.post("/embeddings")
async def create_embeddings(request: Request, params: Embeddings):
    try:
        response = await EmbeddingsService().dispatch(
            params,
            request=request,
            provider_preference=request.headers.get("X-LLM-Provider"),
        )
        return _success_response(payload=response, request=request)
    except Exception as exc:
        return _error_response(exc)
