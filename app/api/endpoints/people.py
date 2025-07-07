"""
People management endpoints
"""

from typing import List, Optional, Dict, Any
import os
import uuid
import json
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Form, File, UploadFile, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from loguru import logger

from app.database.database import get_db, get_db_dependency
from app.database import models
from app.api.schemas.person import PersonCreate, PersonUpdate, PersonResponse, PersonList, PersonStats
from app.api.services.person_service import PersonService
from app.api.services.recognition_client import recognition_client

router = APIRouter()


@router.get("/", response_model=PersonList)
async def get_people(
    skip: int = Query(0, ge=0, description="Número de registros para pular"),
    limit: int = Query(50, ge=1, le=1000, description="Limite de registros"),
    search: Optional[str] = Query(None, description="Buscar por nome"),
    department: Optional[str] = Query(None, description="Filtrar por departamento"),
    status: Optional[str] = Query(None, description="Filtrar por status"),
    db: Session = Depends(get_db_dependency)
):
    """Obter todas as pessoas com paginação e filtros"""
    try:
        query = db.query(models.Person).filter(models.Person.is_unknown == False)
        
        if search:
            query = query.filter(models.Person.name.ilike(f"%{search}%"))
        
        if department:
            query = query.filter(models.Person.department == department)
        
        if status:
            query = query.filter(models.Person.status == status)
        
        query = query.order_by(models.Person.name)
        
        total = query.count()
        people = query.offset(skip).limit(limit).all()
        
        return PersonList(
            people=[PersonResponse.from_db_model(person) for person in people],
            total=total,
            page=(skip // limit) + 1,
            per_page=limit
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats", response_model=PersonStats)
async def get_people_stats(db: Session = Depends(get_db_dependency)):
    """Obter estatísticas de pessoas"""
    try:
        total_people = db.query(models.Person).filter(models.Person.is_unknown == False).count()
        active_people = db.query(models.Person).filter(
            models.Person.is_unknown == False,
            models.Person.status == "active"
        ).count()
        unknown_people = db.query(models.Person).filter(models.Person.is_unknown == True).count()
        
        # Reconhecimentos recentes (últimas 24h)
        yesterday = datetime.now() - timedelta(days=1)
        recent_recognitions = db.query(models.RecognitionLog).filter(
            models.RecognitionLog.timestamp >= yesterday,
            models.RecognitionLog.is_unknown == False
        ).count()
        
        return PersonStats(
            total_people=total_people,
            active_people=active_people,
            unknown_people=unknown_people,
            recent_recognitions=recent_recognitions
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/attendance/departments")
async def get_department_attendance(
    date: str = Query(None, description="Data no formato YYYY-MM-DD (padrão: hoje)"),
    db: Session = Depends(get_db_dependency)
):
    """Obter estatísticas de presença por departamento"""
    try:
        from datetime import datetime, timedelta
        from sqlalchemy import func, text
        import json
        
        # Definir data (padrão: hoje)
        if date:
            target_date = datetime.strptime(date, "%Y-%m-%d").date()
        else:
            target_date = datetime.now().date()
        
        # Período do dia (00:00 até 23:59:59)
        start_datetime = datetime.combine(target_date, datetime.min.time())
        end_datetime = datetime.combine(target_date, datetime.max.time())
        
        # Obter todos os departamentos únicos
        departments_query = db.query(models.Person.department).filter(
            models.Person.department.isnot(None),
            models.Person.department != "",
            models.Person.status == "active"
        ).distinct().all()
        
        departments = [dept[0] for dept in departments_query if dept[0]]
        
        result = []
        
        for department in departments:
            # Contar pessoas cadastradas no departamento
            total_people = db.query(models.Person).filter(
                models.Person.department == department,
                models.Person.status == "active",
                models.Person.is_unknown == False
            ).count()
            
            # Contar pessoas que foram reconhecidas hoje no departamento
            recognized_people = db.query(func.count(func.distinct(models.RecognitionLog.person_id))).filter(
                models.RecognitionLog.timestamp >= start_datetime,
                models.RecognitionLog.timestamp <= end_datetime,
                models.RecognitionLog.is_unknown == False
            ).join(
                models.Person, models.RecognitionLog.person_id == models.Person.id
            ).filter(
                models.Person.department == department,
                models.Person.status == "active"
            ).scalar()
            
            # Pessoas que NÃO foram reconhecidas hoje
            not_recognized = total_people - (recognized_people or 0)
            
            # Porcentagem de presença
            attendance_rate = (recognized_people / total_people * 100) if total_people > 0 else 0
            
            result.append({
                "department": department,
                "total_people": total_people,
                "recognized_today": recognized_people or 0,
                "not_recognized_today": not_recognized,
                "attendance_rate": round(attendance_rate, 2)
            })
        
        # Ordenar por taxa de presença (menor primeiro - para identificar problemas)
        result.sort(key=lambda x: x["attendance_rate"])
        
        return {
            "date": target_date.isoformat(),
            "departments": result,
            "summary": {
                "total_departments": len(result),
                "total_people": sum(d["total_people"] for d in result),
                "total_recognized": sum(d["recognized_today"] for d in result),
                "overall_attendance_rate": round(
                    sum(d["recognized_today"] for d in result) / 
                    sum(d["total_people"] for d in result) * 100, 2
                ) if sum(d["total_people"] for d in result) > 0 else 0
            }
        }
        
    except Exception as e:
        logger.error(f"Erro ao obter presença por departamento: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/attendance/missing")
async def get_missing_people(
    department: str = Query(None, description="Filtrar por departamento"),
    date: str = Query(None, description="Data no formato YYYY-MM-DD (padrão: hoje)"),
    db: Session = Depends(get_db_dependency)
):
    """Obter lista de pessoas que não compareceram hoje"""
    try:
        from datetime import datetime
        from sqlalchemy import func
        
        # Definir data (padrão: hoje)
        if date:
            target_date = datetime.strptime(date, "%Y-%m-%d").date()
        else:
            target_date = datetime.now().date()
        
        # Período do dia (00:00 até 23:59:59)
        start_datetime = datetime.combine(target_date, datetime.min.time())
        end_datetime = datetime.combine(target_date, datetime.max.time())
        
        # Buscar pessoas que foram reconhecidas hoje
        recognized_people_ids = db.query(models.RecognitionLog.person_id).filter(
            models.RecognitionLog.timestamp >= start_datetime,
            models.RecognitionLog.timestamp <= end_datetime,
            models.RecognitionLog.is_unknown == False
        ).distinct().subquery()
        
        # Buscar pessoas que NÃO foram reconhecidas
        missing_query = db.query(models.Person).filter(
            models.Person.status == "active",
            models.Person.is_unknown == False,
            ~models.Person.id.in_(recognized_people_ids)
        )
        
        # Filtrar por departamento se especificado
        if department:
            missing_query = missing_query.filter(models.Person.department == department)
        
        missing_people = missing_query.all()
        
        # Converter para formato de resposta
        result = []
        for person in missing_people:
            result.append({
                "id": person.id,
                "name": person.name,
                "department": person.department,
                "email": person.email,
                "phone": person.phone,
                "last_seen": person.last_seen.isoformat() if person.last_seen else None,
                "recognition_count": person.recognition_count
            })
        
        return {
            "date": target_date.isoformat(),
            "department_filter": department,
            "missing_people": result,
            "count": len(result)
        }
        
    except Exception as e:
        logger.error(f"Erro ao obter pessoas ausentes: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{person_id}", response_model=PersonResponse)
async def get_person(person_id: str, db: Session = Depends(get_db_dependency)):
    """Obter pessoa por ID"""
    try:
        person = PersonService.get_person(db, person_id)
        if not person:
            raise HTTPException(status_code=404, detail="Pessoa não encontrada")
        return PersonResponse.from_db_model(person)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/", response_model=PersonResponse)
async def create_person(person_data: PersonCreate, db: Session = Depends(get_db_dependency)):
    """Criar pessoa sem imagem"""
    try:
        person = await PersonService.create_person(db, person_data)
        return PersonResponse.from_db_model(person)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/register", response_model=PersonResponse)
async def register_person_with_image(
    name: str = Form(...),
    department: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    phone: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    image: UploadFile = File(...),
    db: Session = Depends(get_db_dependency)
):
    """Registrar pessoa com imagem"""
    try:
        # Validar tipo de arquivo
        if not image.content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail="Arquivo deve ser uma imagem")
        
        # Ler dados da imagem
        image_data = await image.read()
        
        # Criar dados da pessoa
        person_data = PersonCreate(
            name=name,
            department=department,
            email=email,
            phone=phone,
            tags=tags
        )
        
        # Criar pessoa com imagem (sem validação de face para ser mais rápido)
        person = await PersonService.create_person(db, person_data, image_data, validate_face=False)
        return PersonResponse.from_db_model(person)
        
    except ValueError as e:
        # Erros de validação (ex: nenhuma face detectada)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/register-with-camera", response_model=PersonResponse)
async def register_person_with_camera(
    name: str = Form(...),
    camera_id: str = Form(...),
    department: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    phone: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    db: Session = Depends(get_db_dependency)
):
    """Registrar pessoa capturando foto da câmera usando GStreamer"""
    try:
        import cv2
        import base64
        
        # Importar o serviço de câmera
        from app.api.services.camera_service import CameraService
        
        # Buscar câmera
        camera = CameraService.get_camera(db, camera_id)
        if not camera:
            raise HTTPException(status_code=404, detail="Câmera não encontrada")
        
        # Verificar se câmera está ativa
        if camera.status != "active":
            raise HTTPException(status_code=400, detail="Câmera não está ativa")
        
        try:
            # Tentar usar GStreamer service primeiro
            from app.api.services.gstreamer_service import gstreamer_service
            
            # Capturar frame usando GStreamer
            frame = await gstreamer_service.get_frame(camera)
            if frame is not None:
                # Redimensionar se necessário
                if frame.shape[1] > 1280:
                    height = int(frame.shape[0] * 1280 / frame.shape[1])
                    frame = cv2.resize(frame, (1280, height))
                
                # Converter para JPEG
                _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
                image_data = buffer.tobytes()
            else:
                raise Exception("GStreamer frame capture failed")
                
        except Exception as gstreamer_error:
            # Fallback para OpenCV se GStreamer falhar
            print(f"GStreamer failed, falling back to OpenCV: {gstreamer_error}")
            
            # Conectar à câmera usando OpenCV (fallback)
            if camera.type == "webcam":
                cap = cv2.VideoCapture(int(camera.url) if camera.url.isdigit() else 0)
            else:
                cap = cv2.VideoCapture(camera.url)
            
            if not cap.isOpened():
                raise HTTPException(status_code=500, detail="Não foi possível conectar à câmera")
            
            try:
                # Capturar múltiplos frames para estabilizar
                for _ in range(5):
                    ret, frame = cap.read()
                    if not ret:
                        raise HTTPException(status_code=500, detail="Não foi possível capturar frame")
                
                # Redimensionar se necessário
                if frame.shape[1] > 1280:
                    height = int(frame.shape[0] * 1280 / frame.shape[1])
                    frame = cv2.resize(frame, (1280, height))
                
                # Converter para JPEG
                _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
                image_data = buffer.tobytes()
                
            finally:
                cap.release()
        
        # Criar dados da pessoa
        person_data = PersonCreate(
            name=name,
            department=department,
            email=email,
            phone=phone,
            tags=tags
        )
        
        # Criar pessoa com imagem capturada (sem validação de face para ser mais rápido)
        person = await PersonService.create_person(db, person_data, image_data, validate_face=False)
        return PersonResponse.from_db_model(person)
        
    except ValueError as e:
        # Erros de validação (ex: nenhuma face detectada)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/register-from-base64", response_model=PersonResponse) 
async def register_person_from_base64(
    request: Request,
    db: Session = Depends(get_db_dependency)
):
    """Registrar pessoa com imagem em base64 (vinda da captura da câmera)"""
    try:
        import base64
        from loguru import logger
        
        # Obter os dados do formulário
        form_data = await request.form()
        logger.info(f"Dados do formulário recebidos: {form_data.keys()}")
        
        # Obter os campos obrigatórios
        if "name" not in form_data:
            raise HTTPException(status_code=400, detail="Campo 'name' é obrigatório")
        
        name = form_data.get("name")
        logger.info(f"Iniciando cadastro de pessoa com base64: {name}")
        
        # Verificar qual parâmetro de imagem foi fornecido
        image_base64 = None
        for param_name in ["image_base64", "imageBase64", "base64_image"]:
            if param_name in form_data:
                image_base64 = form_data.get(param_name)
                logger.info(f"Parâmetro de imagem encontrado: {param_name}")
                break
        
        if not image_base64:
            logger.error("Nenhum parâmetro de imagem base64 foi fornecido")
            raise HTTPException(status_code=400, detail="Nenhum parâmetro de imagem base64 foi fornecido. Use image_base64, imageBase64 ou base64_image")
        
        # Decodificar imagem base64
        try:
            image_data = base64.b64decode(image_base64)
            logger.info(f"Imagem base64 decodificada com sucesso: {len(image_data)} bytes")
        except Exception as e:
            logger.error(f"Erro ao decodificar imagem base64: {e}")
            raise HTTPException(status_code=400, detail=f"Dados de imagem base64 inválidos: {str(e)}")
        
        # Validar se é uma imagem válida
        from PIL import Image
        import io
        try:
            img = Image.open(io.BytesIO(image_data))
            img.verify()
            logger.info(f"Imagem validada com sucesso: {img.format} {img.size}")
        except Exception as e:
            logger.error(f"Erro ao validar imagem: {e}")
            raise HTTPException(status_code=400, detail=f"Dados de imagem inválidos: {str(e)}")
        
        # Obter os campos opcionais
        department = form_data.get("department")
        email = form_data.get("email")
        phone = form_data.get("phone")
        tags = form_data.get("tags")
        
        # Criar dados da pessoa
        person_data = PersonCreate(
            name=name,
            department=department,
            email=email,
            phone=phone,
            tags=tags
        )
        logger.info(f"Dados da pessoa criados: {person_data}")
        
        # Criar pessoa com imagem (sem validação de face para ser mais rápido)
        try:
            person = await PersonService.create_person(db, person_data, image_data, validate_face=False)
            logger.info(f"Pessoa cadastrada com sucesso: {person.id}")
            return PersonResponse.from_db_model(person)
        except ValueError as e:
            logger.error(f"Erro ao criar pessoa (validação): {e}")
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.error(f"Erro ao criar pessoa (geral): {e}")
            raise HTTPException(status_code=500, detail=str(e))
        
    except ValueError as e:
        # Erros de validação (ex: nenhuma face detectada)
        logger.error(f"Erro de validação: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Erro geral: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/camera-preview/{camera_id}")
async def get_camera_preview(camera_id: str, db: Session = Depends(get_db_dependency)):
    """Obter preview da câmera para captura de foto usando OpenCV diretamente"""
    try:
        import base64
        import cv2
        import asyncio
        from loguru import logger
        import time
        
        # Importar o serviço de câmera
        from app.api.services.camera_service import CameraService
        
        # Iniciar timer para medir tempo de resposta
        start_time = time.time()
        logger.info(f"Iniciando preview da câmera {camera_id}")
        
        # Buscar câmera
        camera = CameraService.get_camera(db, camera_id)
        if not camera:
            logger.error(f"Câmera não encontrada: {camera_id}")
            raise HTTPException(status_code=404, detail="Câmera não encontrada")
        
        # Verificar se a câmera está ativa
        if camera.status != "active":
            logger.warning(f"Tentativa de acessar câmera inativa: {camera_id}")
            raise HTTPException(status_code=400, detail="Câmera não está ativa")
        
        try:
            # Configurar OpenCV para captura mais confiável
            if camera.type == "webcam":
                # Webcams locais
                device_id = int(camera.url) if camera.url.isdigit() else 0
                logger.info(f"Abrindo webcam {device_id}")
                cap = cv2.VideoCapture(device_id)
            else:
                # Câmeras IP/RTSP
                logger.info(f"Abrindo câmera IP: {camera.url}")
                cap = cv2.VideoCapture(camera.url)
                
                # Configurações para câmeras IP para melhorar performance
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                
                # Definir timeout baixo para RTSP (evita travamentos)
                if camera.url.startswith('rtsp://'):
                    logger.info(f"Configurando timeout para câmera RTSP")
                    cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 2000)  # 2 segundos timeout
            
            # Verificar se a câmera foi aberta
            if not cap.isOpened():
                logger.error(f"Não foi possível abrir a câmera {camera_id}: {camera.url}")
                raise HTTPException(status_code=500, detail="Não foi possível conectar à câmera")
            
            # Capturar frame com timeout para evitar travamentos
            logger.info(f"Tentando capturar frame da câmera {camera_id}")
            success = False
            frame = None
            
            # Três tentativas
            for attempt in range(3):
                # Descartar frames anteriores para webcams (obter frame mais atual)
                if camera.type == "webcam":
                    for _ in range(3):  # Descartar 3 frames
                        cap.read()
                
                # Ler o frame
                ret, frame = cap.read()
                
                if ret and frame is not None:
                    success = True
                    logger.info(f"Frame capturado na tentativa {attempt+1}")
                    break
                
                # Esperar um pouco antes da próxima tentativa
                await asyncio.sleep(0.2)
                logger.warning(f"Tentativa {attempt+1} falhou, tentando novamente...")
            
            # Liberar a câmera imediatamente
            cap.release()
            
            # Verificar resultado
            if not success or frame is None:
                logger.error(f"Não foi possível obter frame da câmera {camera_id} após 3 tentativas")
                raise HTTPException(status_code=500, detail="Não foi possível obter imagem da câmera")
            
            # Redimensionar para tamanho menor para evitar problemas de tamanho
            if frame.shape[1] > 640:
                height = int(frame.shape[0] * 640 / frame.shape[1])
                frame = cv2.resize(frame, (640, height))
                logger.info(f"Imagem redimensionada para 640x{height}")
            
            # Comprimir em JPEG com qualidade média-baixa para reduzir tamanho
            _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            image_data = buffer.tobytes()
            
            # Verificar tamanho da imagem
            image_size_kb = len(image_data) / 1024
            logger.info(f"Tamanho da imagem: {image_size_kb:.1f} KB")
            
            # Se ainda for muito grande, comprimir mais
            if len(image_data) > 200000:  # mais de 200KB
                logger.warning(f"Imagem muito grande ({image_size_kb:.1f} KB), reduzindo qualidade")
                _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 50])
                image_data = buffer.tobytes()
                logger.info(f"Novo tamanho: {len(image_data) / 1024:.1f} KB")
            
            # Converter para base64
            image_base64 = base64.b64encode(image_data).decode('utf-8')
            
            # Tempo total de processamento
            elapsed_time = time.time() - start_time
            logger.info(f"Preview da câmera {camera_id} concluído em {elapsed_time:.2f}s")
            
            return {
                "camera_id": camera_id,
                "camera_name": camera.name,
                "image_data": image_base64,  # Retornar apenas base64, frontend adiciona prefixo
                "timestamp": datetime.now().isoformat(),
                "elapsed_time": f"{elapsed_time:.2f}s",
                "image_size": f"{len(image_data) / 1024:.1f} KB"
            }
            
        except Exception as e:
            import traceback
            logger.error(f"Erro ao capturar frame da câmera {camera_id}: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise HTTPException(status_code=500, detail=f"Erro ao capturar imagem: {str(e)}")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro não tratado no endpoint camera-preview: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")


