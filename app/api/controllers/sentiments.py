from fastapi import APIRouter, Request

from app.api.controllers._helpers import _success_response, resolve_completion_model
from app.api.services.sentiment_service import SentimentService
from app.api.validators import Sentiments

router = APIRouter(tags=["sentiments"])


@router.post("/beta/sentiments")
async def create_sentiments(request: Request, params: Sentiments):
    public_model, provider_preference = resolve_completion_model(params.model)
    response = await SentimentService().dispatch(
        params,
        request=request,
        provider_preference=provider_preference,
    )
    return _success_response(payload=response, request=request, public_model=public_model)
