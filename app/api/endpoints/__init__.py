from fastapi import APIRouter

from . import completion, embeddings, sentiment, summarize

router = APIRouter()
router.include_router(completion.router)
router.include_router(embeddings.router)
router.include_router(sentiment.router)
router.include_router(summarize.router)

__all__ = [
    "router"
]
