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
        await db.refresh(obj) # Предотвращает MissingGreenlet
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
# 5. ЖУРНАЛ ОБРАЩЕНИЙ
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
        joinedload(HotlineJournal.request_type),
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
    result = await db.execute(
        select(HotlineJournal)
        .options(joinedload(HotlineJournal.channel), joinedload(HotlineJournal.request_type), joinedload(HotlineJournal.requester_type))
        .where(HotlineJournal.id == journal_id)
    )
    return result.scalars().unique().first()

async def create_journal(db: AsyncSession, journal: HotlineJournalCreate):
    db_journal = HotlineJournal(**journal.model_dump()) 
    db.add(db_journal)
    await db.commit()
    await db.refresh(db_journal, attribute_names=['channel', 'request_type', 'requester_type'])
    return db_journal

async def update_journal(db: AsyncSession, journal_id: UUID, journal_update: HotlineJournalUpdate):
    db_journal = await get_journal_by_id(db, journal_id)
    if not db_journal: return None
    
    update_data = journal_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_journal, key, value)
        
    await db.commit()
    await db.refresh(db_journal, attribute_names=['channel', 'request_type', 'requester_type'])
    return db_journal

async def delete_journal(db: AsyncSession, journal_id: UUID):
    db_journal = await get_journal_by_id(db, journal_id)
    if not db_journal: return None
    db_journal.is_deleted = True
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
# 7. ИНИЦИАЛИЗАЦИЯ СПРАВОЧНИКОВ
# ==============================================================================
REQUESTER_TYPES_DATA = [
    {"name": "Клиент", "code": "client"},
    {"name": "Сотрудник", "code": "employee"},
    {"name": "Партнер / Поставщик", "code": "partner"},
    {"name": "Анонимный посетитель", "code": "anonymous"},
]

STORES_DATA = [
    {"city": "Барнаул", "street": "Красноармейский", "house": "131"},
    {"city": "Барнаул", "street": "Мало-Тобольская", "house": "23"},
    {"city": "Барнаул", "street": "Шевченко", "house": "157Б"},
    {"city": "Барнаул", "street": "Космонавтов", "house": "59"},
    {"city": "Барнаул", "street": "Северо-Западная", "house": "6"},
    {"city": "Барнаул", "street": "Германа Титова", "house": "6"},
    {"city": "Барнаул", "street": "Космонавтов", "house": "8/2"},
    {"city": "Барнаул", "street": "Антона Петрова", "house": "190"},
    {"city": "Барнаул", "street": "Взлетная", "house": "2к"},
    {"city": "Барнаул", "street": "Павловский тракт", "house": "188"},
    {"city": "Новоалтайск", "street": "Октябрьская", "house": "36"},
    {"city": "Горно-Алтайск", "street": "Бийская", "house": "8/2"},
    {"city": "Майма", "street": "Ленина", "house": "91"},
    {"city": "Заринск", "street": "Союза Республик", "house": "16"},
    {"city": "Алейск", "street": "Пионерская", "house": "150"},
    {"city": "Белокуриха", "street": "Партизанская", "house": "14/1"},
    {"city": "Бийск", "street": "Коммунарский", "house": "37"},
    {"city": "Бийск", "street": "Советская", "house": "204/3"},
    {"city": "Сростки", "street": "Чуйская", "house": "12"},
    {"city": "Рубцовск", "street": "Заводская", "house": "220"},
    {"city": "Рубцовск", "street": "Ленина", "house": "85"},
    {"city": "Славгород", "street": "Ленина", "house": "179"},
    {"city": "Камень на Оби", "street": "Гагарина", "house": "111/8"},
    {"city": "Новокузнецк", "street": "Вокзальная", "house": "8А"},
    {"city": "Новокузнецк", "street": "Кирова", "house": "111Б"},
    {"city": "Новосибирск", "street": "Плановая", "house": "77"},
    {"city": "Новосибирск", "street": "Гоголя", "house": "43/1"},
    {"city": "Омск", "street": "Мира", "house": "19"},
    {"city": "Омск", "street": "Комарова", "house": "2/2"},
    {"city": "Томск", "street": "Герцена", "house": "61/1"},
    {"city": "Тюмень", "street": "Мельникайте", "house": "126/3"},
    {"city": "Белово", "street": "Советская", "house": "8"},
    {"city": "Поспелиха", "street": "Коммунистическая", "house": "1"},
]