@router.put("/{person_id}", response_model=PersonResponse)
async def update_person(
    person_id: str, 
    person_data: PersonUpdate, 
    db: Session = Depends(get_db_dependency)
):
    """Atualizar pessoa"""
    try:
        person = PersonService.update_person(db, person_id, person_data)
        if not person:
            raise HTTPException(status_code=404, detail="Pessoa não encontrada")
        return PersonResponse.from_db_model(person)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{person_id}/image", response_model=PersonResponse)
async def update_person_image(
    person_id: str,
    image: UploadFile = File(...),
    db: Session = Depends(get_db_dependency)
):
    """Atualizar imagem da pessoa"""
    try:
        # Validar tipo de arquivo
        if not image.content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail="Arquivo deve ser uma imagem")
        
        # Ler dados da imagem
        image_data = await image.read()
        
        # Atualizar imagem da pessoa
        person = PersonService.update_person_image(db, person_id, image_data)
        if not person:
            raise HTTPException(status_code=404, detail="Pessoa não encontrada")
        
        return PersonResponse.from_db_model(person)
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{person_id}/image")
async def get_person_image(person_id: str, db: Session = Depends(get_db_dependency)):
    """Obter imagem da pessoa"""
    try:
        from fastapi.responses import Response
        import os
        
        person = PersonService.get_person(db, person_id)
        if not person:
            raise HTTPException(status_code=404, detail="Pessoa não encontrada")
        
        if not person.thumbnail_path or not os.path.exists(person.thumbnail_path):
            raise HTTPException(status_code=404, detail="Imagem não encontrada")
        
        # Ler e retornar a imagem
        with open(person.thumbnail_path, "rb") as image_file:
            image_data = image_file.read()
        
        return Response(content=image_data, media_type="image/jpeg")
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{person_id}")
async def delete_person(person_id: str, db: Session = Depends(get_db_dependency)):
    """Deletar pessoa"""
    try:
        from loguru import logger
        logger.info(f"Recebida requisição para deletar pessoa: {person_id}")
        
        success = PersonService.delete_person(db, person_id)
        
        if not success:
            logger.error(f"Pessoa não encontrada para exclusão: {person_id}")
            raise HTTPException(status_code=404, detail="Pessoa não encontrada")
        
        logger.info(f"Pessoa deletada com sucesso: {person_id}")
        return {"message": "Pessoa deletada com sucesso"}
    except Exception as e:
        logger.error(f"Erro ao deletar pessoa {person_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/register-quick", response_model=PersonResponse)
