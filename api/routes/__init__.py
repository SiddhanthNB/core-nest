from config.logger import logger
from fastapi.responses import JSONResponse
from utils.helpers.model_loader import get_embedding_model, get_sentiment_analyzer
from fastapi import APIRouter, HTTPException, Header, Body
from api.controllers.completion_controller import CompletionController
from api.controllers.embeddings_controller import EmbeddingsController
from api.controllers.sentiment_controller import SentimentController
from api.validators.completion_validator import CompletionValidator
from api.validators.embedding_validator import EmbeddingValidator
from api.validators.sentiment_validator import SentimentValidator

router = APIRouter()

@router.get('/generate')
async def get_generated_content(params: CompletionValidator = Body(...), auth: str = Header(...)):
    try:
        controller = CompletionController(auth)
        response = await controller.dispatch(params)
        return JSONResponse(content=response, status_code=200)
    except Exception as e:
        logger.error(f'Error: {str(e)}', exc_info=True)
        status_code = e.status_code if isinstance(e, HTTPException) else 500
        content = e.detail if isinstance(e, HTTPException) else 'Internal Server Error'
        return JSONResponse(content=content, status_code=status_code)

@router.get('/embed')
async def get_vector_embeddings(params: EmbeddingValidator = Body(...), auth: str = Header(...)):
    try:
        controller = EmbeddingsController(auth)
        response = await controller.dispatch(params, get_embedding_model())
        return JSONResponse(content=response, status_code=200)
    except Exception as e:
        logger.error(f'Error: {str(e)}', exc_info=True)
        status_code = e.status_code if isinstance(e, HTTPException) else 500
        content = e.detail if isinstance(e, HTTPException) else 'Internal Server Error'
        return JSONResponse(content=content, status_code=status_code)

@router.get('/sentiment')
async def get_sentiment_analysis(params: SentimentValidator = Body(...), auth: str = Header(...)):
    try:
        controller = SentimentController(auth)
        response = await controller.dispatch(params, get_sentiment_analyzer())
        return JSONResponse(content=response, status_code=200)
    except Exception as e:
        logger.error(f'Error: {str(e)}', exc_info=True)
        status_code = e.status_code if isinstance(e, HTTPException) else 500
        content = e.detail if isinstance(e, HTTPException) else 'Internal Server Error'
        return JSONResponse(content=content, status_code=status_code)
