from sqlalchemy import Column, String, ForeignKey, DateTime, Text, Integer, Boolean, Table
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import uuid

Base = declarative_base()

# Промежуточная таблица для связи многие-ко-многим (Тип обращения <-> Тип заявителя)
request_type_allowed_requesters = Table(
    'request_type_allowed_requesters', Base.metadata,
    Column('request_type_id', UUID(as_uuid=True), ForeignKey('request_types.id'), primary_key=True),
    Column('requester_type_id', UUID(as_uuid=True), ForeignKey('requester_types.id'), primary_key=True)
)

class RequesterType(Base):
    """Справочник типов заявителей (Клиент, Сотрудник, Партнер и т.д.)"""
    __tablename__ = "requester_types"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    code = Column(String, nullable=False, unique=True)
    is_deleted = Column(Boolean, default=False, nullable=False)
    
    request_types = relationship("RequestType", secondary=request_type_allowed_requesters, back_populates="allowed_requesters")
    journals = relationship("HotlineJournal", back_populates="requester_type") # <-- Добавлено для стабильности


class Store(Base):
    __tablename__ = "stores"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    address = Column(String, nullable=True)
    is_deleted = Column(Boolean, default=False, nullable=False)
    
    channels = relationship("HotlineChannel", back_populates="store")


class HotlineChannel(Base):
    __tablename__ = "hotline_channels"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(UUID(as_uuid=True), ForeignKey("stores.id"), nullable=False)
    channel_type = Column(String, nullable=False)
    name = Column(String, nullable=False)
    max_url = Column(String, nullable=True)
    site_url = Column(String, nullable=True)
    is_deleted = Column(Boolean, default=False, nullable=False)
    
    store = relationship("Store", back_populates="channels")
    journals = relationship("HotlineJournal", back_populates="channel")


class RequestType(Base):
    __tablename__ = "request_types"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    parent_id = Column(UUID(as_uuid=True), ForeignKey("request_types.id"), nullable=True)
    is_deleted = Column(Boolean, default=False, nullable=False)
    
    parent = relationship("RequestType", remote_side=[id], backref="children")
    allowed_requesters = relationship("RequesterType", secondary=request_type_allowed_requesters, back_populates="request_types")
    journals = relationship("HotlineJournal", back_populates="request_type") # <-- Добавлено для стабильности


class HotlineJournal(Base):
    __tablename__ = "hotline_journal"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    received_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    channel_id = Column(UUID(as_uuid=True), ForeignKey("hotline_channels.id"), nullable=True)
    message_content = Column(Text, nullable=False)
    acceptance_info = Column(Text, nullable=True)
    decision_info = Column(Text, nullable=True)
    decision_date = Column(DateTime(timezone=True), nullable=True)
    administrator = Column(String, nullable=True)
    
    # <-- ВАЖНО: ЭТОЙ СТРОКИ НЕ БЫЛО В ВАШЕМ КОДЕ, ИЗ-ЗА ЧЕГО БЫЛА ОШИБКА
    request_type_id = Column(UUID(as_uuid=True), ForeignKey("request_types.id"), nullable=True)
    
    requester_type_id = Column(UUID(as_uuid=True), ForeignKey("requester_types.id"), nullable=True)
    contact_info = Column(String, nullable=True)
    is_deleted = Column(Boolean, default=False, nullable=False)
    
    # Связи с явным указанием back_populates
    channel = relationship("HotlineChannel", back_populates="journals")
    request_type = relationship("RequestType", back_populates="journals")       # <-- Исправлено
    requester_type = relationship("RequesterType", back_populates="journals")   # <-- Исправлено