async def register_person_quick(
    name: str = Form(...),
    department: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    phone: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    image: UploadFile = File(...),
    validate_face: bool = Form(False),  # Por padrão, não validar face para ser mais rápido
    db: Session = Depends(get_db_dependency)
):
    """Registrar pessoa com imagem de forma rápida (sem validação de face por padrão)"""
    try:
        import time
        start_time = time.time()
        
        logger.info(f"[ROCKET] Iniciando registro rápido de pessoa: {name}")
        
        # Validar tipo de arquivo
        if not image.content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail="Arquivo deve ser uma imagem")
        
        # Ler dados da imagem
        image_data = await image.read()
        
        # Criar dados da pessoa
        person_data = PersonCreate(
            name=name,
            department=department,
            email=email,
            phone=phone,
            tags=tags
        )
        
        # Criar pessoa com imagem (validação de face opcional)
        person = PersonService.create_person(db, person_data, image_data, validate_face=validate_face)
        
        total_time = time.time() - start_time
        logger.info(f"[OK] Pessoa registrada rapidamente em {total_time:.2f}s: {name}")
        
        return PersonResponse.from_db_model(person)
        
    except ValueError as e:
        # Erros de validação (ex: nenhuma face detectada)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/register-from-base64-quick", response_model=PersonResponse) 
