from app.config.logger import logger
from fastapi.responses import JSONResponse
from fastapi import APIRouter, HTTPException, Header
from app.api.services import CompletionService
from app.api.schemas import CompletionSchema

router = APIRouter(tags=["completion"])

@router.post('/generate')
async def generate_content(params: CompletionSchema, auth: str = Header(...)):
    try:
        service = CompletionService(auth)
        response = await service.dispatch(params)
        return JSONResponse(content=response, status_code=200)
    except Exception as e:
        logger.error(f'Error: {str(e)}', exc_info=True)
        status_code = e.status_code if isinstance(e, HTTPException) else 500
        content = e.detail if isinstance(e, HTTPException) else 'Internal Server Error'
        return JSONResponse(content=content, status_code=status_code)
