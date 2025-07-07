"""
Recognition endpoints for real-time facial recognition
"""

import base64
import time
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

import cv2
import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query, Request, File, UploadFile, Form
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database.database import get_db, get_db_dependency
from app.database import models
from app.api.services.recognition_client import recognition_client
from app.api.services.camera_service import CameraService
from app.api.schemas.recognition import (
    ProcessFrameRequest, ProcessFrameResponse, RecognitionLogList,
    RecognitionLogResponse, RecognitionStats, StreamStatus
)
from app.core.config import settings
from app.api.endpoints.websocket import broadcast_recognition_event
from loguru import logger

router = APIRouter()


class RecognizeFrameRequest(BaseModel):
    """Request para reconhecimento de frame"""
    camera_id: str
    image_data: str  # Base64 encoded image
    timestamp: Optional[float] = None


class RecognitionResult(BaseModel):
    """Resultado de reconhecimento individual"""
    person_id: Optional[str]
    person_name: str
    confidence: float
    bbox: List[int]  # [x, y, width, height]
    is_unknown: bool
    face_quality: float


class RecognizeFrameResponse(BaseModel):
    """Response do reconhecimento de frame"""
    camera_id: str
    timestamp: float
    frame_id: Optional[int]
    processing_time_ms: float
    faces_detected: int
    recognitions: List[RecognitionResult]


