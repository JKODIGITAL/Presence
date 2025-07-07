"""
Unknown Detection Configuration API Endpoints
Endpoints para configurar as regras de detecção de desconhecidos
"""

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import Dict, Any
try:
    from pydantic.v1 import BaseModel
except ImportError:
    from pydantic import BaseModel
from loguru import logger

from app.database.database import get_db_dependency
from app.core.unknown_detection_config import unknown_detection_manager


router = APIRouter()


# Simplificar schemas para evitar problemas de compatibilidade
class FaceQualityRulesUpdate(BaseModel):
    min_face_width: int = 100
    min_face_height: int = 100
    min_face_area_ratio: float = 0.03
    min_detection_confidence: float = 0.85
    max_similarity_threshold: float = 0.35
    max_face_angle: float = 25.0
    min_brightness: float = 60.0
    max_brightness: float = 180.0
    min_sharpness: float = 120.0

class TemporalRulesUpdate(BaseModel):
    min_presence_duration: float = 3.0
    min_frame_count: int = 15
    cooldown_period: float = 60.0
    face_tracking_timeout: float = 5.0
    max_detection_attempts: int = 3

class UnknownDetectionConfigUpdate(BaseModel):
    face_quality_rules: FaceQualityRulesUpdate
    temporal_rules: TemporalRulesUpdate
    auto_save_enabled: bool = True
    auto_process_enabled: bool = True


@router.get("/config")
async def get_unknown_detection_config():
    """Obter configuração atual de detecção de desconhecidos"""
    try:
        config = unknown_detection_manager.get_config()
        return {
            "face_quality_rules": {
                "min_face_width": config.face_quality.min_face_width,
                "min_face_height": config.face_quality.min_face_height,
                "min_face_area_ratio": config.face_quality.min_face_area_ratio,
                "min_detection_confidence": config.face_quality.min_detection_confidence,
                "max_similarity_threshold": config.face_quality.max_similarity_threshold,
                "max_face_angle": config.face_quality.max_face_angle,
                "min_brightness": config.face_quality.min_brightness,
                "max_brightness": config.face_quality.max_brightness,
                "min_sharpness": config.face_quality.min_sharpness,
            },
            "temporal_rules": {
                "min_presence_duration": config.temporal.min_presence_duration,
                "min_frame_count": config.temporal.min_frame_count,
                "cooldown_period": config.temporal.cooldown_period,
                "face_tracking_timeout": config.temporal.face_tracking_timeout,
                "max_detection_attempts": getattr(config.temporal, 'max_detection_attempts', 3),
            },
            "system_settings": {
                "unknown_threshold": config.unknown_threshold,
                "max_unknowns_per_session": config.max_unknowns_per_session,
                "auto_cleanup_days": config.auto_cleanup_days,
                "unknown_images_dir": config.unknown_images_dir,
            }
        }
    except Exception as e:
        logger.error(f"Erro ao obter configuração de detecção de desconhecidos: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/config")
async def update_unknown_detection_config(config_update: UnknownDetectionConfigUpdate):
    """Atualizar configuração de detecção de desconhecidos"""
    try:
        # Obter configuração atual
        current_config = unknown_detection_manager.get_config()
        
        # Atualizar regras de qualidade facial (Pydantic v1 compatible)
        if hasattr(config_update.face_quality_rules, 'dict'):
            face_quality_dict = config_update.face_quality_rules.dict()
        else:
            face_quality_dict = config_update.face_quality_rules.__dict__
        
        for key, value in face_quality_dict.items():
            if hasattr(current_config.face_quality, key):
                setattr(current_config.face_quality, key, value)
        
        # Atualizar regras temporais (Pydantic v1 compatible)
        if hasattr(config_update.temporal_rules, 'dict'):
            temporal_dict = config_update.temporal_rules.dict()
        else:
            temporal_dict = config_update.temporal_rules.__dict__
            
        for key, value in temporal_dict.items():
            if hasattr(current_config.temporal, key):
                setattr(current_config.temporal, key, value)
        
        # Salvar configuração
        success = unknown_detection_manager.save_config(current_config)
        
        if success:
            logger.info("[OK] Configuração de detecção de desconhecidos atualizada")
            return {
                "success": True,
                "message": "Configuração atualizada com sucesso",
                "config": await get_unknown_detection_config()
            }
        else:
            logger.error("[ERROR] Falha ao salvar configuração - save_config retornou False")
            raise HTTPException(status_code=500, detail="Falha ao salvar configuração")
            
    except HTTPException:
        # Re-raise HTTPException without catching it
        raise
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        logger.error(f"Erro ao atualizar configuração: {e}")
        logger.error(f"Stack trace completo: {error_details}")
        raise HTTPException(status_code=500, detail=f"Erro ao atualizar configuração: {str(e)}")


