"""
Unknown people management endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session
from typing import List, Optional
import os
from datetime import datetime, timedelta
from loguru import logger

from app.database.database import get_db, get_db_dependency
from app.database import models
from app.api.schemas.person import PersonCreate, PersonResponse
from app.core.config import settings

router = APIRouter()


@router.get("/")
async def get_unknown_people(
    skip: int = Query(0, ge=0, description="Número de registros para pular"),
    limit: int = Query(50, ge=1, le=1000, description="Limite de registros"),
    db: Session = Depends(get_db_dependency)
):
    """Obter todas as pessoas desconhecidas com paginação"""
    try:
        unknown_people_query = db.query(models.Person).filter(
            models.Person.is_unknown == True
        ).order_by(models.Person.last_seen.desc())
        
        total = unknown_people_query.count()
        unknown_people = unknown_people_query.offset(skip).limit(limit).all()
        
        # Converter para formato de resposta
        unknown_list = []
        for person in unknown_people:
            person_dict = {
                "id": person.id,
                "name": person.name,
                "first_seen": person.first_seen.isoformat() if person.first_seen else None,
                "last_seen": person.last_seen.isoformat() if person.last_seen else None,
                "recognition_count": person.recognition_count,
                "thumbnail_path": person.thumbnail_path,
                "has_image": bool(person.thumbnail_path and os.path.exists(person.thumbnail_path)),
                "status": person.status
            }
            unknown_list.append(person_dict)
        
        return {
            "unknown_people": unknown_list,
            "total": total,
            "page": (skip // limit) + 1,
            "per_page": limit
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{unknown_id}")
async def get_unknown_person(unknown_id: str, db: Session = Depends(get_db_dependency)):
    """Obter detalhes de uma pessoa desconhecida"""
    try:
        unknown_person = db.query(models.Person).filter(
            models.Person.id == unknown_id,
            models.Person.is_unknown == True
        ).first()
        
        if not unknown_person:
            raise HTTPException(status_code=404, detail="Pessoa desconhecida não encontrada")
        
        return {
            "id": unknown_person.id,
            "name": unknown_person.name,
            "first_seen": unknown_person.first_seen.isoformat() if unknown_person.first_seen else None,
            "last_seen": unknown_person.last_seen.isoformat() if unknown_person.last_seen else None,
            "recognition_count": unknown_person.recognition_count,
            "thumbnail_path": unknown_person.thumbnail_path,
            "has_image": bool(unknown_person.thumbnail_path and os.path.exists(unknown_person.thumbnail_path)),
            "confidence": unknown_person.confidence,
            "status": unknown_person.status
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{person_id}/image")
async def get_unknown_person_image(person_id: str, db: Session = Depends(get_db_dependency)):
    """Obter imagem da pessoa desconhecida"""
    try:
        from fastapi.responses import Response
        import os
        
        person = db.query(models.Person).filter(
            models.Person.id == person_id,
            models.Person.is_unknown == True
        ).first()
        
        if not person:
            raise HTTPException(status_code=404, detail="Pessoa desconhecida não encontrada")
        
        # Buscar imagem na pasta de desconhecidos
        unknown_images_dir = os.path.join(settings.DATA_DIR, "unknown_faces")
        
        # Procurar por arquivos que contenham o ID da pessoa
        image_files = []
        if os.path.exists(unknown_images_dir):
            for filename in os.listdir(unknown_images_dir):
                if person_id in filename and filename.endswith('.jpg'):
                    image_files.append(os.path.join(unknown_images_dir, filename))
        
        if not image_files:
            raise HTTPException(status_code=404, detail="Imagem não encontrada")
        
        # Usar a imagem mais recente
        latest_image = max(image_files, key=os.path.getctime)
        
        # Ler e retornar a imagem
        with open(latest_image, "rb") as image_file:
            image_data = image_file.read()
        
        return Response(content=image_data, media_type="image/jpeg")
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{unknown_id}/identify")
async def identify_unknown_person(
    unknown_id: str, 
    person_data: PersonCreate,
    db: Session = Depends(get_db_dependency)
):
    """Converter pessoa desconhecida em pessoa conhecida"""
    try:
        unknown_person = db.query(models.Person).filter(
            models.Person.id == unknown_id,
            models.Person.is_unknown == True
        ).first()
        
        if not unknown_person:
            raise HTTPException(status_code=404, detail="Pessoa desconhecida não encontrada")
        
        # Atualizar dados da pessoa
        unknown_person.name = person_data.name
        unknown_person.department = person_data.department
        unknown_person.email = person_data.email
        unknown_person.phone = person_data.phone
        unknown_person.tags = person_data.tags
        unknown_person.is_unknown = False
        
        db.commit()
        
        # Atualizar cache do recognition engine
        try:
            from app.core.recognition_engine import RecognitionEngine
            # Seria necessário ter uma instância global do engine ou método para atualizar
            # Por enquanto, o engine será atualizado na próxima inicialização
        except:
            pass
        
        return PersonResponse.from_db_model(unknown_person)
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{unknown_id}")
async def update_unknown_person(
    unknown_id: str,
    person_data: PersonCreate,
    db: Session = Depends(get_db_dependency)
):
    """Atualizar dados de pessoa desconhecida (sem converter para conhecida)"""
    try:
        unknown_person = db.query(models.Person).filter(
            models.Person.id == unknown_id,
            models.Person.is_unknown == True
        ).first()
        
        if not unknown_person:
            raise HTTPException(status_code=404, detail="Pessoa desconhecida não encontrada")
        
        # Atualizar apenas nome e tags, mantendo como desconhecida
        if person_data.name:
            unknown_person.name = person_data.name
        if person_data.tags:
            unknown_person.tags = person_data.tags
        
        db.commit()
        
        return {"message": "Pessoa desconhecida atualizada com sucesso"}
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{unknown_id}")
async def delete_unknown_person(unknown_id: str, db: Session = Depends(get_db_dependency)):
    """Deletar pessoa desconhecida"""
    try:
        unknown_person = db.query(models.Person).filter(
            models.Person.id == unknown_id,
            models.Person.is_unknown == True
        ).first()
        
        if not unknown_person:
            raise HTTPException(status_code=404, detail="Pessoa desconhecida não encontrada")
        
        # Deletar arquivo de imagem se existir
        if unknown_person.thumbnail_path and os.path.exists(unknown_person.thumbnail_path):
            try:
                os.remove(unknown_person.thumbnail_path)
            except Exception as e:
                # Log mas não falhar a operação
                pass
        
        db.delete(unknown_person)
        db.commit()
        
        return {"message": "Pessoa desconhecida deletada com sucesso"}
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_unknown_people_stats(db: Session = Depends(get_db_dependency)):
    """Obter estatísticas de pessoas desconhecidas"""
    try:
        from datetime import datetime, timedelta
        
        total_unknown = db.query(models.Person).filter(
            models.Person.is_unknown == True
        ).count()
        
        # Calcular data de 7 dias atrás
        seven_days_ago = datetime.now() - timedelta(days=7)
        recent_unknown = db.query(models.Person).filter(
            models.Person.is_unknown == True,
            models.Person.last_seen >= seven_days_ago
        ).count()
        
        with_images = db.query(models.Person).filter(
            models.Person.is_unknown == True,
            models.Person.thumbnail_path.isnot(None)
        ).count()
        
        return {
            "total_unknown": total_unknown,
            "recent_unknown": recent_unknown,
            "with_images": with_images,
            "without_images": total_unknown - with_images
        }
        
    except Exception as e:
        logger.error(f"Erro ao obter estatísticas de pessoas desconhecidas: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats/summary")
async def get_unknown_people_stats_summary(db: Session = Depends(get_db_dependency)):
    """Obter estatísticas detalhadas de pessoas desconhecidas"""
    try:
        from datetime import datetime, timedelta
        
        total_unknown = db.query(models.Person).filter(
            models.Person.is_unknown == True
        ).count()
        
        # Calcular data de 7 dias atrás
        seven_days_ago = datetime.now() - timedelta(days=7)
        recent_unknown = db.query(models.Person).filter(
            models.Person.is_unknown == True,
            models.Person.last_seen >= seven_days_ago
        ).count()
        
        with_images = db.query(models.Person).filter(
            models.Person.is_unknown == True,
            models.Person.thumbnail_path.isnot(None)
        ).count()
        
        # Estatísticas adicionais
        one_day_ago = datetime.now() - timedelta(days=1)
        today_unknown = db.query(models.Person).filter(
            models.Person.is_unknown == True,
            models.Person.last_seen >= one_day_ago
        ).count()
        
        return {
            "total_unknown": total_unknown,
            "recent_unknown": recent_unknown,
            "today_unknown": today_unknown,
            "with_images": with_images,
            "without_images": total_unknown - with_images
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))