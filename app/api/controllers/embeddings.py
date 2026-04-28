from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.config.logger import logger
from app.api.services.embeddings import EmbeddingsService
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
        return JSONResponse(content=response, status_code=status.HTTP_200_OK)
    except Exception as exc:
        logger.error(f"Error: {str(exc)}", exc_info=True)
        if isinstance(exc, HTTPException):
            detail = exc.detail if isinstance(exc.detail, dict) else {"detail": exc.detail}
            return JSONResponse(content=detail, status_code=exc.status_code)
        return JSONResponse(
            content={"detail": "Internal Server Error"},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
