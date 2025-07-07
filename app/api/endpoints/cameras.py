"""
Camera management endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List, Optional
import asyncio
import cv2
import numpy as np
import base64
from datetime import datetime, timedelta
from loguru import logger
import json
import threading
import time
from functools import lru_cache
from cachetools import TTLCache

from app.database.database import get_db, get_db_dependency
from app.database import models
from app.api.schemas.camera import (
    CameraCreate, CameraUpdate, CameraResponse, CameraList, CameraStats, CameraStatus
)
from app.api.services.camera_service import CameraService
from app.api.services.gstreamer_service import gstreamer_api_service as gstreamer_service
from app.api.services.config_sync_service import config_sync_service
from app.api.services.camera_validation_service import camera_validation_service

router = APIRouter()
camera_service = CameraService()

# Cache para snapshots (TTL de 2 segundos)
snapshot_cache = TTLCache(maxsize=50, ttl=2.0)
snapshot_cache_lock = threading.Lock()


@router.get("/")
@router.get("")
async def get_cameras(
    skip: int = Query(0, ge=0, description="Número de registros para pular"),
    limit: int = Query(50, ge=1, le=1000, description="Limite de registros"),
    status: Optional[str] = Query(None, description="Filtrar por status"),
    camera_type: Optional[str] = Query(None, description="Filtrar por tipo"),
    db: Session = Depends(get_db_dependency)
):
    """Listar câmeras com filtros opcionais"""
    try:
        logger.debug(f"Buscando câmeras: skip={skip}, limit={limit}, status={status}, type={camera_type}")
        
        try:
            # Usar uma consulta SQL mais básica para evitar problemas com colunas ausentes
            query = db.query(models.Camera)
            
            # Aplicar filtros apenas em colunas que certamente existem
            if status:
                query = query.filter(models.Camera.status == status)
            
            if camera_type:
                query = query.filter(models.Camera.type == camera_type)
            
            # Obter total de câmeras
            total = query.count()
            
            # Aplicar paginação
            cameras = query.offset(skip).limit(limit).all()
            
            # DEBUG: Log detalhado das câmeras encontradas
            logger.info(f"[DEBUG] Câmeras encontradas no banco: {len(cameras)}")
            for cam in cameras:
                logger.info(f"[DEBUG] Câmera do banco: ID={cam.id}, Nome={cam.name}, Status={cam.status}")
            
        except Exception as query_error:
            logger.error(f"Erro na consulta SQL: {query_error}")
            # Fallback: retornar lista vazia em caso de erro com o banco
            cameras = []
            total = 0
        
        logger.debug(f"Câmeras encontradas: {len(cameras)}, total: {total}")
        
        # Contar câmeras por status
        try:
            active_count = db.query(models.Camera).filter(models.Camera.status == "active").count()
            inactive_count = db.query(models.Camera).filter(models.Camera.status == "inactive").count()
            error_count = db.query(models.Camera).filter(models.Camera.status == "error").count()
            logger.debug(f"Contagens: active={active_count}, inactive={inactive_count}, error={error_count}")
        except Exception as count_error:
            logger.error(f"Erro ao contar câmeras por status: {count_error}")
            active_count = 0
            inactive_count = 0
            error_count = 0
        
        # Construir resposta simplificada
        try:
            camera_responses = []
            for camera in cameras:
                try:
                    logger.info(f"[DEBUG] Convertendo câmera: ID={camera.id}, Nome={camera.name}")
                    # Usar from_db_model simplificado
                    camera_response = CameraResponse.from_db_model(camera)
                    logger.info(f"[DEBUG] Câmera convertida: ID={camera_response.id}, Nome={camera_response.name}")
                    camera_responses.append(camera_response)
                except Exception as cam_error:
                    logger.error(f"Erro ao converter câmera {camera.id}: {cam_error}")
                    # Fallback: adicionar dados básicos manualmente com valores padrão
                    camera_responses.append({
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
                        "created_at": camera.created_at,
                        "updated_at": camera.updated_at
                    })
            
            logger.info(f"Retornando {len(camera_responses)} câmeras para o frontend")
            
            # DEBUG: Log das câmeras na resposta final
            for i, cam_resp in enumerate(camera_responses):
                cam_id = cam_resp.id if hasattr(cam_resp, 'id') else cam_resp.get('id', 'N/A')
                cam_name = cam_resp.name if hasattr(cam_resp, 'name') else cam_resp.get('name', 'N/A')
                logger.info(f"[DEBUG] Resposta[{i}]: ID={cam_id}, Nome={cam_name}")
            
            response = {
                "cameras": camera_responses,
                "total": total,
                "active": active_count,
                "inactive": inactive_count,
                "error": error_count
            }
            return response
        except Exception as resp_error:
            logger.error(f"Erro ao construir resposta: {resp_error}")
            raise
        
    except Exception as e:
        logger.error(f"Erro ao buscar câmeras: {e}")
        logger.exception("Detalhes do erro:")
        
        # Fallback para manter o frontend funcionando
        return {
            "cameras": [],
            "total": 0,
            "active": 0,
            "inactive": 0,
            "error": 0
        }


@router.get("/debug")
async def debug_cameras(db: Session = Depends(get_db_dependency)):
    """Debug: listar todas as câmeras no banco"""
    try:
        cameras = db.query(models.Camera).all()
        result = []
        for camera in cameras:
            result.append({
                "id": camera.id,
                "name": camera.name,
                "url": camera.url,
                "status": camera.status,
                "type": camera.type
            })
        return {
            "total_cameras": len(cameras),
            "cameras": result
        }
    except Exception as e:
        return {"error": str(e)}

@router.get("/stats", response_model=CameraStats)
async def get_camera_stats(db: Session = Depends(get_db_dependency)):
    """Obter estatísticas de câmeras"""
    try:
        stats = CameraService.get_camera_stats(db)
        return CameraStats(**stats)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/active")
async def get_active_cameras(db: Session = Depends(get_db_dependency)):
    """Obter câmeras ativas para o camera worker e WebRTC"""
    try:
        cameras = CameraService.get_active_cameras(db)
        result = []
        
        for camera in cameras:
            camera_data = {
                "id": camera.id,
                "camera_id": camera.id,  # Para compatibilidade com WebRTC
                "name": camera.name,
                "url": camera.url,
                "rtsp_url": camera.url,  # Para compatibilidade com WebRTC
                "fps_limit": camera.fps_limit,
                "type": camera.type,
                "resolution_width": camera.resolution_width,
                "resolution_height": camera.resolution_height,
                "status": camera.status,
                "location": camera.location
            }
            result.append(camera_data)
        
        logger.info(f"Retornando {len(result)} câmeras ativas para WebRTC")
        return result
        
    except Exception as e:
        logger.error(f"Erro ao obter câmeras ativas: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{camera_id}", response_model=CameraResponse)
async def get_camera(camera_id: str, db: Session = Depends(get_db_dependency)):
    """Buscar câmera por ID"""
    camera = CameraService.get_camera(db, camera_id)
    if not camera:
        raise HTTPException(status_code=404, detail="Câmera não encontrada")
    return CameraResponse.from_db_model(camera)


@router.post("/simple", response_model=CameraResponse)
async def create_camera_simple(
    camera_data: CameraCreate,
    db: Session = Depends(get_db_dependency)
):
    """Criar nova câmera de forma simples (sem validações complexas)"""
    try:
        logger.info(f"Criando câmera simples: {camera_data.name}")
        
        # Criar câmera diretamente no banco
        camera = CameraService.create_camera(db, camera_data)
        logger.info(f"Câmera criada com sucesso: {camera.id}")
        
        return CameraResponse.from_db_model(camera)
        
    except Exception as e:
        logger.error(f"Erro ao criar câmera simples: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao criar câmera: {str(e)}")


@router.post("/upload-video", response_model=CameraResponse)
async def upload_video_camera(
    file: UploadFile = File(...),
    name: str = Form(...),
    location: str = Form(""),
    description: str = Form(""),
    fps_limit: int = Form(30),
    db: Session = Depends(get_db_dependency)
):
    """Upload de vídeo MP4 para criar uma câmera baseada em arquivo"""
    import os
    import uuid
    from pathlib import Path
    
    try:
        logger.info(f"Upload de vídeo iniciado: {file.filename}")
        
        # Verificar tipo de arquivo
        if not file.filename.lower().endswith(('.mp4', '.avi', '.mov')):
            raise HTTPException(status_code=400, detail="Formato de arquivo não suportado. Use MP4, AVI ou MOV.")
        
        # Criar diretório de uploads se não existir
        upload_dir = Path("data/videos")
        upload_dir.mkdir(parents=True, exist_ok=True)
        
        # Manter nome original mas adicionar timestamp para evitar conflitos
        file_extension = Path(file.filename).suffix
        safe_filename = f"{name.replace(' ', '_')}_{int(time.time())}{file_extension}"
        file_path = upload_dir / safe_filename
        
        # Salvar arquivo
        logger.info(f"Salvando vídeo em: {file_path}")
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        
        # Verificar se arquivo foi salvo
        if not file_path.exists():
            raise HTTPException(status_code=500, detail="Falha ao salvar arquivo de vídeo")
        
        # Obter tamanho do arquivo
        file_size = file_path.stat().st_size
        logger.info(f"Vídeo salvo com sucesso: {file_size} bytes")
        
        # Converter caminho WSL para Windows (para compatibilidade com WebRTC Server)
        file_path_str = str(file_path.absolute())
        
        # Se estamos no WSL, converter /mnt/d/... para D:\...
        if file_path_str.startswith('/mnt/'):
            # /mnt/d/path -> D:\path
            drive_letter = file_path_str.split('/')[2].upper()
            windows_path = file_path_str.replace(f'/mnt/{drive_letter.lower()}', f'{drive_letter}:').replace('/', '\\')
            logger.info(f"Convertendo caminho WSL para Windows: {file_path_str} -> {windows_path}")
            file_path_for_camera = windows_path
        else:
            # Já é um caminho Windows ou absoluto
            file_path_for_camera = file_path_str
        
        # Criar dados da câmera
        camera_data = CameraCreate(
            name=name,
            url=file_path_for_camera,  # Caminho convertido para Windows
            type="video",  # Novo tipo para vídeos
            location=location,
            description=f"{description} (Arquivo: {file.filename})",
            fps_limit=fps_limit,
            fps=30,  # Padrão para vídeos
            resolution_width=1280,  # Será detectado automaticamente
            resolution_height=720
        )
        
        # Criar câmera no banco
        camera = CameraService.create_camera(db, camera_data)
        logger.info(f"Câmera de vídeo criada com sucesso: {camera.id}")
        
        return CameraResponse.from_db_model(camera)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao fazer upload de vídeo: {e}")
        # Limpar arquivo se houver erro
        if 'file_path' in locals() and file_path.exists():
            try:
                file_path.unlink()
            except:
                pass
        raise HTTPException(status_code=500, detail=f"Erro ao processar vídeo: {str(e)}")


@router.post("/", response_model=CameraResponse)
async def create_camera(
    camera_data: CameraCreate, 
    validate: bool = Query(False, description="Executar validação robusta antes de criar"),
    validation_type: str = Query("basic", description="Tipo de validação: basic, full, performance"),
    db: Session = Depends(get_db_dependency)
):
    """Criar nova câmera com validação simples e prática (padrão: sem validação robusta)"""
    try:
        validation_result = None
        
        if validate:
            logger.info(f"Executando validação {validation_type} para nova câmera: {camera_data.url}")
            
            # Extrair credenciais se presentes na URL
            username = getattr(camera_data, 'username', None)
            password = getattr(camera_data, 'password', None)
            
            # Executar validação robusta
            validation_result = await camera_validation_service.validate_camera_comprehensive(
                url=camera_data.url,
                username=username,
                password=password,
                test_type=validation_type
            )
            
            # Verificar se validação passou
            if not validation_result.success:
                error_details = {
                    "message": "Falha na validação da câmera",
                    "errors": validation_result.errors,
                    "warnings": validation_result.warnings,
                    "suggestions": validation_result.suggested_settings
                }
                raise HTTPException(
                    status_code=400, 
                    detail=error_details
                )
            
            # Log da qualidade da conexão
            logger.info(f"Validação bem-sucedida - Qualidade: {validation_result.connection_quality:.2f}")
        
        # Gerar ID para nova câmera
        import uuid
        camera_id = str(uuid.uuid4())
        
        # Enriquecer dados da câmera com informações da validação
        if validation_result:
            # Atualizar dados com métricas descobertas
            if "actual_resolution" in validation_result.capabilities:
                res = validation_result.capabilities["actual_resolution"]
                camera_data.resolution_width = res.get("width", camera_data.resolution_width)
                camera_data.resolution_height = res.get("height", camera_data.resolution_height)
            
            if "fps" in validation_result.capabilities:
                camera_data.fps = int(validation_result.capabilities["fps"])
        
        # Criar câmera no banco com valores padrão seguros
        try:
            camera = CameraService.create_camera(db, camera_data, camera_id)
            logger.info(f"Câmera criada no banco com ID: {camera.id}")
        except Exception as db_error:
            logger.error(f"Erro ao criar câmera no banco: {db_error}")
            raise HTTPException(status_code=500, detail=f"Erro ao salvar câmera no banco: {str(db_error)}")
        
        # Salvar resultados da validação se disponível (não crítico)
        if validation_result:
            try:
                # Atualizar campos de performance no banco (com verificação de existência)
                if hasattr(camera, 'connection_quality'):
                    camera.connection_quality = validation_result.connection_quality
                if hasattr(camera, 'last_connection_test'):
                    camera.last_connection_test = datetime.now()
                if hasattr(camera, 'connection_test_result'):
                    camera.connection_test_result = json.dumps(validation_result.to_dict())
                
                # Atualizar métricas se disponíveis
                if "avg_latency_ms" in validation_result.metrics and hasattr(camera, 'latency_ms'):
                    camera.latency_ms = int(validation_result.metrics["avg_latency_ms"])
                
                if "fps_measured" in validation_result.metrics and hasattr(camera, 'actual_fps'):
                    camera.actual_fps = validation_result.metrics["fps_measured"]
                
                # Atualizar capacidades se detectadas
                if validation_result.capabilities and hasattr(camera, 'config'):
                    camera.config = json.dumps(validation_result.capabilities)
                
                db.commit()
                logger.info(f"Dados de validação salvos para câmera {camera.id}")
                
            except Exception as save_error:
                logger.warning(f"Erro ao salvar dados de validação (não crítico): {save_error}")
                # Não falhar a criação da câmera por isso
        
        response = CameraResponse.from_db_model(camera)
        
        # Adicionar informações de validação à resposta
        if validation_result:
            response_dict = response.dict()
            response_dict["validation_result"] = {
                "success": validation_result.success,
                "connection_quality": validation_result.connection_quality,
                "test_duration": validation_result.test_duration,
                "metrics": validation_result.metrics,
                "capabilities": validation_result.capabilities,
                "warnings": validation_result.warnings
            }
            return response_dict
        
        return response
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao criar câmera: {e}")
        raise HTTPException(status_code=500, detail="Erro interno do servidor")


@router.post("/{camera_id}/test")
async def test_camera_connection(
    camera_id: str, 
    test_type: str = Query("basic", description="Tipo de teste: basic, full, performance, stress"),
    db: Session = Depends(get_db_dependency)
):
    """Testar conexão com câmera usando validação robusta"""
    try:
        camera = CameraService.get_camera(db, camera_id)
        if not camera:
            raise HTTPException(status_code=404, detail="Câmera não encontrada")
        
        logger.info(f"Executando teste {test_type} para câmera {camera_id}")
        
        # Extrair credenciais se disponíveis
        username = getattr(camera, 'username', None)
        password = getattr(camera, 'password', None)
        
        # Executar validação robusta
        validation_result = await camera_validation_service.validate_camera_comprehensive(
            url=camera.url,
            username=username,
            password=password,
            test_type=test_type
        )
        
        # Salvar resultado do teste no banco
        try:
            camera.connection_quality = validation_result.connection_quality
            camera.last_connection_test = datetime.now()
            camera.connection_test_result = json.dumps(validation_result.to_dict())
            
            # Atualizar status baseado no resultado
            if validation_result.success:
                if validation_result.connection_quality > 0.8:
                    camera.status = "active"
                elif validation_result.connection_quality > 0.5:
                    camera.status = "active"  # Mas com qualidade baixa
                else:
                    camera.status = "error"
            else:
                camera.status = "error"
                camera.last_error = str(validation_result.errors[0]["message"]) if validation_result.errors else "Teste de conexão falhou"
            
            # Atualizar métricas se disponíveis
            if "avg_latency_ms" in validation_result.metrics:
                camera.latency_ms = int(validation_result.metrics["avg_latency_ms"])
            
            if "fps_measured" in validation_result.metrics:
                camera.actual_fps = validation_result.metrics["fps_measured"]
            
            db.commit()
            
        except Exception as save_error:
            logger.warning(f"Erro ao salvar resultado do teste: {save_error}")
        
        return {
            "camera_id": camera_id,
            "test_type": test_type,
            "success": validation_result.success,
            "connection_quality": validation_result.connection_quality,
            "test_duration": validation_result.test_duration,
            "metrics": validation_result.metrics,
            "capabilities": validation_result.capabilities,
            "errors": validation_result.errors,
            "warnings": validation_result.warnings,
            "suggestions": validation_result.suggested_settings,
            "tested_at": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao testar conexão da câmera {camera_id}: {e}")
        raise HTTPException(status_code=500, detail="Erro interno do servidor")


@router.post("/validate")
async def validate_camera_before_creation(
    url: str = Query(..., description="URL da câmera para validar"),
    username: Optional[str] = Query(None, description="Usuário para autenticação"),
    password: Optional[str] = Query(None, description="Senha para autenticação"),
    test_type: str = Query("full", description="Tipo de validação: basic, full, performance, stress")
):
    """Validar câmera antes de criar (sem salvar no banco)"""
    try:
        logger.info(f"Validando câmera antes da criação: {url}")
        
        # Executar validação robusta
        validation_result = await camera_validation_service.validate_camera_comprehensive(
            url=url,
            username=username,
            password=password,
            test_type=test_type
        )
        
        return {
            "url": url,
            "validation_type": test_type,
            "success": validation_result.success,
            "connection_quality": validation_result.connection_quality,
            "test_duration": validation_result.test_duration,
            "metrics": validation_result.metrics,
            "capabilities": validation_result.capabilities,
            "errors": validation_result.errors,
            "warnings": validation_result.warnings,
            "suggestions": validation_result.suggested_settings,
            "recommended_settings": {
                "resolution": validation_result.capabilities.get("actual_resolution"),
                "fps": validation_result.capabilities.get("fps"),
                "codec": validation_result.capabilities.get("supported_codecs")
            },
            "validated_at": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Erro ao validar câmera: {e}")
        raise HTTPException(status_code=500, detail="Erro interno do servidor")


@router.get("/{camera_id}/validation/history")
async def get_camera_validation_history(
    camera_id: str,
    limit: int = Query(10, ge=1, le=50, description="Número de registros"),
    db: Session = Depends(get_db_dependency)
):
    """Obter histórico de validações da câmera"""
    try:
        camera = CameraService.get_camera(db, camera_id)
        if not camera:
            raise HTTPException(status_code=404, detail="Câmera não encontrada")
        
        # Buscar logs de testes de conexão (da nova tabela quando estiver criada)
        # Por enquanto, retornar o último resultado de teste
        history = []
        
        if camera.connection_test_result:
            try:
                last_test = json.loads(camera.connection_test_result)
                history.append({
                    "test_date": camera.last_connection_test.isoformat() if camera.last_connection_test else None,
                    "result": last_test
                })
            except:
                pass
        
        return {
            "camera_id": camera_id,
            "validation_history": history,
            "total_tests": len(history)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao buscar histórico de validação: {e}")
        raise HTTPException(status_code=500, detail="Erro interno do servidor")


@router.get("/{camera_id}/metrics")
async def get_camera_metrics(camera_id: str, db: Session = Depends(get_db_dependency)):
    """Obter métricas detalhadas da câmera"""
    try:
        camera = CameraService.get_camera(db, camera_id)
        if not camera:
            raise HTTPException(status_code=404, detail="Câmera não encontrada")
        
        # Compilar métricas da câmera
        metrics = {
            "camera_id": camera_id,
            "name": camera.name,
            "status": camera.status,
            "connection_quality": camera.connection_quality,
            "last_test": camera.last_connection_test.isoformat() if camera.last_connection_test else None,
            "performance": {
                "actual_fps": camera.actual_fps,
                "latency_ms": camera.latency_ms,
                "packet_loss_percent": camera.packet_loss_percent,
                "bandwidth_mbps": camera.bandwidth_mbps
            },
            "configuration": {
                "resolution": f"{camera.resolution_width}x{camera.resolution_height}",
                "fps_limit": camera.fps_limit,
                "codec": camera.codec,
                "transport": camera.rtsp_transport
            },
            "health": {
                "is_healthy": camera.is_healthy,
                "error_count": camera.error_count,
                "last_error": camera.last_error,
                "last_frame_at": camera.last_frame_at.isoformat() if camera.last_frame_at else None
            }
        }
        
        # Adicionar capacidades se disponíveis
        if camera.config:
            try:
                capabilities = json.loads(camera.config)
                metrics["capabilities"] = capabilities
            except:
                pass
        
        return metrics
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao buscar métricas da câmera: {e}")
        raise HTTPException(status_code=500, detail="Erro interno do servidor")


@router.post("/{camera_id}/optimize")
async def optimize_camera_settings(camera_id: str, db: Session = Depends(get_db_dependency)):
    """Gerar sugestões de otimização para a câmera"""
    try:
        camera = CameraService.get_camera(db, camera_id)
        if not camera:
            raise HTTPException(status_code=404, detail="Câmera não encontrada")
        
        # Executar teste de performance para obter sugestões
        validation_result = await camera_validation_service.validate_camera_comprehensive(
            url=camera.url,
            username=getattr(camera, 'username', None),
            password=getattr(camera, 'password', None),
            test_type="performance"
        )
        
        # Gerar recomendações específicas
        recommendations = {
            "current_performance": {
                "connection_quality": validation_result.connection_quality,
                "avg_latency": validation_result.metrics.get("avg_latency_ms"),
                "fps_measured": validation_result.metrics.get("fps_measured"),
                "frame_drop_rate": validation_result.metrics.get("frame_drop_rate")
            },
            "optimization_suggestions": validation_result.suggested_settings,
            "recommended_changes": []
        }
        
        # Sugestões específicas baseadas nas métricas
        if validation_result.connection_quality < 0.7:
            recommendations["recommended_changes"].append({
                "setting": "resolution",
                "current": f"{camera.resolution_width}x{camera.resolution_height}",
                "suggested": "1280x720",
                "reason": "Reduzir resolução pode melhorar estabilidade"
            })
        
        if validation_result.metrics.get("avg_latency_ms", 0) > 500:
            recommendations["recommended_changes"].append({
                "setting": "fps_limit",
                "current": camera.fps_limit,
                "suggested": max(5, camera.fps_limit - 5),
                "reason": "Reduzir FPS pode diminuir latência"
            })
        
        return recommendations
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao otimizar configurações da câmera: {e}")
        raise HTTPException(status_code=500, detail="Erro interno do servidor")


@router.put("/{camera_id}", response_model=CameraResponse)
async def update_camera(
    camera_id: str, 
    camera_data: CameraUpdate,
    validate: bool = Query(True, description="Executar validação robusta ao alterar URL/tipo"),
    validation_type: str = Query("basic", description="Tipo de validação: basic, full, performance"),
    db: Session = Depends(get_db_dependency)
):
    """Atualizar câmera com validação robusta opcional"""
    try:
        # Verificar se câmera existe
        camera = CameraService.get_camera(db, camera_id)
        if not camera:
            raise HTTPException(status_code=404, detail="Câmera não encontrada")
        
        validation_result = None
        
        # Se URL ou tipo mudaram e validação está habilitada, usar validação robusta
        if validate and (camera_data.url or camera_data.type):
            test_url = camera_data.url or camera.url
            test_type = camera_data.type or camera.type
            
            logger.info(f"Executando validação {validation_type} para atualização da câmera {camera_id}")
            
            # Extrair credenciais se disponíveis
            username = getattr(camera, 'username', None)
            password = getattr(camera, 'password', None)
            
            # Executar validação robusta
            validation_result = await camera_validation_service.validate_camera_comprehensive(
                url=test_url,
                username=username,
                password=password,
                test_type=validation_type
            )
            
            # Verificar se validação passou
            if not validation_result.success:
                error_details = {
                    "message": "Falha na validação da nova configuração da câmera",
                    "errors": validation_result.errors,
                    "warnings": validation_result.warnings,
                    "suggestions": validation_result.suggested_settings
                }
                raise HTTPException(
                    status_code=400, 
                    detail=error_details
                )
            
            # Log da qualidade da conexão
            logger.info(f"Validação de atualização bem-sucedida - Qualidade: {validation_result.connection_quality:.2f}")
            
            # Enriquecer dados com informações da validação
            if "actual_resolution" in validation_result.capabilities:
                res = validation_result.capabilities["actual_resolution"]
                if not camera_data.resolution_width:
                    camera_data.resolution_width = res.get("width", camera.resolution_width)
                if not camera_data.resolution_height:
                    camera_data.resolution_height = res.get("height", camera.resolution_height)
            
            if "fps" in validation_result.capabilities and not camera_data.fps:
                camera_data.fps = int(validation_result.capabilities["fps"])
        
        # Preparar configuração atualizada
        updated_config = {
            'id': camera_id,
            'name': camera_data.name or camera.name,
            'url': camera_data.url or camera.url,
            'type': camera_data.type or camera.type,
            'fps_limit': camera_data.fps_limit or camera.fps_limit,
            'enabled': (camera_data.status == 'active') if camera_data.status else (camera.status == 'active')
        }
        
        # Atualizar via serviço de sincronização
        success = await config_sync_service.update_camera_config(camera_id, updated_config)
        
        if not success:
            raise HTTPException(
                status_code=500, 
                detail="Erro ao atualizar câmera no sistema"
            )
        
        # Atualizar câmera no banco
        camera = CameraService.update_camera(db, camera_id, camera_data)
        
        # Salvar resultados da validação se disponível
        if validation_result:
            try:
                # Atualizar campos de performance no banco
                camera.connection_quality = validation_result.connection_quality
                camera.last_connection_test = datetime.now()
                camera.connection_test_result = json.dumps(validation_result.to_dict())
                
                # Atualizar métricas se disponíveis
                if "avg_latency_ms" in validation_result.metrics:
                    camera.latency_ms = int(validation_result.metrics["avg_latency_ms"])
                
                if "fps_measured" in validation_result.metrics:
                    camera.actual_fps = validation_result.metrics["fps_measured"]
                
                # Atualizar capacidades se detectadas
                if validation_result.capabilities:
                    current_config = json.loads(camera.config) if camera.config else {}
                    current_config.update(validation_result.capabilities)
                    camera.config = json.dumps(current_config)
                
                db.commit()
                logger.info(f"Dados de validação de atualização salvos para câmera {camera.id}")
                
            except Exception as save_error:
                logger.warning(f"Erro ao salvar dados de validação de atualização: {save_error}")
                # Não falhar a atualização da câmera por isso
        
        response = CameraResponse.from_db_model(camera)
        
        # Adicionar informações de validação à resposta se disponível
        if validation_result:
            response_dict = response.dict()
            response_dict["validation_result"] = {
                "success": validation_result.success,
                "connection_quality": validation_result.connection_quality,
                "test_duration": validation_result.test_duration,
                "metrics": validation_result.metrics,
                "capabilities": validation_result.capabilities,
                "warnings": validation_result.warnings
            }
            return response_dict
        
        return response
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao atualizar câmera {camera_id}: {e}")
        raise HTTPException(status_code=500, detail="Erro interno do servidor")


@router.get("/{camera_id}/stream")
async def stream_camera(camera_id: str, db: Session = Depends(get_db_dependency)):
    """Stream de vídeo da câmera usando GStreamer"""
    try:
        from fastapi.responses import StreamingResponse
        
        # Buscar câmera
        camera = CameraService.get_camera(db, camera_id)
        if not camera:
            raise HTTPException(status_code=404, detail="Câmera não encontrada")
        
        if camera.status != "active":
            raise HTTPException(status_code=400, detail="Câmera não está ativa")
        
        # Iniciar stream GStreamer (com fallback)
        try:
            stream_result = gstreamer_service.start_stream(camera)
            if not stream_result.get('success', False):
                raise Exception("GStreamer stream generator failed")
        except Exception as e:
            logger.warning(f"GStreamer stream failed for camera {camera_id}: {e}")
            raise HTTPException(status_code=503, detail="Streaming temporariamente indisponível - GStreamer não acessível")
        
        async def generate_frames():
            try:
                async for frame_data in stream_generator.generate_frames():
                    yield frame_data
            except Exception as e:
                logger.error(f"Erro no stream da câmera {camera_id}: {e}")
            finally:
                stream_generator.stop()
        
        return StreamingResponse(
            generate_frames(),
            media_type="multipart/x-mixed-replace; boundary=frame"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{camera_id}/snapshot")
async def get_camera_snapshot(camera_id: str, db: Session = Depends(get_db_dependency)):
    """Snapshot desabilitado - use WebRTC stream"""
    return {"message": "Snapshot desabilitado - use WebRTC stream para visualização", "status": "disabled"}

@router.get("/{camera_id}/snapshot_old")
async def get_camera_snapshot_old(camera_id: str, db: Session = Depends(get_db_dependency)):
    """Snapshot antigo (fallback se necessário)"""
    try:
        from fastapi.responses import Response
        
        # Verificar cache primeiro
        with snapshot_cache_lock:
            cached_snapshot = snapshot_cache.get(camera_id)
            if cached_snapshot:
                return Response(content=cached_snapshot, media_type="image/jpeg")
        
        # Buscar câmera
        camera = CameraService.get_camera(db, camera_id)
        if not camera:
            raise HTTPException(status_code=404, detail="Câmera não encontrada")
        
        if camera.status != "active":
            raise HTTPException(status_code=400, detail="Câmera não está ativa")
        
        # Capturar snapshot usando fallback otimizado (OpenCV com timeout)
        try:
            # Timeout de 2 segundos para captura
            import threading
            import time
            
            snapshot_data = None
            exception_occurred = None
            
            def capture_with_timeout():
                nonlocal snapshot_data, exception_occurred
                try:
                    if camera.type == "webcam":
                        cap = cv2.VideoCapture(int(camera.url) if camera.url.isdigit() else 0)
                    else:
                        cap = cv2.VideoCapture(camera.url)
                    
                    # Configurar timeout e buffer mínimo
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                    
                    if not cap.isOpened():
                        raise Exception("Não foi possível conectar à câmera")
                    
                    ret, frame = cap.read()
                    cap.release()
                    
                    if not ret:
                        raise Exception("Não foi possível capturar frame")
                    
                    # Converter para JPEG com qualidade otimizada
                    _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
                    snapshot_data = buffer.tobytes()
                    
                except Exception as e:
                    exception_occurred = e
            
            # Executar captura com timeout
            capture_thread = threading.Thread(target=capture_with_timeout)
            capture_thread.start()
            capture_thread.join(timeout=2.0)  # 2 segundos timeout
            
            if capture_thread.is_alive():
                # Thread ainda rodando - timeout
                raise HTTPException(status_code=408, detail="Timeout ao capturar snapshot")
            
            if exception_occurred:
                raise exception_occurred
            
            if snapshot_data is None:
                raise HTTPException(status_code=500, detail="Falha ao capturar snapshot")
                
        except Exception as fallback_error:
            logger.error(f"OpenCV snapshot failed: {fallback_error}")
            raise HTTPException(status_code=500, detail="Não foi possível capturar snapshot da câmera")
        
        # Armazenar no cache
        with snapshot_cache_lock:
            snapshot_cache[camera_id] = snapshot_data
        
        return Response(content=snapshot_data, media_type="image/jpeg")
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{camera_id}/status")
async def update_camera_status(
    camera_id: str,
    status: str = Query(..., description="Novo status: active, inactive, error"),
    db: Session = Depends(get_db_dependency)
):
    """Atualizar status da câmera"""
    try:
        if status not in ["active", "inactive", "error"]:
            raise HTTPException(status_code=400, detail="Status inválido")
        
        CameraService.update_camera_status(db, camera_id, status)
        return {"message": f"Status da câmera atualizado para {status}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{camera_id}/capture")
async def capture_from_camera(camera_id: str, db: Session = Depends(get_db_dependency)):
    """Capturar foto da câmera para registro de pessoa usando GStreamer"""
    try:
        import base64
        from fastapi.responses import JSONResponse
        
        # Buscar câmera
        camera = CameraService.get_camera(db, camera_id)
        if not camera:
            raise HTTPException(status_code=404, detail="Câmera não encontrada")
        
        # Capturar frame usando GStreamer (com fallback OpenCV)
        try:
            frame = gstreamer_service.get_frame(camera)
            if frame is None:
                raise Exception("GStreamer frame capture failed")
        except Exception as gstreamer_error:
            # Fallback para OpenCV
            logger.warning(f"GStreamer capture failed, using OpenCV fallback: {gstreamer_error}")
            
            try:
                if camera.type == "webcam":
                    cap = cv2.VideoCapture(int(camera.url) if camera.url.isdigit() else 0)
                else:
                    cap = cv2.VideoCapture(camera.url)
                
                if not cap.isOpened():
                    raise HTTPException(status_code=500, detail="Não foi possível conectar à câmera")
                
                # Capturar múltiplos frames para estabilizar
                for _ in range(5):
                    ret, frame = cap.read()
                    if not ret:
                        raise HTTPException(status_code=500, detail="Não foi possível capturar frame")
                
                cap.release()
                
            except Exception as opencv_error:
                logger.error(f"Both GStreamer and OpenCV capture failed: {opencv_error}")
                raise HTTPException(status_code=500, detail="Não foi possível capturar frame da câmera")
        
        # Redimensionar para tamanho menor para evitar HTTP 431
        if frame.shape[1] > 640:
            height = int(frame.shape[0] * 640 / frame.shape[1])
            frame = cv2.resize(frame, (640, height))
        
        # Converter para JPEG com qualidade menor para reduzir tamanho
        _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 60])
        frame_bytes = buffer.tobytes()
        
        # Verificar tamanho do frame para evitar HTTP 431
        if len(frame_bytes) > 1000000:  # 1MB limit
            # Redimensionar ainda mais se necessário
            height = int(frame.shape[0] * 480 / frame.shape[1])
            frame = cv2.resize(frame, (480, height))
            _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 50])
            frame_bytes = buffer.tobytes()
        
        # Converter para base64 para retornar
        frame_base64 = base64.b64encode(frame_bytes).decode('utf-8')
        
        return {
            "success": True,
            "image_data": frame_base64,
            "image_format": "jpeg",
            "camera_id": camera_id,
            "camera_name": camera.name,
            "timestamp": models.get_current_timestamp().isoformat(),
            "image_size": len(frame_bytes)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{camera_id}")
async def delete_camera(camera_id: str, db: Session = Depends(get_db_dependency)):
    """Deletar câmera"""
    try:
        # Verificar se câmera existe
        camera = CameraService.get_camera(db, camera_id)
        if not camera:
            raise HTTPException(status_code=404, detail="Câmera não encontrada")
        
        # Remover via serviço de sincronização
        success = await config_sync_service.remove_camera_config(camera_id)
        
        if not success:
            raise HTTPException(
                status_code=500, 
                detail="Erro ao remover câmera do sistema"
            )
        
        return {"message": "Câmera removida com sucesso"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao deletar câmera {camera_id}: {e}")
        raise HTTPException(status_code=500, detail="Erro interno do servidor")


@router.get("/{camera_id}/status", response_model=CameraStatus)
async def get_camera_status(camera_id: str, db: Session = Depends(get_db_dependency)):
    """Obter status da câmera"""
    try:
        # Buscar câmera no banco
        camera = CameraService.get_camera(db, camera_id)
        if not camera:
            raise HTTPException(status_code=404, detail="Câmera não encontrada")
        
        # Verificar se câmera está ativa no worker
        from app.camera_worker.gstreamer_worker import gstreamer_worker
        
        worker_camera = gstreamer_worker.cameras.get(camera_id)
        is_running = worker_camera.is_running if worker_camera else False
        last_activity = worker_camera.last_activity if worker_camera else None
        
        return CameraStatus(
            camera_id=camera_id,
            status=camera.status,
            is_running=is_running,
            last_activity=last_activity.isoformat() if last_activity else None
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao obter status da câmera {camera_id}: {e}")
        raise HTTPException(status_code=500, detail="Erro interno do servidor")


@router.get("/sync/status")
async def get_sync_status():
    """Obter status da sincronização de configurações"""
    try:
        status = await config_sync_service.get_sync_status()
        return status
    except Exception as e:
        logger.error(f"Erro ao obter status de sincronização: {e}")
        raise HTTPException(status_code=500, detail="Erro interno do servidor")


@router.post("/sync/force")
async def force_sync():
    """Forçar sincronização de configurações"""
    try:
        success = await config_sync_service.force_sync()
        
        if not success:
            raise HTTPException(
                status_code=500, 
                detail="Erro ao forçar sincronização"
            )
        
        return {"message": "Sincronização forçada com sucesso"}
        
    except Exception as e:
        logger.error(f"Erro ao forçar sincronização: {e}")
        raise HTTPException(status_code=500, detail="Erro interno do servidor")


@router.put("/{camera_id}/config", response_model=CameraResponse)
async def update_camera_config(
    camera_id: str,
    config_data: dict,
    db: Session = Depends(get_db_dependency)
):
    """Atualizar configurações específicas de uma câmera"""
    try:
        from loguru import logger
        
        # Verificar se a câmera existe
        camera = CameraService.get_camera(db, camera_id)
        if not camera:
            raise HTTPException(status_code=404, detail="Câmera não encontrada")
        
        logger.info(f"Atualizando configurações da câmera {camera_id}: {config_data}")
        
        # Validar parâmetros permitidos
        allowed_params = [
            'buffer_size', 'max_buffers', 'latency', 'fps_limit',
            'reconnect_delay', 'connection_timeout'
        ]
        
        # Filtrar apenas os parâmetros permitidos
        valid_config = {}
        for param, value in config_data.items():
            if param in allowed_params:
                valid_config[param] = value
            else:
                logger.warning(f"Parâmetro ignorado: {param}")
        
        if not valid_config:
            raise HTTPException(status_code=400, detail="Nenhum parâmetro válido fornecido")
        
        # Atualizar configuração no banco de dados
        current_config = json.loads(camera.config) if camera.config else {}
        current_config.update(valid_config)
        
        # Salvar configuração atualizada
        camera.config = json.dumps(current_config)
        db.commit()
        
        # Reiniciar câmera para aplicar as configurações
        try:
            from app.camera_worker.gstreamer_worker import gstreamer_worker
            await gstreamer_worker.remove_camera(camera_id)
            await gstreamer_worker.add_camera(camera_id, current_config)
            logger.info(f"Câmera {camera_id} reiniciada com novas configurações")
        except Exception as e:
            logger.warning(f"Não foi possível reiniciar a câmera: {e}")
        
        return CameraResponse.from_db_model(camera)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao atualizar configurações da câmera: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{camera_id}/disable", response_model=CameraResponse)
async def disable_camera(
    camera_id: str,
    db: Session = Depends(get_db_dependency)
):
    """Desabilitar uma câmera (remover do worker sem excluir do banco)"""
    try:
        from loguru import logger
        
        # Verificar se a câmera existe
        camera = CameraService.get_camera(db, camera_id)
        if not camera:
            raise HTTPException(status_code=404, detail="Câmera não encontrada")
        
        logger.info(f"Desabilitando câmera {camera_id}")
        
        # Remover câmera do worker
        try:
            from app.camera_worker.gstreamer_worker import gstreamer_worker
            await gstreamer_worker.remove_camera(camera_id)
            logger.info(f"Câmera {camera_id} removida do worker")
        except Exception as e:
            logger.warning(f"Não foi possível remover a câmera do worker: {e}")
        
        # Atualizar status da câmera no banco de dados
        camera.status = "inactive"
        db.commit()
        
        return CameraResponse.from_db_model(camera)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao desabilitar câmera: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{camera_id}/use-alt-pipeline", response_model=CameraResponse)
async def use_alt_pipeline(
    camera_id: str,
    db: Session = Depends(get_db_dependency)
):
    """Alternar para o pipeline alternativo para uma câmera problemática"""
    try:
        from loguru import logger
        
        # Verificar se a câmera existe
        camera = CameraService.get_camera(db, camera_id)
        if not camera:
            raise HTTPException(status_code=404, detail="Câmera não encontrada")
        
        logger.info(f"Alternando para pipeline alternativo para câmera {camera_id}")
        
        # Atualizar configuração no banco de dados
        current_config = json.loads(camera.config) if camera.config else {}
        current_config['use_alt_pipeline'] = True
        
        # Salvar configuração atualizada
        camera.config = json.dumps(current_config)
        db.commit()
        
        # Reiniciar câmera para aplicar as configurações
        try:
            from app.camera_worker.gstreamer_worker import gstreamer_worker
            await gstreamer_worker.remove_camera(camera_id)
            await gstreamer_worker.add_camera(camera_id, current_config)
            logger.info(f"Câmera {camera_id} reiniciada com pipeline alternativo")
        except Exception as e:
            logger.warning(f"Não foi possível reiniciar a câmera: {e}")
        
        return CameraResponse.from_db_model(camera)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao alternar para pipeline alternativo: {e}")
        raise HTTPException(status_code=500, detail=str(e))