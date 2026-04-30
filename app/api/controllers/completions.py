from fastapi import APIRouter, Request

from app.api.controllers._helpers import _error_response, _success_response
from app.api.services.completion_service import CompletionService
from app.api.validators import Completions

router = APIRouter(tags=["completions"])


@router.post("/completions")
async def create_completions(request: Request, params: Completions):
    try:
        response = await CompletionService().dispatch(
            params,
            request=request,
            provider_preference=request.headers.get("X-LLM-Provider"),
        )
        return _success_response(payload=response, request=request)
    except Exception as exc:
        return _error_response(exc)
