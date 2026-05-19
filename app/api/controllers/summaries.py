from fastapi import APIRouter, Request

from app.api.controllers._helpers import _success_response, resolve_completion_model
from app.api.services.summarization_service import SummarizationService
from app.api.validators import Summarization

router = APIRouter(tags=["summaries"])


@router.post("/beta/summaries")
async def create_summaries(request: Request, params: Summarization):
    public_model, provider_preference = resolve_completion_model(params.model)
    response = await SummarizationService().dispatch(
        params,
        request=request,
        provider_preference=provider_preference,
    )
    return _success_response(payload=response, request=request, public_model=public_model)
