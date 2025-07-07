from sqlalchemy import Column, Integer, String, DateTime, Float, Boolean, ForeignKey, LargeBinary, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database.database import Base
import uuid

class Person(Base):
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
    tags = Column(Text, nullable=True)  # JSON string
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    # Relacionamentos
    recognition_logs = relationship("RecognitionLog", back_populates="person")

class Camera(Base):
    __tablename__ = "cameras"
    
    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    url = Column(String, nullable=False)
    type = Column(String, default="ip")  # ip, webcam
    status = Column(String, default="inactive")  # active, inactive, error
    fps = Column(Integer, default=30)
    resolution_width = Column(Integer, default=1280)
    resolution_height = Column(Integer, default=720)
    fps_limit = Column(Integer, default=5)
    location = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    last_frame_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    # Relacionamentos
    recognition_logs = relationship("RecognitionLog", back_populates="camera")

class RecognitionLog(Base):
    __tablename__ = "recognition_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    person_id = Column(String, nullable=True)  # Permitir NULL para faces desconhecidas
    camera_id = Column(String, nullable=False)
    confidence = Column(Float, nullable=False)
    bounding_box = Column(Text, nullable=True)  # JSON string [x, y, w, h]
    frame_path = Column(String, nullable=True)
    timestamp = Column(DateTime, default=func.now())
    is_unknown = Column(Boolean, default=False)
    
    # Relacionamentos
    person = relationship("Person", back_populates="recognition_logs")
    camera = relationship("Camera", back_populates="recognition_logs")
