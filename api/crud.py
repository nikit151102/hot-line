from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import joinedload
from uuid import UUID
from typing import Optional
from models import Store, HotlineChannel, RequestType, HotlineJournal
from schemas import StoreCreate, HotlineChannelCreate, RequestTypeCreate, HotlineJournalCreate, HotlineJournalUpdate

# ================= МАГАЗИНЫ =================
async def get_stores(db: AsyncSession, skip: int = 0, limit: int = 100):
    result = await db.execute(select(Store).offset(skip).limit(limit))
    return result.scalars().all()

async def create_store(db: AsyncSession, store: StoreCreate):
    db_store = Store(**store.model_dump())
    db.add(db_store)
    await db.commit()
    await db.refresh(db_store)
    return db_store

# ================= КАНАЛЫ =================
async def get_channels(db: AsyncSession, skip: int = 0, limit: int = 100, store_id: Optional[UUID] = None):
    query = select(HotlineChannel).options(joinedload(HotlineChannel.store)).offset(skip).limit(limit)
    if store_id:
        query = query.where(HotlineChannel.store_id == store_id)
    result = await db.execute(query)
    return result.scalars().unique().all()

async def create_channel(db: AsyncSession, channel: HotlineChannelCreate):
    db_channel = HotlineChannel(**channel.model_dump())
    db.add(db_channel)
    await db.commit()
    await db.refresh(db_channel)
    return db_channel

# ================= ТИПЫ ОБРАЩЕНИЙ =================
# (Оставляем как было, с get_request_types и create_request_type)
async def get_request_types(db: AsyncSession, skip: int = 0, limit: int = 100, parent_id: Optional[UUID] = None):
    query = select(RequestType).offset(skip).limit(limit)
    query = query.where(RequestType.parent_id == parent_id)
    result = await db.execute(query)
    return result.scalars().all()

async def create_request_type(db: AsyncSession, req_type: RequestTypeCreate):
    db_req_type = RequestType(**req_type.model_dump())
    db.add(db_req_type)
    await db.commit()
    await db.refresh(db_req_type)
    return db_req_type

# ================= ЖУРНАЛ =================
# (Оставляем как было, но добавляем joinedload для channel.store, если нужно в аналитике)
async def get_journals(db: AsyncSession, skip: int = 0, limit: int = 100):
    result = await db.execute(
        select(HotlineJournal)
        .options(
            joinedload(HotlineJournal.channel).joinedload(HotlineChannel.store), # Загружаем и канал, и магазин
            joinedload(HotlineJournal.request_type)
        )
        .offset(skip).limit(limit)
    )
    return result.scalars().unique().all()


async def get_journal_by_id(db: AsyncSession, journal_id: UUID):
    result = await db.execute(
        select(HotlineJournal)
        .options(joinedload(HotlineJournal.channel), joinedload(HotlineJournal.request_type))
        .where(HotlineJournal.id == journal_id)
    )
    return result.scalars().unique().first()

async def create_journal(db: AsyncSession, journal: HotlineJournalCreate):
    db_journal = HotlineJournal(**journal.model_dump()) 
    db.add(db_journal)
    await db.commit()
    await db.refresh(db_journal, attribute_names=['channel', 'request_type'])
    return db_journal

async def update_journal(db: AsyncSession, journal_id: UUID, journal_update: HotlineJournalUpdate):
    db_journal = await get_journal_by_id(db, journal_id)
    if not db_journal: return None
    
    update_data = journal_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_journal, key, value)
        
    await db.commit()
    await db.refresh(db_journal, attribute_names=['channel', 'request_type'])
    return db_journal

async def delete_journal(db: AsyncSession, journal_id: UUID):
    db_journal = await get_journal_by_id(db, journal_id)
    if not db_journal: return None
    await db.delete(db_journal)
    await db.commit()
    return db_journal