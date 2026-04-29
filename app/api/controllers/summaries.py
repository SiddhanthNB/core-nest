from fastapi import APIRouter, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.config.logger import logger
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
        return JSONResponse(content=jsonable_encoder(response), status_code=status.HTTP_200_OK)
    except Exception as exc:
        logger.error(f"Error: {str(exc)}", exc_info=True)
        if isinstance(exc, HTTPException):
            detail = exc.detail if isinstance(exc.detail, dict) else {"detail": exc.detail}
            return JSONResponse(content=detail, status_code=exc.status_code)
        return JSONResponse(
            content={"detail": "Internal Server Error"},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
