"""
API endpoints para gerenciamento de pessoas desconhecidas
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_
from datetime import datetime, timedelta
import json
import base64
import numpy as np

from app.database.database import get_db_session
from app.database.models import UnknownPerson, Person
from app.api.schemas.unknown_people import (
    UnknownPersonResponse, 
    UnknownPersonIdentification,
    UnknownPersonStats,
    UnknownDetectionConfigResponse,
    UnknownDetectionConfigUpdate
)
from app.core.unknown_detection_config import unknown_detection_manager
from app.core.unknown_detector import unknown_detector

router = APIRouter()


@router.get("/unknown-people", response_model=List[UnknownPersonResponse])
async def get_unknown_people(
    status: Optional[str] = Query(None, description="Filtrar por status: pending, identified, ignored"),
    camera_id: Optional[str] = Query(None, description="Filtrar por câmera"),
    limit: int = Query(50, ge=1, le=200, description="Limite de resultados"),
    offset: int = Query(0, ge=0, description="Offset para paginação"),
    db: Session = Depends(get_db_session)
):
    """Listar pessoas desconhecidas detectadas"""
    
    query = db.query(UnknownPerson)
    
    # Aplicar filtros
    if status:
        query = query.filter(UnknownPerson.status == status)
    if camera_id:
        query = query.filter(UnknownPerson.camera_id == camera_id)
    
    # Ordenar por data de detecção (mais recentes primeiro)
    query = query.order_by(desc(UnknownPerson.detected_at))
    
    # Aplicar paginação
    unknown_people = query.offset(offset).limit(limit).all()
    
    # Converter para response format
    results = []
    for unknown in unknown_people:
        # Parse bbox data
        bbox = []
        if unknown.bbox_data:
            try:
                bbox = json.loads(unknown.bbox_data)
            except:
                pass
        
        # Parse additional data
        additional_data = {}
        if unknown.additional_data:
            try:
                additional_data = unknown.additional_data
            except:
                pass
        
        result = UnknownPersonResponse(
            id=unknown.id,
            image_data=unknown.image_data,
            bbox=bbox,
            confidence=unknown.confidence,
            quality_score=unknown.quality_score,
            camera_id=unknown.camera_id,
            detected_at=unknown.detected_at,
            status=unknown.status,
            identified_as_person_id=unknown.identified_as_person_id,
            identified_at=unknown.identified_at,
            identified_by=unknown.identified_by,
            frame_count=unknown.frame_count,
            presence_duration=unknown.presence_duration,
            additional_data=additional_data
        )
        results.append(result)
    
    return results


@router.get("/unknown-people/{unknown_id}", response_model=UnknownPersonResponse)
async def get_unknown_person(
    unknown_id: str,
    db: Session = Depends(get_db_session)
):
    """Obter detalhes de uma pessoa desconhecida específica"""
    
    unknown = db.query(UnknownPerson).filter(UnknownPerson.id == unknown_id).first()
    if not unknown:
        raise HTTPException(status_code=404, detail="Pessoa desconhecida não encontrada")
    
    # Parse bbox data
    bbox = []
    if unknown.bbox_data:
        try:
            bbox = json.loads(unknown.bbox_data)
        except:
            pass
    
    # Parse additional data
    additional_data = {}
    if unknown.additional_data:
        try:
            additional_data = unknown.additional_data
        except:
            pass
    
    return UnknownPersonResponse(
        id=unknown.id,
        image_data=unknown.image_data,
        bbox=bbox,
        confidence=unknown.confidence,
        quality_score=unknown.quality_score,
        camera_id=unknown.camera_id,
        detected_at=unknown.detected_at,
        status=unknown.status,
        identified_as_person_id=unknown.identified_as_person_id,
        identified_at=unknown.identified_at,
        identified_by=unknown.identified_by,
        frame_count=unknown.frame_count,
        presence_duration=unknown.presence_duration,
        additional_data=additional_data
    )


@router.post("/unknown-people/{unknown_id}/identify")
async def identify_unknown_person(
    unknown_id: str,
    identification: UnknownPersonIdentification,
    db: Session = Depends(get_db_session)
):
    """Identificar uma pessoa desconhecida"""
    
    # Buscar pessoa desconhecida
    unknown = db.query(UnknownPerson).filter(UnknownPerson.id == unknown_id).first()
    if not unknown:
        raise HTTPException(status_code=404, detail="Pessoa desconhecida não encontrada")
    
    if unknown.status != "pending":
        raise HTTPException(status_code=400, detail="Pessoa já foi processada")
    
    try:
        if identification.action == "create_new":
            # Criar nova pessoa
            from app.api.services.person_service import PersonService
            person_service = PersonService(db)
            
            # Criar pessoa usando os dados do formulário + embedding da detecção
            person_data = {
                'name': identification.name,
                'department': identification.department,
                'email': identification.email,
                'phone': identification.phone,
                'tags': identification.tags
            }
            
            # Usar embedding da detecção automaticamente
            if unknown.embedding_data:
                try:
                    embedding = np.frombuffer(unknown.embedding_data, dtype=np.float32)
                    person_data['face_encoding'] = embedding.tobytes()
                except Exception as e:
                    print(f"Erro ao processar embedding: {e}")
            
            # Criar nova pessoa
            new_person = await person_service.create_person_from_unknown(person_data, unknown.image_data)
            
            # Atualizar registro de desconhecido
            unknown.status = "identified"
            unknown.identified_as_person_id = new_person.id
            unknown.identified_at = datetime.now()
            unknown.identified_by = identification.identified_by or "system"
            
            db.commit()
            
            return {
                "status": "success",
                "message": f"Nova pessoa criada: {identification.name}",
                "person_id": new_person.id,
                "unknown_id": unknown_id
            }
            
        elif identification.action == "link_existing":
            # Vincular a pessoa existente
            if not identification.existing_person_id:
                raise HTTPException(status_code=400, detail="ID da pessoa existente é obrigatório")
            
            # Verificar se a pessoa existe
            existing_person = db.query(Person).filter(Person.id == identification.existing_person_id).first()
            if not existing_person:
                raise HTTPException(status_code=404, detail="Pessoa existente não encontrada")
            
            # Atualizar embedding da pessoa existente se necessário
            if unknown.embedding_data and not existing_person.face_encoding:
                existing_person.face_encoding = unknown.embedding_data
            
            # Atualizar registro de desconhecido
            unknown.status = "identified"
            unknown.identified_as_person_id = identification.existing_person_id
            unknown.identified_at = datetime.now()
            unknown.identified_by = identification.identified_by or "system"
            
            db.commit()
            
            return {
                "status": "success",
                "message": f"Vinculado à pessoa existente: {existing_person.name}",
                "person_id": identification.existing_person_id,
                "unknown_id": unknown_id
            }
            
        elif identification.action == "ignore":
            # Ignorar/marcar como não relevante
            unknown.status = "ignored"
            unknown.identified_at = datetime.now()
            unknown.identified_by = identification.identified_by or "system"
            
            db.commit()
            
            return {
                "status": "success",
                "message": "Pessoa marcada como ignorada",
                "unknown_id": unknown_id
            }
        
        else:
            raise HTTPException(status_code=400, detail="Ação inválida")
            
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Erro ao processar identificação: {str(e)}")


@router.delete("/unknown-people/{unknown_id}")
async def delete_unknown_person(
    unknown_id: str,
    db: Session = Depends(get_db_session)
):
    """Deletar uma pessoa desconhecida"""
    
    unknown = db.query(UnknownPerson).filter(UnknownPerson.id == unknown_id).first()
    if not unknown:
        raise HTTPException(status_code=404, detail="Pessoa desconhecida não encontrada")
    
    db.delete(unknown)
    db.commit()
    
    return {"status": "success", "message": "Pessoa desconhecida deletada"}


@router.get("/unknown-people/stats", response_model=UnknownPersonStats)
async def get_unknown_stats(
    days: int = Query(7, ge=1, le=365, description="Período em dias para estatísticas"),
    db: Session = Depends(get_db_session)
):
    """Obter estatísticas de pessoas desconhecidas"""
    
    # Calcular período
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    # Query base
    base_query = db.query(UnknownPerson).filter(
        UnknownPerson.detected_at >= start_date
    )
    
    # Estatísticas básicas
    total_detected = base_query.count()
    pending = base_query.filter(UnknownPerson.status == "pending").count()
    identified = base_query.filter(UnknownPerson.status == "identified").count()
    ignored = base_query.filter(UnknownPerson.status == "ignored").count()
    
    # Estatísticas por câmera
    camera_stats = {}
    cameras = db.query(UnknownPerson.camera_id).filter(
        UnknownPerson.detected_at >= start_date
    ).distinct().all()
    
    for (camera_id,) in cameras:
        camera_count = base_query.filter(UnknownPerson.camera_id == camera_id).count()
        camera_stats[camera_id] = camera_count
    
    # Qualidade média
    avg_quality = db.query(db.func.avg(UnknownPerson.quality_score)).filter(
        UnknownPerson.detected_at >= start_date
    ).scalar() or 0.0
    
    # Estatísticas do detector
    detector_stats = unknown_detector.get_stats() if unknown_detector else {}
    
    return UnknownPersonStats(
        total_detected=total_detected,
        pending=pending,
        identified=identified,
        ignored=ignored,
        detection_rate_per_day=total_detected / days if days > 0 else 0,
        average_quality_score=float(avg_quality),
        cameras_with_detections=len(camera_stats),
        camera_stats=camera_stats,
        detector_stats=detector_stats
    )


@router.get("/unknown-detection/config", response_model=UnknownDetectionConfigResponse)
async def get_unknown_detection_config():
    """Obter configuração de detecção automática"""
    config = unknown_detection_manager.get_config_dict()
    return UnknownDetectionConfigResponse(**config)


@router.post("/unknown-detection/config")
async def update_unknown_detection_config(
    config_update: UnknownDetectionConfigUpdate
):
    """Atualizar configuração de detecção automática"""
    
    try:
        # Atualizar configurações
        update_dict = config_update.dict(exclude_unset=True)
        
        # Aplicar configurações atualizadas
        for key, value in update_dict.items():
            if hasattr(unknown_detection_manager.config, key):
                setattr(unknown_detection_manager.config, key, value)
            elif key == 'face_quality' and isinstance(value, dict):
                for fq_key, fq_value in value.items():
                    if hasattr(unknown_detection_manager.config.face_quality, fq_key):
                        setattr(unknown_detection_manager.config.face_quality, fq_key, fq_value)
            elif key == 'temporal' and isinstance(value, dict):
                for t_key, t_value in value.items():
                    if hasattr(unknown_detection_manager.config.temporal, t_key):
                        setattr(unknown_detection_manager.config.temporal, t_key, t_value)
        
        # Salvar configuração
        unknown_detection_manager.save_config()
        
        return {
            "status": "success",
            "message": "Configuração atualizada com sucesso",
            "config": unknown_detection_manager.get_config_dict()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao atualizar configuração: {str(e)}")


@router.post("/unknown-people/cleanup")
async def cleanup_old_unknown_people(
    days: int = Query(30, ge=1, le=365, description="Remover registros mais antigos que X dias"),
    status: Optional[str] = Query(None, description="Limpar apenas registros com status específico"),
    db: Session = Depends(get_db_session)
):
    """Limpar registros antigos de pessoas desconhecidas"""
    
    try:
        # Calcular data limite
        cutoff_date = datetime.now() - timedelta(days=days)
        
        # Query base
        query = db.query(UnknownPerson).filter(UnknownPerson.detected_at < cutoff_date)
        
        # Filtrar por status se especificado
        if status:
            query = query.filter(UnknownPerson.status == status)
        
        # Contar antes de deletar
        count_to_delete = query.count()
        
        # Deletar
        deleted_count = query.delete()
        db.commit()
        
        return {
            "status": "success",
            "message": f"Limpeza concluída",
            "deleted_count": deleted_count,
            "days_threshold": days,
            "status_filter": status
        }
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Erro na limpeza: {str(e)}")