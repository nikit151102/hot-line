from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.orm import joinedload
from uuid import UUID
from typing import Optional, List
from datetime import datetime, timedelta

from models import (
    Store, HotlineChannel, RequestType, HotlineJournal, 
    RequesterType, request_type_allowed_requesters
)
from schemas import (
    StoreCreate, HotlineChannelCreate, RequestTypeCreate, RequestTypeUpdate,
    HotlineJournalCreate, HotlineJournalUpdate, RequesterTypeCreate
)
import uuid


NIL_UUID = UUID("00000000-0000-0000-0000-000000000000")


# ==============================================================================
# ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ: ВАЛИДАЦИЯ FOREIGN KEYS
# ==============================================================================
async def _validate_journal_keys(db: AsyncSession, journal_data: dict) -> dict:
    """
    Проверяет существование внешних ключей.
    Если ID нет в БД (например, бот прислал старый UUID из кэша), 
    заменяет его на NIL_UUID. Это предотвращает IntegrityError / 500.
    """
    # channel_id
    if journal_data.get("channel_id") and journal_data["channel_id"] != NIL_UUID:
        exists = await db.scalar(select(HotlineChannel.id).where(HotlineChannel.id == journal_data["channel_id"]))
        if not exists:
            journal_data["channel_id"] = NIL_UUID

    # requester_type_id
    if journal_data.get("requester_type_id") and journal_data["requester_type_id"] != NIL_UUID:
        exists = await db.scalar(select(RequesterType.id).where(RequesterType.id == journal_data["requester_type_id"]))
        if not exists:
            journal_data["requester_type_id"] = NIL_UUID

    # request_type_id
    if journal_data.get("request_type_id") and journal_data["request_type_id"] != NIL_UUID:
        exists = await db.scalar(select(RequestType.id).where(RequestType.id == journal_data["request_type_id"]))
        if not exists:
            journal_data["request_type_id"] = NIL_UUID
            
    return journal_data


# ==============================================================================
# 1. ТИПЫ ЗАЯВИТЕЛЕЙ
# ==============================================================================
async def get_requester_types(db: AsyncSession, include_deleted: bool = False):
    query = select(RequesterType)
    if not include_deleted:
        query = query.where(RequesterType.is_deleted == False)
    result = await db.execute(query.order_by(RequesterType.name))
    return result.scalars().all()

