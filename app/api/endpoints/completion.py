from app.config.logger import logger
from fastapi.responses import JSONResponse
from fastapi import APIRouter, HTTPException, Depends
from app.api.services import CompletionService
from app.api.schemas import CompletionSchema
from app.api.dependencies import validate_auth_token

router = APIRouter(tags=["completion"])

@router.post('/generate')
async def generate_content(params: CompletionSchema, auth: dict = Depends(validate_auth_token)):
    try:
        service = CompletionService()
        response = await service.dispatch(params)
        return JSONResponse(content=response, status_code=200)
    except Exception as e:
        logger.error(f'Error: {str(e)}', exc_info=True)
        status_code = e.status_code if isinstance(e, HTTPException) else 500
        content = e.detail if isinstance(e, HTTPException) else 'Internal Server Error'
        return JSONResponse(content=content, status_code=status_code)
