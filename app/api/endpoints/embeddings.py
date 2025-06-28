from app.config.logger import logger
from fastapi.responses import JSONResponse
from fastapi import APIRouter, HTTPException, Depends
from app.api.services import EmbeddingsService
from app.api.schemas import EmbeddingSchema
from app.api.dependencies import validate_auth_token, get_db_session

router = APIRouter(tags=["embeddings"])

@router.post('/embed')
async def get_vector_embeddings(params: EmbeddingSchema, auth: dict = Depends(validate_auth_token), db_session = Depends(get_db_session)):
    try:
        service = EmbeddingsService()
        response = await service.dispatch(params)
        return JSONResponse(content=response, status_code=200)
    except Exception as e:
        logger.error(f'Error: {str(e)}', exc_info=True)
        status_code = e.status_code if isinstance(e, HTTPException) else 500
        content = e.detail if isinstance(e, HTTPException) else 'Internal Server Error'
        return JSONResponse(content=content, status_code=status_code)
