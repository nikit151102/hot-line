from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List
from uuid import UUID

# --- Базовые поля для Soft Delete ---
class SoftDeleteMixin(BaseModel):
    is_deleted: bool = False

# --- Магазины ---
class StoreBase(BaseModel):
    name: str
    address: Optional[str] = None

class StoreCreate(StoreBase): pass
class StoreResponse(StoreBase, SoftDeleteMixin):
    id: UUID
    class Config: from_attributes = True

# --- Каналы ---
class HotlineChannelBase(BaseModel):
    store_id: UUID
    channel_type: str
    name: str
    max_url: Optional[str] = None
    site_url: Optional[str] = None

class HotlineChannelCreate(HotlineChannelBase): pass
class HotlineChannelResponse(HotlineChannelBase, SoftDeleteMixin):
    id: UUID
    store: Optional[StoreResponse] = None
    class Config: from_attributes = True

# --- Типы обращений ---
class RequestTypeBase(BaseModel):
    name: str
    description: Optional[str] = None
    parent_id: Optional[UUID] = None

class RequestTypeCreate(RequestTypeBase): pass
class RequestTypeResponse(RequestTypeBase, SoftDeleteMixin):
    id: UUID
    class Config: from_attributes = True

# --- Журнал ---
class HotlineJournalBase(BaseModel):
    received_at: Optional[datetime] = None
    channel_id: Optional[UUID] = None
    message_content: str
    acceptance_info: Optional[str] = None
    decision_info: Optional[str] = None
    decision_date: Optional[datetime] = None
    administrator: Optional[str] = None
    request_type_id: Optional[UUID] = None

class HotlineJournalCreate(HotlineJournalBase): pass
class HotlineJournalUpdate(BaseModel):
    received_at: Optional[datetime] = None
    channel_id: Optional[UUID] = None
    message_content: Optional[str] = None
    acceptance_info: Optional[str] = None
    decision_info: Optional[str] = None
    decision_date: Optional[datetime] = None
    administrator: Optional[str] = None
    request_type_id: Optional[UUID] = None

class HotlineJournalResponse(HotlineJournalBase, SoftDeleteMixin):
    id: UUID
    channel: Optional[HotlineChannelResponse] = None
    request_type: Optional[RequestTypeResponse] = None
    class Config: from_attributes = True

# ==========================================
# --- СХЕМЫ ДЛЯ СТАТИСТИКИ И МЕТРИК ---
# ==========================================
class StatItem(BaseModel):
    label: str
    count: int

class TimelineItem(BaseModel):
    date: str  # Формат YYYY-MM-DD
    count: int

class HotlineStatsResponse(BaseModel):
    total_requests: int
    resolved_requests: int  # Где есть decision_date
    avg_resolution_hours: Optional[float] = None
    by_channel_type: List[StatItem]
    by_store: List[StatItem]
    by_request_type: List[StatItem]
    timeline_last_30_days: List[TimelineItem]


class StatItem(BaseModel):
    label: str
    count: int

class TimelineItem(BaseModel):
    date: str  # Формат YYYY-MM-DD
    count: int

class HourlyStatItem(BaseModel):
    hour: int  # 0-23
    count: int

class WeeklyStatItem(BaseModel):
    day_of_week: int  # 1 (Пн) - 7 (Вс)
    day_name: str
    count: int

class CrossSectionItem(BaseModel):
    category_1: str  # Например, Название магазина
    category_2: str  # Например, Тип канала (MAX/Сайт)
    count: int

class HotlineStatsResponse(BaseModel):
    # 1. Общие метрики (KPI)
    total_requests: int
    resolved_requests: int
    unresolved_requests: int
    resolution_rate_percent: float  # Процент решенных
    avg_resolution_hours: Optional[float] = None

    # 2. Временные ряды (для линейных графиков)
    timeline_daily: List[TimelineItem]       # Динамика по дням
    timeline_hourly: List[HourlyStatItem]    # Пиковые часы (для графиков смен)
    timeline_weekly: List[WeeklyStatItem]    # Загрузка по дням недели

    # 3. Категориальные разрезы (для круговых/столбчатых диаграмм)
    by_channel_type: List[StatItem]
    by_store: List[StatItem]
    by_request_type: List[StatItem]
    by_administrator: List[StatItem]         # Кто больше всех обрабатывает

    # 4. Кросс-аналитика (Матрицы / Heatmaps)
    store_vs_channel: List[CrossSectionItem] # Какой канал популярен в каком магазине
    type_vs_channel: List[CrossSectionItem]  # Какие жалобы чаще приходят с сайта, а какие из MAX