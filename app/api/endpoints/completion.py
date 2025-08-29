from app.api.dependencies.auth import get_current_client
from app.config.logger import logger
from fastapi.responses import JSONResponse
from fastapi import APIRouter, HTTPException, Depends, status
from app.api.services import CompletionService
from app.api.schemas import CompletionSchema
from app.api.dependencies import apply_rate_limiting

router = APIRouter(tags=["completion"], dependencies=[Depends(apply_rate_limiting)])

@router.post('/generate')
async def generate_content(params: CompletionSchema):
    try:
        service = CompletionService()
        response = await service.dispatch(params)
        return JSONResponse(content=response, status_code=status.HTTP_200_OK)
    except Exception as e:
        logger.error(f'Error: {str(e)}', exc_info=True)
        status_code = e.status_code if isinstance(e, HTTPException) else status.HTTP_500_INTERNAL_SERVER_ERROR
        content = e.detail if isinstance(e, HTTPException) else 'Internal Server Error'
        return JSONResponse(content=content, status_code=status_code)
