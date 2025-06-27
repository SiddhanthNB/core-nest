from app.config.logger import logger
from fastapi.responses import JSONResponse
from app.utils.helpers.model_loader import get_embedding_model
from fastapi import APIRouter, HTTPException, Header
from app.api.services import EmbeddingsService
from app.api.schemas import EmbeddingSchema

router = APIRouter(tags=["embeddings"])

@router.post('/embed')
async def get_vector_embeddings(params: EmbeddingSchema, auth: str = Header(...)):
    try:
        service = EmbeddingsService(auth)
        response = await service.dispatch(params, get_embedding_model())
        return JSONResponse(content=response, status_code=200)
    except Exception as e:
        logger.error(f'Error: {str(e)}', exc_info=True)
        status_code = e.status_code if isinstance(e, HTTPException) else 500
        content = e.detail if isinstance(e, HTTPException) else 'Internal Server Error'
        return JSONResponse(content=content, status_code=status_code)
