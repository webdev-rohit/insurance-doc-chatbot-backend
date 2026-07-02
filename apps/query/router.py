from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from apps.core.database import get_db
from apps.core.global_utils import get_current_user
from .services import QueryService
from .schemas import QueryRequest, QueryResponse


router = APIRouter(prefix="/query", tags=["Query Process"])


@router.post("/text", response_model=QueryResponse, status_code=200)
async def query_bot(
    request: QueryRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user),
):  
    try:
        user_query = request.query
        answer, token_usage = QueryService(db).process_query(user_query, user_id)

        return QueryResponse(
            answer=answer,
            token_usage=token_usage
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))