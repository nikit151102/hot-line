from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import Optional
from datetime import datetime
from crud import (
    # Магазины
    get_stores, create_store, delete_store,
    # Каналы
    get_channels, create_channel, delete_channel,
    # Типы заявителей
    get_requester_types, create_requester_type, delete_requester_type,
    # Типы обращений
    get_request_types, create_request_type, update_request_type, delete_request_type,
    get_allowed_request_types,
    # Журнал
    create_journal, get_journals, get_journal_by_id, update_journal, delete_journal,
    # Статистика
    get_hotline_stats
)
from schemas import (
    # Магазины
    StoreResponse, StoreCreate,
    # Каналы
    HotlineChannelResponse, HotlineChannelCreate,
    # Типы заявителей
    RequesterTypeResponse, RequesterTypeCreate,
    # Типы обращений
    RequestTypeResponse, RequestTypeCreate, RequestTypeUpdate,
    # Журнал
    HotlineJournalResponse, HotlineJournalCreate, HotlineJournalUpdate,
    # Статистика
    HotlineStatsResponse
)
from database.database_app import get_session

router = APIRouter()


"""
Логическая группировка по тегам:
Public — эндпоинты для бота и сайта
Admin - Requesters — управление типами заявителей
Admin - Request Types — управление типами обращений с правами
Admin - Stores — управление магазинами
Admin - Channels — управление каналами
Admin - Journals — управление журналом обращений
Analytics — статистика
Публичные эндпоинты для бота/сайта:
GET /public/requester-types/ — список типов заявителей
GET /public/request-types/allowed?requester_code=client — типы обращений, доступные конкретному заявителю
GET /public/channels/by-type?channel_type=MAX — каналы по типу
Расширенные фильтры для журнала:
requester_type_id — фильтр по типу заявителя
request_type_id — фильтр по типу обращения
channel_id — фильтр по каналу
store_id — фильтр по магазину
status_filter — статус (new/resolved)
date_from / date_to — период
search — поиск по тексту
Быстрые действия:
POST /admin/journals/{id}/resolve — быстро принять решение
POST /admin/journals/{id}/assign — назначить администратора
GET по ID для всех сущностей (магазины, каналы, типы обращений, обращения).
Обновлённый фильтр по типу канала в get_channels — теперь можно фильтровать по channel_type (MAX/Сайт).

"""

# ============================================================
# ==================== СТАТИСТИКА ============================
# ============================================================
@router.get("/stats/", response_model=HotlineStatsResponse, tags=["Analytics"])
async def get_hotline_statistics(
    days: int = Query(30, ge=1, le=365, description="Период анализа в днях (по умолчанию 30)"),
    store_id: Optional[UUID] = Query(None, description="Фильтр по магазину"),
    channel_type: Optional[str] = Query(None, description="Фильтр по типу канала (MAX/Сайт)"),
    requester_type_id: Optional[UUID] = Query(None, description="Фильтр по типу заявителя"),
    db: AsyncSession = Depends(get_session)
):
    """
    Возвращает комплексную статистику для дашборда:
    - KPI (всего, решено, среднее время)
    - Временные ряды (по дням, часам, дням недели)
    - Категориальные разрезы (магазины, каналы, типы, админы)
    - Кросс-аналитику (матрицы)
    """
    return await get_hotline_stats(
        db, days=days,
        store_id=store_id,
        channel_type=channel_type,
        requester_type_id=requester_type_id
    )


# ============================================================
# ============ ПУБЛИЧНЫЕ ЭНДПОИНТЫ (для бота/сайта) ===========
# ============================================================
@router.get("/public/requester-types/", response_model=list[RequesterTypeResponse], tags=["Public"])
async def get_public_requester_types(db: AsyncSession = Depends(get_session)):
    """Список типов заявителей для выбора в форме (Клиент, Сотрудник, Партнер и т.д.)"""
    return await get_requester_types(db, include_deleted=False)


@router.get("/public/request-types/allowed", response_model=list[RequestTypeResponse], tags=["Public"])
async def get_allowed_types(
    requester_code: str = Query(..., description="Код заявителя: client, employee, partner, anonymous"),
    parent_id: Optional[UUID] = Query(None, description="ID родительского типа (для получения подтипов)"),
    db: AsyncSession = Depends(get_session)
):
    """
    Получить типы обращений, доступные КОНКРЕТНОМУ типу заявителя.
    Используется ботом/сайтом для динамического отображения кнопок выбора.
    """
    return await get_allowed_request_types(db, requester_code, parent_id)


