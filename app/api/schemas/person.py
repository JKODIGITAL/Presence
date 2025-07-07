"""
Pydantic schemas for Person API
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class PersonBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Nome da pessoa")
    department: Optional[str] = Field(None, max_length=100, description="Departamento")
    email: Optional[str] = Field(None, max_length=255, description="Email")
    phone: Optional[str] = Field(None, max_length=20, description="Telefone")
    tags: Optional[str] = Field(None, description="Tags em formato JSON")


class PersonCreate(PersonBase):
    pass


class PersonUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    department: Optional[str] = Field(None, max_length=100)
    email: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=20)
    status: Optional[str] = Field(None, description="Status da pessoa")
    detection_enabled: Optional[bool] = Field(None, description="Se a detecção está habilitada")
    tags: Optional[str] = Field(None, description="Tags em formato JSON")


class PersonResponse(PersonBase):
    id: str
    is_unknown: bool
    thumbnail_path: Optional[str]
    first_seen: datetime
    last_seen: datetime
    recognition_count: int
    confidence: float
    status: str
    detection_enabled: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
    
    @classmethod
    def from_db_model(cls, db_model):
        """Método seguro para criar instância a partir de modelo do banco"""
        try:
            return cls.from_orm(db_model)
        except Exception:
            # Fallback manual para compatibilidade
            return cls(
                id=db_model.id,
                name=db_model.name,
                department=db_model.department,
                email=db_model.email,
                phone=db_model.phone,
                tags=db_model.tags,
                is_unknown=db_model.is_unknown,
                thumbnail_path=db_model.thumbnail_path,
                first_seen=db_model.first_seen,
                last_seen=db_model.last_seen,
                recognition_count=db_model.recognition_count,
                confidence=db_model.confidence,
                status=db_model.status,
                detection_enabled=getattr(db_model, 'detection_enabled', True),
                created_at=db_model.created_at,
                updated_at=db_model.updated_at
            )


class PersonList(BaseModel):
    people: List[PersonResponse]
    total: int
    page: int = 1
    per_page: int = 50


class PersonStats(BaseModel):
    total_people: int
    active_people: int
    unknown_people: int
    recent_recognitions: int


class PersonRegister(BaseModel):
    """Schema para registrar uma pessoa com imagem"""
    name: str = Field(..., min_length=1, max_length=100)
    department: Optional[str] = Field(None, max_length=100)
    email: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=20)
    tags: Optional[str] = Field(None)