"""
Pydantic schemas for Camera API
"""

from typing import List, Optional, Any, Dict
from datetime import datetime
from pydantic import BaseModel, Field, validator
from app.database.models import Camera

# Verificar versão do Pydantic para compatibilidade
try:
    import pydantic
    pydantic_version = pydantic.VERSION
    if pydantic_version.startswith('1.'):
        from pydantic import BaseModel, Field, validator
        PYDANTIC_V1 = True
    else:
        from pydantic import BaseModel, Field, validator
        PYDANTIC_V1 = False
except ImportError:
    from pydantic import BaseModel, Field, validator
    PYDANTIC_V1 = False


class CameraBase(BaseModel):
    """Modelo base para câmeras"""
    name: str
    url: str
    type: str = "ip"
    fps: int = 30
    resolution_width: int = 1280
    resolution_height: int = 720
    fps_limit: int = 5
    location: Optional[str] = None
    description: Optional[str] = None


class CameraCreate(CameraBase):
    """Modelo para criação de câmeras"""
    username: Optional[str] = None
    password: Optional[str] = None


class CameraUpdate(BaseModel):
    """Modelo para atualização de câmeras"""
    name: Optional[str] = None
    url: Optional[str] = None
    type: Optional[str] = None
    fps: Optional[int] = None
    resolution_width: Optional[int] = None
    resolution_height: Optional[int] = None
    fps_limit: Optional[int] = None
    location: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    ip_address: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None
    stream_path: Optional[str] = None
    rtsp_transport: Optional[str] = None
    connection_timeout: Optional[int] = None
    reconnect_attempts: Optional[int] = None
    is_enabled: Optional[bool] = None
    config: Optional[Any] = None


class CameraResponse(BaseModel):
    """Modelo para resposta de câmeras com informações completas"""
    id: str
    name: str
    url: str
    type: str = "ip"
    status: str
    fps: int = 30
    resolution_width: int = 1280
    resolution_height: int = 720
    fps_limit: int = 5
    location: Optional[str] = None
    description: Optional[str] = None
    last_frame_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    config: Optional[Any] = None
    
    # Campos adicionais que podem não existir no banco
    ip_address: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None
    stream_path: Optional[str] = None
    connection_quality: Optional[float] = None
    last_connection_test: Optional[datetime] = None
    connection_test_result: Optional[str] = None
    codec: Optional[str] = None
    actual_fps: Optional[float] = None
    latency_ms: Optional[int] = None
    packet_loss_percent: Optional[float] = None
    bandwidth_mbps: Optional[float] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    firmware_version: Optional[str] = None
    has_ptz: Optional[bool] = None
    has_audio: Optional[bool] = None
    has_recording: Optional[bool] = None
    supports_onvif: Optional[bool] = None
    rtsp_transport: Optional[str] = None
    connection_timeout: Optional[int] = None
    reconnect_attempts: Optional[int] = None
    is_enabled: Optional[bool] = None
    auto_reconnect: Optional[bool] = None
    last_error: Optional[str] = None
    error_count: Optional[int] = None
    
    # Campo auxiliar para permitir qualquer campo adicional 
    additional_fields: Optional[Dict[str, Any]] = Field(default_factory=dict, alias="__extra__")
    
    @classmethod
    def from_db_model(cls, camera: Camera):
        """Converter modelo do banco para modelo de resposta"""
        try:
            camera_dict = {
                "id": camera.id,
                "name": camera.name,
                "url": camera.url,
                "type": camera.type or "ip",
                "status": camera.status or "inactive",
                "fps": camera.fps or 30,
                "resolution_width": camera.resolution_width or 1280,
                "resolution_height": camera.resolution_height or 720,
                "fps_limit": camera.fps_limit or 5,
                "location": camera.location,
                "description": camera.description,
                "config": camera.config,
                "last_frame_at": camera.last_frame_at,
                "created_at": camera.created_at,
                "updated_at": camera.updated_at
            }
            
            # Adicionar campos opcionais se existirem no modelo do banco
            optional_fields = [
                'ip_address', 'port', 'username', 'password', 'stream_path',
                'connection_quality', 'last_connection_test', 'connection_test_result',
                'codec', 'actual_fps', 'latency_ms', 'packet_loss_percent',
                'bandwidth_mbps', 'manufacturer', 'model', 'firmware_version',
                'has_ptz', 'has_audio', 'has_recording', 'supports_onvif',
                'rtsp_transport', 'connection_timeout', 'reconnect_attempts',
                'is_enabled', 'auto_reconnect', 'last_error', 'error_count'
            ]
            
            for field in optional_fields:
                if hasattr(camera, field):
                    camera_dict[field] = getattr(camera, field)
            
            # Pydantic v1 usa parse_obj, detectar versão dinamicamente
            if hasattr(cls, 'model_validate'):
                return cls.model_validate(camera_dict)
            else:
                return cls.parse_obj(camera_dict)
                
        except Exception as e:
            # Fallback para criação manual se a validação falhar
            from loguru import logger
            logger.warning(f"Fallback para criação manual de CameraResponse para câmera {camera.id}: {e}")
            
            # Criar resposta com campos mínimos necessários
            response = cls(
                id=camera.id,
                name=camera.name,
                url=camera.url,
                type=camera.type or "ip",
                status=camera.status or "inactive",
                fps=camera.fps or 30,
                resolution_width=camera.resolution_width or 1280,
                resolution_height=camera.resolution_height or 720,
                fps_limit=camera.fps_limit or 5,
                location=camera.location,
                description=camera.description,
                config=camera.config,
                last_frame_at=camera.last_frame_at,
                created_at=camera.created_at,
                updated_at=camera.updated_at
            )
            return response
    
    class Config:
        """Configuração do modelo Pydantic"""
        from_attributes = True
        orm_mode = True
        extra = "allow"


class CameraList(BaseModel):
    """Lista de câmeras com informações de paginação"""
    cameras: List[CameraResponse]
    total: int
    active: int
    inactive: int
    error: int = 0


class CameraStats(BaseModel):
    total_cameras: int
    active_cameras: int
    inactive_cameras: int
    error_cameras: int
    frames_processed_today: int


class CameraStatus(BaseModel):
    camera_id: str
    status: str = Field(..., description="Status da câmera no banco")
    is_running: bool = Field(..., description="Se a câmera está rodando no worker")
    last_activity: Optional[str] = Field(None, description="Última atividade da câmera")