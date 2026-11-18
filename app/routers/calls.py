import sqlite3
from datetime import datetime

from fastapi import APIRouter, Depends

from app.deps import PageParams, get_conn, get_now, get_page_params
from app.schemas import CallCreate, CallOut, Page
from app.services import calls

router = APIRouter(prefix="/calls", tags=["calls"])


@router.post("", status_code=201, response_model=CallOut)
def create_call(
    data: CallCreate,
    conn: sqlite3.Connection = Depends(get_conn),
    now: datetime = Depends(get_now),
) -> dict:
    return calls.create_call(conn, data, now)


@router.get("", response_model=Page[CallOut])
def list_calls(
    company_id: int | None = None,
    page: PageParams = Depends(get_page_params),
    conn: sqlite3.Connection = Depends(get_conn),
) -> dict:
    return calls.list_calls(conn, company_id, page)
