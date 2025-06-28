from fastapi import APIRouter
from .completion import router as completion_router
from .embeddings import router as embeddings_router
from .sentiment import router as sentiment_router
from .summarize import router as summarization_router

# Main router that combines all feature routers
router = APIRouter()
router.include_router(completion_router)
router.include_router(embeddings_router)
router.include_router(sentiment_router)
router.include_router(summarization_router)

__all__ = ['router']
