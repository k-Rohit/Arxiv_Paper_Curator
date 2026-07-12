"""User feedback endpoint — attaches 👍/👎 scores to LangSmith traces.

Feedback lands on the exact run that produced the answer, so downvoted
runs can be filtered in LangSmith and turned into eval datasets.
"""

import logging
from typing import Literal

from fastapi import APIRouter, HTTPException
from langsmith import Client
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(tags=["feedback"])

# Module-level singleton — reuses one HTTP session instead of one per request
_langsmith_client = Client()


class FeedbackRequest(BaseModel):
    run_id: str = Field(..., description="LangSmith run ID from the AskResponse")
    score: Literal[1, 0] = Field(..., description="1 = thumbs up, 0 = thumbs down")
    comment: str = ""


@router.post("/feedback")
async def submit_feedback(req: FeedbackRequest):
    try:
        _langsmith_client.create_feedback(
            run_id=req.run_id,
            key="user-rating",
            score=req.score,
            comment=req.comment,
        )
    except Exception as e:
        logger.error(f"Failed to record feedback for run {req.run_id}: {e}")
        raise HTTPException(status_code=502, detail=f"Feedback recording failed: {e}")

    logger.info(f"Feedback recorded: run={req.run_id} score={req.score}")
    return {"status": "recorded"}
