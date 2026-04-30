from fastapi import APIRouter, Request

from app.api.controllers._helpers import _error_response, _success_response
from app.api.services.summarization_service import SummarizationService
from app.api.validators import Summarization

router = APIRouter(tags=["summaries"])


@router.post("/summaries")
async def create_summaries(request: Request, params: Summarization):
    try:
        response = await SummarizationService().dispatch(
            params,
            request=request,
            provider_preference=request.headers.get("X-LLM-Provider"),
        )
        return _success_response(payload=response, request=request)
    except Exception as exc:
        return _error_response(exc)