REQUEST_TYPES_TREE = [
    {
        "name": "Жалоба", "description": "Негативный отзыв о товаре, сервисе или работе",
        "children": [
            {"name": "Качество товара", "description": "Брак, просрочка", "allowed": ["client", "employee", "partner", "anonymous"]},
            {"name": "Обслуживание персонала", "description": "Грубость, хамство", "allowed": ["client", "employee", "partner", "anonymous"]},
            {"name": "Чистота и порядок", "description": "Грязь, беспорядок", "allowed": ["client", "employee", "partner", "anonymous"]},
            {"name": "Работа кассы", "description": "Очереди, ошибки", "allowed": ["client", "anonymous"]},
            {"name": "Цены и ценники", "description": "Несоответствие цен", "allowed": ["client", "employee", "anonymous"]},
            {"name": "Работа сайта", "description": "Ошибки на сайте", "allowed": ["client", "employee", "partner", "anonymous"]},
            {"name": "Работа MAX-бота", "description": "Бот не отвечает", "allowed": ["client", "employee", "partner", "anonymous"]},
            {"name": "Доставка", "description": "Опоздание, повреждение", "allowed": ["client", "partner", "anonymous"]},
            {"name": "Возврат товара", "description": "Отказ в возврате", "allowed": ["client", "employee"]},
        ]
    },
    {
        "name": "Предложение", "description": "Идеи по улучшению работы компании",
        "children": [
            {"name": "Ассортимент", "description": "Добавить новые товары", "allowed": ["client", "employee", "partner"]},
            {"name": "Улучшение сервиса", "description": "Идеи по качеству", "allowed": ["client", "employee", "partner", "anonymous"]},
            {"name": "Программа лояльности", "description": "Бонусы и скидки", "allowed": ["client", "employee"]},
            {"name": "Акции и распродажи", "description": "Маркетинговые идеи", "allowed": ["client", "employee", "partner"]},
            {"name": "Корпоративные процессы", "description": "Внутренние предложения", "allowed": ["employee", "partner"]},
        ]
    },
    {
        "name": "Вопрос", "description": "Запрос справочной информации",
        "children": [
            {"name": "Наличие товара", "description": "Уточнение остатков", "allowed": ["client", "anonymous"]},
            {"name": "Условия сотрудничества", "description": "Вопросы от поставщиков", "allowed": ["partner", "employee"]},
            {"name": "Вакансии и трудоустройство", "description": "Вопросы о работе", "allowed": ["employee", "partner"]},
            {"name": "График работы", "description": "Часы работы", "allowed": ["client", "anonymous"]},
        ]
    },
    {
        "name": "Благодарность", "description": "Положительный отзыв о работе",
        "children": [
            {"name": "Сотруднику", "description": "Благодарность сотруднику", "allowed": ["client", "employee", "partner", "anonymous"]},
            {"name": "Магазину", "description": "Благодарность команде", "allowed": ["client", "employee", "partner", "anonymous"]},
            {"name": "Качеству товара", "description": "Отзыв о продукции", "allowed": ["client", "employee", "partner", "anonymous"]},
            {"name": "Сервису доставки", "description": "Благодарность курьеру", "allowed": ["client", "partner", "anonymous"]},
        ]
    },
    {
        "name": "Нарушение / Этика", "description": "Серьезные нарушения",
        "children": [
            {"name": "Конфликтная ситуация", "description": "Скандал, угрозы", "allowed": ["client", "employee", "partner", "anonymous"]},
            {"name": "Нарушение стандартов", "description": "Несоблюдение регламентов", "allowed": ["employee", "partner"]},
            {"name": "Безопасность", "description": "Угроза здоровью", "allowed": ["client", "employee", "partner", "anonymous"]},
            {"name": "Мошенничество", "description": "Обман, махинации", "allowed": ["client", "employee", "partner", "anonymous"]},
            {"name": "Коррупция", "description": "Взяточничество", "allowed": ["employee", "partner"]},
        ]
    },
    {
        "name": "Техническая проблема", "description": "Проблемы с IT-системами",
        "children": [
            {"name": "Ошибка на сайте", "description": "Не работает кнопка", "allowed": ["client", "employee", "partner", "anonymous"]},
            {"name": "Проблема с оплатой", "description": "Не проходит платеж", "allowed": ["client", "employee", "partner", "anonymous"]},
            {"name": "Личный кабинет", "description": "Не входит, забыл пароль", "allowed": ["client", "employee", "partner"]},
            {"name": "Внутренние IT-системы", "description": "Проблемы с кассой, 1С", "allowed": ["employee"]},
        ]
    },
]