@router.post("/config/reset")
async def reset_unknown_detection_config():
    """Resetar configuração para valores padrão"""
    try:
        success = unknown_detection_manager.reset_to_defaults()
        
        if success:
            logger.info("[OK] Configuração resetada para valores padrão")
            return {
                "success": True,
                "message": "Configuração resetada para valores padrão",
                "config": await get_unknown_detection_config()
            }
        else:
            raise HTTPException(status_code=500, detail="Falha ao resetar configuração")
            
    except Exception as e:
        logger.error(f"Erro ao resetar configuração: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_unknown_detection_stats(db: Session = Depends(get_db_dependency)):
    """Obter estatísticas de detecção de desconhecidos"""
    try:
        from app.database import models
        
        # Contar desconhecidos por status
        pending_count = db.query(models.UnknownPerson).filter(
            models.UnknownPerson.status == "pending"
        ).count()
        
        identified_count = db.query(models.UnknownPerson).filter(
            models.UnknownPerson.status == "identified"
        ).count()
        
        ignored_count = db.query(models.UnknownPerson).filter(
            models.UnknownPerson.status == "ignored"
        ).count()
        
        total_count = db.query(models.UnknownPerson).count()
        
        # Estatísticas por câmera
        from sqlalchemy import func
        camera_stats = db.query(
            models.UnknownPerson.camera_id,
            func.count(models.UnknownPerson.id).label('count')
        ).group_by(models.UnknownPerson.camera_id).all()
        
        return {
            "totals": {
                "total": total_count,
                "pending": pending_count,
                "identified": identified_count,
                "ignored": ignored_count,
            },
            "by_camera": [
                {"camera_id": stat.camera_id, "count": stat.count}
                for stat in camera_stats
            ],
            "detection_rate": {
                "identification_rate": (identified_count / total_count * 100) if total_count > 0 else 0,
                "pending_rate": (pending_count / total_count * 100) if total_count > 0 else 0,
            }
        }
        
    except Exception as e:
        logger.error(f"Erro ao obter estatísticas: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test")
async def test_unknown_detection_config():
    """Testar configuração atual com dados mock"""
    try:
        config = unknown_detection_manager.get_config()
        
        # Criar dados de teste
        test_results = {
            "config_loaded": True,
            "face_quality_rules": {
                "min_face_size": f"{config.face_quality_rules.min_face_width}x{config.face_quality_rules.min_face_height}",
                "similarity_threshold": f"{config.face_quality_rules.max_similarity_threshold:.1%}",
                "detection_confidence": f"{config.face_quality_rules.min_detection_confidence:.1%}",
            },
            "temporal_rules": {
                "presence_duration": f"{config.temporal_rules.min_presence_duration}s",
                "min_frames": config.temporal_rules.min_frame_count,
                "cooldown": f"{config.temporal_rules.cooldown_period}s",
            },
            "test_status": "[OK] Configuração válida para detecção automática"
        }
        
        return test_results
        
    except Exception as e:
        logger.error(f"Erro no teste de configuração: {e}")
        raise HTTPException(status_code=500, detail=str(e))