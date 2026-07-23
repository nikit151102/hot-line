from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import joinedload
from uuid import UUID
from typing import Optional, List
from models import Store, HotlineChannel, RequestType, HotlineJournal
from schemas import (
    StoreCreate, HotlineChannelCreate, RequestTypeCreate, 
    HotlineJournalCreate, HotlineJournalUpdate
)

# ================= МАГАЗИНЫ =================
async def get_stores(db: AsyncSession, skip: int = 0, limit: int = 100, include_deleted: bool = False):
    query = select(Store)
    if not include_deleted:
        query = query.where(Store.is_deleted == False)
    result = await db.execute(query.offset(skip).limit(limit))
    return result.scalars().all()

async def create_store(db: AsyncSession, store: StoreCreate):
    db_store = Store(**store.model_dump())
    db.add(db_store)
    await db.commit()
    await db.refresh(db_store)
    return db_store

async def delete_store(db: AsyncSession, store_id: UUID):
    result = await db.execute(select(Store).where(Store.id == store_id))
    store = result.scalar_one_or_none()
    if store:
        store.is_deleted = True
        await db.commit()
        await db.refresh(store) 
    return store

# ================= КАНАЛЫ =================
async def get_channels(db: AsyncSession, skip: int = 0, limit: int = 100, store_id: Optional[UUID] = None, include_deleted: bool = False):
    query = select(HotlineChannel).options(joinedload(HotlineChannel.store))
    if not include_deleted:
        query = query.where(HotlineChannel.is_deleted == False)
    if store_id:
        query = query.where(HotlineChannel.store_id == store_id)
    
    result = await db.execute(query.offset(skip).limit(limit))
    return result.scalars().unique().all()

async def create_channel(db: AsyncSession, channel: HotlineChannelCreate):
    db_channel = HotlineChannel(**channel.model_dump())
    db.add(db_channel)
    await db.commit()
    
    result = await db.execute(
        select(HotlineChannel)
        .options(joinedload(HotlineChannel.store))
        .where(HotlineChannel.id == db_channel.id)
    )
    return result.scalars().unique().first()

async def delete_channel(db: AsyncSession, channel_id: UUID):
    result = await db.execute(select(HotlineChannel).where(HotlineChannel.id == channel_id))
    channel = result.scalar_one_or_none()
    if channel:
        channel.is_deleted = True
        await db.commit()
        await db.refresh(channel)
    return channel

# ================= ТИПЫ ОБРАЩЕНИЙ =================
async def get_request_types(db: AsyncSession, skip: int = 0, limit: int = 100, parent_id: Optional[UUID] = None, include_deleted: bool = False):
    query = select(RequestType)
    if not include_deleted:
        query = query.where(RequestType.is_deleted == False)
    query = query.where(RequestType.parent_id == parent_id)
    
    result = await db.execute(query.offset(skip).limit(limit))
    return result.scalars().all()

async def create_request_type(db: AsyncSession, req_type: RequestTypeCreate):
    db_req_type = RequestType(**req_type.model_dump())
    db.add(db_req_type)
    await db.commit()
    await db.refresh(db_req_type)
    return db_req_type

async def delete_request_type(db: AsyncSession, req_type_id: UUID):
    result = await db.execute(select(RequestType).where(RequestType.id == req_type_id))
    req_type = result.scalar_one_or_none()
    if req_type:
        req_type.is_deleted = True
        await db.commit()
        await db.refresh(req_type)
    return req_type

# ================= ЖУРНАЛ =================
async def get_journals(db: AsyncSession, skip: int = 0, limit: int = 100, include_deleted: bool = False):
    query = select(HotlineJournal).options(
        joinedload(HotlineJournal.channel).joinedload(HotlineChannel.store),
        joinedload(HotlineJournal.request_type)
    )
    if not include_deleted:
        query = query.where(HotlineJournal.is_deleted == False)
        
    result = await db.execute(query.offset(skip).limit(limit))
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
    db_journal.is_deleted = True 
    await db.commit()
    await db.refresh(db_journal)
    return db_journal

