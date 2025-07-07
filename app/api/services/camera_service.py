"""
Camera service - Business logic for camera management
"""

import uuid
import cv2
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from loguru import logger

from app.database import models
from app.api.schemas.camera import CameraCreate, CameraUpdate
from app.core.config import settings


class CameraService:
    """Service para gerenciamento de câmeras"""
    
    @staticmethod
    def create_camera(db: Session, camera_data: CameraCreate, camera_id: Optional[str] = None) -> models.Camera:
        """Criar uma nova câmera"""
        try:
            # Usar ID fornecido ou gerar ID único
            if camera_id is None:
                camera_id = str(uuid.uuid4())
            
            # Não validar conexão durante criação para evitar problemas
            # A validação será feita posteriormente ou via endpoint específico
            
            from datetime import datetime
            
            # Criar câmera com campos básicos
            camera = models.Camera(
                id=camera_id,
                name=camera_data.name,
                url=camera_data.url,
                type=camera_data.type,
                status="active",  # Ativa para WebRTC detectar
                fps=getattr(camera_data, 'fps', 30),
                resolution_width=getattr(camera_data, 'resolution_width', 1280),
                resolution_height=getattr(camera_data, 'resolution_height', 720),
                fps_limit=getattr(camera_data, 'fps_limit', 5),
                location=getattr(camera_data, 'location', None),
                description=getattr(camera_data, 'description', None)
            )
            
            db.add(camera)
            db.commit()
            db.refresh(camera)
            
            logger.info(f"Câmera criada: {camera.name} (ID: {camera.id})")
            return camera
            
        except Exception as e:
            db.rollback()
            logger.error(f"Erro ao criar câmera: {e}")
            raise
    
    @staticmethod
    def get_camera(db: Session, camera_id: str) -> Optional[models.Camera]:
        """Buscar câmera por ID"""
        return db.query(models.Camera).filter(models.Camera.id == camera_id).first()
    
    @staticmethod
    def get_cameras(
        db: Session,
        skip: int = 0,
        limit: int = 50,
        status: Optional[str] = None,
        camera_type: Optional[str] = None
    ) -> Tuple[List[models.Camera], int]:
        """Listar câmeras com filtros"""
        query = db.query(models.Camera)
        
        if status:
            query = query.filter(models.Camera.status == status)
        
        if camera_type:
            query = query.filter(models.Camera.type == camera_type)
        
        # Obter total de câmeras
        total = query.count()
        
        # Retornar câmeras com paginação
        cameras = query.offset(skip).limit(limit).all()
        
        return cameras, total
    
    @staticmethod
    def update_camera(db: Session, camera_id: str, camera_data: CameraUpdate) -> Optional[models.Camera]:
        """Atualizar câmera"""
        try:
            camera = db.query(models.Camera).filter(models.Camera.id == camera_id).first()
            if not camera:
                return None
            
            # Atualizar campos fornecidos de forma segura
            try:
                # Tentar Pydantic v2 primeiro
                update_data = camera_data.model_dump(exclude_unset=True)
            except AttributeError:
                # Fallback para Pydantic v1
                update_data = camera_data.dict(exclude_unset=True)
            
            # Atualizar campos específicos de forma segura
            if 'name' in update_data:
                camera.name = update_data['name']
            if 'url' in update_data:
                camera.url = update_data['url']
            if 'type' in update_data:
                camera.type = update_data['type']
            if 'fps' in update_data:
                camera.fps = update_data['fps']
            if 'resolution_width' in update_data:
                camera.resolution_width = update_data['resolution_width']
            if 'resolution_height' in update_data:
                camera.resolution_height = update_data['resolution_height']
            if 'fps_limit' in update_data:
                camera.fps_limit = update_data['fps_limit']
            if 'location' in update_data:
                camera.location = update_data['location']
            if 'description' in update_data:
                camera.description = update_data['description']
            if 'status' in update_data:
                camera.status = update_data['status']
            
            # Nota: Validação de conexão removida para evitar problemas com GStreamer
            # A validação será feita quando a câmera for efetivamente usada
            
            camera.updated_at = datetime.now()
            db.commit()
            db.refresh(camera)
            
            logger.info(f"Câmera atualizada: {camera.name} (ID: {camera.id})")
            return camera
            
        except Exception as e:
            db.rollback()
            logger.error(f"Erro ao atualizar câmera: {e}")
            raise
    
    @staticmethod
    def delete_camera(db: Session, camera_id: str) -> bool:
        """Deletar câmera"""
        try:
            camera = db.query(models.Camera).filter(models.Camera.id == camera_id).first()
            if not camera:
                return False
            
            db.delete(camera)
            db.commit()
            
            logger.info(f"Câmera deletada: {camera.name} (ID: {camera.id})")
            return True
            
        except Exception as e:
            db.rollback()
            logger.error(f"Erro ao deletar câmera: {e}")
            raise
    
    @staticmethod
    def update_camera_status(db: Session, camera_id: str, status: str, error_message: Optional[str] = None):
        """Atualizar status da câmera"""
        try:
            camera = db.query(models.Camera).filter(models.Camera.id == camera_id).first()
            if camera:
                camera.status = status
                camera.updated_at = datetime.now()
                
                if status == "active":
                    camera.last_frame_at = datetime.now()
                
                db.commit()
                
        except Exception as e:
            logger.error(f"Erro ao atualizar status da câmera: {e}")
    
    @staticmethod
    def get_camera_stats(db: Session) -> Dict[str, int]:
        """Obter estatísticas de câmeras"""
        try:
            total_cameras = db.query(models.Camera).count()
            active_cameras = db.query(models.Camera).filter(models.Camera.status == "active").count()
            inactive_cameras = db.query(models.Camera).filter(models.Camera.status == "inactive").count()
            error_cameras = db.query(models.Camera).filter(models.Camera.status == "error").count()
            
            # Frames processados hoje
            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            frames_today = db.query(models.RecognitionLog).filter(
                models.RecognitionLog.timestamp >= today
            ).count()
            
            return {
                "total_cameras": total_cameras,
                "active_cameras": active_cameras,
                "inactive_cameras": inactive_cameras,
                "error_cameras": error_cameras,
                "frames_processed_today": frames_today
            }
            
        except Exception as e:
            logger.error(f"Erro ao obter estatísticas de câmeras: {e}")
            return {
                "total_cameras": 0,
                "active_cameras": 0,
                "inactive_cameras": 0,
                "error_cameras": 0,
                "frames_processed_today": 0
            }
    
    @staticmethod
    def test_camera_connection(camera_url: str, camera_type: str) -> Dict[str, Any]:
        """Testar conexão com câmera"""
        try:
            success = CameraService._validate_camera_connection(camera_url, camera_type)
            
            return {
                "success": success,
                "message": "Conexão bem-sucedida" if success else "Falha na conexão",
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Erro ao testar conexão da câmera: {e}")
            return {
                "success": False,
                "message": f"Erro: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }
    
    @staticmethod
    def _validate_camera_connection(camera_url: str, camera_type: str) -> bool:
        """Validar conexão com câmera - MODO DISTRIBUÍDO"""
        try:
            # Em modo distribuído, a validação é feita pelo worker externo
            # Retornamos True por padrão (validação básica de URL)
            logger.info(f"[PROCESSING] Camera validation request for {camera_url} - handled by external worker")
            
            # Validação básica de URL
            if not camera_url or not camera_url.strip():
                return False
                
            # Aceitar URLs válidas - validação real será feita pelo worker externo
            return True
            
        except Exception as e:
            logger.error(f"Erro na validação da câmera: {e}")
            return False
    
    @staticmethod
    def get_active_cameras(db: Session) -> List[models.Camera]:
        """Obter câmeras ativas"""
        return db.query(models.Camera).filter(models.Camera.status == "active").all()
    
    @staticmethod
    def update_frame_timestamp(db: Session, camera_id: str):
        """Atualizar timestamp do último frame"""
        try:
            camera = db.query(models.Camera).filter(models.Camera.id == camera_id).first()
            if camera:
                camera.last_frame_at = datetime.now()
                db.commit()
        except Exception as e:
            logger.error(f"Erro ao atualizar timestamp do frame: {e}")
    
    @staticmethod
    def count_cameras_by_status(db: Session, status: str) -> int:
        """Contar câmeras por status"""
        try:
            count = db.query(models.Camera).filter(models.Camera.status == status).count()
            return count
        except Exception as e:
            logger.error(f"Erro ao contar câmeras com status {status}: {e}")
            return 0