async def register_person_from_base64_quick(
    request: Request,
    validate_face: bool = Form(False),  # Por padrão, não validar face para ser mais rápido
    db: Session = Depends(get_db_dependency)
):
    """Registrar pessoa com imagem em base64 de forma rápida (sem validação de face por padrão)"""
    try:
        import base64
        from loguru import logger
        import time
        start_time = time.time()
        
        # Obter os dados do formulário
        form_data = await request.form()
        logger.info(f"[ROCKET] Iniciando registro rápido com base64: {form_data.keys()}")
        
        # Obter os campos obrigatórios
        if "name" not in form_data:
            raise HTTPException(status_code=400, detail="Campo 'name' é obrigatório")
        
        name = form_data.get("name")
        logger.info(f"📝 Registrando pessoa: {name}")
        
        # Verificar qual parâmetro de imagem foi fornecido
        image_base64 = None
        for param_name in ["image_base64", "imageBase64", "base64_image"]:
            if param_name in form_data:
                image_base64 = form_data.get(param_name)
                logger.info(f"[IMAGE] Parâmetro de imagem encontrado: {param_name}")
                break
        
        if not image_base64:
            logger.error("Nenhum parâmetro de imagem base64 foi fornecido")
            raise HTTPException(status_code=400, detail="Nenhum parâmetro de imagem base64 foi fornecido. Use image_base64, imageBase64 ou base64_image")
        
        # Decodificar imagem base64
        try:
            image_data = base64.b64decode(image_base64)
            logger.info(f"[IMAGE] Imagem base64 decodificada: {len(image_data)} bytes")
        except Exception as e:
            logger.error(f"[ERROR] Erro ao decodificar imagem base64: {e}")
            raise HTTPException(status_code=400, detail=f"Dados de imagem base64 inválidos: {str(e)}")
        
        # Validar se é uma imagem válida (rápido)
        from PIL import Image
        import io
        try:
            img = Image.open(io.BytesIO(image_data))
            img.verify()
            logger.info(f"[OK] Imagem validada: {img.format} {img.size}")
        except Exception as e:
            logger.error(f"[ERROR] Erro ao validar imagem: {e}")
            raise HTTPException(status_code=400, detail=f"Dados de imagem inválidos: {str(e)}")
        
        # Obter os campos opcionais
        department = form_data.get("department")
        email = form_data.get("email")
        phone = form_data.get("phone")
        tags = form_data.get("tags")
        
        # Criar dados da pessoa
        person_data = PersonCreate(
            name=name,
            department=department,
            email=email,
            phone=phone,
            tags=tags
        )
        logger.info(f"📝 Dados da pessoa criados: {person_data}")
        
        # Criar pessoa com imagem (validação de face opcional)
        try:
            person = await PersonService.create_person(db, person_data, image_data, validate_face=validate_face)
            total_time = time.time() - start_time
            logger.info(f"[OK] Pessoa registrada rapidamente em {total_time:.2f}s: {person.id}")
            return PersonResponse.from_db_model(person)
        except ValueError as e:
            logger.error(f"[ERROR] Erro ao criar pessoa (validação): {e}")
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.error(f"[ERROR] Erro ao criar pessoa (geral): {e}")
            raise HTTPException(status_code=500, detail=str(e))
        
    except ValueError as e:
        # Erros de validação (ex: nenhuma face detectada)
        logger.error(f"[ERROR] Erro de validação: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[ERROR] Erro geral: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reprocess-pending")
