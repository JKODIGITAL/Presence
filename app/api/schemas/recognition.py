"""
Pydantic schemas for Recognition API
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class BoundingBox(BaseModel):
    x: int = Field(..., ge=0)
    y: int = Field(..., ge=0)
    width: int = Field(..., gt=0)
    height: int = Field(..., gt=0)


class FaceDetection(BaseModel):
    bbox: BoundingBox
    confidence: float = Field(..., ge=0.0, le=1.0)
    landmarks: Optional[List[List[int]]] = None


class RecognitionResult(BaseModel):
    person_id: Optional[str]
    person_name: Optional[str]
    confidence: float = Field(..., ge=0.0, le=1.0)
    is_unknown: bool
    bbox: BoundingBox
    landmarks: Optional[List[List[int]]] = None


class ProcessFrameRequest(BaseModel):
    camera_id: str = Field(..., description="ID da câmera")
    timestamp: Optional[datetime] = None
    save_frame: bool = Field(default=False, description="Salvar frame processado")


class ProcessFrameResponse(BaseModel):
    camera_id: str
    timestamp: datetime
    faces_detected: int
    recognitions: List[RecognitionResult]
    processed: bool
    frame_path: Optional[str] = None
    error: Optional[str] = None


class RecognitionLogResponse(BaseModel):
    id: int
    person_id: str
    person_name: Optional[str]
    camera_id: str
    camera_name: Optional[str]
    confidence: float
    bounding_box: Optional[str]
    frame_path: Optional[str]
    timestamp: datetime
    is_unknown: bool

    class Config:
        orm_mode = True


class RecognitionLogList(BaseModel):
    logs: List[RecognitionLogResponse]
    total: int
    page: int = 1
    per_page: int = 50


class RecognitionStats(BaseModel):
    total_recognitions_today: int
    total_recognitions_week: int
    total_recognitions_month: int
    unique_people_today: int
    unknown_faces_today: int
    avg_confidence: float


class StreamStatus(BaseModel):
    camera_id: str
    is_streaming: bool
    fps_current: float
    frames_processed: int
    last_frame_at: Optional[datetime]
    error: Optional[str] = None