@router.get("/public/channels/by-type", response_model=list[HotlineChannelResponse], tags=["Public"])
async def get_public_channels_by_type(
    channel_type: str = Query(..., description="Тип канала: MAX, Сайт"),
    db: AsyncSession = Depends(get_session)
):
    """Получить все каналы определённого типа (для админки или аналитики)"""
    return await get_channels(db, channel_type=channel_type, include_deleted=False)


# ============================================================
# ============ АДМИНКА: ТИПЫ ЗАЯВИТЕЛЕЙ ======================
# ============================================================
@router.post("/admin/requester-types/", response_model=RequesterTypeResponse, status_code=status.HTTP_201_CREATED, tags=["Admin - Requesters"])
async def admin_create_requester_type(data: RequesterTypeCreate, db: AsyncSession = Depends(get_session)):
    """Создать новый тип заявителя (Клиент, Сотрудник, Партнер и т.д.)"""
    return await create_requester_type(db, data)


@router.get("/admin/requester-types/", response_model=list[RequesterTypeResponse], tags=["Admin - Requesters"])
async def admin_get_requester_types(
    include_deleted: bool = Query(False, description="Включать удаленные"),
    db: AsyncSession = Depends(get_session)
):
    """Список всех типов заявителей"""
    return await get_requester_types(db, include_deleted)


@router.delete("/admin/requester-types/{obj_id}", response_model=RequesterTypeResponse, tags=["Admin - Requesters"])
async def admin_delete_requester_type(obj_id: UUID, db: AsyncSession = Depends(get_session)):
    """Мягкое удаление типа заявителя"""
    deleted = await delete_requester_type(db, obj_id)
    if deleted is None:
        raise HTTPException(status_code=404, detail="Тип заявителя не найден")
    return deleted


# ============================================================
# ============ АДМИНКА: ТИПЫ ОБРАЩЕНИЙ =======================
# ============================================================
@router.post("/admin/request-types/", response_model=RequestTypeResponse, status_code=status.HTTP_201_CREATED, tags=["Admin - Request Types"])
async def admin_create_request_type(data: RequestTypeCreate, db: AsyncSession = Depends(get_session)):
    """Создать тип обращения с указанием прав доступа (allowed_requester_ids)"""
    return await create_request_type(db, data)


@router.get("/admin/request-types/", response_model=list[RequestTypeResponse], tags=["Admin - Request Types"])
async def admin_get_request_types(
    skip: int = 0,
    limit: int = 100,
    parent_id: Optional[UUID] = Query(None, description="ID родителя (None - только корневые)"),
    include_deleted: bool = Query(False, description="Включать удаленные"),
    db: AsyncSession = Depends(get_session)
):
    """Список типов обращений с их правами доступа"""
    return await get_request_types(db, skip, limit, parent_id, include_deleted)


@router.get("/admin/request-types/{obj_id}", response_model=RequestTypeResponse, tags=["Admin - Request Types"])
async def admin_get_request_type_by_id(obj_id: UUID, db: AsyncSession = Depends(get_session)):
    """Получить тип обращения по ID"""
    result = await get_request_types(db, parent_id=None, include_deleted=True)
    for rt in result:
        if rt.id == obj_id:
            return rt
    raise HTTPException(status_code=404, detail="Тип обращения не найден")


@router.put("/admin/request-types/{obj_id}", response_model=RequestTypeResponse, tags=["Admin - Request Types"])
async def admin_update_request_type(
    obj_id: UUID,
    data: RequestTypeUpdate,
    db: AsyncSession = Depends(get_session)
):
    """Обновить тип обращения (включая права доступа)"""
    updated = await update_request_type(db, obj_id, data)
    if updated is None:
        raise HTTPException(status_code=404, detail="Тип обращения не найден")
    return updated


@router.delete("/admin/request-types/{obj_id}", response_model=RequestTypeResponse, tags=["Admin - Request Types"])
async def admin_delete_request_type(obj_id: UUID, db: AsyncSession = Depends(get_session)):
    """Мягкое удаление типа обращения"""
    deleted = await delete_request_type(db, obj_id)
    if deleted is None:
        raise HTTPException(status_code=404, detail="Тип обращения не найден")
    return deleted


