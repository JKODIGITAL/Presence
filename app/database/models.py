"""
Database models for Presence
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Text, LargeBinary, ForeignKey, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from .database import Base


def get_current_timestamp():
    """Get current timestamp"""
    return datetime.now()


class Person(Base):
    """Modelo para pessoas cadastradas"""
    __tablename__ = "people"
    
    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    department = Column(String, nullable=True)
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    is_unknown = Column(Boolean, default=False)
    face_encoding = Column(LargeBinary, nullable=True)
    thumbnail_path = Column(String, nullable=True)
    first_seen = Column(DateTime, default=func.now())
    last_seen = Column(DateTime, default=func.now())
    recognition_count = Column(Integer, default=0)
    confidence = Column(Float, default=0.0)
    status = Column(String, default="active")
    detection_enabled = Column(Boolean, default=True)  # Controla se a pessoa deve ser detectada
    tags = Column(Text, nullable=True)  # JSON string
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class Camera(Base):
    """Modelo para câmeras"""
    __tablename__ = "cameras"
    
    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    url = Column(String, nullable=False)
    type = Column(String, default="ip")
    status = Column(String, default="inactive")
    fps = Column(Integer, default=30)
    resolution_width = Column(Integer, default=1280)
    resolution_height = Column(Integer, default=720)
    fps_limit = Column(Integer, default=5)
    location = Column(String, nullable=True)
    description = Column(String, nullable=True)
    config = Column(Text, nullable=True)  # JSON string para configurações adicionais
    last_frame_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    def __repr__(self):
        return f"<Camera(id='{self.id}', name='{self.name}', status='{self.status}')>"


class RecognitionLog(Base):
    """Modelo para logs de reconhecimento"""
    __tablename__ = "recognition_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    person_id = Column(String, nullable=True)  # Permitir NULL para faces desconhecidas
    camera_id = Column(String, nullable=False)
    confidence = Column(Float, nullable=False)
    bounding_box = Column(Text, nullable=True)  # JSON string [x, y, w, h]
    frame_path = Column(String, nullable=True)
    timestamp = Column(DateTime, default=func.now())
    is_unknown = Column(Boolean, default=False)


class SystemLog(Base):
    """Modelo para logs do sistema"""
    __tablename__ = "system_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    level = Column(String, nullable=False)  # INFO, WARNING, ERROR
    module = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    details = Column(Text, nullable=True)  # JSON string
    timestamp = Column(DateTime, default=func.now())


class Settings(Base):
    """Modelo para configurações do sistema"""
    __tablename__ = "settings"
    
    key = Column(String, primary_key=True)
    value = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class UnknownPerson(Base):
    """Modelo para pessoas desconhecidas detectadas automaticamente"""
    __tablename__ = "unknown_people"
    
    id = Column(String, primary_key=True, index=True)  # unknown_xxxxxxxx
    image_data = Column(Text, nullable=False)  # Base64 da melhor foto
    embedding_data = Column(LargeBinary, nullable=False)  # Embedding binário
    bbox_data = Column(Text, nullable=True)  # JSON com bbox [x1, y1, x2, y2]
    confidence = Column(Float, nullable=False)  # Confiança da detecção
    quality_score = Column(Float, nullable=False)  # Pontuação de qualidade (0-1)
    camera_id = Column(String, nullable=False)  # ID da câmera que detectou
    detected_at = Column(DateTime, default=func.now())  # Quando foi detectado
    
    # Status de processamento
    status = Column(String, default="pending")  # pending, identified, ignored
    
    # Se foi identificado manualmente
    identified_as_person_id = Column(String, nullable=True)  # Link para Person.id se identificado
    identified_at = Column(DateTime, nullable=True)  # Quando foi identificado
    identified_by = Column(String, nullable=True)  # Quem identificou (usuário)
    
    # Metadados adicionais
    frame_count = Column(Integer, default=1)  # Quantos frames detectaram a pessoa
    presence_duration = Column(Float, default=0.0)  # Tempo que ficou visível (segundos)
    additional_data = Column(JSON, nullable=True)  # Dados extras (localização na imagem, etc.)
    
    # Timestamps
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    def __repr__(self):
        return f"<UnknownPerson(id='{self.id}', camera='{self.camera_id}', status='{self.status}')>"