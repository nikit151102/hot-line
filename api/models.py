from sqlalchemy import Column, String, ForeignKey, DateTime, Text, Integer, Boolean, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import uuid

Base = declarative_base()

class HotlineChannel(Base):
    __tablename__ = "hotline_channels"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False, unique=True)
    max_url = Column(String, nullable=True)  
    site_url = Column(String, nullable=True)  

class RequestType(Base):
    __tablename__ = "request_types"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)  # unique=True убран для поддержки иерархии
    description = Column(Text, nullable=True)
    
    # САМОРЕФЕРЕНТНАЯ СВЯЗЬ ДЛЯ ПОДТИПОВ
    parent_id = Column(UUID(as_uuid=True), ForeignKey("request_types.id"), nullable=True)
    
    # Связи
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
    
    channel = relationship("HotlineChannel")
    request_type = relationship("RequestType")