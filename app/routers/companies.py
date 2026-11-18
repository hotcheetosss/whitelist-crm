import sqlite3
from datetime import datetime

from fastapi import APIRouter, Depends

from app.deps import PageParams, get_conn, get_now, get_page_params
from app.schemas import CompanyCreate, CompanyOut, CompanyStatus, Page
from app.services import companies

router = APIRouter(prefix="/companies", tags=["companies"])


@router.post("", status_code=201, response_model=CompanyOut)
def create_company(
    data: CompanyCreate,
    conn: sqlite3.Connection = Depends(get_conn),
    now: datetime = Depends(get_now),
) -> dict:
    return companies.create_company(conn, data, now)


@router.get("", response_model=Page[CompanyOut])
def list_companies(
    status: CompanyStatus | None = None,
    page: PageParams = Depends(get_page_params),
    conn: sqlite3.Connection = Depends(get_conn),
) -> dict:
    return companies.list_companies(conn, status, page)


@router.get("/{company_id}", response_model=CompanyOut)
def get_company(company_id: int, conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    return companies.get_company(conn, company_id)