async def init_default_data(db: AsyncSession):
    created_items = []
    
    # 1. Заявители
    requester_map = {}
    for r_data in REQUESTER_TYPES_DATA:
        result = await db.execute(select(RequesterType).where(RequesterType.code == r_data["code"]))
        req_type = result.scalar_one_or_none()
        if not req_type:
            req_type = RequesterType(**r_data)
            db.add(req_type)
            await db.flush()
            created_items.append(f"👤 Заявитель: {r_data['name']}")
        requester_map[r_data["code"]] = req_type.id

    # 2. Типы обращений
    for type_data in REQUEST_TYPES_TREE:
        result_parent = await db.execute(select(RequestType).where(RequestType.name == type_data["name"], RequestType.parent_id == None))
        parent_type = result_parent.scalar_one_or_none()
        if not parent_type:
            parent_type = RequestType(name=type_data["name"], description=type_data["description"])
            db.add(parent_type)
            await db.flush()
            created_items.append(f"📂 Тип: {type_data['name']}")
        
        for child_data in type_data.get("children", []):
            result_child = await db.execute(select(RequestType).where(RequestType.name == child_data["name"], RequestType.parent_id == parent_type.id))
            if not result_child.scalar_one_or_none():
                child_type = RequestType(name=child_data["name"], description=child_data["description"], parent_id=parent_type.id)
                allowed_codes = child_data.get("allowed", ["client", "employee", "partner", "anonymous"])
                allowed_ids = [requester_map[code] for code in allowed_codes if code in requester_map]
                if allowed_ids:
                    req_result = await db.execute(select(RequesterType).where(RequesterType.id.in_(allowed_ids)))
                    child_type.allowed_requesters = req_result.scalars().all()
                db.add(child_type)
                created_items.append(f"  ↳ Подтип: {child_data['name']}")

    # 3. Магазины и каналы
    for data in STORES_DATA:
        store_name = f"{data['city']}, {data['street']}, {data['house']}"
        store_address = f"{data['city']}, ул. {data['street']}, д. {data['house']}"
        result_store = await db.execute(select(Store).where(Store.name == store_name))
        store = result_store.scalar_one_or_none()
        if not store:
            store = Store(name=store_name, address=store_address)
            db.add(store)
            await db.flush()
            created_items.append(f"🏪 Магазин: {store_name}")

        result_max = await db.execute(select(HotlineChannel).where(HotlineChannel.store_id == store.id, HotlineChannel.channel_type == "MAX"))
        if not result_max.scalar_one_or_none():
            channel_id_max = uuid.uuid4()
            db.add(HotlineChannel(id=channel_id_max, store_id=store.id, channel_type="MAX", name=f"MAX Бот - {store_name}", max_url=f"https://max.ru/id5404205450_4_bot?start={channel_id_max}"))

        result_site = await db.execute(select(HotlineChannel).where(HotlineChannel.store_id == store.id, HotlineChannel.channel_type == "Сайт"))
        if not result_site.scalar_one_or_none():
            channel_id_site = uuid.uuid4()
            db.add(HotlineChannel(id=channel_id_site, store_id=store.id, channel_type="Сайт", name=f"Сайт - {store_name}", site_url=f"https://пакетон.рф/hotline?pkt_ch={channel_id_site}"))

    await db.commit()
    if created_items:
        print(f"✅ Инициализация завершена. Создано/обновлено записей: {len(created_items)}")
    else:
        print("✅ Справочники уже актуальны.")