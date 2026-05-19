from fastapi import APIRouter, Request

from app.api.controllers._helpers import _success_response, resolve_completion_model
from app.api.services.completion_service import CompletionService
from app.api.validators import Completions

router = APIRouter(tags=["completions"])


@router.post("/v1/chat/completions")
async def create_completions(request: Request, params: Completions):
    public_model, provider_preference = resolve_completion_model(params.model)
    response = await CompletionService().dispatch(
        params,
        request=request,
        provider_preference=provider_preference,
    )
    return _success_response(payload=response, request=request, public_model=public_model)