# ============================================================
# ============ АДМИНКА: МАГАЗИНЫ =============================
# ============================================================
@router.post("/admin/stores/", response_model=StoreResponse, status_code=status.HTTP_201_CREATED, tags=["Admin - Stores"])
async def admin_create_store(store: StoreCreate, db: AsyncSession = Depends(get_session)):
    """Создать новый магазин"""
    return await create_store(db, store)


@router.get("/admin/stores/", response_model=list[StoreResponse], tags=["Admin - Stores"])
async def admin_get_stores(
    skip: int = 0,
    limit: int = 100,
    include_deleted: bool = Query(False, description="Включать удаленные"),
    db: AsyncSession = Depends(get_session)
):
    """Список всех магазинов"""
    return await get_stores(db, skip, limit, include_deleted)


@router.get("/admin/stores/{store_id}", response_model=StoreResponse, tags=["Admin - Stores"])
async def admin_get_store_by_id(store_id: UUID, db: AsyncSession = Depends(get_session)):
    """Получить магазин по ID"""
    stores = await get_stores(db, include_deleted=True)
    for s in stores:
        if s.id == store_id:
            return s
    raise HTTPException(status_code=404, detail="Магазин не найден")


@router.delete("/admin/stores/{store_id}", response_model=StoreResponse, tags=["Admin - Stores"])
async def admin_delete_store(store_id: UUID, db: AsyncSession = Depends(get_session)):
    """Мягкое удаление магазина"""
    deleted = await delete_store(db, store_id)
    if deleted is None:
        raise HTTPException(status_code=404, detail="Магазин не найден")
    return deleted


# ============================================================
# ============ АДМИНКА: КАНАЛЫ ===============================
# ============================================================
@router.post("/admin/channels/", response_model=HotlineChannelResponse, status_code=status.HTTP_201_CREATED, tags=["Admin - Channels"])
async def admin_create_channel(channel: HotlineChannelCreate, db: AsyncSession = Depends(get_session)):
    """Создать новый канал (MAX, Сайт, Телефон)"""
    return await create_channel(db, channel)


@router.get("/admin/channels/", response_model=list[HotlineChannelResponse], tags=["Admin - Channels"])
async def admin_get_channels(
    skip: int = 0,
    limit: int = 100,
    store_id: Optional[UUID] = Query(None, description="Фильтр по ID магазина"),
    channel_type: Optional[str] = Query(None, description="Фильтр по типу канала (MAX/Сайт)"),
    include_deleted: bool = Query(False, description="Включать удаленные"),
    db: AsyncSession = Depends(get_session)
):
    """Список каналов с фильтрами"""
    return await get_channels(db, skip, limit, store_id, include_deleted, channel_type)


@router.get("/admin/channels/{channel_id}", response_model=HotlineChannelResponse, tags=["Admin - Channels"])
async def admin_get_channel_by_id(channel_id: UUID, db: AsyncSession = Depends(get_session)):
    """Получить канал по ID"""
    channels = await get_channels(db, include_deleted=True)
    for c in channels:
        if c.id == channel_id:
            return c
    raise HTTPException(status_code=404, detail="Канал не найден")


@router.delete("/admin/channels/{channel_id}", response_model=HotlineChannelResponse, tags=["Admin - Channels"])
async def admin_delete_channel(channel_id: UUID, db: AsyncSession = Depends(get_session)):
    """Мягкое удаление канала"""
    deleted = await delete_channel(db, channel_id)
    if deleted is None:
        raise HTTPException(status_code=404, detail="Канал не найден")
    return deleted


# ============================================================
# ============ АДМИНКА: ЖУРНАЛ ОБРАЩЕНИЙ =====================
# ============================================================
@router.post("/admin/journals/", response_model=HotlineJournalResponse, status_code=status.HTTP_201_CREATED, tags=["Admin - Journals"])
async def admin_create_journal(journal: HotlineJournalCreate, db: AsyncSession = Depends(get_session)):
    """Создать обращение (обычно создаётся ботом/сайтом, но можно и вручную)"""
    return await create_journal(db, journal)


