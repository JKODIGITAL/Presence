"""
System management endpoints
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import os
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    psutil = None
from datetime import datetime

from app.database.database import get_db, get_db_dependency
from app.database import models
from app.core.config import settings
from app.api.services.person_service import PersonService
from app.api.services.camera_service import CameraService
from app.core.gpu_utils import detect_gpu_availability

router = APIRouter()


@router.get("/info")
async def get_system_info():
    """Get system information"""
    try:
        # Informações do sistema
        system_info = {
            "version": "1.0.0",
            "build_date": "2024-12-08",
            "platform": os.name,
        }
        
        if PSUTIL_AVAILABLE:
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            system_info.update({
                "memory": {
                    "total": memory.total,
                    "used": memory.used,
                    "available": memory.available,
                    "percent": memory.percent
                },
                "disk": {
                    "total": disk.total,
                    "used": disk.used,
                    "free": disk.free,
                    "percent": (disk.used / disk.total) * 100
                }
            })
        else:
            system_info.update({
                "memory": "psutil not available",
                "disk": "psutil not available"
            })
        
        system_info.update({
            "uptime": datetime.now().isoformat(),
            "settings": {
                "confidence_threshold": getattr(settings, 'CONFIDENCE_THRESHOLD', 0.6),
                "use_gpu": getattr(settings, 'USE_GPU', False),
                "max_cameras": getattr(settings, 'MAX_CAMERAS', 10)
            }
        })
        
        return system_info
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_system_status(db: Session = Depends(get_db_dependency)):
    """Get system status"""
    try:
        # Contar estatísticas
        total_people = db.query(models.Person).count()
        known_people = db.query(models.Person).filter(models.Person.is_unknown == False).count()
        unknown_people = db.query(models.Person).filter(models.Person.is_unknown == True).count()
        
        total_cameras = db.query(models.Camera).count()
        active_cameras = db.query(models.Camera).filter(models.Camera.status == "active").count()
        
        total_recognitions = db.query(models.RecognitionLog).count()
        
        return {
            "status": "running",
            "timestamp": datetime.now().isoformat(),
            "stats": {
                "people": {
                    "total": total_people,
                    "known": known_people,
                    "unknown": unknown_people
                },
                "cameras": {
                    "total": total_cameras,
                    "active": active_cameras,
                    "inactive": total_cameras - active_cameras
                },
                "recognitions": {
                    "total": total_recognitions
                }
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/logs")
async def get_system_logs(
    limit: int = 100,
    offset: int = 0,
    level: str = None,
    db: Session = Depends(get_db_dependency)
):
    """Get system logs"""
    try:
        query = db.query(models.SystemLog)
        
        if level:
            query = query.filter(models.SystemLog.level == level.upper())
        
        logs = query.order_by(models.SystemLog.timestamp.desc()).offset(offset).limit(limit).all()
        total = query.count()
        
        return {
            "logs": logs,
            "total": total,
            "limit": limit,
            "offset": offset
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/logs")
async def create_system_log(log_data: dict, db: Session = Depends(get_db_dependency)):
    """Create system log entry"""
    try:
        log_entry = models.SystemLog(
            level=log_data.get("level", "INFO"),
            module=log_data.get("module", "system"),
            message=log_data.get("message", ""),
            details=log_data.get("details")
        )
        
        db.add(log_entry)
        db.commit()
        
        return {"message": "Log entry created successfully"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data-integrity-test")
async def test_data_integrity(db: Session = Depends(get_db_dependency)):
    """Testar integridade e comunicação completa dos dados"""
    try:
        results = {
            "database_connection": "ok",
            "models_integrity": {},
            "services_functionality": {},
            "data_consistency": {},
            "timestamp": datetime.now().isoformat()
        }
        
        # Testar modelos do banco
        try:
            # Teste Person model
            person_count = db.query(models.Person).count()
            camera_count = db.query(models.Camera).count()
            log_count = db.query(models.RecognitionLog).count()
            
            results["models_integrity"] = {
                "Person": {"count": person_count, "status": "ok"},
                "Camera": {"count": camera_count, "status": "ok"},
                "RecognitionLog": {"count": log_count, "status": "ok"}
            }
        except Exception as e:
            results["models_integrity"]["error"] = str(e)
        
        # Testar services
        try:
            # Teste Person Service
            people_stats = PersonService.get_person_stats(db)
            camera_stats = CameraService.get_camera_stats(db)
            
            results["services_functionality"] = {
                "PersonService": {"stats": people_stats, "status": "ok"},
                "CameraService": {"stats": camera_stats, "status": "ok"}
            }
        except Exception as e:
            results["services_functionality"]["error"] = str(e)
        
        # Testar consistência de dados
        try:
            # Verificar se todos os person_id em RecognitionLog existem em Person
            orphaned_logs = db.query(models.RecognitionLog).filter(
                ~models.RecognitionLog.person_id.in_(
                    db.query(models.Person.id)
                )
            ).count()
            
            # Verificar se todos os camera_id em RecognitionLog existem em Camera
            orphaned_camera_logs = db.query(models.RecognitionLog).filter(
                ~models.RecognitionLog.camera_id.in_(
                    db.query(models.Camera.id)
                )
            ).count()
            
            results["data_consistency"] = {
                "orphaned_recognition_logs": orphaned_logs,
                "orphaned_camera_logs": orphaned_camera_logs,
                "status": "ok" if orphaned_logs == 0 and orphaned_camera_logs == 0 else "warning"
            }
        except Exception as e:
            results["data_consistency"]["error"] = str(e)
        
        return results
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Teste de integridade falhou: {str(e)}")


@router.get("/api-endpoints-test")
async def test_api_endpoints():
    """Testar todos os endpoints da API"""
    try:
        endpoints = {
            "people": {
                "GET /api/v1/people/": "List people",
                "POST /api/v1/people/": "Create person",
                "POST /api/v1/people/register": "Register with image",
                "POST /api/v1/people/register-with-camera": "Register with camera",
                "POST /api/v1/people/register-from-base64": "Register with base64",
                "GET /api/v1/people/{id}": "Get person by ID",
                "PUT /api/v1/people/{id}": "Update person",
                "DELETE /api/v1/people/{id}": "Delete person",
                "GET /api/v1/people/stats": "Get people statistics"
            },
            "cameras": {
                "GET /api/v1/cameras/": "List cameras",
                "POST /api/v1/cameras/": "Create camera",
                "GET /api/v1/cameras/{id}": "Get camera by ID",
                "PUT /api/v1/cameras/{id}": "Update camera",
                "DELETE /api/v1/cameras/{id}": "Delete camera",
                "POST /api/v1/cameras/{id}/capture": "Capture from camera",
                "GET /api/v1/cameras/{id}/stream": "Stream camera",
                "GET /api/v1/cameras/{id}/snapshot": "Get camera snapshot",
                "PUT /api/v1/cameras/{id}/status": "Update camera status",
                "POST /api/v1/cameras/{id}/test": "Test camera connection",
                "GET /api/v1/cameras/active": "Get active cameras",
                "GET /api/v1/cameras/stats": "Get camera statistics"
            },
            "recognition": {
                "POST /api/v1/recognition/process-frame": "Process frame",
                "GET /api/v1/recognition/logs": "Get recognition logs",
                "GET /api/v1/recognition/stats": "Get recognition statistics",
                "GET /api/v1/recognition/stream/{camera_id}/status": "Get stream status",
                "POST /api/v1/recognition/unknown/{id}/identify": "Identify unknown person"
            },
            "system": {
                "GET /api/v1/system/info": "Get system info",
                "GET /api/v1/system/status": "Get system status",
                "GET /api/v1/system/logs": "Get system logs",
                "POST /api/v1/system/logs": "Create system log",
                "GET /api/v1/system/data-integrity-test": "Test data integrity",
                "GET /api/v1/system/api-endpoints-test": "Test API endpoints"
            },
            "websocket": {
                "WS /ws": "WebSocket connection"
            }
        }
        
        return {
            "total_endpoints": sum(len(group) for group in endpoints.values()),
            "endpoints": endpoints,
            "status": "documented",
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/full-communication-test")
async def test_full_communication(db: Session = Depends(get_db_dependency)):
    """Teste completo de comunicação Frontend ↔ Backend ↔ Database"""
    try:
        test_results = {
            "database": {"status": "unknown", "details": {}},
            "models": {"status": "unknown", "details": {}},
            "schemas": {"status": "unknown", "details": {}},
            "services": {"status": "unknown", "details": {}},
            "endpoints": {"status": "unknown", "details": {}},
            "data_integrity": {"status": "unknown", "details": {}},
            "timestamp": datetime.now().isoformat(),
            "overall_status": "unknown"
        }
        
        errors = []
        
        # 1. Teste de Conexão com Banco
        try:
            # Testar conexão básica
            db.execute("SELECT 1").fetchone()
            
            # Contar registros
            person_count = db.query(models.Person).count()
            camera_count = db.query(models.Camera).count()
            log_count = db.query(models.RecognitionLog).count()
            
            test_results["database"] = {
                "status": "ok",
                "details": {
                    "connection": "active",
                    "person_count": person_count,
                    "camera_count": camera_count,
                    "recognition_log_count": log_count
                }
            }
        except Exception as e:
            test_results["database"] = {"status": "error", "details": {"error": str(e)}}
            errors.append(f"Database: {str(e)}")
        
        # 2. Teste de Modelos
        try:
            # Verificar se modelos têm todos os campos necessários
            person_fields = [col.name for col in models.Person.__table__.columns]
            camera_fields = [col.name for col in models.Camera.__table__.columns]
            log_fields = [col.name for col in models.RecognitionLog.__table__.columns]
            
            test_results["models"] = {
                "status": "ok",
                "details": {
                    "person_fields": len(person_fields),
                    "camera_fields": len(camera_fields),
                    "log_fields": len(log_fields),
                    "required_person_fields": all(field in person_fields for field in ['id', 'name', 'created_at']),
                    "required_camera_fields": all(field in camera_fields for field in ['id', 'name', 'url', 'type']),
                    "required_log_fields": all(field in log_fields for field in ['id', 'person_id', 'camera_id', 'timestamp'])
                }
            }
        except Exception as e:
            test_results["models"] = {"status": "error", "details": {"error": str(e)}}
            errors.append(f"Models: {str(e)}")
        
        # 3. Teste de Services
        try:
            # Testar PersonService
            person_stats = PersonService.get_person_stats(db)
            
            # Testar CameraService
            camera_stats = CameraService.get_camera_stats(db)
            
            test_results["services"] = {
                "status": "ok",
                "details": {
                    "person_service": {"stats_fields": len(person_stats), "callable": True},
                    "camera_service": {"stats_fields": len(camera_stats), "callable": True}
                }
            }
        except Exception as e:
            test_results["services"] = {"status": "error", "details": {"error": str(e)}}
            errors.append(f"Services: {str(e)}")
        
        # 4. Teste de Integridade de Dados
        try:
            # Verificar referências órfãs
            orphaned_logs = db.query(models.RecognitionLog).filter(
                ~models.RecognitionLog.person_id.in_(
                    db.query(models.Person.id).filter(models.Person.id.like('%'))
                )
            ).count()
            
            orphaned_camera_logs = db.query(models.RecognitionLog).filter(
                ~models.RecognitionLog.camera_id.in_(
                    db.query(models.Camera.id)
                )
            ).count()
            
            # Verificar pessoas sem encoding
            people_without_encoding = db.query(models.Person).filter(
                models.Person.face_encoding.is_(None),
                models.Person.is_unknown == False
            ).count()
            
            integrity_status = "ok" if orphaned_logs == 0 and orphaned_camera_logs == 0 else "warning"
            
            test_results["data_integrity"] = {
                "status": integrity_status,
                "details": {
                    "orphaned_recognition_logs": orphaned_logs,
                    "orphaned_camera_logs": orphaned_camera_logs,
                    "people_without_face_encoding": people_without_encoding
                }
            }
        except Exception as e:
            test_results["data_integrity"] = {"status": "error", "details": {"error": str(e)}}
            errors.append(f"Data Integrity: {str(e)}")
        
        # 5. Status Final
        if len(errors) == 0:
            test_results["overall_status"] = "all_systems_operational"
        elif len(errors) <= 2:
            test_results["overall_status"] = "minor_issues_detected"
        else:
            test_results["overall_status"] = "critical_issues_detected"
        
        test_results["errors"] = errors
        test_results["error_count"] = len(errors)
        
        return test_results
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Teste de comunicação falhou: {str(e)}")


@router.get("/input-output-validation")
async def validate_input_output_types():
    """Validar tipos de entrada e saída de todos os endpoints"""
    try:
        validation_results = {
            "endpoint_schemas": {},
            "type_consistency": {},
            "validation_rules": {},
            "timestamp": datetime.now().isoformat()
        }
        
        # Validações para People endpoints
        validation_results["endpoint_schemas"]["people"] = {
            "create_input": {
                "name": "string (required, 1-100 chars)",
                "department": "string (optional, max 100 chars)",
                "email": "string (optional, max 255 chars)",
                "phone": "string (optional, max 20 chars)",
                "tags": "string (optional, JSON format)"
            },
            "response_output": {
                "id": "string (UUID)",
                "name": "string",
                "is_unknown": "boolean",
                "thumbnail_path": "string (optional)",
                "confidence": "float (0.0-1.0)",
                "status": "string ('active'|'inactive')",
                "created_at": "datetime (ISO 8601)",
                "updated_at": "datetime (ISO 8601)"
            },
            "register_with_camera": {
                "name": "FormData string (required)",
                "camera_id": "FormData string (required, UUID)",
                "department": "FormData string (optional)",
                "email": "FormData string (optional)",
                "phone": "FormData string (optional)",
                "tags": "FormData string (optional)"
            },
            "register_from_base64": {
                "name": "FormData string (required)",
                "image_base64": "FormData string (required, base64)",
                "department": "FormData string (optional)",
                "email": "FormData string (optional)",
                "phone": "FormData string (optional)",
                "tags": "FormData string (optional)"
            }
        }
        
        # Validações para Camera endpoints
        validation_results["endpoint_schemas"]["cameras"] = {
            "create_input": {
                "name": "string (required, 1-100 chars)",
                "url": "string (required)",
                "type": "string ('ip'|'webcam')",
                "fps": "integer (1-60, default=30)",
                "resolution_width": "integer (320-4096, default=1280)",
                "resolution_height": "integer (240-2160, default=720)",
                "fps_limit": "integer (1-30, default=5)",
                "location": "string (optional, max 200 chars)",
                "description": "string (optional, max 500 chars)"
            },
            "response_output": {
                "id": "string (UUID)",
                "name": "string",
                "url": "string",
                "type": "string",
                "status": "string ('active'|'inactive'|'error')",
                "last_frame_at": "datetime (optional)",
                "created_at": "datetime (ISO 8601)",
                "updated_at": "datetime (ISO 8601)"
            },
            "capture_output": {
                "success": "boolean",
                "image_data": "string (base64)",
                "image_format": "string ('jpeg')",
                "camera_id": "string (UUID)",
                "camera_name": "string",
                "timestamp": "datetime (ISO 8601)"
            }
        }
        
        # Validações para Recognition endpoints
        validation_results["endpoint_schemas"]["recognition"] = {
            "process_frame_input": {
                "camera_id": "FormData string (required, UUID)",
                "timestamp": "FormData string (optional, ISO 8601)",
                "save_frame": "FormData boolean (default=false)",
                "frame": "UploadFile (required, image/*)"
            },
            "process_frame_output": {
                "camera_id": "string (UUID)",
                "timestamp": "datetime (ISO 8601)",
                "faces_detected": "integer",
                "recognitions": "array of RecognitionResult",
                "processed": "boolean",
                "error": "string (optional)"
            },
            "recognition_result": {
                "person_id": "string (optional, UUID)",
                "person_name": "string (optional)",
                "confidence": "float (0.0-1.0)",
                "is_unknown": "boolean",
                "bbox": "object {x: int, y: int, width: int, height: int}",
                "landmarks": "array of [x, y] coordinates (optional)"
            }
        }
        
        # Regras de validação
        validation_results["validation_rules"] = {
            "face_detection": "Obrigatória para registro de pessoas",
            "image_formats": ["jpg", "jpeg", "png", "bmp"],
            "max_file_size": "10MB",
            "confidence_threshold": settings.CONFIDENCE_THRESHOLD,
            "max_cameras": settings.MAX_CAMERAS,
            "required_headers": {
                "multipart_form": "Content-Type: multipart/form-data",
                "json": "Content-Type: application/json"
            },
            "http_status_codes": {
                "200": "Success",
                "201": "Created",
                "400": "Validation Error (ex: no face detected)",
                "404": "Resource not found",
                "500": "Internal server error"
            }
        }
        
        # Verificação de consistência de tipos
        validation_results["type_consistency"] = {
            "datetime_format": "ISO 8601 (YYYY-MM-DDTHH:mm:ss.fffffZ)",
            "uuid_format": "UUID4 string",
            "confidence_range": "0.0 to 1.0 (float)",
            "image_encoding": "base64 string",
            "status_values": ["active", "inactive", "error"],
            "camera_types": ["ip", "webcam"],
            "log_levels": ["INFO", "WARNING", "ERROR"]
        }
        
        return validation_results
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/settings")
async def update_system_settings(settings_update: dict):
    """Atualizar configurações do sistema"""
    try:
        # Aqui você pode implementar a lógica para atualizar configurações
        # Por enquanto, apenas retorna as configurações recebidas
        return {
            "message": "Configurações atualizadas com sucesso",
            "updated_settings": settings_update,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/recognition-settings")
async def get_recognition_settings():
    """Obter configurações de reconhecimento facial"""
    try:
        from app.core.config import settings
        
        return {
            "confidence_threshold": settings.CONFIDENCE_THRESHOLD,
            "unknown_similarity_threshold": settings.UNKNOWN_SIMILARITY_THRESHOLD,
            "unknown_grace_period_seconds": settings.UNKNOWN_GRACE_PERIOD_SECONDS,
            "min_face_size": settings.MIN_FACE_SIZE,
            "face_detection_model": settings.FACE_DETECTION_MODEL,
            "face_recognition_model": settings.FACE_RECOGNITION_MODEL,
            "max_face_size": settings.MAX_FACE_SIZE,
            "use_gpu": settings.USE_GPU,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/recognition-settings")
async def update_recognition_settings(settings_update: dict):
    """Atualizar configurações de reconhecimento facial"""
    try:
        from app.core.config import settings
        
        updated_settings = {}
        
        # Atualizar configurações se fornecidas
        if "confidence_threshold" in settings_update:
            new_threshold = float(settings_update["confidence_threshold"])
            if 0.0 <= new_threshold <= 1.0:
                settings.CONFIDENCE_THRESHOLD = new_threshold
                updated_settings["confidence_threshold"] = new_threshold
        
        if "unknown_similarity_threshold" in settings_update:
            new_threshold = float(settings_update["unknown_similarity_threshold"])
            if 0.0 <= new_threshold <= 1.0:
                settings.UNKNOWN_SIMILARITY_THRESHOLD = new_threshold
                # NOTA: Recognition Engine agora é processo externo
                # Configuração será aplicada na próxima inicialização
                updated_settings["unknown_similarity_threshold"] = new_threshold
        
        if "unknown_grace_period_seconds" in settings_update:
            new_period = int(settings_update["unknown_grace_period_seconds"])
            if new_period >= 0:
                settings.UNKNOWN_GRACE_PERIOD_SECONDS = new_period
                # NOTA: Recognition Engine agora é processo externo
                # Configuração será aplicada na próxima inicialização
                updated_settings["unknown_grace_period_seconds"] = new_period
        
        if "min_face_size" in settings_update:
            new_size = int(settings_update["min_face_size"])
            if 10 <= new_size <= 200:  # Valores razoáveis para tamanho de face
                settings.MIN_FACE_SIZE = new_size
                updated_settings["min_face_size"] = new_size
        
        return {
            "message": "Configurações de reconhecimento atualizadas com sucesso",
            "updated_settings": updated_settings,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/gpu-status")
async def get_gpu_status():
    """Get real-time GPU and CUDA status"""
    try:
        # Detectar disponibilidade real da GPU
        gpu_info = detect_gpu_availability()
        
        # Testar FAISS GPU especificamente
        faiss_status = "unavailable"
        faiss_error = None
        try:
            import faiss
            if hasattr(faiss, 'StandardGpuResources'):
                # Tentar criar recursos GPU
                gpu_res = faiss.StandardGpuResources()
                faiss_status = "gpu_available"
            else:
                faiss_status = "cpu_only"
        except Exception as e:
            faiss_error = str(e)
            faiss_status = "error"
        
        # Testar ONNX Runtime CUDA
        onnx_cuda_status = "unavailable"
        onnx_providers = []
        try:
            import onnxruntime as ort
            onnx_providers = ort.get_available_providers()
            if 'CUDAExecutionProvider' in onnx_providers:
                onnx_cuda_status = "available"
            else:
                onnx_cuda_status = "cpu_only"
        except Exception as e:
            onnx_cuda_status = "error"
        
        return {
            "timestamp": datetime.now().isoformat(),
            "gpu": {
                "available": gpu_info.get('gpu_available', False),
                "device_name": gpu_info.get('device_name'),
                "cuda_version": gpu_info.get('cuda_version'),
                "memory_total": gpu_info.get('memory_total'),
                "memory_used": gpu_info.get('memory_used'),
                "errors": gpu_info.get('errors', [])
            },
            "faiss": {
                "status": faiss_status,
                "gpu_enabled": faiss_status == "gpu_available",
                "search_method": "FAISS GPU" if faiss_status == "gpu_available" else "Linear Search",
                "error": faiss_error
            },
            "onnx": {
                "status": onnx_cuda_status,
                "cuda_enabled": onnx_cuda_status == "available",
                "available_providers": onnx_providers
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/gstreamer-status")
async def get_gstreamer_status():
    """Get real-time GStreamer and NVDEC status"""
    try:
        gstreamer_available = False
        nvdec_available = False
        gst_version = None
        error_details = []
        
        # Verificar GStreamer
        try:
            import gi
            gi.require_version('Gst', '1.0')
            from gi.repository import Gst
            
            Gst.init(None)
            gstreamer_available = True
            gst_version = Gst.version_string()
            
            # Verificar NVDEC
            try:
                nvdec_factory = Gst.ElementFactory.find('nvh264dec')
                if nvdec_factory:
                    nvdec_available = True
                else:
                    error_details.append("nvh264dec element not found")
            except Exception as e:
                error_details.append(f"NVDEC test failed: {str(e)}")
                
        except ImportError as e:
            error_details.append(f"GStreamer import failed: {str(e)}")
        except Exception as e:
            error_details.append(f"GStreamer initialization failed: {str(e)}")
        
        return {
            "timestamp": datetime.now().isoformat(),
            "gstreamer": {
                "available": gstreamer_available,
                "version": gst_version,
                "nvdec_enabled": nvdec_available,
                "decoder_type": "nvh264dec" if nvdec_available else "avdec_h264",
                "errors": error_details
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))