@router.post("/recognize-frame", response_model=RecognizeFrameResponse)
async def recognize_frame(
    request: RecognizeFrameRequest,
    db: Session = Depends(get_db_dependency)
):
    """
    Reconhecer faces em um frame de imagem
    """
    start_time = time.time()
    
    try:
        logger.info(f"[TARGET] Processando reconhecimento para câmera {request.camera_id}")
        
        # Verificar se câmera existe
        camera = CameraService.get_camera(db, request.camera_id)
        if not camera:
            raise HTTPException(status_code=404, detail="Câmera não encontrada")
        
        # Decodificar imagem base64
        try:
            image_bytes = base64.b64decode(request.image_data)
            nparr = np.frombuffer(image_bytes, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if frame is None:
                raise ValueError("Não foi possível decodificar a imagem")
                
        except Exception as e:
            logger.error(f"[ERROR] Erro ao decodificar imagem: {e}")
            raise HTTPException(status_code=400, detail="Imagem inválida")
        
        # Processar reconhecimento facial usando Recognition Worker
        try:
            # Converter frame para bytes para envio
            _, encoded_frame = cv2.imencode('.jpg', frame)
            frame_bytes = encoded_frame.tobytes()
            
            # Usar recognition client para processar
            recognition_results = await recognition_client.recognize_faces(frame_bytes)
            
            if recognition_results is None:
                recognition_results = []
                
        except Exception as e:
            logger.warning(f"[WARNING] Recognition worker não disponível, usando detecção local: {e}")
            recognition_results = []
        
        # Calcular tempo de processamento
        processing_time = (time.time() - start_time) * 1000
        
        # Converter resultados para formato da response
        converted_results = []
        for result in recognition_results:
            converted_result = RecognitionResult(
                person_id=result.get('person_id'),
                person_name=result.get('person_name', 'Desconhecido'),
                confidence=result.get('confidence', 0.0),
                bbox=result.get('bbox', [0, 0, 0, 0]),
                is_unknown=result.get('is_unknown', True),
                face_quality=result.get('face_quality', 1.0)
            )
            converted_results.append(converted_result)
        
        # Salvar reconhecimentos no banco de dados
        for result in converted_results:
            if not result.is_unknown and result.person_id:
                try:
                    # Salvar log de reconhecimento
                    recognition_log = models.RecognitionLog(
                        person_id=result.person_id,
                        camera_id=request.camera_id,
                        confidence=result.confidence,
                        bbox_x=result.bbox[0],
                        bbox_y=result.bbox[1],
                        bbox_width=result.bbox[2],
                        bbox_height=result.bbox[3],
                        is_unknown=False,
                        timestamp=datetime.now()
                    )
                    db.add(recognition_log)
                    
                    # Atualizar estatísticas da pessoa
                    person = db.query(models.Person).filter(
                        models.Person.id == result.person_id
                    ).first()
                    
                    if person:
                        person.last_seen = datetime.now()
                        person.recognition_count += 1
                        person.confidence = max(person.confidence, result.confidence)
                    
                except Exception as db_error:
                    logger.error(f"[ERROR] Erro ao salvar reconhecimento no banco: {db_error}")
                    # Continuar sem salvar se houver erro no banco
        
        try:
            db.commit()
        except Exception as commit_error:
            logger.error(f"[ERROR] Erro ao fazer commit: {commit_error}")
            db.rollback()
        
        # Criar response
        response = RecognizeFrameResponse(
            camera_id=request.camera_id,
            timestamp=request.timestamp or time.time(),
            frame_id=None,  # Será definido pelo WebRTC server se disponível
            processing_time_ms=processing_time,
            faces_detected=len(converted_results),
            recognitions=converted_results
        )
        
        # Log do resultado
        if converted_results:
            recognized_names = [r.person_name for r in converted_results if not r.is_unknown]
            unknown_count = len([r for r in converted_results if r.is_unknown])
            
            if recognized_names:
                logger.info(f"[OK] Reconhecido: {', '.join(recognized_names)} ({processing_time:.1f}ms)")
            if unknown_count > 0:
                logger.info(f"❓ {unknown_count} face(s) desconhecida(s) ({processing_time:.1f}ms)")
        else:
            logger.info(f"[SEARCH] Nenhuma face detectada ({processing_time:.1f}ms)")
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[ERROR] Erro no reconhecimento: {e}")
        raise HTTPException(status_code=500, detail="Erro interno no reconhecimento")


async def save_frame_to_disk(image: np.ndarray, camera_id: str, timestamp: datetime) -> str:
    """Salvar frame no disco"""
    try:
        # Criar diretório para frames
        frames_dir = settings.DATA_DIR / "frames" / camera_id
        frames_dir.mkdir(parents=True, exist_ok=True)
        
        # Gerar nome do arquivo
        timestamp_str = timestamp.strftime("%Y%m%d_%H%M%S_%f")
        filename = f"frame_{timestamp_str}.jpg"
        filepath = frames_dir / filename
        
        # Salvar imagem
        cv2.imwrite(str(filepath), image)
        
        return str(filepath.relative_to(settings.BASE_DIR))
        
    except Exception as e:
        logger.error(f"Erro ao salvar frame: {e}")
        return ""


@router.post("/process-frame", response_model=ProcessFrameResponse)
async def process_frame(
    camera_id: str = Form(...),
    timestamp: Optional[str] = Form(None),
    save_frame: bool = Form(False),
    frame: UploadFile = File(...),
    db: Session = Depends(get_db_dependency),
    request: Request = None
):
    """Processar frame de câmera para reconhecimento facial"""
    try:
        # Validar câmera
        camera = db.query(models.Camera).filter(models.Camera.id == camera_id).first()
        if not camera:
            raise HTTPException(status_code=404, detail="Câmera não encontrada")
        
        # Processar timestamp
        if timestamp:
            try:
                frame_timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            except:
                frame_timestamp = datetime.now()
        else:
            frame_timestamp = datetime.now()
        
        # Ler e processar imagem
        image_data = await frame.read()
        
        # Converter para numpy array
        nparr = np.frombuffer(image_data, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if image is None:
            raise HTTPException(status_code=400, detail="Imagem inválida")
        
        # NOTA: Recognition engine agora roda em processo separado
        # Este endpoint é usado pelos workers, não pela API diretamente
        logger.warning("[WARNING] Endpoint /process-frame chamado diretamente - reconhecimento via worker separado")
        
        # Retornar resultado indicando que o processamento é feito via worker
        return ProcessFrameResponse(
            camera_id=camera_id,
            timestamp=frame_timestamp,
            faces_detected=0,
            recognitions=[],
            processed=False,
            error="Reconhecimento processado via worker separado"
        )
        
    except Exception as e:
        logger.error(f"Erro ao processar frame: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/logs", response_model=RecognitionLogList)
async def get_recognition_logs(
    skip: int = Query(0, ge=0, description="Número de registros para pular"),
    limit: int = Query(50, ge=1, le=1000, description="Limite de registros"),
    camera_id: Optional[str] = Query(None, description="Filtrar por câmera"),
    person_id: Optional[str] = Query(None, description="Filtrar por pessoa"),
    is_unknown: Optional[bool] = Query(None, description="Filtrar desconhecidos"),
    start_date: Optional[datetime] = Query(None, description="Data inicial"),
    end_date: Optional[datetime] = Query(None, description="Data final"),
    db: Session = Depends(get_db_dependency)
):
    """Obter logs de reconhecimento com filtros"""
    try:
        query = db.query(models.RecognitionLog)
        
        if camera_id:
            query = query.filter(models.RecognitionLog.camera_id == camera_id)
        
        if person_id:
            query = query.filter(models.RecognitionLog.person_id == person_id)
        
        if is_unknown is not None:
            query = query.filter(models.RecognitionLog.is_unknown == is_unknown)
        
        if start_date:
            query = query.filter(models.RecognitionLog.timestamp >= start_date)
        
        if end_date:
            query = query.filter(models.RecognitionLog.timestamp <= end_date)
        
        query = query.order_by(models.RecognitionLog.timestamp.desc())
        
        logs = query.offset(skip).limit(limit).all()
        total = query.count()
        
        # Enriquecer com nomes de pessoas e câmeras
        enriched_logs = []
        for log in logs:
            person = db.query(models.Person).filter(models.Person.id == log.person_id).first()
            camera = db.query(models.Camera).filter(models.Camera.id == log.camera_id).first()
            
            enriched_log = RecognitionLogResponse(
                id=log.id,
                person_id=log.person_id,
                person_name=person.name if person else "Desconhecido",
                camera_id=log.camera_id,
                camera_name=camera.name if camera else "Câmera removida",
                confidence=log.confidence,
                bounding_box=log.bounding_box,
                frame_path=log.frame_path,
                timestamp=log.timestamp,
                is_unknown=log.is_unknown
            )
            enriched_logs.append(enriched_log)
        
        return RecognitionLogList(
            logs=enriched_logs,
            total=total,
            page=(skip // limit) + 1,
            per_page=limit
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats", response_model=RecognitionStats)
async def get_recognition_stats(db: Session = Depends(get_db_dependency)):
    """Obter estatísticas de reconhecimento"""
    try:
        now = datetime.now()
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_ago = today - timedelta(days=7)
        month_ago = today - timedelta(days=30)
        
        # Reconhecimentos hoje
        total_today = db.query(models.RecognitionLog).filter(
            models.RecognitionLog.timestamp >= today
        ).count()
        
        # Reconhecimentos na semana
        total_week = db.query(models.RecognitionLog).filter(
            models.RecognitionLog.timestamp >= week_ago
        ).count()
        
        # Reconhecimentos no mês
        total_month = db.query(models.RecognitionLog).filter(
            models.RecognitionLog.timestamp >= month_ago
        ).count()
        
        # Pessoas únicas hoje
        unique_today = db.query(models.RecognitionLog.person_id).filter(
            models.RecognitionLog.timestamp >= today,
            models.RecognitionLog.is_unknown == False
        ).distinct().count()
        
        # Desconhecidos hoje
        unknown_today = db.query(models.RecognitionLog).filter(
            models.RecognitionLog.timestamp >= today,
            models.RecognitionLog.is_unknown == True
        ).count()
        
        # Confiança média
        avg_confidence = db.query(models.RecognitionLog.confidence).filter(
            models.RecognitionLog.timestamp >= today
        ).all()
        
        avg_conf = sum([conf[0] for conf in avg_confidence]) / len(avg_confidence) if avg_confidence else 0.0
        
        return RecognitionStats(
            total_recognitions_today=total_today,
            total_recognitions_week=total_week,
            total_recognitions_month=total_month,
            unique_people_today=unique_today,
            unknown_faces_today=unknown_today,
            avg_confidence=round(avg_conf, 3)
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stream/{camera_id}/status", response_model=StreamStatus)
async def get_stream_status(camera_id: str, db: Session = Depends(get_db_dependency)):
    """Obter status do stream de uma câmera"""
    try:
        camera = db.query(models.Camera).filter(models.Camera.id == camera_id).first()
        if not camera:
            raise HTTPException(status_code=404, detail="Câmera não encontrada")
        
        # Contar frames processados hoje
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        frames_today = db.query(models.RecognitionLog).filter(
            models.RecognitionLog.camera_id == camera_id,
            models.RecognitionLog.timestamp >= today
        ).count()
        
        # Calcular FPS atual (estimativa baseada nos últimos frames)
        last_minute = datetime.now() - timedelta(minutes=1)
        frames_last_minute = db.query(models.RecognitionLog).filter(
            models.RecognitionLog.camera_id == camera_id,
            models.RecognitionLog.timestamp >= last_minute
        ).count()
        
        current_fps = frames_last_minute / 60.0
        
        return StreamStatus(
            camera_id=camera_id,
            is_streaming=camera.status == "active",
            fps_current=round(current_fps, 2),
            frames_processed=frames_today,
            last_frame_at=camera.last_frame_at,
            error=None if camera.status != "error" else "Erro na câmera"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/unknown/{recognition_id}/identify")
async def identify_unknown_person(
    recognition_id: int,
    person_id: str,
    db: Session = Depends(get_db_dependency)
):
    """Identificar uma pessoa desconhecida"""
    try:
        # Buscar log de reconhecimento
        log = db.query(models.RecognitionLog).filter(
            models.RecognitionLog.id == recognition_id
        ).first()
        
        if not log:
            raise HTTPException(status_code=404, detail="Log de reconhecimento não encontrado")
        
        # Verificar se a pessoa existe
        person = db.query(models.Person).filter(models.Person.id == person_id).first()
        if not person:
            raise HTTPException(status_code=404, detail="Pessoa não encontrada")
        
        # Atualizar log
        log.person_id = person_id
        log.is_unknown = False
        
        db.commit()
        
        return {"message": "Pessoa identificada com sucesso"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))