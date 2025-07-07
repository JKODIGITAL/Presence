"""
Recognition Worker - Processador isolado de reconhecimento facial usando ONNX Runtime + CUDA
Separado do GStreamer para evitar conflitos de bibliotecas
"""

import asyncio
import time
import threading
import os
import sys
import json
import uuid
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
import numpy as np
import cv2
from loguru import logger
import socketio
import uvicorn

# Configurar ambiente para forçar CUDA/GPU
os.environ.pop('DISABLE_GPU', None)          # Remover desabilitação GPU se existir
os.environ['RECOGNITION_WORKER'] = 'true'    # Marcar como processo de reconhecimento
# Garantir que CUDA_VISIBLE_DEVICES esteja configurado
if 'CUDA_VISIBLE_DEVICES' not in os.environ:
    os.environ['CUDA_VISIBLE_DEVICES'] = '0'

# CRITICAL: Força USE_GPU=true no ambiente para Recognition Worker
os.environ['USE_GPU'] = 'true'

print(f"[CONFIG] Recognition Worker ENV Config:")
print(f"   - RECOGNITION_WORKER: {os.environ.get('RECOGNITION_WORKER')}")
print(f"   - CUDA_VISIBLE_DEVICES: {os.environ.get('CUDA_VISIBLE_DEVICES')}")
print(f"   - USE_GPU: {os.environ.get('USE_GPU')}")
print(f"   - FORCE_USE_GPU: {os.environ.get('USE_GPU')}")

# Importar módulos da aplicação
try:
    from app.core.config import settings
    from app.core.recognition_engine import RecognitionEngine
    from app.core.gpu_utils import detect_gpu_availability, setup_cuda_environment
    from app.database.database import get_db_sync
    from app.database import models
except ImportError as e:
    logger.error(f"Erro ao importar dependências: {e}")
    sys.exit(1)


# Import utility functions
try:
    from app.core.utils import make_json_serializable, safe_float_conversion
except ImportError:
    logger.warning("Funções utilitárias não encontradas, usando implementação básica")
    def make_json_serializable(obj):
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return obj
    def safe_float_conversion(value):
        try:
            return float(value)
        except:
            return 0.0


