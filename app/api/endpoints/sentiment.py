from app.config.logger import logger
from fastapi.responses import JSONResponse
from app.utils.helpers.model_loader import get_sentiment_analyzer
from fastapi import APIRouter, HTTPException, Header
from app.api.services import SentimentService
from app.api.schemas import SentimentSchema

router = APIRouter(tags=["sentiment"])

@router.post('/sentiment')
async def get_sentiment_analysis(params: SentimentSchema, auth: str = Header(...)):
    try:
        service = SentimentService(auth)
        response = await service.dispatch(params, get_sentiment_analyzer())
        return JSONResponse(content=response, status_code=200)
    except Exception as e:
        logger.error(f'Error: {str(e)}', exc_info=True)
        status_code = e.status_code if isinstance(e, HTTPException) else 500
        content = e.detail if isinstance(e, HTTPException) else 'Internal Server Error'
        return JSONResponse(content=content, status_code=status_code)
