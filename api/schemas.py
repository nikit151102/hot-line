from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List
from uuid import UUID

# --- Магазины ---
class StoreBase(BaseModel):
    name: str
    address: Optional[str] = None

class StoreCreate(StoreBase): pass

class StoreResponse(StoreBase):
    id: UUID
    class Config: from_attributes = True

# --- Каналы ---
class HotlineChannelBase(BaseModel):
    store_id: UUID
    channel_type: str  # "MAX", "Сайт", "Телефон"
    name: str
    max_url: Optional[str] = None
    site_url: Optional[str] = None

class HotlineChannelCreate(HotlineChannelBase): pass

class HotlineChannelResponse(HotlineChannelBase):
    id: UUID
    store: Optional[StoreResponse] = None # Чтобы видеть название магазина при получении канала
    class Config: from_attributes = True

# --- Типы обращений (без изменений) ---
class RequestTypeBase(BaseModel):
    name: str
    description: Optional[str] = None
    parent_id: Optional[UUID] = None

class RequestTypeCreate(RequestTypeBase): pass

class RequestTypeResponse(RequestTypeBase):
    id: UUID
    class Config: from_attributes = True

# --- Журнал обращений ---
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

class HotlineJournalResponse(HotlineJournalBase):
    id: UUID
    channel: Optional[HotlineChannelResponse] = None
    request_type: Optional[RequestTypeResponse] = None
    class Config: from_attributes = True