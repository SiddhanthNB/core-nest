from fastapi import APIRouter

from .completions import router as completions_router
from .embeddings import router as embeddings_router
from .sentiments import router as sentiments_router
from .summaries import router as summaries_router

router = APIRouter()
router.include_router(completions_router)
router.include_router(embeddings_router)
router.include_router(sentiments_router)
router.include_router(summaries_router)

__all__ = [
    "router"
]
