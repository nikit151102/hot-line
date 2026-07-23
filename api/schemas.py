from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List
from uuid import UUID

# --- Каналы ---
class HotlineChannelBase(BaseModel):
    name: str
    max_url: Optional[str] = None
    site_url: Optional[str] = None

class HotlineChannelCreate(HotlineChannelBase): pass
class HotlineChannelResponse(HotlineChannelBase):
    id: UUID
    class Config: from_attributes = True

# --- Типы обращений ---
class RequestTypeBase(BaseModel):
    name: str
    description: Optional[str] = None
    parent_id: Optional[UUID] = None  # <-- НОВОЕ ПОЛЕ

class RequestTypeCreate(RequestTypeBase): pass

class RequestTypeResponse(RequestTypeBase):
    id: UUID
    # Можно раскомментировать, если нужно сразу отдавать дерево, 
    # но для бота проще делать два отдельных запроса (см. ниже)
    # children: List['RequestTypeResponse'] = [] 
    
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