@router.get("/admin/journals/", response_model=list[HotlineJournalResponse], tags=["Admin - Journals"])
async def admin_get_journals(
    skip: int = 0,
    limit: int = 100,
    include_deleted: bool = Query(False, description="Включать удаленные"),
    requester_type_id: Optional[UUID] = Query(None, description="Фильтр по типу заявителя"),
    request_type_id: Optional[UUID] = Query(None, description="Фильтр по типу обращения"),
    channel_id: Optional[UUID] = Query(None, description="Фильтр по каналу"),
    store_id: Optional[UUID] = Query(None, description="Фильтр по магазину"),
    status_filter: Optional[str] = Query(None, description="Статус: new (не решено), resolved (решено)"),
    date_from: Optional[datetime] = Query(None, description="Дата начала периода"),
    date_to: Optional[datetime] = Query(None, description="Дата окончания периода"),
    search: Optional[str] = Query(None, description="Поиск по тексту обращения"),
    db: AsyncSession = Depends(get_session)
):
    """
    Расширенный список обращений с множеством фильтров для админки.
    Поддерживает фильтрацию по магазину, каналу, типу заявителя, статусу и датам.
    """
    return await get_journals(
        db, skip, limit,
        include_deleted=include_deleted,
        requester_type_id=requester_type_id,
        request_type_id=request_type_id,
        channel_id=channel_id,
        store_id=store_id,
        status=status_filter,
        date_from=date_from,
        date_to=date_to,
        search=search
    )


@router.get("/admin/journals/{journal_id}", response_model=HotlineJournalResponse, tags=["Admin - Journals"])
async def admin_get_journal_by_id(journal_id: UUID, db: AsyncSession = Depends(get_session)):
    """Получить обращение по ID"""
    db_journal = await get_journal_by_id(db, journal_id)
    if db_journal is None:
        raise HTTPException(status_code=404, detail="Запись в журнале не найдена")
    return db_journal


@router.put("/admin/journals/{journal_id}", response_model=HotlineJournalResponse, tags=["Admin - Journals"])
async def admin_update_journal(
    journal_id: UUID,
    journal_update: HotlineJournalUpdate,
    db: AsyncSession = Depends(get_session)
):
    """Обновить обращение (принять решение, назначить администратора и т.д.)"""
    updated_journal = await update_journal(db, journal_id, journal_update)
    if updated_journal is None:
        raise HTTPException(status_code=404, detail="Запись в журнале не найдена")
    return updated_journal


@router.delete("/admin/journals/{journal_id}", response_model=HotlineJournalResponse, tags=["Admin - Journals"])
async def admin_delete_journal(journal_id: UUID, db: AsyncSession = Depends(get_session)):
    """Мягкое удаление обращения"""
    deleted_journal = await delete_journal(db, journal_id)
    if deleted_journal is None:
        raise HTTPException(status_code=404, detail="Запись в журнале не найдена")
    return deleted_journal


# ============================================================
# ============ БЫСТРЫЕ ДЕЙСТВИЯ С ОБРАЩЕНИЯМИ ================
# ============================================================
@router.post("/admin/journals/{journal_id}/resolve", response_model=HotlineJournalResponse, tags=["Admin - Journals"])
async def resolve_journal(
    journal_id: UUID,
    decision_info: str = Query(..., description="Текст принятого решения"),
    administrator: str = Query(..., description="ФИО администратора"),
    db: AsyncSession = Depends(get_session)
):
    """Быстрое принятие решения по обращению (устанавливает decision_date и decision_info)"""
    from datetime import datetime as dt
    update_data = HotlineJournalUpdate(
        decision_info=decision_info,
        administrator=administrator,
        decision_date=dt.utcnow()
    )
    updated = await update_journal(db, journal_id, update_data)
    if updated is None:
        raise HTTPException(status_code=404, detail="Обращение не найдено")
    return updated


@router.post("/admin/journals/{journal_id}/assign", response_model=HotlineJournalResponse, tags=["Admin - Journals"])
async def assign_journal(
    journal_id: UUID,
    administrator: str = Query(..., description="ФИО администратора для назначения"),
    db: AsyncSession = Depends(get_session)
):
    """Назначить администратора на обращение"""
    update_data = HotlineJournalUpdate(administrator=administrator)
    updated = await update_journal(db, journal_id, update_data)
    if updated is None:
        raise HTTPException(status_code=404, detail="Обращение не найдено")
    return updated