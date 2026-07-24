from __future__ import annotations  # <-- ВАЖНО: Позволяет ссылаться на классы, объявленные ниже
from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List
from uuid import UUID


# ==========================================
# 1. БАЗОВЫЕ МИКСИНЫ
# ==========================================
class SoftDeleteMixin(BaseModel):
    is_deleted: bool = False


# ==========================================
# 2. ТИПЫ ЗАЯВИТЕЛЕЙ
# ==========================================
class RequesterTypeBase(BaseModel):
    name: str
    code: str  # 'client', 'employee', 'partner', 'anonymous'

class RequesterTypeCreate(RequesterTypeBase): pass

class RequesterTypeResponse(RequesterTypeBase, SoftDeleteMixin):
    id: UUID
    class Config: 
        from_attributes = True


# ==========================================
# 3. МАГАЗИНЫ И КАНАЛЫ (Добавлено, чтобы Journal мог на них ссылаться)
# ==========================================
class StoreBase(BaseModel):
    name: str
    address: Optional[str] = None

class StoreCreate(StoreBase): pass

class StoreResponse(StoreBase, SoftDeleteMixin):
    id: UUID
    class Config: 
        from_attributes = True


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
    class Config: 
        from_attributes = True


# ==========================================
# 4. ТИПЫ ОБРАЩЕНИЙ
# ==========================================
class RequestTypeBase(BaseModel):
    name: str
    description: Optional[str] = None
    parent_id: Optional[UUID] = None
    allowed_requester_ids: List[UUID] = []

class RequestTypeCreate(RequestTypeBase): pass

class RequestTypeUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    parent_id: Optional[UUID] = None
    allowed_requester_ids: Optional[List[UUID]] = None

class RequestTypeResponse(RequestTypeBase, SoftDeleteMixin):
    id: UUID
    allowed_requesters: List[RequesterTypeResponse] = []
    class Config: 
        from_attributes = True


# ==========================================
# 5. ЖУРНАЛ ОБРАЩЕНИЙ
# ==========================================
class HotlineJournalBase(BaseModel):
    received_at: Optional[datetime] = None
    channel_id: Optional[UUID] = None
    message_content: str
    acceptance_info: Optional[str] = None
    decision_info: Optional[str] = None
    decision_date: Optional[datetime] = None
    administrator: Optional[str] = None
    request_type_id: Optional[UUID] = None
    requester_type_id: Optional[UUID] = None 
    contact_info: Optional[str] = None       

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
    requester_type_id: Optional[UUID] = None
    contact_info: Optional[str] = None

class HotlineJournalResponse(HotlineJournalBase, SoftDeleteMixin):
    id: UUID
    # Теперь эти классы уже объявлены выше, ошибки не будет
    channel: Optional[HotlineChannelResponse] = None
    request_type: Optional[RequestTypeResponse] = None
    requester_type: Optional[RequesterTypeResponse] = None 
    class Config: 
        from_attributes = True


# ==========================================
# 6. СТАТИСТИКА И МЕТРИКИ (Убраны дубликаты, оставлена полная версия)
# ==========================================
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
    category_1: str  
    category_2: str  
    count: int

class HotlineStatsResponse(BaseModel):
    # 1. Общие метрики (KPI)
    total_requests: int
    resolved_requests: int
    unresolved_requests: int
    resolution_rate_percent: float  
    avg_resolution_hours: Optional[float] = None

    # 2. Временные ряды
    timeline_daily: List[TimelineItem]       
    timeline_hourly: List[HourlyStatItem]    
    timeline_weekly: List[WeeklyStatItem]    

    # 3. Категориальные разрезы
    by_channel_type: List[StatItem]
    by_store: List[StatItem]
    by_request_type: List[StatItem]
    by_administrator: List[StatItem]         

    # 4. Кросс-аналитика (Матрицы)
    store_vs_channel: List[CrossSectionItem] 
    type_vs_channel: List[CrossSectionItem]  

    class Config:
        from_attributes = True