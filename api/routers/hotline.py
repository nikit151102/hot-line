from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import Optional
from crud import (
    get_stores, create_store, delete_store,
    get_channels, create_channel, delete_channel, 
    get_request_types, create_request_type, delete_request_type,
    create_journal, get_journals, get_journal_by_id, update_journal, delete_journal,
    get_hotline_stats # <--- НОВОЕ
)
from schemas import (
    StoreResponse, StoreCreate,
    HotlineChannelResponse, HotlineChannelCreate, 
    RequestTypeResponse, RequestTypeCreate, 
    HotlineJournalResponse, HotlineJournalCreate, HotlineJournalUpdate,
    HotlineStatsResponse # <--- НОВОЕ
)
from database.database_app import get_session  

router = APIRouter(prefix="/hotline", tags=["Hotline"])

# --- Статистика ---
@router.get("/stats/", response_model=HotlineStatsResponse, tags=["Analytics"])
async def get_hotline_statistics(
    days: int = Query(30, ge=1, le=365, description="Период анализа в днях (по умолчанию 30)"),
    db: AsyncSession = Depends(get_session)
):
    """
    Возвращает комплексную статистику для дашборда:
    - KPI (всего, решено, среднее время)
    - Временные ряды (по дням, часам, дням недели)
    - Категориальные разрезы (магазины, каналы, типы, админы)
    - Кросс-аналитику (матрицы)
    """
    return await get_hotline_stats(db, days=days)

# --- Магазины ---
@router.post("/stores/", response_model=StoreResponse, status_code=status.HTTP_201_CREATED)
async def create_store_endpoint(store: StoreCreate, db: AsyncSession = Depends(get_session)):
    return await create_store(db, store)

@router.get("/stores/", response_model=list[StoreResponse])
async def read_stores(
    skip: int = 0, limit: int = 100, 
    include_deleted: bool = Query(False, description="Включать удаленные"),
    db: AsyncSession = Depends(get_session)
):
    return await get_stores(db, skip, limit, include_deleted)

@router.delete("/stores/{store_id}", response_model=StoreResponse)
async def soft_delete_store(store_id: UUID, db: AsyncSession = Depends(get_session)):
    return await delete_store(db, store_id)

# --- Каналы ---
@router.post("/channels/", response_model=HotlineChannelResponse, status_code=status.HTTP_201_CREATED)
async def create_channel_endpoint(channel: HotlineChannelCreate, db: AsyncSession = Depends(get_session)):
    return await create_channel(db, channel)

@router.get("/channels/", response_model=list[HotlineChannelResponse])
async def read_channels(
    skip: int = 0, limit: int = 100, 
    store_id: Optional[UUID] = Query(None, description="Фильтр по ID магазина"),
    include_deleted: bool = Query(False, description="Включать удаленные"),
    db: AsyncSession = Depends(get_session)
):
    return await get_channels(db, skip, limit, store_id, include_deleted)

@router.delete("/channels/{channel_id}", response_model=HotlineChannelResponse)
async def soft_delete_channel(channel_id: UUID, db: AsyncSession = Depends(get_session)):
    return await delete_channel(db, channel_id)

# --- Типы обращений ---
@router.post("/request-types/", response_model=RequestTypeResponse, status_code=status.HTTP_201_CREATED)
async def create_request_type_endpoint(req_type: RequestTypeCreate, db: AsyncSession = Depends(get_session)):
    return await create_request_type(db, req_type)

@router.get("/request-types/", response_model=list[RequestTypeResponse])
async def read_request_types(
    skip: int = 0, limit: int = 100, 
    parent_id: Optional[UUID] = Query(None),
    include_deleted: bool = Query(False, description="Включать удаленные"),
    db: AsyncSession = Depends(get_session)
):
    return await get_request_types(db, skip, limit, parent_id, include_deleted)

@router.delete("/request-types/{req_type_id}", response_model=RequestTypeResponse)
async def soft_delete_request_type(req_type_id: UUID, db: AsyncSession = Depends(get_session)):
    return await delete_request_type(db, req_type_id)

# --- Журнал обращений ---
@router.post("/journal/", response_model=HotlineJournalResponse, status_code=status.HTTP_201_CREATED)
async def create_journal_endpoint(journal: HotlineJournalCreate, db: AsyncSession = Depends(get_session)):
    return await create_journal(db, journal)

@router.get("/journal/", response_model=list[HotlineJournalResponse])
async def read_journals(
    skip: int = 0, limit: int = 100, 
    include_deleted: bool = Query(False, description="Включать удаленные"),
    db: AsyncSession = Depends(get_session)
):
    return await get_journals(db, skip, limit, include_deleted)

@router.get("/journal/{journal_id}", response_model=HotlineJournalResponse)
async def read_journal(journal_id: UUID, db: AsyncSession = Depends(get_session)):
    db_journal = await get_journal_by_id(db, journal_id)
    if db_journal is None:
        raise HTTPException(status_code=404, detail="Запись в журнале не найдена")
    return db_journal

@router.put("/journal/{journal_id}", response_model=HotlineJournalResponse)
async def update_journal_endpoint(journal_id: UUID, journal_update: HotlineJournalUpdate, db: AsyncSession = Depends(get_session)):
    updated_journal = await update_journal(db, journal_id, journal_update)
    if updated_journal is None:
        raise HTTPException(status_code=404, detail="Запись в журнале не найдена")
    return updated_journal

@router.delete("/journal/{journal_id}", response_model=HotlineJournalResponse)
async def soft_delete_journal(journal_id: UUID, db: AsyncSession = Depends(get_session)):
    deleted_journal = await delete_journal(db, journal_id)
    if deleted_journal is None:
        raise HTTPException(status_code=404, detail="Запись в журнале не найдена")
    return deleted_journal