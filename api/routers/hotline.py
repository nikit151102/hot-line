from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import Optional
from crud import (
    get_stores, create_store, 
    get_channels, create_channel, 
    create_request_type, get_request_types, 
    create_journal, get_journals, get_journal_by_id, update_journal, delete_journal
)
from schemas import (
    StoreResponse, StoreCreate,
    HotlineChannelResponse, HotlineChannelCreate, 
    RequestTypeResponse, RequestTypeCreate, 
    HotlineJournalResponse, HotlineJournalCreate, HotlineJournalUpdate
)
from database.database_app import get_session  

router = APIRouter(prefix="/hotline", tags=["Hotline"])

# --- Магазины ---
@router.post("/stores/", response_model=StoreResponse, status_code=status.HTTP_201_CREATED)
async def create_store_endpoint(store: StoreCreate, db: AsyncSession = Depends(get_session)):
    return await create_store(db, store)

@router.get("/stores/", response_model=list[StoreResponse])
async def read_stores(skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_session)):
    return await get_stores(db, skip, limit)

# --- Каналы ---
@router.post("/channels/", response_model=HotlineChannelResponse, status_code=status.HTTP_201_CREATED)
async def create_channel_endpoint(channel: HotlineChannelCreate, db: AsyncSession = Depends(get_session)):
    return await create_channel(db, channel)

@router.get("/channels/", response_model=list[HotlineChannelResponse])
async def read_channels(
    skip: int = 0, 
    limit: int = 100, 
    store_id: Optional[UUID] = Query(None, description="Фильтр по ID магазина"),
    db: AsyncSession = Depends(get_session)
):
    return await get_channels(db, skip, limit, store_id)

# --- Типы обращений и Журнал ---
# (Оставляем ваши существующие эндпоинты для request-types и journal без изменений)
@router.post("/request-types/", response_model=RequestTypeResponse, status_code=status.HTTP_201_CREATED)
async def create_request_type_endpoint(req_type: RequestTypeCreate, db: AsyncSession = Depends(get_session)):
    return await create_request_type(db, req_type)

@router.get("/request-types/", response_model=list[RequestTypeResponse])
async def read_request_types(
    skip: int = 0, limit: int = 100, 
    parent_id: Optional[UUID] = Query(None),
    db: AsyncSession = Depends(get_session)
):
    return await get_request_types(db, skip, limit, parent_id)

@router.post("/journal/", response_model=HotlineJournalResponse, status_code=status.HTTP_201_CREATED)
async def create_journal_endpoint(journal: HotlineJournalCreate, db: AsyncSession = Depends(get_session)):
    return await create_journal(db, journal)

@router.get("/journal/", response_model=list[HotlineJournalResponse])
async def read_journals(skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_session)):
    return await get_journals(db, skip, limit)
    
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
async def delete_journal_endpoint(journal_id: UUID, db: AsyncSession = Depends(get_session)):
    deleted_journal = await delete_journal(db, journal_id)
    if deleted_journal is None:
        raise HTTPException(status_code=404, detail="Запись в журнале не найдена")
    return deleted_journal