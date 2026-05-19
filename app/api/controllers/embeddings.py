from fastapi import APIRouter, Request

from app.api.controllers._helpers import _success_response, resolve_embedding_model
from app.api.services.embeddings_service import EmbeddingsService
from app.api.validators import Embeddings

router = APIRouter(tags=["embeddings"])


@router.post("/v1/embeddings")
async def create_embeddings(request: Request, params: Embeddings):
    public_model, provider_preference = resolve_embedding_model(
        params.model,
        legacy_provider_preference=request.headers.get("X-LLM-Provider"),
    )
    response = await EmbeddingsService().dispatch(
        params,
        request=request,
        provider_preference=provider_preference,
    )
    return _success_response(payload=response, request=request, public_model=public_model)
