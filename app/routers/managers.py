import sqlite3
from datetime import datetime

from fastapi import APIRouter, Depends

from app.deps import PageParams, get_conn, get_now, get_page_params
from app.schemas import ManagerCreate, ManagerOut, Page
from app.services import managers

router = APIRouter(prefix="/managers", tags=["managers"])


@router.post("", status_code=201, response_model=ManagerOut)
def create_manager(
    data: ManagerCreate,
    conn: sqlite3.Connection = Depends(get_conn),
    now: datetime = Depends(get_now),
) -> dict:
    return managers.create_manager(conn, data, now)


@router.get("", response_model=Page[ManagerOut])
def list_managers(
    page: PageParams = Depends(get_page_params),
    conn: sqlite3.Connection = Depends(get_conn),
) -> dict:
    return managers.list_managers(conn, page)