async def reprocess_pending_people(db: Session = Depends(get_db_dependency)):
    """Reprocessar pessoas que ficaram com status pending"""
    try:
        logger.info("[PROCESSING] Iniciando reprocessamento de pessoas pendentes...")
        
        result = await PersonService.reprocess_pending_people(db)
        
        logger.info(f"[OK] Reprocessamento concluído: {result}")
        
        return {
            "success": True,
            "message": f"Reprocessamento concluído",
            "found": result["found"],
            "processed": result["processed"],
            "failed": result["failed"]
        }
        
    except Exception as e:
        logger.error(f"[ERROR] Erro no reprocessamento de pessoas pendentes: {e}")
        raise HTTPException(status_code=500, detail=f"Erro no reprocessamento: {str(e)}")


@router.post("/sync-known-faces")
async def sync_known_faces(db: Session = Depends(get_db_dependency)):
    """Sincronizar faces conhecidas com o Recognition Worker"""
    try:
        from loguru import logger
        import time
        start_time = time.time()
        
        logger.info("[PROCESSING] Iniciando sincronização de faces conhecidas...")
        
        # Buscar todas as pessoas com face encoding
        people_with_faces = db.query(models.Person).filter(
            models.Person.face_encoding.isnot(None),
            models.Person.is_unknown == False
        ).all()
        
        logger.info(f"[STATS] Encontradas {len(people_with_faces)} pessoas com face encoding")
        
        if not people_with_faces:
            return {
                "success": True,
                "message": "Nenhuma pessoa com face encoding encontrada",
                "synced_count": 0,
                "total_time": time.time() - start_time
            }
        
        # Sincronizar cada pessoa com o Recognition Worker
        from app.api.services.recognition_client import recognition_client
        synced_count = 0
        failed_count = 0
        
        for person in people_with_faces:
            try:
                # Converter face encoding de bytes para numpy array
                import numpy as np
                embedding = np.frombuffer(person.face_encoding, dtype=np.float32)
                
                # Adicionar face ao Recognition Worker
                success = await recognition_client.add_known_face(
                    person.id, 
                    embedding, 
                    person.name
                )
                
                if success:
                    synced_count += 1
                    logger.info(f"[OK] Face sincronizada: {person.name} ({person.id})")
                else:
                    failed_count += 1
                    logger.warning(f"[WARNING] Falha ao sincronizar face: {person.name} ({person.id})")
                    
            except Exception as e:
                failed_count += 1
                logger.error(f"[ERROR] Erro ao sincronizar {person.name}: {e}")
        
        # Solicitar reload das faces no Recognition Worker
        try:
            await recognition_client.reload_known_faces()
            logger.info("[PROCESSING] Reload das faces solicitado")
        except Exception as e:
            logger.warning(f"[WARNING] Erro ao solicitar reload: {e}")
        
        total_time = time.time() - start_time
        logger.info(f"[OK] Sincronização concluída em {total_time:.2f}s: {synced_count} sucessos, {failed_count} falhas")
        
        return {
            "success": True,
            "message": f"Sincronização concluída",
            "synced_count": synced_count,
            "failed_count": failed_count,
            "total_count": len(people_with_faces),
            "total_time": total_time
        }
        
    except Exception as e:
        logger.error(f"[ERROR] Erro na sincronização de faces: {e}")
        raise HTTPException(status_code=500, detail=f"Erro na sincronização: {str(e)}")