# ==========================================
# --- СТАТИСТИКА И МЕТРИКИ ---
# ==========================================
from datetime import datetime, timedelta
async def get_hotline_stats(db: AsyncSession, days: int = 30) -> dict:
    """Собирает комплексную аналитику для дашборда"""
    
    start_date = datetime.utcnow() - timedelta(days=days)
    
    # Базовый фильтр для всех запросов: не удаленные и в периоде
    base_filter = (HotlineJournal.is_deleted == False) & (HotlineJournal.received_at >= start_date)

    # ==========================================
    # 1. ОБЩИЕ KPI
    # ==========================================
    total_res = await db.execute(select(func.count()).select_from(HotlineJournal).where(base_filter))
    total_requests = total_res.scalar() or 0

    resolved_res = await db.execute(
        select(func.count()).select_from(HotlineJournal).where(base_filter & HotlineJournal.decision_date.isnot(None))
    )
    resolved_requests = resolved_res.scalar() or 0
    unresolved_requests = total_requests - resolved_requests
    resolution_rate = round((resolved_requests / total_requests * 100), 1) if total_requests > 0 else 0.0

    avg_time_res = await db.execute(
        select(func.avg(func.extract('epoch', HotlineJournal.decision_date - HotlineJournal.received_at) / 3600))
        .select_from(HotlineJournal)
        .where(base_filter & HotlineJournal.decision_date.isnot(None))
    )
    avg_resolution_hours = round(avg_time_res.scalar() or 0, 2)

    # ==========================================
    # 2. ВРЕМЕННЫЕ РАЗРЕЗЫ
    # ==========================================
    # По дням
    daily_res = await db.execute(
        select(func.date_trunc('day', HotlineJournal.received_at).label('date'), func.count(HotlineJournal.id))
        .where(base_filter).group_by('date').order_by('date')
    )
    timeline_daily = [{"date": row[0].strftime('%Y-%m-%d'), "count": row[1]} for row in daily_res.all()]

    # По часам (0-23) - чтобы понять пиковую нагрузку
    hourly_res = await db.execute(
        select(func.extract('hour', HotlineJournal.received_at).label('hour'), func.count(HotlineJournal.id))
        .where(base_filter).group_by('hour').order_by('hour')
    )
    timeline_hourly = [{"hour": int(row[0]), "count": row[1]} for row in hourly_res.all()]

    # По дням недели (1=Пн, 7=Вс)
    day_names = {1: "Пн", 2: "Вт", 3: "Ср", 4: "Чт", 5: "Пт", 6: "Сб", 7: "Вс"}
    weekly_res = await db.execute(
        select(func.extract('isodow', HotlineJournal.received_at).label('dow'), func.count(HotlineJournal.id))
        .where(base_filter).group_by('dow').order_by('dow')
    )
    timeline_weekly = [{"day_of_week": int(row[0]), "day_name": day_names.get(int(row[0]), "Неизв"), "count": row[1]} for row in weekly_res.all()]

    # ==========================================
    # 3. КАТЕГОРИАЛЬНЫЕ РАЗРЕЗЫ
    # ==========================================
    # По типам каналов
    channel_res = await db.execute(
        select(HotlineChannel.channel_type, func.count(HotlineJournal.id))
        .join(HotlineChannel, HotlineJournal.channel_id == HotlineChannel.id, isouter=True)
        .where(base_filter).group_by(HotlineChannel.channel_type).order_by(func.count(HotlineJournal.id).desc())
    )
    by_channel_type = [{"label": row[0] or "Не указан", "count": row[1]} for row in channel_res.all()]

    # По магазинам
    store_res = await db.execute(
        select(Store.name, func.count(HotlineJournal.id))
        .join(HotlineChannel, Store.id == HotlineChannel.store_id)
        .join(HotlineJournal, HotlineChannel.id == HotlineJournal.channel_id)
        .where(base_filter & (Store.is_deleted == False))
        .group_by(Store.name).order_by(func.count(HotlineJournal.id).desc())
    )
    by_store = [{"label": row[0], "count": row[1]} for row in store_res.all()]

    # По типам обращений
    type_res = await db.execute(
        select(RequestType.name, func.count(HotlineJournal.id))
        .join(RequestType, HotlineJournal.request_type_id == RequestType.id, isouter=True)
        .where(base_filter & (RequestType.is_deleted == False))
        .group_by(RequestType.name).order_by(func.count(HotlineJournal.id).desc())
    )
    by_request_type = [{"label": row[0] or "Без типа", "count": row[1]} for row in type_res.all()]

    # По администраторам (кто обрабатывает)
    admin_res = await db.execute(
        select(HotlineJournal.administrator, func.count(HotlineJournal.id))
        .where(base_filter).group_by(HotlineJournal.administrator).order_by(func.count(HotlineJournal.id).desc())
    )
    by_administrator = [{"label": row[0] or "Не назначен", "count": row[1]} for row in admin_res.all()]

    # ==========================================
    # 4. КРОСС-АНАЛИТИКА (МАТРИЦЫ)
    # ==========================================
    # Магазин vs Тип канала (Где какой канал популярнее?)
    store_channel_res = await db.execute(
        select(Store.name, HotlineChannel.channel_type, func.count(HotlineJournal.id))
        .join(HotlineChannel, Store.id == HotlineChannel.store_id)
        .join(HotlineJournal, HotlineChannel.id == HotlineJournal.channel_id)
        .where(base_filter & (Store.is_deleted == False))
        .group_by(Store.name, HotlineChannel.channel_type)
        .order_by(func.count(HotlineJournal.id).desc())
    )
    store_vs_channel = [
        {"category_1": row[0], "category_2": row[1] or "Не указан", "count": row[2]} 
        for row in store_channel_res.all()
    ]

    type_channel_res = await db.execute(
        select(RequestType.name, HotlineChannel.channel_type, func.count(HotlineJournal.id))
        .join(HotlineChannel, HotlineJournal.channel_id == HotlineChannel.id, isouter=True)
        .join(RequestType, HotlineJournal.request_type_id == RequestType.id, isouter=True)
        .where(base_filter)
        .group_by(RequestType.name, HotlineChannel.channel_type)
        .order_by(func.count(HotlineJournal.id).desc())
    )
    type_vs_channel = [
        {"category_1": row[0] or "Без типа", "category_2": row[1] or "Не указан", "count": row[2]} 
        for row in type_channel_res.all()
    ]

    # ==========================================
    # СБОРКА ОТВЕТА
    # ==========================================
    return {
        "total_requests": total_requests,
        "resolved_requests": resolved_requests,
        "unresolved_requests": unresolved_requests,
        "resolution_rate_percent": resolution_rate,
        "avg_resolution_hours": avg_resolution_hours,
        "timeline_daily": timeline_daily,
        "timeline_hourly": timeline_hourly,
        "timeline_weekly": timeline_weekly,
        "by_channel_type": by_channel_type,
        "by_store": by_store,
        "by_request_type": by_request_type,
        "by_administrator": by_administrator,
        "store_vs_channel": store_vs_channel,
        "type_vs_channel": type_vs_channel
    }