async def create_requester_type(db: AsyncSession, data: RequesterTypeCreate):
    obj = RequesterType(**data.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj

async def delete_requester_type(db: AsyncSession, obj_id: UUID):
    result = await db.execute(select(RequesterType).where(RequesterType.id == obj_id))
    obj = result.scalar_one_or_none()
    if obj:
        obj.is_deleted = True
        await db.commit()
        await db.refresh(obj)
    return obj


# ==============================================================================
# 2. МАГАЗИНЫ
# ==============================================================================
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


# ==============================================================================
# 3. КАНАЛЫ
# ==============================================================================
async def get_channels(db: AsyncSession, skip: int = 0, limit: int = 100, 
                       store_id: Optional[UUID] = None, include_deleted: bool = False,
                       channel_type: Optional[str] = None):
    query = select(HotlineChannel).options(joinedload(HotlineChannel.store))
    if not include_deleted:
        query = query.where(HotlineChannel.is_deleted == False)
    if store_id:
        query = query.where(HotlineChannel.store_id == store_id)
    if channel_type:
        query = query.where(HotlineChannel.channel_type == channel_type)
    
    result = await db.execute(query.offset(skip).limit(limit))
    return result.scalars().unique().all()

async def create_channel(db: AsyncSession, channel: HotlineChannelCreate):
    db_channel = HotlineChannel(**channel.model_dump())
    db.add(db_channel)
    await db.commit()
    
    result = await db.execute(
        select(HotlineChannel).options(joinedload(HotlineChannel.store)).where(HotlineChannel.id == db_channel.id)
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


# ==============================================================================
# 4. ТИПЫ ОБРАЩЕНИЙ
# ==============================================================================
async def get_request_types(db: AsyncSession, skip: int = 0, limit: int = 100, 
                            parent_id: Optional[UUID] = None, include_deleted: bool = False):
    query = select(RequestType).options(joinedload(RequestType.allowed_requesters))
    if not include_deleted:
        query = query.where(RequestType.is_deleted == False)
    
    if parent_id is not None:
        query = query.where(RequestType.parent_id == parent_id)
    else:
        query = query.where(RequestType.parent_id == None)
        
    result = await db.execute(query.offset(skip).limit(limit).order_by(RequestType.name))
    return result.scalars().unique().all()

async def get_allowed_request_types(db: AsyncSession, requester_code: str, parent_id: Optional[UUID] = None):
    query = (
        select(RequestType)
        .join(RequestType.allowed_requesters)
        .where(RequesterType.code == requester_code, RequestType.is_deleted == False)
        .options(joinedload(RequestType.allowed_requesters))
    )
    if parent_id is not None:
        query = query.where(RequestType.parent_id == parent_id)
    else:
        query = query.where(RequestType.parent_id == None)
        
    result = await db.execute(query.order_by(RequestType.name))
    return result.scalars().unique().all()

async def create_request_type(db: AsyncSession, data: RequestTypeCreate):
    allowed_ids = data.allowed_requester_ids
    data_dict = data.model_dump(exclude={'allowed_requester_ids'})
    
    obj = RequestType(**data_dict)
    if allowed_ids:
        res = await db.execute(select(RequesterType).where(RequesterType.id.in_(allowed_ids)))
        obj.allowed_requesters = res.scalars().all()
        
    db.add(obj)
    await db.commit()
    
    res = await db.execute(select(RequestType).options(joinedload(RequestType.allowed_requesters)).where(RequestType.id == obj.id))
    return res.scalars().unique().first()

async def update_request_type(db: AsyncSession, obj_id: UUID, data: RequestTypeUpdate):
    result = await db.execute(select(RequestType).where(RequestType.id == obj_id))
    obj = result.scalar_one_or_none()
    if not obj: return None
    
    update_data = data.model_dump(exclude_unset=True, exclude={'allowed_requester_ids'})
    for key, value in update_data.items():
        setattr(obj, key, value)
        
    if data.allowed_requester_ids is not None:
        res = await db.execute(select(RequesterType).where(RequesterType.id.in_(data.allowed_requester_ids)))
        obj.allowed_requesters = res.scalars().all()
        
    await db.commit()
    res = await db.execute(select(RequestType).options(joinedload(RequestType.allowed_requesters)).where(RequestType.id == obj.id))
    return res.scalars().unique().first()

async def delete_request_type(db: AsyncSession, obj_id: UUID):
    result = await db.execute(select(RequestType).where(RequestType.id == obj_id))
    obj = result.scalar_one_or_none()
    if obj:
        obj.is_deleted = True
        await db.commit()
        await db.refresh(obj)
    return obj


# ==============================================================================
# 5. ЖУРНАЛ ОБРАЩЕНИЙ (ИСПРАВЛЕНО: MissingGreenlet при db_journal.id)
# ==============================================================================
async def get_journals(
    db: AsyncSession, skip: int = 0, limit: int = 100, 
    include_deleted: bool = False,
    requester_type_id: Optional[UUID] = None,
    request_type_id: Optional[UUID] = None,
    channel_id: Optional[UUID] = None,
    store_id: Optional[UUID] = None,
    status: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    search: Optional[str] = None
):
    query = select(HotlineJournal).options(
        joinedload(HotlineJournal.channel).joinedload(HotlineChannel.store),
        joinedload(HotlineJournal.request_type).joinedload(RequestType.allowed_requesters),
        joinedload(HotlineJournal.requester_type)
    )
    if not include_deleted:
        query = query.where(HotlineJournal.is_deleted == False)
    if requester_type_id:
        query = query.where(HotlineJournal.requester_type_id == requester_type_id)
    if request_type_id:
        query = query.where(HotlineJournal.request_type_id == request_type_id)
    if channel_id:
        query = query.where(HotlineJournal.channel_id == channel_id)
    if store_id:
        query = query.join(HotlineChannel, HotlineJournal.channel_id == HotlineChannel.id)
        query = query.where(HotlineChannel.store_id == store_id)
    if date_from:
        query = query.where(HotlineJournal.received_at >= date_from)
    if date_to:
        query = query.where(HotlineJournal.received_at <= date_to)
    if status == 'resolved':
        query = query.where(HotlineJournal.decision_date.isnot(None))
    elif status == 'new':
        query = query.where(HotlineJournal.decision_date.is_(None))
    if search:
        query = query.where(HotlineJournal.message_content.ilike(f"%{search}%"))

    result = await db.execute(query.order_by(HotlineJournal.received_at.desc()).offset(skip).limit(limit))
    return result.scalars().unique().all()

async def get_journal_by_id(db: AsyncSession, journal_id: UUID):
    """Загружает обращение со ВСЕМИ вложенными связями (для сериализации FastAPI)."""
    result = await db.execute(
        select(HotlineJournal)
        .options(
            joinedload(HotlineJournal.channel).joinedload(HotlineChannel.store),
            joinedload(HotlineJournal.request_type).joinedload(RequestType.allowed_requesters),
            joinedload(HotlineJournal.requester_type)
        )
        .where(HotlineJournal.id == journal_id)
    )
    return result.scalars().unique().first()

async def create_journal(db: AsyncSession, journal: HotlineJournalCreate):
    # Защита от битых UUID (если бот прислал старый ID)
    data_dict = journal.model_dump()
    data_dict = await _validate_journal_keys(db, data_dict)
    
    db_journal = HotlineJournal(**data_dict) 
    db.add(db_journal)
    
    # ВАЖНО: flush() чтобы получить ID до commit (иначе после commit объект будет expired)
    await db.flush()
    journal_id = db_journal.id  # Сохраняем ID пока объект не expired
    
    await db.commit()
    
    # Возвращаем через get_journal_by_id, чтобы все связи были загружены
    return await get_journal_by_id(db, journal_id)

async def update_journal(db: AsyncSession, journal_id: UUID, journal_update: HotlineJournalUpdate):
    db_journal = await get_journal_by_id(db, journal_id)
    if not db_journal: return None
    
    update_data = journal_update.model_dump(exclude_unset=True)
    validated_data = await _validate_journal_keys(db, update_data)
    
    for key, value in validated_data.items():
        setattr(db_journal, key, value)
    
    # flush() перед commit для избежания проблем с expired объектами
    await db.flush()
    await db.commit()
    
    # Возвращаем актуальный объект с загруженными связями
    return await get_journal_by_id(db, journal_id)

async def delete_journal(db: AsyncSession, journal_id: UUID):
    db_journal = await get_journal_by_id(db, journal_id)
    if not db_journal: return None
    db_journal.is_deleted = True
    await db.flush()
    await db.commit()
    await db.refresh(db_journal)
    return db_journal


# ==============================================================================
# 6. СТАТИСТИКА
# ==============================================================================
async def get_hotline_stats(
    db: AsyncSession, days: int = 30,
    store_id: Optional[UUID] = None,
    channel_type: Optional[str] = None,
    requester_type_id: Optional[UUID] = None
) -> dict:
    start_date = datetime.utcnow() - timedelta(days=days)
    
    base_filter = (HotlineJournal.is_deleted == False) & (HotlineJournal.received_at >= start_date)
    if store_id:
        base_filter = base_filter & (HotlineJournal.channel.has(HotlineChannel.store_id == store_id))
    if channel_type:
        base_filter = base_filter & (HotlineJournal.channel.has(HotlineChannel.channel_type == channel_type))
    if requester_type_id:
        base_filter = base_filter & (HotlineJournal.requester_type_id == requester_type_id)

    total_res = await db.execute(select(func.count()).select_from(HotlineJournal).where(base_filter))
    total_requests = total_res.scalar() or 0

    resolved_res = await db.execute(select(func.count()).select_from(HotlineJournal).where(base_filter & HotlineJournal.decision_date.isnot(None)))
    resolved_requests = resolved_res.scalar() or 0
    unresolved_requests = total_requests - resolved_requests
    resolution_rate = round((resolved_requests / total_requests * 100), 1) if total_requests > 0 else 0.0

    avg_time_res = await db.execute(
        select(func.avg(func.extract('epoch', HotlineJournal.decision_date - HotlineJournal.received_at) / 3600))
        .select_from(HotlineJournal).where(base_filter & HotlineJournal.decision_date.isnot(None))
    )
    avg_resolution_hours = round(avg_time_res.scalar() or 0, 2)

    daily_res = await db.execute(select(func.date_trunc('day', HotlineJournal.received_at).label('date'), func.count(HotlineJournal.id)).where(base_filter).group_by('date').order_by('date'))
    timeline_daily = [{"date": row[0].strftime('%Y-%m-%d'), "count": row[1]} for row in daily_res.all()]

    hourly_res = await db.execute(select(func.extract('hour', HotlineJournal.received_at).label('hour'), func.count(HotlineJournal.id)).where(base_filter).group_by('hour').order_by('hour'))
    timeline_hourly = [{"hour": int(row[0]), "count": row[1]} for row in hourly_res.all()]

    day_names = {1: "Пн", 2: "Вт", 3: "Ср", 4: "Чт", 5: "Пт", 6: "Сб", 7: "Вс"}
    weekly_res = await db.execute(select(func.extract('isodow', HotlineJournal.received_at).label('dow'), func.count(HotlineJournal.id)).where(base_filter).group_by('dow').order_by('dow'))
    timeline_weekly = [{"day_of_week": int(row[0]), "day_name": day_names.get(int(row[0]), "Неизв"), "count": row[1]} for row in weekly_res.all()]

    channel_res = await db.execute(select(HotlineChannel.channel_type, func.count(HotlineJournal.id)).join(HotlineChannel, HotlineJournal.channel_id == HotlineChannel.id, isouter=True).where(base_filter).group_by(HotlineChannel.channel_type).order_by(func.count(HotlineJournal.id).desc()))
    by_channel_type = [{"label": row[0] or "Не указан", "count": row[1]} for row in channel_res.all()]

    store_res = await db.execute(select(Store.name, func.count(HotlineJournal.id)).join(HotlineChannel, Store.id == HotlineChannel.store_id).join(HotlineJournal, HotlineChannel.id == HotlineJournal.channel_id).where(base_filter & (Store.is_deleted == False)).group_by(Store.name).order_by(func.count(HotlineJournal.id).desc()))
    by_store = [{"label": row[0], "count": row[1]} for row in store_res.all()]

    type_res = await db.execute(select(RequestType.name, func.count(HotlineJournal.id)).join(RequestType, HotlineJournal.request_type_id == RequestType.id, isouter=True).where(base_filter & (RequestType.is_deleted == False)).group_by(RequestType.name).order_by(func.count(HotlineJournal.id).desc()))
    by_request_type = [{"label": row[0] or "Без типа", "count": row[1]} for row in type_res.all()]

    admin_res = await db.execute(select(HotlineJournal.administrator, func.count(HotlineJournal.id)).where(base_filter).group_by(HotlineJournal.administrator).order_by(func.count(HotlineJournal.id).desc()))
    by_administrator = [{"label": row[0] or "Не назначен", "count": row[1]} for row in admin_res.all()]

    store_channel_res = await db.execute(select(Store.name, HotlineChannel.channel_type, func.count(HotlineJournal.id)).join(HotlineChannel, Store.id == HotlineChannel.store_id).join(HotlineJournal, HotlineChannel.id == HotlineJournal.channel_id).where(base_filter & (Store.is_deleted == False)).group_by(Store.name, HotlineChannel.channel_type).order_by(func.count(HotlineJournal.id).desc()))
    store_vs_channel = [{"category_1": row[0], "category_2": row[1] or "Не указан", "count": row[2]} for row in store_channel_res.all()]

    type_channel_res = await db.execute(select(RequestType.name, HotlineChannel.channel_type, func.count(HotlineJournal.id)).join(HotlineChannel, HotlineJournal.channel_id == HotlineChannel.id, isouter=True).join(RequestType, HotlineJournal.request_type_id == RequestType.id, isouter=True).where(base_filter).group_by(RequestType.name, HotlineChannel.channel_type).order_by(func.count(HotlineJournal.id).desc()))
    type_vs_channel = [{"category_1": row[0] or "Без типа", "category_2": row[1] or "Не указан", "count": row[2]} for row in type_channel_res.all()]

    return {
        "total_requests": total_requests, "resolved_requests": resolved_requests, "unresolved_requests": unresolved_requests,
        "resolution_rate_percent": resolution_rate, "avg_resolution_hours": avg_resolution_hours,
        "timeline_daily": timeline_daily, "timeline_hourly": timeline_hourly, "timeline_weekly": timeline_weekly,
        "by_channel_type": by_channel_type, "by_store": by_store, "by_request_type": by_request_type, "by_administrator": by_administrator,
        "store_vs_channel": store_vs_channel, "type_vs_channel": type_vs_channel
    }


# ==============================================================================
# 7. ИНИЦИАЛИЗАЦИЯ СПРАВОЧНИКОВ (ID ЖЕСТКО ПРОПИСАНЫ ДЛЯ СТАБИЛЬНОСТИ)
# ==============================================================================
REQUESTER_TYPES_DATA = [
    {"id": UUID("4c146788-1150-45b2-851a-a665e320cd74"), "name": "Клиент", "code": "client"},
    {"id": UUID("d2eff114-eb43-45ed-b7d6-a9a7dd43ab9c"), "name": "Сотрудник", "code": "employee"},
    {"id": UUID("2e1faebd-598a-456e-b781-ff448ec55119"), "name": "Партнер / Поставщик", "code": "partner"},
    {"id": UUID("c9aa7514-3f61-45d5-a90f-ecf38f68bedd"), "name": "Анонимный посетитель", "code": "anonymous"},
]

STORES_DATA = [
    {"id": UUID("593b830d-b31e-45f3-93b0-65d8fd25c789"), "max_id": UUID("8d8d2093-e608-4289-9e7c-d05e70430c20"), "site_id": UUID("aaa4ad9b-f1a8-4e50-a45e-f51265e62090"), "city": "Барнаул", "street": "Красноармейский", "house": "131"},
    {"id": UUID("7b4466bc-3371-4b95-ad62-90708159aa31"), "max_id": UUID("e8b4fa6d-9739-4391-b559-f276165a1b70"), "site_id": UUID("1be4dcb5-b3b0-44a4-ace6-9879606d0b8f"), "city": "Барнаул", "street": "Мало-Тобольская", "house": "23"},
    {"id": UUID("1df0c6e1-dacf-450d-a06f-462edb638a6f"), "max_id": UUID("cfdbcddf-104a-4d7c-a3c8-327937f3fe48"), "site_id": UUID("1a5c6d9b-061e-4b2d-a8fe-46d26f24fc01"), "city": "Барнаул", "street": "Шевченко", "house": "157Б"},
    {"id": UUID("a8b05dd2-c2f0-4462-a138-11dfaea5b8f6"), "max_id": UUID("83bab255-1dbb-4100-bc5d-8fd43f28a68f"), "site_id": UUID("30ec4cae-52d0-44c2-a3fb-37b9ca9e60f6"), "city": "Барнаул", "street": "Космонавтов", "house": "59"},
    {"id": UUID("0eafadd2-ff07-4e83-953a-28b40f55fc1e"), "max_id": UUID("9c6e9555-e1f2-4e73-bcd8-1b191c53cf23"), "site_id": UUID("b499fe69-21db-4786-a739-e633397566dc"), "city": "Барнаул", "street": "Северо-Западная", "house": "6"},
    {"id": UUID("ea3a4369-6625-452b-ac92-cd2105d271b4"), "max_id": UUID("10f93dff-a456-44aa-9aa6-97f225d530f7"), "site_id": UUID("4ca50bf6-2d2e-4994-b139-519eb5713187"), "city": "Барнаул", "street": "Германа Титова", "house": "6"},
    {"id": UUID("fb8461bb-3161-4a3a-be13-c392e320419e"), "max_id": UUID("599d3586-f325-44c2-8cb6-974269e00ed2"), "site_id": UUID("3ad97581-5529-4eab-8242-2331c211eb2a"), "city": "Барнаул", "street": "Космонавтов", "house": "8/2"},
    {"id": UUID("1da4103c-0400-45a3-9b91-1c62c61cb40b"), "max_id": UUID("c965be8b-abbe-4e60-907e-79ffe4b459c1"), "site_id": UUID("91e5d306-55b1-45eb-b5cd-d033d0e17972"), "city": "Барнаул", "street": "Антона Петрова", "house": "190"},
    {"id": UUID("4c1ca409-b922-48db-b450-1ee4625968fc"), "max_id": UUID("f27a175f-246e-48d8-b795-013cce676aa6"), "site_id": UUID("66a26064-cee6-4538-a49c-dc6497794881"), "city": "Барнаул", "street": "Взлетная", "house": "2к"},
    {"id": UUID("1a39e913-de43-48f0-8528-9c262040d77c"), "max_id": UUID("a5b94fcb-fdab-4e79-ba09-4e150cc49f4a"), "site_id": UUID("3b8f9a34-1b26-4b27-b8b5-3f37429b9640"), "city": "Барнаул", "street": "Павловский тракт", "house": "188"},
    {"id": UUID("b9874943-cb1b-47c6-b193-9670830cdf4e"), "max_id": UUID("45af5bfc-3c05-4adb-a129-cc1330cc22ca"), "site_id": UUID("28ca0126-0e60-4000-a83f-211fb7b8900e"), "city": "Новоалтайск", "street": "Октябрьская", "house": "36"},
    {"id": UUID("5b229c9b-5d77-4cf7-af95-4553b46681ce"), "max_id": UUID("3a6071b2-6948-41f6-8284-7626a0c799bc"), "site_id": UUID("b3f4c34d-4674-4d55-ae3e-ab7e36591169"), "city": "Горно-Алтайск", "street": "Бийская", "house": "8/2"},
    {"id": UUID("985deac5-b9e0-464e-90ff-24232200a8a4"), "max_id": UUID("bd9f408b-4363-4a91-be3e-10aff85640ed"), "site_id": UUID("cb491730-dbca-4455-a3d9-a1677ce3e994"), "city": "Майма", "street": "Ленина", "house": "91"},
    {"id": UUID("b3383774-5dad-489c-a014-3dd322ee7dbf"), "max_id": UUID("319258cb-bcf0-494a-8d52-cd6a0643f152"), "site_id": UUID("c82bf948-72c6-410f-9773-ec1d56d0ffd7"), "city": "Заринск", "street": "Союза Республик", "house": "16"},
    {"id": UUID("0c616107-bc8d-46f1-a67a-a00f7a1743e8"), "max_id": UUID("95c702ea-3d26-49b6-87ac-1723109b75b1"), "site_id": UUID("ee3f270e-6131-400d-8179-6f83c17ec302"), "city": "Алейск", "street": "Пионерская", "house": "150"},
    {"id": UUID("8a5b53a3-ce7f-498b-bea7-80935b8e7e63"), "max_id": UUID("115cb57e-4c70-4de1-8db4-4ffa86c4c72e"), "site_id": UUID("9ae78db4-6cf5-4021-9ffd-4712e7efbe4a"), "city": "Белокуриха", "street": "Партизанская", "house": "14/1"},
    {"id": UUID("2f3153da-3681-488a-ae41-7324682883ac"), "max_id": UUID("8ccedbaf-663c-450b-b4d0-70ec5de4c6f6"), "site_id": UUID("041b9029-74fc-4173-b828-d8e64198a661"), "city": "Бийск", "street": "Коммунарский", "house": "37"},
    {"id": UUID("ca17a74e-cb2d-4b5c-b8ca-4e060de93f52"), "max_id": UUID("d7faf01f-fe75-4ac1-b5ee-ce352314e700"), "site_id": UUID("66e2e1e9-f77c-4ad7-becf-220003a8329b"), "city": "Бийск", "street": "Советская", "house": "204/3"},
    {"id": UUID("bd747441-29a9-4280-be9f-80ce38fea24b"), "max_id": UUID("855aa7bc-75f3-4793-bab2-f4c8ef8b75c1"), "site_id": UUID("df099715-c9e5-4f64-9e49-e128819d8fd3"), "city": "Сростки", "street": "Чуйская", "house": "12"},
    {"id": UUID("5ddc90b9-2609-4c46-905f-e18ec6a9d494"), "max_id": UUID("c4f8e563-dc07-4514-92a9-ed72668a8da5"), "site_id": UUID("cc4da95b-5c62-4103-96aa-8fab4d9837c2"), "city": "Рубцовск", "street": "Заводская", "house": "220"},
    {"id": UUID("efb5a2a1-588b-4004-8a51-b22d1ad404c8"), "max_id": UUID("097182cf-c3b4-4372-b84a-5307b370fd19"), "site_id": UUID("bf53be3d-ef69-48df-af82-73112eb34ae3"), "city": "Рубцовск", "street": "Ленина", "house": "85"},
    {"id": UUID("a6ff65f2-1ba0-4991-b6d0-a1a128d63846"), "max_id": UUID("ab493a6a-5a9b-4f32-8a2d-85b55fc86eab"), "site_id": UUID("2727a070-07cb-4199-8f3f-ebb50075bc8b"), "city": "Славгород", "street": "Ленина", "house": "179"},
    {"id": UUID("b003d405-b62c-4f63-8b95-30bf07e969d3"), "max_id": UUID("c4c582b3-7bf9-4be8-be69-757aa47f5dfe"), "site_id": UUID("4ddf6a32-723a-4f88-8ff8-6e89865ab8fc"), "city": "Камень на Оби", "street": "Гагарина", "house": "111/8"},
    {"id": UUID("b2a78060-491c-44c9-b9aa-36d175362ce9"), "max_id": UUID("2901e937-9922-42ba-89a3-58b845788f4a"), "site_id": UUID("31325c56-b800-4b39-b380-6d10a0787a07"), "city": "Новокузнецк", "street": "Вокзальная", "house": "8А"},
    {"id": UUID("e11fc445-424d-40bb-af5c-7d5fe77eb14c"), "max_id": UUID("9c94ccc1-0a40-411d-9b2d-281ea0e6fb47"), "site_id": UUID("329cf30e-3284-41a6-b280-a44121d9a6a7"), "city": "Новокузнецк", "street": "Кирова", "house": "111Б"},
    {"id": UUID("2bf39adf-a6f0-4ed0-a8ce-55d8dd3eb5e5"), "max_id": UUID("ea60d92b-3a4d-43c7-acbf-1b8a13f1dd10"), "site_id": UUID("d1747c75-edb0-44e3-ae58-cc2f72881da9"), "city": "Новосибирск", "street": "Плановая", "house": "77"},
    {"id": UUID("e84f78a4-90b7-435f-8395-e0f5900efca6"), "max_id": UUID("6744c2bd-75ce-4793-909c-2ef7294ebc40"), "site_id": UUID("541a01d4-b017-4683-aa05-775104372112"), "city": "Новосибирск", "street": "Гоголя", "house": "43/1"},
    {"id": UUID("9eef9823-56fe-42ff-8bb6-acb35aa4bb62"), "max_id": UUID("6c816a2f-e02b-4459-b93e-a430b1ab8277"), "site_id": UUID("25ce4d90-4e58-4c90-9146-e6d8e37549a9"), "city": "Омск", "street": "Мира", "house": "19"},
    {"id": UUID("eb08f488-b8a6-471d-9cc7-94bb6cf9f098"), "max_id": UUID("c3f7d262-7dd8-4843-969a-0f87125a6272"), "site_id": UUID("f9f69a62-5cd1-4459-9615-1abf8a92fea8"), "city": "Омск", "street": "Комарова", "house": "2/2"},
    {"id": UUID("d6a6744d-694d-43f0-82b8-28f8d33c41f9"), "max_id": UUID("7d2da39f-f983-441d-839c-8397f34c517b"), "site_id": UUID("7881178c-bb18-41bd-a4ce-a5b286560ca4"), "city": "Томск", "street": "Герцена", "house": "61/1"},
    {"id": UUID("f4fd388e-1e52-4232-ba84-da8ba9553481"), "max_id": UUID("aa8b0492-6b23-4700-8822-c1e0a1b5c9f9"), "site_id": UUID("06d76d83-bc25-43ae-ae80-e5e488ab67af"), "city": "Тюмень", "street": "Мельникайте", "house": "126/3"},
    {"id": UUID("9e33b589-ec55-42ce-8b82-c1d917534a03"), "max_id": UUID("1b95956b-3713-4c46-9743-00e1a1b22d30"), "site_id": UUID("1bdb1e02-ecc9-4240-8b9c-7a7291245e80"), "city": "Белово", "street": "Советская", "house": "8"},
    {"id": UUID("fca52be9-a366-423c-a14f-429888d600c2"), "max_id": UUID("b99ffb9e-deb6-4113-b8e7-8e8372988d04"), "site_id": UUID("d0cb5244-95c5-4102-8d1d-fb2427fcf117"), "city": "Поспелиха", "street": "Коммунистическая", "house": "1"},
]

REQUEST_TYPES_TREE = [
    {
        "id": UUID("774d5c21-9dd1-4ae2-ab5d-3d542074804d"),
        "name": "Жалоба", "description": "Негативный отзыв о товаре, сервисе или работе",
        "children": [
            {"id": UUID("d4eb36c5-156b-4bdc-89d4-ce0b5f4f8558"), "name": "Качество товара", "description": "Брак, просрочка", "allowed": ["client", "employee", "partner", "anonymous"]},
            {"id": UUID("acd81935-10f9-45de-9a8d-7bf160fc23f8"), "name": "Обслуживание персонала", "description": "Грубость, хамство", "allowed": ["client", "employee", "partner", "anonymous"]},
            {"id": UUID("3335b783-577d-476a-86ca-96df641eb3b4"), "name": "Чистота и порядок", "description": "Грязь, беспорядок", "allowed": ["client", "employee", "partner", "anonymous"]},
            {"id": UUID("aeed2d94-6aa1-4027-8c93-39d27dc7e574"), "name": "Работа кассы", "description": "Очереди, ошибки", "allowed": ["client", "anonymous"]},
            {"id": UUID("c39056a7-24f0-4088-ba7b-094083003a61"), "name": "Цены и ценники", "description": "Несоответствие цен", "allowed": ["client", "employee", "anonymous"]},
            {"id": UUID("e4aef8d3-0292-4723-9269-34d1035cfd02"), "name": "Работа сайта", "description": "Ошибки на сайте", "allowed": ["client", "employee", "partner", "anonymous"]},
            {"id": UUID("63074328-bd07-4f81-8a58-423347dfbf9d"), "name": "Работа MAX-бота", "description": "Бот не отвечает", "allowed": ["client", "employee", "partner", "anonymous"]},
            {"id": UUID("8a61cba2-8d36-4a41-8b1b-b7bca6488181"), "name": "Доставка", "description": "Опоздание, повреждение", "allowed": ["client", "partner", "anonymous"]},
            {"id": UUID("90724749-1041-494b-bdd7-064286841fa4"), "name": "Возврат товара", "description": "Отказ в возврате", "allowed": ["client", "employee"]},
        ]
    },
    {
        "id": UUID("c3d5a6c3-36ce-40cb-85ca-ad1cec9262e2"),
        "name": "Предложение", "description": "Идеи по улучшению работы компании",
        "children": [
            {"id": UUID("c3d47926-bbd9-492f-bd88-8238cfd15131"), "name": "Ассортимент", "description": "Добавить новые товары", "allowed": ["client", "employee", "partner"]},
            {"id": UUID("dca0f85e-8ca8-45c1-9648-2b6638bff05a"), "name": "Улучшение сервиса", "description": "Идеи по качеству", "allowed": ["client", "employee", "partner", "anonymous"]},
            {"id": UUID("3d9a1de3-6e85-4b51-b8bd-b164df133cb7"), "name": "Программа лояльности", "description": "Бонусы и скидки", "allowed": ["client", "employee"]},
            {"id": UUID("c0012bcb-aa7c-43c5-9851-266b7ab538e8"), "name": "Акции и распродажи", "description": "Маркетинговые идеи", "allowed": ["client", "employee", "partner"]},
            {"id": UUID("6e88c16d-9b50-48e3-8bde-2c795b9789f2"), "name": "Корпоративные процессы", "description": "Внутренние предложения", "allowed": ["employee", "partner"]},
        ]
    },
    {
        "id": UUID("a559a140-cae9-4f54-b1da-f4aa066dd6b4"),
        "name": "Вопрос", "description": "Запрос справочной информации",
        "children": [
            {"id": UUID("3e940281-bdff-4033-90a4-878a277e0e83"), "name": "Наличие товара", "description": "Уточнение остатков", "allowed": ["client", "anonymous"]},
            {"id": UUID("1505e79b-1de7-4ad0-9896-380d442cf5ca"), "name": "Условия сотрудничества", "description": "Вопросы от поставщиков", "allowed": ["partner", "employee"]},
            {"id": UUID("7637a89f-5a0f-47ca-8a39-d74479636633"), "name": "Вакансии и трудоустройство", "description": "Вопросы о работе", "allowed": ["employee", "partner"]},
            {"id": UUID("c11d9d2d-e0a4-423d-9cad-1612dea46ae1"), "name": "График работы", "description": "Часы работы", "allowed": ["client", "anonymous"]},
        ]
    },
    {
        "id": UUID("50818cf3-ce20-442f-ad9c-a9a690581342"),
        "name": "Благодарность", "description": "Положительный отзыв о работе",
        "children": [
            {"id": UUID("96fb9b67-b98f-440f-a4c5-237bfbf49e57"), "name": "Сотруднику", "description": "Благодарность сотруднику", "allowed": ["client", "employee", "partner", "anonymous"]},
            {"id": UUID("3ccb33f2-f5f6-417d-b248-7c92e53b8651"), "name": "Магазину", "description": "Благодарность команде", "allowed": ["client", "employee", "partner", "anonymous"]},
            {"id": UUID("41237ffe-8171-459f-8cb8-5e4fb0c5d422"), "name": "Качеству товара", "description": "Отзыв о продукции", "allowed": ["client", "employee", "partner", "anonymous"]},
            {"id": UUID("499333b1-e57e-4a12-abff-d41b58aa0ca0"), "name": "Сервису доставки", "description": "Благодарность курьеру", "allowed": ["client", "partner", "anonymous"]},
        ]
    },
    {
        "id": UUID("de8d7d5d-6796-4671-aa18-ad981ebc9fbe"),
        "name": "Нарушение / Этика", "description": "Серьезные нарушения",
        "children": [
            {"id": UUID("ce788c97-dc70-42d5-9fd1-6b35d9b298b5"), "name": "Конфликтная ситуация", "description": "Скандал, угрозы", "allowed": ["client", "employee", "partner", "anonymous"]},
            {"id": UUID("57d36bc5-15c9-470d-b4e2-17b28e224b03"), "name": "Нарушение стандартов", "description": "Несоблюдение регламентов", "allowed": ["employee", "partner"]},
            {"id": UUID("5cb1afef-5e64-4bf8-8dd1-199284b8fe07"), "name": "Безопасность", "description": "Угроза здоровью", "allowed": ["client", "employee", "partner", "anonymous"]},
            {"id": UUID("98dbe042-32f6-4092-934a-e2d887df3108"), "name": "Мошенничество", "description": "Обман, махинации", "allowed": ["client", "employee", "partner", "anonymous"]},
            {"id": UUID("0b599e80-b3cf-4863-b739-d332e0da833f"), "name": "Коррупция", "description": "Взяточничество", "allowed": ["employee", "partner"]},
        ]
    },
    {
        "id": UUID("2d2c02a9-db95-4a23-898a-a1326696324b"),
        "name": "Техническая проблема", "description": "Проблемы с IT-системами",
        "children": [
            {"id": UUID("3e549f08-f199-43b8-bbae-55d8e4c0c2e6"), "name": "Ошибка на сайте", "description": "Не работает кнопка", "allowed": ["client", "employee", "partner", "anonymous"]},
            {"id": UUID("4488fcc5-fb8b-43f0-bf92-9f918847ca7e"), "name": "Проблема с оплатой", "description": "Не проходит платеж", "allowed": ["client", "employee", "partner", "anonymous"]},
            {"id": UUID("f8b67a4a-c5ca-48bc-b713-f2c2e635e874"), "name": "Личный кабинет", "description": "Не входит, забыл пароль", "allowed": ["client", "employee", "partner"]},
            {"id": UUID("2860e7b2-888f-4d17-a2dd-61739879dd13"), "name": "Внутренние IT-системы", "description": "Проблемы с кассой, 1С", "allowed": ["employee"]},
        ]
    },
]

async def init_default_data(db: AsyncSession):
    created_items = []
    
    # --- 0. ДЕФОЛТНЫЕ ЗАПИСИ (С НУЛЕВЫМ UUID) ---
    result_def_store = await db.execute(select(Store).where(Store.id == NIL_UUID))
    if not result_def_store.scalar_one_or_none():
        db.add(Store(id=NIL_UUID, name="Не указан", address="Не указан"))
        created_items.append("🏪 Магазин по умолчанию (0000...)")
        
    result_def_req = await db.execute(select(RequesterType).where(RequesterType.id == NIL_UUID))
    if not result_def_req.scalar_one_or_none():
        db.add(RequesterType(id=NIL_UUID, name="Не указан", code="none"))
        created_items.append("👤 Заявитель по умолчанию (0000...)")
    
    result_def_rt = await db.execute(select(RequestType).where(RequestType.id == NIL_UUID))
    if not result_def_rt.scalar_one_or_none():
        db.add(RequestType(id=NIL_UUID, name="Не указан", description="Тип обращения не выбран"))
        created_items.append("📂 Тип обращения по умолчанию (0000...)")
        
    result_def_ch = await db.execute(select(HotlineChannel).where(HotlineChannel.id == NIL_UUID))
    if not result_def_ch.scalar_one_or_none():
        db.add(HotlineChannel(id=NIL_UUID, name="Не указан", channel_type="Не указан", store_id=NIL_UUID))
        created_items.append("📞 Канал по умолчанию (0000...)")

    await db.flush()
    
    # 1. Заявители
    requester_map = {"none": NIL_UUID}
    for r_data in REQUESTER_TYPES_DATA:
        result = await db.execute(select(RequesterType).where(RequesterType.id == r_data["id"]))
        req_type = result.scalar_one_or_none()
        if not req_type:
            req_type = RequesterType(**r_data)
            db.add(req_type)
            await db.flush()
            created_items.append(f"👤 Заявитель: {r_data['name']}")
        requester_map[r_data["code"]] = req_type.id

    # 2. Типы обращений
    for type_data in REQUEST_TYPES_TREE:
        result_parent = await db.execute(select(RequestType).where(RequestType.id == type_data["id"]))
        parent_type = result_parent.scalar_one_or_none()
        
        if not parent_type:
            parent_type = RequestType(id=type_data["id"], name=type_data["name"], description=type_data["description"])
            db.add(parent_type)
            await db.flush()
            created_items.append(f"📂 Тип: {type_data['name']}")
        
        await db.refresh(parent_type, attribute_names=['allowed_requesters'])
        parent_allowed_codes = set()
        
        for child_data in type_data.get("children", []):
            result_child = await db.execute(select(RequestType).where(RequestType.id == child_data["id"]))
            child_type = result_child.scalar_one_or_none()
            
            if not child_type:
                child_type = RequestType(id=child_data["id"], name=child_data["name"], description=child_data["description"], parent_id=parent_type.id)
                db.add(child_type)
                await db.flush()
                created_items.append(f"  ↳ Подтип: {child_data['name']}")
            
            await db.refresh(child_type, attribute_names=['allowed_requesters'])
            
            child_allowed_codes = child_data.get("allowed", ["client", "employee", "partner", "anonymous"])
            parent_allowed_codes.update(child_allowed_codes)
            
            child_allowed_ids = [requester_map[code] for code in child_allowed_codes if code in requester_map]
            if child_allowed_ids:
                req_result = await db.execute(select(RequesterType).where(RequesterType.id.in_(child_allowed_ids)))
                child_type.allowed_requesters = req_result.scalars().all()
                await db.flush()
        
        parent_allowed_ids = [requester_map[code] for code in parent_allowed_codes if code in requester_map]
        if parent_allowed_ids:
            req_result = await db.execute(select(RequesterType).where(RequesterType.id.in_(parent_allowed_ids)))
            parent_type.allowed_requesters = req_result.scalars().all()
            await db.flush()

    # 3. Магазины и каналы
    for data in STORES_DATA:
        store_name = f"{data['city']}, {data['street']}, {data['house']}"
        store_address = f"{data['city']}, ул. {data['street']}, д. {data['house']}"
        result_store = await db.execute(select(Store).where(Store.id == data["id"]))
        store = result_store.scalar_one_or_none()
        if not store:
            store = Store(id=data["id"], name=store_name, address=store_address)
            db.add(store)
            await db.flush()
            created_items.append(f"🏪 Магазин: {store_name}")

        result_max = await db.execute(select(HotlineChannel).where(HotlineChannel.id == data["max_id"]))
        if not result_max.scalar_one_or_none():
            db.add(HotlineChannel(
                id=data["max_id"], store_id=store.id, channel_type="MAX", 
                name=f"MAX Бот - {store_name}", 
                max_url=f"https://max.ru/id5404205450_4_bot?start={data['max_id']}"
            ))
            await db.flush()
            created_items.append(f"  ↳ Канал MAX: {store_name}")

        result_site = await db.execute(select(HotlineChannel).where(HotlineChannel.id == data["site_id"]))
        if not result_site.scalar_one_or_none():
            db.add(HotlineChannel(
                id=data["site_id"], store_id=store.id, channel_type="Сайт", 
                name=f"Сайт - {store_name}", 
                site_url=f"https://пакетон.рф/hotline?pkt_ch={data['site_id']}"
            ))
            await db.flush()
            created_items.append(f"  ↳ Канал Сайт: {store_name}")

    await db.commit()
    if created_items:
        print(f"✅ Инициализация завершена. Создано/обновлено записей: {len(created_items)}")
    else:
        print("✅ Справочники уже актуальны.")