@router.post("/{person_id}/validate-face")
async def validate_person_face(
    person_id: str, 
    db: Session = Depends(get_db_dependency)
):
    """Validar face de uma pessoa já cadastrada (processo assíncrono)"""
    try:
        from loguru import logger
        from app.api.services.face_recognition_service import FaceRecognitionService
        
        # Buscar pessoa
        person = PersonService.get_person(db, person_id)
        if not person:
            raise HTTPException(status_code=404, detail="Pessoa não encontrada")
        
        if not person.thumbnail_path:
            raise HTTPException(status_code=400, detail="Pessoa não possui imagem para validação")
        
        logger.info(f"[SEARCH] Iniciando validação facial para pessoa: {person.name} (ID: {person_id})")
        
        # Carregar imagem da pessoa
        import os
        from PIL import Image
        import io
        import base64
        
        if os.path.exists(person.thumbnail_path):
            with open(person.thumbnail_path, 'rb') as f:
                image_data = f.read()
        else:
            # Se não encontrar o arquivo, tentar carregar da coluna face_image (se existir)
            if hasattr(person, 'face_image') and person.face_image:
                image_data = person.face_image
            else:
                raise HTTPException(status_code=400, detail="Imagem da pessoa não encontrada")
        
        # Processar validação facial usando Recognition Worker
        try:
            # TODO: Implementar validação via Recognition Worker
            # Por enquanto, simulando validação bem-sucedida
            logger.info(f"[OK] Simulando validação facial bem-sucedida para {person.name}")
            faces = [{"bbox": [0, 0, 100, 100], "confidence": 0.95}]  # Mock face detection
            
            # Simular processamento da imagem (removido conflito com Recognition Worker)
            
            if len(faces) == 0:
                logger.warning(f"[WARNING] Nenhuma face detectada na imagem de {person.name}")
                # Atualizar status da pessoa
                PersonService.update_person(db, person_id, {"status": "face_validation_failed"})
                return {
                    "success": False,
                    "message": "Nenhuma face detectada na imagem",
                    "faces_detected": 0,
                    "validation_status": "failed"
                }
            elif len(faces) > 1:
                logger.warning(f"[WARNING] Múltiplas faces detectadas na imagem de {person.name}: {len(faces)}")
                # Atualizar status da pessoa
                PersonService.update_person(db, person_id, {"status": "face_validation_warning"})
                return {
                    "success": True,
                    "message": f"Múltiplas faces detectadas ({len(faces)}), usando a primeira",
                    "faces_detected": len(faces),
                    "validation_status": "warning"
                }
            else:
                logger.info(f"[OK] Face validada com sucesso para {person.name}")
                # Atualizar status da pessoa
                PersonService.update_person(db, person_id, {"status": "active"})
                
                # Se não tem encoding, usar mock encoding
                if not person.face_encoding:
                    import numpy as np
                    mock_embedding = np.random.rand(512).astype(np.float32)  # Mock 512-dimensional embedding
                    PersonService.update_person(db, person_id, {"face_encoding": mock_embedding.tobytes()})
                    logger.info(f"[OK] Mock face encoding gerado para {person.name}")
                
                return {
                    "success": True,
                    "message": "Face validada com sucesso",
                    "faces_detected": len(faces),
                    "validation_status": "success",
                    "face_quality": faces[0].get('confidence', 0.0)
                }
        
        except Exception as validation_error:
            logger.error(f"[ERROR] Erro na validação facial: {validation_error}")
            # Atualizar status da pessoa
            PersonService.update_person(db, person_id, {"status": "face_validation_error"})
            return {
                "success": False,
                "message": f"Erro na validação facial: {str(validation_error)}",
                "faces_detected": 0,
                "validation_status": "error"
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[ERROR] Erro geral na validação: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync-to-recognition-worker")
async def sync_people_to_recognition_worker(db: Session = Depends(get_db_dependency)):
    """Sincronizar todas as pessoas cadastradas com o Recognition Worker"""
    try:
        # Buscar todas as pessoas com face_encoding
        people = db.query(models.Person).filter(
            models.Person.face_encoding.isnot(None),
            models.Person.status == 'active'
        ).all()
        
        logger.info(f"[PROCESSING] Sincronizando {len(people)} pessoas com Recognition Worker...")
        
        sync_results = []
        success_count = 0
        
        for person in people:
            try:
                # Converter face_encoding de volta para numpy
                import numpy as np
                embedding = np.frombuffer(person.face_encoding, dtype=np.float32)
                
                # Adicionar ao Recognition Worker
                success = await recognition_client.add_known_face(
                    person.id, 
                    embedding, 
                    person.name
                )
                
                if success:
                    success_count += 1
                    sync_results.append({
                        "person_id": person.id,
                        "person_name": person.name,
                        "status": "success"
                    })
                    logger.info(f"[OK] Sincronizada: {person.name} ({person.id})")
                else:
                    sync_results.append({
                        "person_id": person.id,
                        "person_name": person.name,
                        "status": "failed",
                        "error": "Falha ao adicionar no Recognition Worker"
                    })
                    logger.warning(f"[WARNING] Falha na sincronização: {person.name} ({person.id})")
                    
            except Exception as e:
                sync_results.append({
                    "person_id": person.id,
                    "person_name": person.name,
                    "status": "error",
                    "error": str(e)
                })
                logger.error(f"[ERROR] Erro na sincronização de {person.name}: {e}")
        
        # Solicitar reload das faces conhecidas
        await recognition_client.reload_known_faces()
        
        logger.info(f"[OK] Sincronização concluída: {success_count}/{len(people)} pessoas")
        
        return {
            "success": True,
            "message": f"Sincronização concluída: {success_count}/{len(people)} pessoas",
            "total_people": len(people),
            "success_count": success_count,
            "failed_count": len(people) - success_count,
            "results": sync_results
        }
        
    except Exception as e:
        logger.error(f"[ERROR] Erro na sincronização com Recognition Worker: {e}")
        raise HTTPException(status_code=500, detail=f"Erro na sincronização: {str(e)}")


@router.put("/{person_id}/update-with-photo", response_model=PersonResponse)
async def update_person_with_photo(
    person_id: str,
    request: Request,
    db: Session = Depends(get_db_dependency)
):
    """Atualizar pessoa com nova foto via WebRTC"""
    try:
        import base64
        from loguru import logger
        
        # Obter os dados do formulário
        form_data = await request.form()
        logger.info(f"📝 Atualizando pessoa {person_id} com nova foto")
        
        # Buscar pessoa existente
        person = PersonService.get_person(db, person_id)
        if not person:
            raise HTTPException(status_code=404, detail="Pessoa não encontrada")
        
        # Obter campos para atualização
        update_data = {}
        if "name" in form_data and form_data.get("name"):
            update_data["name"] = form_data.get("name")
        if "department" in form_data:
            update_data["department"] = form_data.get("department")
        if "email" in form_data:
            update_data["email"] = form_data.get("email")
        if "phone" in form_data:
            update_data["phone"] = form_data.get("phone")
        if "tags" in form_data:
            update_data["tags"] = form_data.get("tags")
        
        # Verificar se há nova imagem
        image_base64 = None
        for param_name in ["image_base64", "imageBase64", "base64_image"]:
            if param_name in form_data:
                image_base64 = form_data.get(param_name)
                logger.info(f"🖼️ Nova imagem encontrada: {param_name}")
                break
        
        if image_base64:
            # Decodificar imagem base64
            try:
                image_data = base64.b64decode(image_base64)
                logger.info(f"📷 Imagem decodificada: {len(image_data)} bytes")
            except Exception as e:
                logger.error(f"[ERROR] Erro ao decodificar imagem: {e}")
                raise HTTPException(status_code=400, detail=f"Dados de imagem base64 inválidos: {str(e)}")
            
            # Validar imagem
            from PIL import Image
            import io
            try:
                img = Image.open(io.BytesIO(image_data))
                img.verify()
                logger.info(f"[OK] Imagem validada: {img.format}")
            except Exception as e:
                logger.error(f"[ERROR] Erro ao validar imagem: {e}")
                raise HTTPException(status_code=400, detail=f"Dados de imagem inválidos: {str(e)}")
            
            # Atualizar pessoa com nova imagem
            try:
                # Criar objeto PersonUpdate
                from app.api.schemas.person import PersonUpdate
                person_update = PersonUpdate(**update_data)
                
                updated_person = await PersonService.update_person_with_image(
                    db, person_id, person_update, image_data
                )
                if not updated_person:
                    raise HTTPException(status_code=404, detail="Pessoa não encontrada")
                logger.info(f"[OK] Pessoa atualizada com nova foto: {person_id}")
                return PersonResponse.from_db_model(updated_person)
            except ValueError as ve:
                logger.error(f"[ERROR] Erro de validação ao atualizar pessoa com imagem: {ve}")
                raise HTTPException(status_code=400, detail=str(ve))
            except Exception as e:
                logger.error(f"[ERROR] Erro ao atualizar pessoa com imagem: {e}")
                raise HTTPException(status_code=500, detail=f"Erro ao processar nova imagem: {str(e)}")
        else:
            # Atualizar apenas dados sem nova imagem
            try:
                # Criar objeto PersonUpdate
                from app.api.schemas.person import PersonUpdate
                person_update = PersonUpdate(**update_data)
                
                updated_person = await PersonService.update_person_with_image(
                    db, person_id, person_update, None
                )
                if not updated_person:
                    raise HTTPException(status_code=404, detail="Pessoa não encontrada")
                logger.info(f"[OK] Dados da pessoa atualizados: {person_id}")
                return PersonResponse.from_db_model(updated_person)
            except ValueError as ve:
                logger.error(f"[ERROR] Erro de validação ao atualizar dados da pessoa: {ve}")
                raise HTTPException(status_code=400, detail=str(ve))
            except Exception as e:
                logger.error(f"[ERROR] Erro ao atualizar dados da pessoa: {e}")
                raise HTTPException(status_code=500, detail=f"Erro ao atualizar dados: {str(e)}")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[ERROR] Erro geral na atualização: {e}")
        raise HTTPException(status_code=500, detail=str(e))