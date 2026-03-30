from app.config.logger import logger
from fastapi.responses import JSONResponse
from fastapi import APIRouter, HTTPException, Depends, status
from app.api.services.completions import CompletionService
from app.api.deps import apply_rate_limiting
from app.api.validators import Completions

router = APIRouter(tags=["completions"], dependencies=[Depends(apply_rate_limiting)])

@router.post('/completions')
async def create_completions(params: Completions):
    try:
        service = CompletionService()
        response = await service.dispatch(params)
        return JSONResponse(content=response, status_code=status.HTTP_200_OK)
    except Exception as e:
        logger.error(f'Error: {str(e)}', exc_info=True)
        status_code = e.status_code if isinstance(e, HTTPException) else status.HTTP_500_INTERNAL_SERVER_ERROR
        content = e.detail if isinstance(e, HTTPException) else 'Internal Server Error'
        return JSONResponse(content=content, status_code=status_code)
