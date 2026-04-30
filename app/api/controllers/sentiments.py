from fastapi import APIRouter, Request

from app.api.controllers._helpers import _error_response, _success_response
from app.api.services.sentiment_service import SentimentService
from app.api.validators import Sentiments

router = APIRouter(tags=["sentiments"])


@router.post("/sentiments")
async def create_sentiments(request: Request, params: Sentiments):
    try:
        response = await SentimentService().dispatch(
            params,
            request=request,
            provider_preference=request.headers.get("X-LLM-Provider"),
        )
        return _success_response(payload=response, request=request)
    except Exception as exc:
        return _error_response(exc)