class RecognitionWorker:
    """Worker isolado para reconhecimento facial usando GPU/CUDA"""
    
    def __init__(self, port: int = None):
        # Obter porta do ambiente ou usar padrão
        if port is None:
            port = int(os.environ.get('RECOGNITION_PORT', 17235))
        self.port = port
        self.recognition_engine = None
        self.is_running = False
        self.lock = threading.Lock()
        
        # Configurar ambiente CUDA e detectar GPU
        logger.info("[SEARCH] Detectando disponibilidade de GPU...")
        self.gpu_info = setup_cuda_environment()
        
        # Socket.IO para comunicação com camera worker
        self.sio = socketio.AsyncServer(
            cors_allowed_origins="*",
            async_mode='asgi',
            logger=False,
            engineio_logger=False
        )
        
        # Estatísticas
        self.stats = {
            'frames_processed': 0,
            'faces_detected': 0,
            'recognitions_made': 0,
            'start_time': None,
            'last_activity': None,
            'gpu_available': self.gpu_info['gpu_available'],
            'gpu_device': self.gpu_info.get('device_name'),
            'cuda_version': self.gpu_info.get('cuda_version')
        }
        
        # Configurar eventos do Socket.IO
        self._setup_socketio_events()
    
    def _setup_socketio_events(self):
        """Configurar eventos do Socket.IO"""
        
        @self.sio.event
        async def connect(sid, environ):
            logger.info(f"Cliente conectado ao Recognition Worker: {sid}")
            await self.sio.emit('status', {
                'status': 'connected',
                'gpu_available': self.gpu_info['gpu_available'],
                'gpu_device': self.gpu_info.get('device_name'),
                'cuda_version': self.gpu_info.get('cuda_version'),
                'recognition_ready': self.recognition_engine is not None and self.recognition_engine.is_initialized
            }, room=sid)
        
        @self.sio.event
        async def disconnect(sid):
            logger.info(f"Cliente desconectado do Recognition Worker: {sid}")
        
        @self.sio.event
        async def process_frame(sid, data):
            """Processar frame enviado pelo camera worker"""
            logger.debug(f"Frame recebido - SID: {sid}")
            
            try:
                # Decodificar dados do frame (formato correto do Performance Worker)
                frame_base64 = data.get('frame_base64')
                camera_id = data.get('camera_id')
                timestamp_str = data.get('timestamp')
                frame_id = data.get('frame_id')
                
                if not frame_base64 or not camera_id:
                    logger.error(f"Dados inválidos - frame_base64: {bool(frame_base64)}, camera_id: {bool(camera_id)}")
                    await self.sio.emit('error', {
                        'message': 'Dados do frame inválidos',
                        'camera_id': camera_id
                    }, room=sid)
                    return
                
                # Converter base64 para numpy array
                import base64
                frame_bytes = base64.b64decode(frame_base64)
                frame_array = np.frombuffer(frame_bytes, dtype=np.uint8)
                frame = cv2.imdecode(frame_array, cv2.IMREAD_COLOR)
                
                if frame is None:
                    logger.error(f"Falha ao decodificar frame da câmera {camera_id}")
                    await self.sio.emit('error', {
                        'message': 'Falha ao decodificar frame'
                    }, room=sid)
                    return
                
                # Processar frame
                timestamp = datetime.fromisoformat(timestamp_str) if timestamp_str else datetime.now()
                result = await self._process_frame_internal(frame, camera_id, timestamp)
                
                # Log apenas se houver faces detectadas
                if result.get('faces_detected', 0) > 0:
                    logger.info(f"Câmera {camera_id}: {result.get('faces_detected', 0)} faces detectadas, {len(result.get('recognitions', []))} reconhecidas")
                
                # Enviar resultado de volta - convert numpy types to JSON-serializable
                serializable_result = make_json_serializable(result)
                await self.sio.emit('recognition_result', serializable_result, room=sid)
                
            except Exception as e:
                logger.error(f"[ERROR] [SOCKETIO] Erro ao processar frame: {e}")
                import traceback
                logger.error(f"[ERROR] [SOCKETIO] Traceback: {traceback.format_exc()}")
                await self.sio.emit('error', {
                    'message': f'Erro no processamento: {str(e)}'
                }, room=sid)
        
        @self.sio.event
        async def get_stats(sid, data):
            """Obter estatísticas do worker"""
            stats = make_json_serializable(self.get_stats())
            await self.sio.emit('stats_response', stats, room=sid)
        
        @self.sio.event
        async def reload_faces(sid, data):
            """Recarregar faces conhecidas"""
            if self.recognition_engine:
                await self.recognition_engine.load_known_faces()
                response_data = make_json_serializable({
                    'known_faces_count': self.recognition_engine.get_known_faces_count()
                })
                await self.sio.emit('faces_reloaded', response_data, room=sid)
        
        @self.sio.event
        async def extract_embedding(sid, data):
            """Extrair embedding de face para a API"""
            try:
                image_data = data.get('image_data')
                request_id = data.get('request_id')
                
                if not image_data:
                    await self.sio.emit('embedding_response', make_json_serializable({
                        'success': False,
                        'error': 'Dados da imagem não fornecidos',
                        'request_id': request_id
                    }), room=sid)
                    return
                
                # Verificar se recognition engine está disponível
                if not self.recognition_engine or not self.recognition_engine.is_initialized:
                    await self.sio.emit('embedding_response', make_json_serializable({
                        'success': False,
                        'error': 'Recognition engine não inicializado',
                        'request_id': request_id
                    }), room=sid)
                    return
                
                # Decodificar imagem
                import base64
                frame_bytes = base64.b64decode(image_data)
                frame_array = np.frombuffer(frame_bytes, dtype=np.uint8)
                frame = cv2.imdecode(frame_array, cv2.IMREAD_COLOR)
                
                if frame is None:
                    await self.sio.emit('embedding_response', make_json_serializable({
                        'success': False,
                        'error': 'Falha ao decodificar imagem',
                        'request_id': request_id
                    }), room=sid)
                    return
                
                # Detectar faces e extrair embeddings
                faces = self.recognition_engine.face_analysis.get(frame)
                
                if not faces or len(faces) == 0:
                    await self.sio.emit('embedding_response', make_json_serializable({
                        'success': False,
                        'error': 'Nenhuma face detectada na imagem',
                        'request_id': request_id
                    }), room=sid)
                    return
                
                # Usar primeira face detectada
                face = faces[0]
                embedding = face.embedding
                
                # Converter embedding para lista (JSON serializable)
                embedding_list = embedding.tolist()
                
                await self.sio.emit('embedding_response', make_json_serializable({
                    'success': True,
                    'embedding': embedding_list,
                    'faces_detected': len(faces),
                    'request_id': request_id
                }), room=sid)
                
            except Exception as e:
                logger.error(f"Erro ao extrair embedding: {e}")
                await self.sio.emit('embedding_response', make_json_serializable({
                    'success': False,
                    'error': str(e),
                    'request_id': request_id
                }), room=sid)
        
        @self.sio.event
        async def add_known_face(sid, data):
            """Adicionar face conhecida ao Recognition Worker"""
            try:
                person_id = data.get('person_id')
                person_name = data.get('person_name', '')
                embedding_data = data.get('embedding')
                request_id = data.get('request_id')
                
                if not person_id or not embedding_data:
                    await self.sio.emit('add_face_response', make_json_serializable({
                        'success': False,
                        'error': 'person_id e embedding são obrigatórios',
                        'request_id': request_id
                    }), room=sid)
                    return
                
                # Verificar se recognition engine está disponível
                if not self.recognition_engine or not self.recognition_engine.is_initialized:
                    await self.sio.emit('add_face_response', make_json_serializable({
                        'success': False,
                        'error': 'Recognition engine não inicializado',
                        'request_id': request_id
                    }), room=sid)
                    return
                
                # Decodificar embedding
                import base64
                embedding_bytes = base64.b64decode(embedding_data)
                embedding = np.frombuffer(embedding_bytes, dtype=np.float32)
                
                # Adicionar face conhecida
                success = self.recognition_engine.add_known_face(person_id, embedding)
                
                if success:
                    logger.info(f"[OK] Face adicionada: {person_name} ({person_id})")
                    await self.sio.emit('add_face_response', make_json_serializable({
                        'success': True,
                        'message': f'Face adicionada com sucesso: {person_name}',
                        'request_id': request_id
                    }), room=sid)
                else:
                    await self.sio.emit('add_face_response', make_json_serializable({
                        'success': False,
                        'error': 'Falha ao adicionar face ao índice',
                        'request_id': request_id
                    }), room=sid)
                
            except Exception as e:
                logger.error(f"Erro ao adicionar face conhecida: {e}")
                await self.sio.emit('add_face_response', make_json_serializable({
                    'success': False,
                    'error': str(e),
                    'request_id': request_id
                }), room=sid)
    
    async def initialize(self):
        """Inicializar worker de reconhecimento"""
        try:
            logger.info("Inicializando Recognition Worker...")
            
            # Verificar se GPU está disponível
            if settings.USE_GPU:
                try:
                    import torch
                    gpu_available = torch.cuda.is_available()
                    if gpu_available:
                        logger.info(f"GPU disponível: {torch.cuda.get_device_name(0)}")
                    else:
                        logger.warning("CUDA instalado mas GPU não disponível")
                except ImportError:
                    logger.warning("PyTorch não instalado - verificação de GPU pulada")
            
            # Inicializar Recognition Engine com GPU habilitada
            self.recognition_engine = RecognitionEngine()
            
            # FORÇAR GPU no Recognition Worker (sobrescrever qualquer inicialização anterior)
            self.recognition_engine.use_gpu = True
            self.recognition_engine._initialized = False  # Forçar reinicialização
            self.recognition_engine.is_initialized = False
            
            # Re-inicializar com GPU
            await self._reinitialize_recognition_engine()
            
            self.is_running = True
            self.stats['start_time'] = datetime.now()
            self.stats['last_activity'] = datetime.now()
            
            logger.info("[OK] Recognition Worker inicializado com sucesso")
            return True
            
        except Exception as e:
            logger.error(f"[ERROR] Erro ao inicializar Recognition Worker: {e}")
            return False
    
    async def _reinitialize_recognition_engine(self):
        """Re-inicializar recognition engine com GPU"""
        try:
            # Limpar estado anterior
            self.recognition_engine._initialized = False
            self.recognition_engine.is_initialized = False
            self.recognition_engine._initialization_error = None
            
            # MANTER GPU configurado - NÃO remover CUDA_VISIBLE_DEVICES
            # Apenas garantir que DISABLE_GPU não está definido
            if 'DISABLE_GPU' in os.environ:
                del os.environ['DISABLE_GPU']
                
            # Garantir que CUDA_VISIBLE_DEVICES está configurado
            if 'CUDA_VISIBLE_DEVICES' not in os.environ:
                os.environ['CUDA_VISIBLE_DEVICES'] = '0'
            
            logger.info("Re-inicializando Recognition Engine com GPU habilitada...")
            
            # Importar InsightFace aqui para garantir ambiente limpo (compatibilidade v0.7.3)
            try:
                from insightface import FaceAnalysis
            except ImportError:
                # Para InsightFace 0.7.3 e anteriores
                from insightface.app import FaceAnalysis
            
            # Configurar providers para GPU - FORÇAR CUDA no Recognition Worker
            logger.info(f"[CONFIG] DEBUG settings.USE_GPU = {settings.USE_GPU}")
            logger.info(f"[CONFIG] DEBUG os.environ USE_GPU = {os.environ.get('USE_GPU', 'NOT_SET')}")
            logger.info(f"[CONFIG] DEBUG self.recognition_engine.use_gpu = {self.recognition_engine.use_gpu}")
            
            # Configurar providers ONNX Runtime para GPU
            from app.core.gpu_utils import get_optimal_providers
            providers, provider_info = get_optimal_providers()
            logger.info(f"[ROCKET] PROVIDERS SELECIONADOS: {providers}")
            logger.info(f"[ROCKET] Info: {provider_info}")
            
            # Log adicional para debug
            logger.info(f"[CONFIG] Configuração GPU:")
            logger.info(f"   - USE_GPU env: {os.environ.get('USE_GPU')}")
            logger.info(f"   - CUDA_VISIBLE_DEVICES: {os.environ.get('CUDA_VISIBLE_DEVICES')}")
            logger.info(f"   - RECOGNITION_WORKER env: {os.environ.get('RECOGNITION_WORKER')}")
            
            # Verificar e baixar modelo antelopev2
            await self.recognition_engine._ensure_antelopev2_model()
            
            # Inicializar FaceAnalysis com antelopev2 e fallback para CPU se CUDA falhar
            try:
                logger.info(f"Inicializando InsightFace com providers: {providers}")
                self.recognition_engine.face_analysis = FaceAnalysis(name='antelopev2', providers=providers)
                
                # Preparar modelo
                logger.info("Preparando modelo InsightFace...")
                self.recognition_engine.face_analysis.prepare(ctx_id=0, det_size=(640, 640))
                
                # Se chegou até aqui com providers CUDA, sucesso!
                if 'CUDAExecutionProvider' in providers:
                    logger.info("[SUCCESS] InsightFace inicializado com CUDA com sucesso!")
                
            except Exception as insightface_error:
                error_str = str(insightface_error)
                logger.warning(f"[WARNING] Erro ao inicializar InsightFace com providers {providers}: {error_str}")
                
                # Se CUDA estava nos providers, tentar fallback para CPU
                if 'CUDAExecutionProvider' in providers:
                    logger.warning("[PROCESSING] Tentando fallback para CPU devido a erro CUDA...")
                    
                    try:
                        cpu_providers = ['CPUExecutionProvider']
                        logger.info(f"Reinicializando InsightFace com CPU providers: {cpu_providers}")
                        self.recognition_engine.face_analysis = FaceAnalysis(name='antelopev2', providers=cpu_providers)
                        self.recognition_engine.face_analysis.prepare(ctx_id=0, det_size=(640, 640))
                        
                        logger.info("[OK] InsightFace inicializado com CPU fallback")
                        providers = cpu_providers  # Atualizar para refletir providers reais
                        
                        # Atualizar stats para refletir CPU usage
                        self.stats['gpu_available'] = False
                        self.stats['gpu_device'] = 'CPU Fallback'
                        
                    except Exception as cpu_error:
                        logger.error(f"[ERROR] Falha crítica: não foi possível inicializar InsightFace nem com CPU: {cpu_error}")
                        raise
                else:
                    # Já estava usando CPU e ainda falhou
                    logger.error(f"[ERROR] Falha crítica: InsightFace falhou mesmo com CPU: {error_str}")
                    raise
            
            # Debug: Verificar providers realmente utilizados
            try:
                # Verificar modelo de detecção
                if hasattr(self.recognition_engine.face_analysis, 'det_model'):
                    det_model = self.recognition_engine.face_analysis.det_model
                    logger.info(f"[SEARCH] Modelo de detecção: {type(det_model)}")
                    
                    # Tentar acessar providers de diferentes formas
                    if hasattr(det_model, 'providers'):
                        logger.info(f"[SEARCH] Providers detecção (direto): {det_model.providers}")
                    elif hasattr(det_model, 'session') and hasattr(det_model.session, 'get_providers'):
                        logger.info(f"[SEARCH] Providers detecção (session): {det_model.session.get_providers()}")
                
                # Verificar modelo de reconhecimento  
                # InsightFace pode ter diferentes estruturas dependendo da versão
                for attr_name in ['rec_model', 'recognition_model', 'models']:
                    if hasattr(self.recognition_engine.face_analysis, attr_name):
                        rec_model = getattr(self.recognition_engine.face_analysis, attr_name)
                        logger.info(f"[SEARCH] Modelo de reconhecimento ({attr_name}): {type(rec_model)}")
                        
                        if hasattr(rec_model, 'providers'):
                            logger.info(f"[SEARCH] Providers reconhecimento: {rec_model.providers}")
                        elif hasattr(rec_model, 'session') and hasattr(rec_model.session, 'get_providers'):
                            logger.info(f"[SEARCH] Providers reconhecimento (session): {rec_model.session.get_providers()}")
                        break
                
                # Verificar lista de modelos se disponível
                if hasattr(self.recognition_engine.face_analysis, 'models'):
                    models = self.recognition_engine.face_analysis.models
                    logger.info(f"[SEARCH] Total de modelos carregados: {len(models)}")
                    for i, model in enumerate(models):
                        if hasattr(model, 'session') and hasattr(model.session, 'get_providers'):
                            logger.info(f"[SEARCH] Modelo {i} providers: {model.session.get_providers()}")
                            
            except Exception as debug_e:
                logger.warning(f"[WARNING] Erro ao verificar providers: {debug_e}")
            
            # Log final baseado nos providers realmente utilizados
            if 'CUDAExecutionProvider' in providers:
                logger.info("[OK] InsightFace inicializado com GPU")
            else:
                logger.info("[OK] InsightFace inicializado com CPU")
            
            # Carregar faces conhecidas
            await self.recognition_engine.load_known_faces()
            
            self.recognition_engine.is_initialized = True
            self.recognition_engine._initialized = True
            self.recognition_engine._initialization_error = None
            
            logger.info("[OK] Recognition Engine re-inicializado com GPU com sucesso")
            
        except Exception as e:
            logger.error(f"[ERROR] Erro ao re-inicializar Recognition Engine: {e}")
            self.recognition_engine._initialization_error = str(e)
            raise
    
    async def _process_frame_internal(
        self, 
        frame: np.ndarray, 
        camera_id: str,
        timestamp: datetime
    ) -> Dict:
        """Processar frame internamente"""
        logger.debug(f"Processando frame - Camera: {camera_id}, Shape: {frame.shape}")
        
        try:
            # Verificar se o recognition engine está disponível
            if not self.recognition_engine or not self.recognition_engine.is_initialized:
                logger.error(f"Recognition engine não disponível - Camera: {camera_id}")
                return {
                    'camera_id': camera_id,
                    'timestamp': timestamp.isoformat(),
                    'faces_detected': 0,
                    'recognitions': [],
                    'processed': False,
                    'error': 'Recognition engine não inicializado'
                }
            
            # Processar frame com recognition engine
            result = await self.recognition_engine.process_frame(frame, camera_id, timestamp)
            
            # Atualizar estatísticas
            self.stats['frames_processed'] += 1
            self.stats['faces_detected'] += result.get('faces_detected', 0)
            self.stats['recognitions_made'] += len([r for r in result.get('recognitions', []) if r.get('person_id')])
            self.stats['last_activity'] = datetime.now()
            
            # Log apenas a cada 100 frames processados
            if self.stats['frames_processed'] % 100 == 0:
                logger.info(f"Processados {self.stats['frames_processed']} frames, {self.stats['faces_detected']} faces detectadas")
            
            # Salvar reconhecimentos no banco de dados
            await self._save_recognitions(result, camera_id, timestamp)
            
            return result
            
        except Exception as e:
            logger.error(f"Erro ao processar frame: {e}")
            return {
                'camera_id': camera_id,
                'timestamp': timestamp.isoformat(),
                'faces_detected': 0,
                'recognitions': [],
                'processed': False,
                'error': str(e)
            }
    
    async def _save_recognitions(self, result: Dict, camera_id: str, timestamp: datetime):
        """Salvar reconhecimentos no banco de dados"""
        try:
            recognitions = result.get('recognitions', [])
            if not recognitions:
                return
            
            # Obter sessão do banco de dados
            db = next(get_db_sync())
            
            for recognition in recognitions:
                person_id = recognition.get('person_id')
                if not person_id:
                    continue
                
                # Criar log de reconhecimento
                bbox = recognition.get('bbox', [])
                # Convert numpy types to Python types before JSON serialization
                serializable_bbox = make_json_serializable(bbox)
                recognition_log = models.RecognitionLog(
                    id=str(uuid.uuid4()),
                    person_id=person_id,
                    camera_id=camera_id,
                    confidence=safe_float_conversion(recognition.get('confidence', 0.0)),
                    bounding_box=json.dumps(serializable_bbox),
                    timestamp=timestamp,
                    is_unknown=recognition.get('is_unknown', False)
                )
                
                db.add(recognition_log)
            
            db.commit()
            logger.debug(f"Salvos {len(recognitions)} reconhecimentos no banco de dados")
            
        except Exception as e:
            logger.error(f"Erro ao salvar reconhecimentos: {e}")
    
    def get_stats(self) -> Dict:
        """Obter estatísticas do worker"""
        stats = self.stats.copy()
        
        # Adicionar informações do recognition engine
        if self.recognition_engine:
            stats.update(self.recognition_engine.get_stats())
        
        # Adicionar tempo de execução
        if stats['start_time']:
            runtime = datetime.now() - stats['start_time']
            stats['runtime_seconds'] = runtime.total_seconds()
        
        return stats
    
    async def run(self):
        """Executar worker como servidor Socket.IO"""
        try:
            from fastapi import FastAPI
            from fastapi.middleware.cors import CORSMiddleware
            
            # Criar aplicação FastAPI
            app = FastAPI(title="Recognition Worker", version="1.0.0")
            
            # Configurar CORS
            app.add_middleware(
                CORSMiddleware,
                allow_origins=["*"],
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
            )
            
            # Endpoint de saúde (ANTES de montar Socket.IO)
            @app.get("/health")
            async def health():
                return {
                    "status": "healthy",
                    "recognition_ready": self.recognition_engine is not None and self.recognition_engine.is_initialized,
                    "gpu_available": self.gpu_info['gpu_available'],
                    "gpu_device": self.gpu_info.get('device_name'),
                    "cuda_version": self.gpu_info.get('cuda_version'),
                    "torch_cuda": self.gpu_info.get('torch_cuda', False),
                    "faiss_gpu": self.gpu_info.get('faiss_gpu', False),
                    "onnx_cuda": self.gpu_info.get('onnx_cuda', False),
                    "gpu_errors": self.gpu_info.get('errors', [])
                }
            
            @app.get("/stats")
            async def stats():
                return self.get_stats()
            
            @app.get("/test-insightface")
            async def test_insightface():
                """Test endpoint to check InsightFace installation"""
                try:
                    # Test import of InsightFace
                    try:
                        from insightface import FaceAnalysis
                        import_method = "from insightface import FaceAnalysis"
                    except ImportError:
                        try:
                            from insightface.app import FaceAnalysis
                            import_method = "from insightface.app import FaceAnalysis"
                        except ImportError as e:
                            return {
                                "insightface_available": False,
                                "error": str(e),
                                "import_method": None
                            }
                    
                    # Test if we can create an instance
                    try:
                        providers = ['CUDAExecutionProvider', 'CPUExecutionProvider'] if settings.USE_GPU else ['CPUExecutionProvider']
                        face_analysis = FaceAnalysis(name='antelopev2', providers=providers)
                        can_create_instance = True
                        instance_error = None
                    except Exception as e:
                        can_create_instance = False
                        instance_error = str(e)
                    
                    return {
                        "insightface_available": True,
                        "import_method": import_method,
                        "can_create_instance": can_create_instance,
                        "instance_error": instance_error,
                        "providers": providers if 'providers' in locals() else None
                    }
                    
                except Exception as e:
                    return {
                        "insightface_available": False,
                        "error": str(e)
                    }
            
            # Combinar FastAPI com Socket.IO
            combined_app = socketio.ASGIApp(self.sio, other_asgi_app=app)
            
            logger.info(f"Recognition Worker rodando na porta {self.port}")
            
            # Executar servidor com múltiplas tentativas de host
            hosts_to_try = [
                ('127.0.0.1', 'IPv4 loopback'),
                ('0.0.0.0', 'bind all interfaces')
            ]
            
            # Usar host preferido do ambiente se especificado
            preferred_host = os.environ.get('RECOGNITION_HOST')
            if preferred_host:
                hosts_to_try.insert(0, (preferred_host, 'environment specified'))
            
            server_started = False
            last_error = None
            
            for host, description in hosts_to_try:
                if server_started:
                    break
                    
                try:
                    logger.info(f"[ROCKET] Tentando iniciar servidor Recognition Worker:")
                    logger.info(f"   - Host: {host} ({description})")
                    logger.info(f"   - Porta: {self.port}")
                    
                    # Tentar bind simples primeiro para diagnosticar o problema
                    import socket
                    test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    test_socket.bind((host, self.port))
                    test_socket.close()
                    logger.info(f"✅ Socket bind test successful for {host}:{self.port}")
                    
                    # Usar uvicorn.run diretamente para evitar problemas de loop
                    logger.info(f"🚀 Starting uvicorn server with uvicorn.run...")
                    
                    # Executar servidor em thread separada para evitar conflitos de loop
                    import threading
                    import uvicorn
                    
                    def run_server():
                        uvicorn.run(
                            combined_app,
                            host=host,
                            port=self.port,
                            log_level="error",
                            access_log=False
                        )
                    
                    server_thread = threading.Thread(target=run_server, daemon=True)
                    server_thread.start()
                    
                    # Aguardar um momento para o servidor inicializar
                    await asyncio.sleep(2)
                    
                    # Verificar se o servidor está rodando (teste simples de conexão)
                    import socket
                    try:
                        test_connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        result = test_connection.connect_ex((host, self.port))
                        test_connection.close()
                        
                        if result == 0:
                            logger.info(f"✅ Server started successfully on {host}:{self.port}")
                            server_started = True
                            
                            # Manter o thread principal vivo AQUI
                            logger.info("🔄 Mantendo Recognition Worker ativo...")
                            while True:
                                await asyncio.sleep(1)
                        else:
                            logger.warning(f"Server connection test failed for {host}:{self.port}")
                    except Exception as e:
                        logger.warning(f"Server health check failed for {host}:{self.port}: {e}")
                    logger.info(f"[OK] Servidor iniciado com sucesso em {host}:{self.port}")
                    
                except OSError as e:
                    error_msg = str(e)
                    last_error = e
                    
                    if "getaddrinfo failed" in error_msg:
                        logger.warning(f"[WARNING] Erro DNS/hostname para {host}: {error_msg}")
                    elif "Address already in use" in error_msg:
                        logger.error(f"[ERROR] Porta {self.port} já está em uso!")
                        break  # Não tentar outros hosts se porta estiver em uso
                    elif "Permission denied" in error_msg:
                        logger.warning(f"[WARNING] Permissão negada para {host}:{self.port}")
                    else:
                        logger.warning(f"[WARNING] Erro de rede para {host}: {error_msg}")
                    
                    if host != hosts_to_try[-1][0]:  # Se não é o último host
                        logger.info(f"[PROCESSING] Tentando próximo host...")
                except Exception as e:
                    logger.warning(f"[WARNING] Erro inesperado para {host}: {e}")
                    last_error = e
                    
            if not server_started:
                logger.error(f"[ERROR] Falha ao iniciar servidor em todos os hosts tentados")
                if last_error:
                    raise last_error
                else:
                    raise RuntimeError("Não foi possível iniciar o servidor Recognition Worker")
            
        except Exception as e:
            logger.error(f"Erro ao executar Recognition Worker: {e}")
            raise
    
    async def cleanup(self):
        """Limpeza de recursos"""
        logger.info("Limpando recursos do Recognition Worker")
        
        if self.recognition_engine:
            await self.recognition_engine.cleanup()
        
        self.is_running = False
        logger.info("Recognition Worker finalizado")


# Função principal para executar o worker
async def main():
    """Função principal"""
    worker = RecognitionWorker()
    
    try:
        # Inicializar worker
        success = await worker.initialize()
        if not success:
            logger.error("Falha ao inicializar Recognition Worker")
            return
        
        # Executar
        await worker.run()
        
    except KeyboardInterrupt:
        logger.info("Recognition Worker interrompido pelo usuário")
    except Exception as e:
        logger.error(f"Erro no Recognition Worker: {e}")
    finally:
        await worker.cleanup()


if __name__ == "__main__":
    # Configurar logging
    import sys
    logger.remove()
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | <white>{message}</white>",
        level="INFO"
    )
    
    logger.info("Iniciando Recognition Worker...")
    asyncio.run(main())