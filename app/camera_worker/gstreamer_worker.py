"""
GStreamer Worker - Processador otimizado de câmeras usando GStreamer
"""

import asyncio
import time
import threading
import os
import sys
import platform
import base64
import json
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
import numpy as np
import cv2
from loguru import logger
import socketio

# Importar configuração compatível com MSYS2
try:
    # Tentar configuração normal primeiro (para ambiente Conda)
    from app.core.config import settings
    config_source = "app.core.config"
except ImportError:
    # Fallback para configuração simplificada (ambiente MSYS2)
    from app.camera_worker.simple_config import settings
    config_source = "app.camera_worker.simple_config"

logger.info(f"[GStreamerWorker] Configuração carregada de: {config_source}")

# Importar módulos da aplicação
try:
    from app.camera_worker.gstreamer_camera import (
        GStreamerCamera, 
        GStreamerCameraManager, 
        gstreamer_service, 
        GSTREAMER_AVAILABLE
    )
    from app.camera_worker.nvenc_encoder import nvenc_manager
except ImportError as nvenc_import_error:
    logger.warning(f"NVENC Encoder não disponível: {nvenc_import_error}")
    nvenc_manager = None
except ImportError as e:
    # Se o erro for específico de _gi, mostrar mensagem mais clara
    if "DLL load failed" in str(e) and "_gi" in str(e):
        logger.error(f"Erro de importação PyGObject/GStreamer: {e}")
        logger.error("Para resolver: execute 'conda install -c conda-forge pygobject' no seu ambiente")
    else:
        logger.error(f"Erro ao importar dependências: {e}")
    
    # Definir variáveis para evitar erros de referência
    settings = None
    GStreamerCamera = None
    GStreamerCameraManager = None
    gstreamer_service = None
    GSTREAMER_AVAILABLE = False



# Compatibilidade para MSYS2 sem FastAPI
# Forçar uso do database_simple no Camera Worker (MSYS2)
logger.info("Camera Worker usando database_simple para compatibilidade MSYS2")
from app.database.database_simple import get_db_sync, models

