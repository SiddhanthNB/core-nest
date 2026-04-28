from fastapi import APIRouter, Depends

from app.api.deps import rate_limiter

from .completions import router as completions_router
from .embeddings import router as embeddings_router
from .sentiments import router as sentiments_router
from .summaries import router as summaries_router

api_router = APIRouter(dependencies=[Depends(rate_limiter)])
api_router.include_router(completions_router)
api_router.include_router(embeddings_router)
api_router.include_router(sentiments_router)
api_router.include_router(summaries_router)

__all__ = [
    "api_router",
]
