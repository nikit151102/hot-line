from sqlalchemy import Column, String, ForeignKey, DateTime, Text, Integer, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import uuid

Base = declarative_base()

class Store(Base):
    __tablename__ = "stores"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    address = Column(String, nullable=True)
    is_deleted = Column(Boolean, default=False, nullable=False) # <--- НОВОЕ
    
    channels = relationship("HotlineChannel", back_populates="store")

class HotlineChannel(Base):
    __tablename__ = "hotline_channels"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(UUID(as_uuid=True), ForeignKey("stores.id"), nullable=False)
    channel_type = Column(String, nullable=False)  # "MAX", "Сайт", "Телефон"
    name = Column(String, nullable=False)
    max_url = Column(String, nullable=True)
    site_url = Column(String, nullable=True)
    is_deleted = Column(Boolean, default=False, nullable=False) # <--- НОВОЕ
    
    store = relationship("Store", back_populates="channels")
    journals = relationship("HotlineJournal", back_populates="channel")

class RequestType(Base):
    __tablename__ = "request_types"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    parent_id = Column(UUID(as_uuid=True), ForeignKey("request_types.id"), nullable=True)
    is_deleted = Column(Boolean, default=False, nullable=False) # <--- НОВОЕ
    
    parent = relationship("RequestType", remote_side=[id], backref="children")

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
    request_type_id = Column(UUID(as_uuid=True), ForeignKey("request_types.id"), nullable=True)
    is_deleted = Column(Boolean, default=False, nullable=False) # <--- НОВОЕ
    
    channel = relationship("HotlineChannel", back_populates="journals")
    request_type = relationship("RequestType")