class GStreamerWorker:
    """Worker otimizado para processamento de câmeras usando GStreamer"""
    
    def __init__(self):
        self.cameras: Dict[str, Any] = {}
        self.camera_configs: Dict[str, Any] = {}  # Dicionário para armazenar configurações de câmeras
        self.camera_names: Dict[str, str] = {}    # Dicionário para armazenar nomes de câmeras
        self.is_running = False
        self.lock = threading.Lock()
        self.gstreamer_available = GSTREAMER_AVAILABLE  # Usar uma cópia local
        
        # Configurações de processamento
        self.processing_interval = 5.0  # Intervalo entre verificações (segundos)
        self.frame_skip = 5  # Pular mais frames para otimização
        self.frame_count = 0
        
        # Socket.IO client para comunicação com recognition worker
        self.recognition_client = None
        self.recognition_worker_url = os.environ.get('RECOGNITION_WORKER_URL', 'http://localhost:17235')
        self.recognition_available = False
        
        # Estatísticas
        self.stats = {
            'total_frames_processed': 0,
            'total_frames_sent': 0,
            'recognition_responses': 0,
            'start_time': None,
            'last_activity': None,
            'gstreamer_available': self.gstreamer_available,
            'recognition_available': False
        }
        
        # NVENC Encoder integration
        self.nvenc_enabled = os.environ.get('USE_NVENC', 'true').lower() == 'true'
        self.nvenc_available = nvenc_manager is not None
        
        # Verificar dependências
        self._check_dependencies()
    
    def _check_dependencies(self):
        """Verificar se todas as dependências estão disponíveis"""
        missing_deps = []
        
        # Verificar GStreamer
        if not self.gstreamer_available:
            missing_deps.append("GStreamer")
            logger.warning("GStreamer não disponível - funcionalidade limitada")
        
        # Verificar settings
        if settings is None:
            missing_deps.append("settings")
            logger.warning("Configurações não disponíveis")
        
        # Verificar NVENC
        if self.nvenc_enabled and not self.nvenc_available:
            logger.warning("NVENC solicitado mas não disponível - usando fallback")
            self.nvenc_enabled = False
        elif self.nvenc_enabled and self.nvenc_available:
            logger.info("🚀 NVENC Encoder habilitado para alta performance")
        
        # Registrar dependências faltantes
        if missing_deps:
            logger.warning(f"Dependências faltantes: {', '.join(missing_deps)}")
            logger.warning("O worker funcionará com funcionalidade limitada")
    
    async def initialize(self):
        """Inicializar worker"""
        if not self.gstreamer_available:
            logger.error("GStreamer não disponível - worker não pode ser inicializado completamente")
            # Continuar com funcionalidade limitada
        
        try:
            logger.info("Inicializando GStreamer Worker...")
            
            # Garantir que o GStreamer está inicializado (se disponível)
            if self.gstreamer_available and not gstreamer_service.is_initialized():
                logger.error("GStreamer não pôde ser inicializado - worker funcionará em modo limitado")
                self.gstreamer_available = False
            
            # Conectar ao recognition worker
            await self._connect_to_recognition_worker()
            
            # Carregar câmeras do banco de dados (se GStreamer disponível)
            if self.gstreamer_available:
                await self.load_cameras_from_database()
            
            self.is_running = True
            self.stats['start_time'] = datetime.now()
            self.stats['last_activity'] = datetime.now()
            
            num_cameras = len(self.cameras) if self.cameras else 0
            if self.gstreamer_available:
                logger.info(f"🚀 GStreamer Worker inicializado com {num_cameras} câmeras (GPU auto-detection ativa)")
            else:
                logger.info(f"⚠️ GStreamer Worker inicializado com {num_cameras} câmeras (modo CPU básico)")
            
            # Mesmo com problemas, retornar True para permitir funcionalidade parcial
            return True
            
        except Exception as e:
            logger.error(f"Erro ao inicializar GStreamer Worker: {e}")
            logger.exception("Detalhes do erro:")
            return False
    
    async def _connect_to_recognition_worker(self):
        """Conectar ao recognition worker via Socket.IO"""
        try:
            logger.info(f"Conectando ao Recognition Worker em {self.recognition_worker_url}")
            
            # Criar cliente Socket.IO
            self.recognition_client = socketio.AsyncClient()
            
            # Configurar eventos
            @self.recognition_client.event
            async def connect():
                logger.info("✅ Conectado ao Recognition Worker")
                self.recognition_available = True
                self.stats['recognition_available'] = True
            
            @self.recognition_client.event
            async def disconnect():
                logger.warning("❌ Desconectado do Recognition Worker")
                self.recognition_available = False
                self.stats['recognition_available'] = False
            
            @self.recognition_client.event
            async def recognition_result(data):
                """Receber resultado do reconhecimento"""
                try:
                    self.stats['recognition_responses'] += 1
                    camera_id = data.get('camera_id')
                    recognitions = data.get('recognitions', [])
                    
                    # Log dos reconhecimentos
                    for recognition in recognitions:
                        if recognition.get('person_id') and not recognition.get('is_unknown'):
                            person_id = recognition['person_id']
                            confidence = recognition.get('confidence', 0)
                            logger.info(f"👤 Pessoa {person_id} reconhecida na câmera {camera_id} (confiança: {confidence:.2f})")
                        elif recognition.get('is_unknown'):
                            person_id = recognition.get('person_id', 'unknown')
                            logger.info(f"❓ Pessoa desconhecida {person_id} detectada na câmera {camera_id}")
                    
                except Exception as e:
                    logger.error(f"Erro ao processar resultado do reconhecimento: {e}")
            
            @self.recognition_client.event
            async def error(data):
                """Receber erro do recognition worker"""
                logger.error(f"Erro do Recognition Worker: {data.get('message', 'Erro desconhecido')}")
            
            # Conectar com timeout (usando sub-path socket.io)
            try:
                await asyncio.wait_for(
                    self.recognition_client.connect(self.recognition_worker_url),
                    timeout=10.0
                )
                logger.info("✅ Conexão com Recognition Worker estabelecida")
            except asyncio.TimeoutError:
                logger.warning("⏰ Timeout ao conectar com Recognition Worker - funcionará sem reconhecimento")
                self.recognition_available = False
            
        except Exception as e:
            logger.warning(f"⚠️ Não foi possível conectar ao Recognition Worker: {e}")
            logger.warning("Sistema funcionará apenas com captura de câmeras, sem reconhecimento")
            self.recognition_available = False
    
    async def load_cameras_from_database(self):
        """Carregar câmeras do banco de dados"""
        if not self.gstreamer_available:
            logger.warning("GStreamer não disponível - não é possível carregar câmeras")
            return
            
        try:
            # Implementar lógica para carregar câmeras do banco de dados
            import aiohttp
            
            # URL da API interna
            api_url = os.environ.get('API_BASE_URL', 'http://localhost:17234')
            
            try:
                timeout = aiohttp.ClientTimeout(total=10)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(f"{api_url}/api/v1/cameras/") as response:
                        if response.status == 200:
                            response_data = await response.json()
                            
                            # Verificar se a resposta tem estrutura {"cameras": [...]} ou é uma lista direta
                            if isinstance(response_data, dict) and 'cameras' in response_data:
                                cameras_data = response_data['cameras']
                            elif isinstance(response_data, list):
                                cameras_data = response_data
                            else:
                                logger.warning(f"Formato de resposta inesperado: {type(response_data)}")
                                cameras_data = []
                            
                            logger.info(f"Encontradas {len(cameras_data)} câmeras no banco de dados")
                            
                            for camera in cameras_data:
                                camera_id = str(camera.get('id'))
                                camera_config = {
                                    'url': camera.get('connection_string', camera.get('url')),
                                    'type': camera.get('type', 'rtsp'),
                                    'fps_limit': min(camera.get('fps_limit', 5), 10),  # Limitar FPS
                                    'enabled': camera.get('enabled', True)
                                }
                                
                                if camera_config['enabled'] and camera_config['url']:
                                    # Adicionar timeout e validação de URL
                                    try:
                                        logger.info(f"Tentando carregar câmera {camera_id} com URL: {camera_config['url']}")
                                        success = await asyncio.wait_for(
                                            self.add_camera(camera_id, camera_config), 
                                            timeout=90  # 90 segundos para inicialização
                                        )
                                        if success:
                                            logger.info(f"✅ Câmera {camera_id} carregada com sucesso")
                                        else:
                                            logger.warning(f"❌ Falha ao carregar câmera {camera_id}")
                                    except asyncio.TimeoutError:
                                        logger.error(f"⏰ Timeout ao carregar câmera {camera_id} - ignorando")
                                    except Exception as e:
                                        logger.error(f"❌ Erro ao carregar câmera {camera_id}: {e}")
                                else:
                                    logger.debug(f"Câmera {camera_id} desabilitada ou sem URL válida")
                                        
                            logger.info(f"Carregamento de câmeras concluído. Ativas: {len(self.cameras)}")
                        else:
                            logger.error(f"Erro ao carregar câmeras da API: {response.status}")
                            
            except aiohttp.ClientError as client_error:
                logger.error(f"Erro de conexão ao carregar câmeras: {client_error}")
            except asyncio.TimeoutError:
                logger.error("Timeout ao carregar câmeras da API")
                        
        except Exception as e:
            logger.error(f"Erro ao carregar câmeras do banco de dados: {e}")
            logger.exception("Detalhes do erro:")
    
    async def add_camera(self, camera_id, camera_config=None):
        """Adicionar câmera ao worker"""
        try:
            if camera_id in self.cameras:
                logger.warning(f"Câmera {camera_id} já existe no worker, removendo primeiro")
                await self.remove_camera(camera_id)
                
            # Obter detalhes da câmera do banco de dados
            camera_details = await self._get_camera_details(camera_id)
            if not camera_details:
                logger.error(f"Não foi possível obter detalhes da câmera {camera_id}")
                return False
                
            camera_url = camera_details.get('url')
            camera_name = camera_details.get('name', 'Sem nome')
            
            # Mesclar configuração da câmera
            config = camera_config or {}
            config.update({
                'fps_limit': camera_details.get('fps_limit', 10),
                'type': camera_details.get('type', 'rtsp')
            })
            
            # Armazenar configuração
            self.camera_configs[camera_id] = config
            
            # Armazenar nome da câmera para uso nos logs
            self.camera_names[camera_id] = camera_name
            
            # Criar instância da câmera
            logger.info(f"Adicionando câmera {camera_id} ({camera_name}) com URL: {camera_url}")
            
            # Criar configuração completa da câmera
            camera_config = {
                'url': camera_url,
                'name': camera_name,
                'type': config.get('type', 'rtsp'),
                'fps_limit': config.get('fps_limit', 10),
                'resolution_width': config.get('resolution_width', 640),
                'resolution_height': config.get('resolution_height', 480),
                'buffer_size': config.get('buffer_size', 5),
                'max_buffers': config.get('max_buffers', 3),
                'latency': config.get('latency', 100),
                'use_alt_pipeline': config.get('use_alt_pipeline', False)
            }
            
            # Criar instância da câmera com configuração
            camera = GStreamerCamera(camera_id, camera_config)
            
            # Configurar callback de frame
            camera.set_frame_callback(self.frame_callback)
            
            # Configurar callback de erro
            camera.set_error_callback(self.camera_error_handler)
            
            # Armazenar câmera
            self.cameras[camera_id] = camera
            
            # Criar encoder NVENC se habilitado
            if self.nvenc_enabled and self.nvenc_available:
                width = camera_config.get('resolution_width', 1920)
                height = camera_config.get('resolution_height', 1080)
                fps = camera_config.get('fps_limit', 30)
                
                if nvenc_manager.create_encoder(camera_id, width, height, fps):
                    logger.info(f"🚀 NVENC Encoder criado para câmera {camera_id} ({width}x{height}@{fps}fps)")
                    
                    # Configurar callback para frames codificados
                    nvenc_manager.set_callback(camera_id, self._on_nvenc_encoded_frame)
                else:
                    logger.warning(f"⚠️ Falha ao criar NVENC Encoder para câmera {camera_id}")
            
            logger.info(f"Câmera {camera_id} ({camera_name}) adicionada com sucesso")
            return True
            
        except Exception as e:
            logger.error(f"Erro ao adicionar câmera {camera_id}: {e}")
            return False
    
    async def remove_camera(self, camera_id: str):
        """Remover câmera do worker"""
        if not self.gstreamer_available:
            logger.warning(f"GStreamer não disponível - nenhuma câmera para remover")
            return
            
        try:
            with self.lock:
                if camera_id in self.cameras:
                    camera = self.cameras[camera_id]
                    await camera.stop()
                    del self.cameras[camera_id]
                    
                    # Remover encoder NVENC se existir
                    if self.nvenc_enabled and self.nvenc_available:
                        nvenc_manager.stop_encoder(camera_id)
                        logger.info(f"🚀 NVENC Encoder removido para câmera {camera_id}")
                    
                    logger.info(f"Câmera {camera_id} removida")
                else:
                    logger.warning(f"Câmera {camera_id} não encontrada")
        except Exception as e:
            logger.error(f"Erro ao remover câmera {camera_id}: {e}")
    
    async def _process_frame(self, camera_id: str, frame: np.ndarray):
        """Processar frame de câmera de forma assíncrona"""
        if frame is None:
            return
            
        try:
            # Incrementar contador de frames
            self.frame_count += 1
            
            # Pular frames para otimização
            if self.frame_count % self.frame_skip != 0:
                return
                
            # Atualizar estatísticas
            self.stats['total_frames_processed'] += 1
            self.stats['last_activity'] = datetime.now()
            
            # Enviar frame para recognition worker se disponível
            if self.recognition_available and self.recognition_client:
                try:
                    await self._send_frame_to_recognition_worker(camera_id, frame)
                except Exception as recognition_error:
                    logger.error(f"Erro ao enviar frame para recognition worker (câmera {camera_id}): {recognition_error}")
            else:
                logger.debug(f"Frame capturado da câmera {camera_id} (recognition worker indisponível)")
            
            # Enviar frame para NVENC encoder se habilitado
            if self.nvenc_enabled and self.nvenc_available:
                try:
                    success = nvenc_manager.encode_frame(camera_id, frame)
                    if success:
                        logger.debug(f"Frame enviado para NVENC encoder {camera_id}")
                    else:
                        logger.warning(f"Falha ao enviar frame para NVENC encoder {camera_id}")
                except Exception as nvenc_error:
                    logger.error(f"Erro no NVENC encoding para câmera {camera_id}: {nvenc_error}")
                
        except Exception as e:
            logger.error(f"Erro ao processar frame da câmera {camera_id}: {e}")
    
    def _on_nvenc_encoded_frame(self, camera_id: str, encoded_data: bytes):
        """Callback para frames codificados pelo NVENC"""
        try:
            logger.debug(f"Frame NVENC codificado para câmera {camera_id}: {len(encoded_data)} bytes")
            
            # Aqui pode ser integrado com WebRTC ou streaming
            # Por exemplo: enviar para clientes WebSocket, salvar em arquivo, etc.
            
            # Atualizar estatísticas
            if 'nvenc_frames_encoded' not in self.stats:
                self.stats['nvenc_frames_encoded'] = 0
            self.stats['nvenc_frames_encoded'] += 1
            
            # Exemplo: broadcast para WebSockets conectados
            # asyncio.create_task(self._broadcast_encoded_frame(camera_id, encoded_data))
            
        except Exception as e:
            logger.error(f"Erro no callback de frame NVENC codificado: {e}")
    
    async def _send_frame_to_recognition_worker(self, camera_id: str, frame: np.ndarray):
        """Enviar frame para o recognition worker"""
        try:
            # Redimensionar frame para otimizar transmissão
            height, width = frame.shape[:2]
            if width > 640:
                scale = 640 / width
                new_width = 640
                new_height = int(height * scale)
                frame = cv2.resize(frame, (new_width, new_height))
            
            # Codificar frame como JPEG para reduzir tamanho
            success, encoded_frame = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if not success:
                logger.error("Falha ao codificar frame")
                return
            
            # Converter para base64
            frame_bytes = encoded_frame.tobytes()
            frame_base64 = base64.b64encode(frame_bytes).decode('utf-8')
            
            # Enviar via Socket.IO
            await self.recognition_client.emit('process_frame', {
                'camera_id': camera_id,
                'frame_base64': frame_base64,
                'timestamp': datetime.now().isoformat()
            })
            
            self.stats['total_frames_sent'] += 1
            
        except Exception as e:
            logger.error(f"Erro ao enviar frame para recognition worker: {e}")
    
    async def run(self):
        """Executar worker em loop"""
        if not self.is_running:
            logger.error("Worker não está inicializado")
            return
            
        logger.info("Iniciando loop principal do GStreamer Worker")
        
        try:
            # Loop principal
            while self.is_running:
                # Verificar saúde das câmeras
                await self._check_cameras_health()
                
                # Verificar conexão com Recognition Worker
                await self._check_recognition_worker_connection()
                
                # Aguardar próximo ciclo
                await asyncio.sleep(self.processing_interval)
                
        except asyncio.CancelledError:
            logger.info("Loop do worker cancelado")
        except Exception as e:
            logger.error(f"Erro no loop principal do worker: {e}")
        finally:
            # Garantir limpeza adequada
            await self.cleanup()
    
    async def _check_cameras_health(self):
        """Verificar saúde das câmeras e reconectar se necessário"""
        if not self.gstreamer_available or not self.cameras:
            return
            
        cameras_to_reconnect = []
        
        # Verificar cada câmera
        for camera_id, camera in self.cameras.items():
            try:
                # Verificar se é um objeto GStreamerCamera ou fallback OpenCV
                if hasattr(camera, 'is_healthy'):
                    if not camera.is_healthy():
                        logger.warning(f"Câmera {camera_id} não está saudável - tentando reconectar")
                        cameras_to_reconnect.append(camera_id)
                elif isinstance(camera, dict) and camera.get('type') == 'opencv_fallback':
                    # Para fallback OpenCV, assumir que está saudável
                    logger.debug(f"Câmera {camera_id} usando fallback OpenCV - assumindo saudável")
                else:
                    logger.warning(f"Câmera {camera_id} tem tipo desconhecido: {type(camera)}")
            except Exception as e:
                logger.error(f"Erro ao verificar saúde da câmera {camera_id}: {e}")
                cameras_to_reconnect.append(camera_id)
        
        # Tentar reconectar câmeras com problemas
        for camera_id in cameras_to_reconnect:
            camera = self.cameras.get(camera_id)
            if camera and hasattr(camera, 'reconnect'):
                success = await camera.reconnect()
                if success:
                    logger.info(f"Câmera {camera_id} reconectada com sucesso")
                else:
                    logger.error(f"Falha ao reconectar câmera {camera_id}")
            elif isinstance(camera, dict):
                logger.debug(f"Câmera {camera_id} é fallback OpenCV - não pode reconectar automaticamente")
    
    async def _check_recognition_worker_connection(self):
        """Verificar e reconectar ao Recognition Worker se necessário"""
        if not self.recognition_available and self.recognition_client:
            try:
                # Tentar reconectar ao Recognition Worker
                logger.info("Tentando reconectar ao Recognition Worker...")
                await self._connect_to_recognition_worker()
            except Exception as e:
                logger.debug(f"Falha na tentativa de reconexão: {e}")
    
    async def cleanup(self):
        """Limpar recursos do worker"""
        logger.info("Limpando recursos do GStreamer Worker")
        
        # Desconectar do recognition worker
        if self.recognition_client:
            try:
                await self.recognition_client.disconnect()
                logger.info("Desconectado do Recognition Worker")
            except Exception as e:
                logger.error(f"Erro ao desconectar do Recognition Worker: {e}")
        
        # Parar todas as câmeras
        if self.cameras:
            for camera_id, camera in list(self.cameras.items()):
                try:
                    if hasattr(camera, 'stop'):
                        await camera.stop()
                        logger.debug(f"Câmera GStreamer {camera_id} parada")
                    elif isinstance(camera, dict) and camera.get('type') == 'opencv_fallback':
                        logger.debug(f"Câmera OpenCV fallback {camera_id} removida")
                    else:
                        logger.debug(f"Câmera desconhecida {camera_id} removida")
                except Exception as e:
                    logger.error(f"Erro ao parar câmera {camera_id}: {e}")
            
            # Limpar dicionário de câmeras
            self.cameras.clear()
        
        # Parar todos os encoders NVENC
        if self.nvenc_enabled and self.nvenc_available:
            try:
                nvenc_manager.stop_all()
                logger.info("🚀 Todos os NVENC Encoders parados")
            except Exception as e:
                logger.error(f"Erro ao parar NVENC Encoders: {e}")
        
        # Marcar como não em execução
        self.is_running = False
        logger.info("GStreamer Worker finalizado")
    
    def get_stats(self) -> dict:
        """Obter estatísticas do worker"""
        # Atualizar estatísticas em tempo real
        stats = self.stats.copy()
        
        # Adicionar informações sobre câmeras
        stats['cameras'] = {}
        if self.cameras:
            for camera_id, camera in self.cameras.items():
                try:
                    if hasattr(camera, 'get_stats'):
                        stats['cameras'][camera_id] = camera.get_stats()
                    elif isinstance(camera, dict) and camera.get('type') == 'opencv_fallback':
                        stats['cameras'][camera_id] = {
                            'camera_id': camera_id,
                            'type': 'opencv_fallback',
                            'status': camera.get('status', 'unknown'),
                            'config': camera.get('config', {})
                        }
                    else:
                        stats['cameras'][camera_id] = {
                            'camera_id': camera_id,
                            'type': 'unknown',
                            'status': 'unknown'
                        }
                except Exception as e:
                    logger.error(f"Erro ao obter stats da câmera {camera_id}: {e}")
                    stats['cameras'][camera_id] = {
                        'camera_id': camera_id,
                        'type': 'error',
                        'error': str(e)
                    }
        
        # Adicionar informações sobre tempo de execução
        if stats['start_time']:
            runtime = datetime.now() - stats['start_time']
            stats['runtime_seconds'] = runtime.total_seconds()
        
        # Adicionar informações sobre NVENC
        stats['nvenc_enabled'] = self.nvenc_enabled
        stats['nvenc_available'] = self.nvenc_available
        
        if self.nvenc_enabled and self.nvenc_available:
            try:
                nvenc_stats = nvenc_manager.get_stats()
                stats['nvenc'] = nvenc_stats
            except Exception as e:
                logger.error(f"Erro ao obter stats do NVENC: {e}")
                stats['nvenc'] = {'error': str(e)}
        
        return stats
    
    def __del__(self):
        """Destrutor para garantir limpeza adequada"""
        if self.is_running:
            logger.warning("GStreamerWorker destruído sem chamar cleanup()")

    def recognition_result(self, camera_id, person_id, person_name, confidence, frame_path=None, bounding_box=None):
        """Callback para resultados de reconhecimento"""
        try:
            camera_name = self.camera_names.get(camera_id, "Desconhecida")
            is_unknown = person_id is None or person_id.startswith('unknown_')
            
            # Formatar nome para pessoas desconhecidas
            if is_unknown:
                person_display = f"Pessoa desconhecida {person_name}"
            else:
                person_display = person_name
                
            # Log do resultado
            emoji = "❓" if is_unknown else "✅"
            logger.info(f"{emoji} {person_display} detectada na câmera {camera_id}")
            
            # Enviar para o banco de dados
            self.save_recognition(camera_id, person_id, person_name, confidence, 
                                frame_path, bounding_box)
                                
        except Exception as e:
            logger.error(f"Erro ao processar resultado de reconhecimento: {e}")
            
    def camera_error_handler(self, camera_id, error_message):
        """Manipulador de erros de câmera"""
        try:
            logger.error(f"Erro na câmera {camera_id}: {error_message}")
            
            # Se o erro estiver relacionado à decodificação, podemos tentar alternar para o pipeline alternativo
            if "decode" in error_message.lower() or "codec" in error_message.lower() or "buffer" in error_message.lower():
                logger.warning(f"Erro de decodificação detectado na câmera {camera_id}. Tentando alternar para pipeline alternativo.")
                
                # Obter configuração atual
                current_config = self.camera_configs.get(camera_id, {})
                
                # Se já estiver usando o pipeline alternativo, apenas registrar o erro
                if current_config.get('use_alt_pipeline', False):
                    logger.warning(f"Câmera {camera_id} já está usando pipeline alternativo. Erro persistente.")
                    return
                
                # Alternar para pipeline alternativo
                current_config['use_alt_pipeline'] = True
                self.camera_configs[camera_id] = current_config
                
                # Reiniciar a câmera
                logger.info(f"Reiniciando câmera {camera_id} com pipeline alternativo...")
                asyncio.create_task(self.restart_camera_with_alt_pipeline(camera_id, current_config))
        except Exception as e:
            logger.error(f"Erro ao manipular erro de câmera: {e}")
    
    async def restart_camera_with_alt_pipeline(self, camera_id, config):
        """Reiniciar câmera com pipeline alternativo"""
        try:
            # Remover câmera atual
            await self.remove_camera(camera_id)
            
            # Pequena pausa para garantir que a câmera seja encerrada corretamente
            await asyncio.sleep(2)
            
            # Adicionar câmera novamente com pipeline alternativo
            await self.add_camera(camera_id, config)
            
            # Atualizar configuração no banco de dados
            asyncio.create_task(self.update_camera_config_in_db(camera_id, config))
            
            logger.info(f"Câmera {camera_id} reiniciada com pipeline alternativo")
        except Exception as e:
            logger.error(f"Erro ao reiniciar câmera com pipeline alternativo: {e}")
    
    async def update_camera_config_in_db(self, camera_id, config):
        """Atualizar configuração da câmera no banco de dados"""
        try:
            import json
            
            # Usar SQLite direto (compatibilidade com MSYS2)
            with get_db_sync() as cursor:
                # Atualizar configuração da câmera
                cursor.execute("""
                    UPDATE cameras 
                    SET config = ? 
                    WHERE id = ?
                """, (json.dumps(config), camera_id))
                
                if cursor.rowcount > 0:
                    logger.info(f"Configuração da câmera {camera_id} atualizada no banco de dados")
                else:
                    logger.warning(f"Câmera {camera_id} não encontrada no banco de dados")
                    
        except Exception as e:
            logger.error(f"Erro ao atualizar configuração da câmera no banco de dados: {e}")

    async def _get_camera_details(self, camera_id):
        """Obter detalhes da câmera do banco de dados"""
        try:
            import json
            
            # Usar SQLite direto (compatibilidade com MSYS2)
            logger.debug(f"Obtendo detalhes da câmera {camera_id} via SQLite")
            
            with get_db_sync() as cursor:
                cursor.execute("""
                    SELECT id, name, url, type, status, fps_limit, config 
                    FROM cameras 
                    WHERE id = ?
                """, (camera_id,))
                row = cursor.fetchone()
                
                if not row:
                    logger.warning(f"Câmera {camera_id} não encontrada no banco de dados")
                    return None
                
                # Criar objeto compatível
                camera = models.Camera(row)
                
                # Extrair configuração
                config = json.loads(camera.config) if camera.config else {}
                
                # Retornar detalhes da câmera
                return {
                    'id': camera.id,
                    'name': camera.name,
                    'url': camera.url,
                    'type': camera.type,
                    'fps_limit': camera.fps_limit or 10,
                    'config': config
                }
                
        except Exception as e:
            logger.error(f"Erro ao obter detalhes da câmera {camera_id}: {e}")
            return None

    async def frame_callback(self, camera_id, frame):
        """Callback para processar frames das câmeras"""
        try:
            if frame is None:
                return
            
            # Processar o frame (análise, reconhecimento, etc)
            await self._process_frame(camera_id, frame)
                
        except Exception as e:
            logger.error(f"Erro no callback de frame da câmera {camera_id}: {e}")

# Criar instância global do worker para ser importada por outros módulos
gstreamer_worker = GStreamerWorker() 
