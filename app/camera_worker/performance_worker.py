"""
Performance Worker - Worker principal usando o sistema de alta performance
Substitui o GStreamer Worker tradicional com arquitetura multiprocessing
"""

import asyncio
import aiohttp
import os
import sys
import time
from typing import Dict, List, Any, Optional
from datetime import datetime
from loguru import logger
import signal
import threading

# Importar configuração compatível com MSYS2
try:
    # Tentar configuração normal primeiro (para ambiente Conda)
    from app.core.config import settings
    config_source = "app.core.config"
except ImportError:
    # Fallback para configuração simplificada (ambiente MSYS2)
    from app.camera_worker.simple_config import settings
    config_source = "app.camera_worker.simple_config"

logger.info(f"[PerformanceWorker] Configuração carregada de: {config_source}")

# Tentar importar módulos de performance (podem não estar disponíveis no MSYS2)
try:
    from app.core.performance.manager import PerformanceManager
    from app.core.performance.camera_worker import FrameData, RecognitionResult
    from app.core.utils import make_json_serializable
    PERFORMANCE_AVAILABLE = True
except ImportError as e:
    logger.warning(f"⚠️ Módulos de performance não disponíveis: {e}")
    logger.info("🔄 Performance Worker será desabilitado, usando fallback tradicional")
    PERFORMANCE_AVAILABLE = False
    
    # Definir classes dummy para compatibilidade
    class PerformanceManager:
        def __init__(self): pass
        def start(self): return False
        def stop(self): pass
        def is_running(self): return False
        def add_camera(self, *args): return False
        def get_stats(self): return {}
        def register_result_callback(self, *args): pass
    
    class FrameData:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)
    
    class RecognitionResult:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)
    
    def make_json_serializable(obj):
        return obj


class PerformanceWorkerMain:
    """
    Worker principal que gerencia o sistema de alta performance
    - Integração com API para carregar câmeras
    - Gerenciamento via PerformanceManager
    - Comunicação com Recognition Worker via Socket.IO
    - Monitoramento e estatísticas
    """
    
    def __init__(self):
        self.performance_manager = PerformanceManager()
        self.is_running = False
        
        # URLs de serviços (usando localhost pois estamos com network_mode: host)
        self.api_url = os.environ.get('API_BASE_URL', 'http://127.0.0.1:17234')
        self.recognition_worker_url = os.environ.get('RECOGNITION_WORKER_URL', 'http://127.0.0.1:17235')
        
        # Socket.IO para comunicação com recognition worker
        self.recognition_client = None
        self.recognition_available = False
        
        # Socket.IO para comunicação com WebRTC bridge
        self.webrtc_client = None
        self.webrtc_available = False
        self.webrtc_url = "http://127.0.0.1:17236"  # WebRTC server port
        
        # Estatísticas
        self.stats = {
            'start_time': None,
            'cameras_loaded': 0,
            'total_frames_sent': 0,
            'recognition_responses': 0
        }
        
        # Thread de monitoramento
        self.monitor_thread = None
        self.monitor_stop = threading.Event()
        
        logger.info("Performance Worker Main inicializado")
    
    async def initialize(self) -> bool:
        """Inicializar o worker de performance"""
        try:
            logger.info("🚀 Inicializando Performance Worker...")
            logger.info(f"🔧 Python executable: {sys.executable}")
            logger.info(f"🔧 Working directory: {os.getcwd()}")
            logger.info(f"🔧 PYTHONPATH: {os.environ.get('PYTHONPATH', 'Not set')}")
            logger.info(f"🔧 USE_PERFORMANCE_WORKER: {os.environ.get('USE_PERFORMANCE_WORKER', 'Not set')}")
            logger.info(f"🔧 API_BASE_URL: {self.api_url}")
            logger.info(f"🔧 Performance modules available: {PERFORMANCE_AVAILABLE}")
            
            # Se módulos de performance não estão disponíveis, falhar graciosamente
            if not PERFORMANCE_AVAILABLE:
                logger.warning("⚠️ Módulos de performance não disponíveis - usando fallback tradicional")
                return False
            
            # Aguardar API estar disponível
            await self._wait_for_api()
            
            # Conectar ao recognition worker
            await self._connect_to_recognition_worker()
            
            # Conectar ao WebRTC bridge
            await self._connect_to_webrtc_bridge()
            
            # Registrar callback para resultados
            self.performance_manager.register_result_callback(self._on_recognition_result)
            
            # Iniciar performance manager
            if not self.performance_manager.start():
                logger.error("Falha ao iniciar Performance Manager")
                return False
            
            # Carregar câmeras do banco de dados
            await self._load_cameras_from_database()
            
            # Iniciar monitoramento
            self._start_monitoring()
            
            self.is_running = True
            self.stats['start_time'] = datetime.now()
            
            logger.info("✅ Performance Worker inicializado com sucesso")
            return True
            
        except Exception as e:
            logger.error(f"❌ Erro ao inicializar Performance Worker: {e}")
            return False
    
    async def _wait_for_api(self):
        """Aguardar API estar disponível"""
        max_retries = 30
        retry_count = 0
        
        logger.info(f"Aguardando API em {self.api_url}")
        
        while retry_count < max_retries:
            try:
                timeout = aiohttp.ClientTimeout(total=10)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(f"{self.api_url}/health") as response:
                        if response.status == 200:
                            data = await response.json()
                            logger.info(f"✅ API disponível: {data.get('status', 'unknown')}")
                            return
                        else:
                            logger.warning(f"API respondeu com status {response.status}")
                            
            except Exception as e:
                # Tentativa alternativa com localhost explícito
                if "Name or service not known" in str(e) and "presence-api" in str(e):
                    try:
                        # Tentar com localhost explícito
                        alt_url = "http://localhost:9000"
                        logger.debug(f"Tentando API com localhost: {alt_url}")
                        async with aiohttp.ClientSession(timeout=timeout) as session:
                            async with session.get(f"{alt_url}/health") as response:
                                if response.status == 200:
                                    data = await response.json()
                                    logger.info(f"✅ API disponível via localhost: {data.get('status', 'unknown')}")
                                    # Atualizar URL para futuras chamadas
                                    self.api_url = alt_url
                                    return
                    except Exception as alt_e:
                        logger.debug(f"API não disponível via localhost: {alt_e}")
                
                logger.debug(f"API não disponível ainda: {e}")
            
            retry_count += 1
            await asyncio.sleep(2)
            
            # A cada 5 tentativas, mostrar tempo restante
            if retry_count % 5 == 0:
                remaining = ((max_retries - retry_count) * 2)  # segundos restantes
                logger.info(f"API ainda não disponível, aguardando... ({retry_count}/{max_retries})s")
        
        logger.error(f"❌ Timeout aguardando API. Continuando mesmo assim...")
        logger.warning(f"⚠️ API não disponível, mas continuando...")
        # Não lançar exceção, apenas continuar mesmo sem API
    
    async def _connect_to_recognition_worker(self):
        """Conectar ao recognition worker via Socket.IO"""
        try:
            try:
                import socketio
            except ImportError as e:
                logger.error(f"❌ python-socketio não está instalado: {e}")
                logger.error("Execute: pip install python-socketio")
                self.recognition_available = False
                return
            
            logger.info(f"Conectando ao Recognition Worker em {self.recognition_worker_url}")
            
            self.recognition_client = socketio.AsyncClient()
            
            @self.recognition_client.event
            async def connect():
                logger.info("✅ Conectado ao Recognition Worker via Socket.IO")
                logger.info("📡 Camera Worker pronto para enviar frames")
                self.recognition_available = True
            
            @self.recognition_client.event
            async def disconnect():
                logger.warning("❌ Desconectado do Recognition Worker")
                self.recognition_available = False
            
            @self.recognition_client.event
            async def status(data):
                """Receber status do Recognition Worker"""
                logger.info(f"📊 Status do Recognition Worker: {data}")
                if data.get('status') == 'connected' and data.get('recognition_ready'):
                    logger.info("✅ Recognition Worker pronto para processar frames")
                    self.recognition_available = True
            
            @self.recognition_client.event
            async def error(data):
                """Receber erros do Recognition Worker"""
                logger.error(f"❌ Erro do Recognition Worker: {data.get('message', 'Unknown error')}")
            
            @self.recognition_client.event
            async def recognition_result(data):
                """Receber resultado do recognition worker"""
                try:
                    self.stats['recognition_responses'] += 1
                    camera_id = data.get('camera_id')
                    faces_detected = data.get('faces_detected', 0)
                    recognitions = data.get('recognitions', [])
                    
                    logger.info(f"🎯 Resultado recebido: Câmera {camera_id}, {faces_detected} faces, {len(recognitions)} reconhecimentos")
                    
                    # Log de pessoas reconhecidas
                    for recognition in recognitions:
                        if recognition.get('person_id') and not recognition.get('is_unknown', False):
                            person_name = recognition.get('person_name', 'Desconhecido')
                            confidence = recognition.get('confidence', 0)
                            logger.info(f"👤 {person_name} reconhecido (conf: {confidence:.2f})")
                    
                except Exception as e:
                    logger.error(f"Erro ao processar resultado: {e}")
            
            # Conectar
            try:
                logger.info(f"🔌 Tentando conectar Socket.IO em: {self.recognition_worker_url}")
                await asyncio.wait_for(
                    self.recognition_client.connect(self.recognition_worker_url),
                    timeout=10.0
                )
                logger.info("✅ Conexão Socket.IO com Recognition Worker estabelecida")
            except asyncio.TimeoutError:
                logger.warning("⏰ Timeout ao conectar Socket.IO com Recognition Worker")
                self.recognition_available = False
            except ConnectionError as e:
                logger.error(f"❌ Erro de conexão Socket.IO: {e}")
                self.recognition_available = False
            
        except Exception as e:
            logger.warning(f"⚠️ Não foi possível conectar ao Recognition Worker: {e}")
            self.recognition_available = False
    
    async def _connect_to_webrtc_bridge(self):
        """Conectar ao WebRTC bridge via Socket.IO"""
        try:
            try:
                import socketio
            except ImportError as e:
                logger.error(f"❌ python-socketio não está instalado: {e}")
                self.webrtc_available = False
                return
            
            logger.info(f"Conectando ao WebRTC Bridge em {self.webrtc_url}")
            
            self.webrtc_client = socketio.AsyncClient()
            
            @self.webrtc_client.event
            async def connect():
                logger.info("✅ Conectado ao WebRTC Bridge")
                self.webrtc_available = True
            
            @self.webrtc_client.event
            async def disconnect():
                logger.warning("❌ Desconectado do WebRTC Bridge")
                self.webrtc_available = False
            
            @self.webrtc_client.event
            async def request_stream(data):
                """WebRTC solicitou stream de uma câmera específica"""
                try:
                    camera_id = data.get('camera_id')
                    logger.info(f"🎥 WebRTC solicitou stream da câmera {camera_id}")
                    # Confirmar que temos essa câmera ativa
                    await self.webrtc_client.emit('stream_available', {'camera_id': camera_id, 'status': 'ready'})
                except Exception as e:
                    logger.error(f"Erro ao processar solicitação de stream: {e}")
            
            # Tentar conectar (com timeout)
            try:
                await asyncio.wait_for(
                    self.webrtc_client.connect(self.webrtc_url),
                    timeout=5.0
                )
                logger.info("✅ Conexão estabelecida com WebRTC Bridge")
            except asyncio.TimeoutError:
                logger.warning(f"⚠️ Timeout ao conectar ao WebRTC Bridge em {self.webrtc_url}")
                self.webrtc_available = False
            except Exception as e:
                logger.warning(f"⚠️ WebRTC Bridge não disponível: {e}")
                self.webrtc_available = False
                
        except Exception as e:
            logger.error(f"Erro ao conectar ao WebRTC bridge: {e}")
            self.webrtc_available = False
    
    async def _load_cameras_from_database(self):
        """Carregar câmeras do banco de dados via API"""
        try:
            logger.info("Carregando câmeras do banco de dados...")
            
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(f"{self.api_url}/api/v1/cameras") as response:
                    if response.status == 200:
                        response_data = await response.json()
                        
                        # Verificar formato da resposta
                        if isinstance(response_data, dict) and 'cameras' in response_data:
                            cameras_data = response_data['cameras']
                        elif isinstance(response_data, list):
                            cameras_data = response_data
                        else:
                            cameras_data = []
                        
                        logger.info(f"Encontradas {len(cameras_data)} câmeras no banco")
                        
                        # Adicionar cada câmera ao performance manager
                        for camera in cameras_data:
                            # Verificar se câmera está ativa e tem URL
                            is_enabled = camera.get('status') == 'active' or camera.get('enabled', True)
                            camera_url = camera.get('url') or camera.get('connection_string')
                            
                            logger.debug(f"Processando câmera {camera.get('id')}: status={camera.get('status')}, enabled={is_enabled}, url={camera_url}")
                            
                            if is_enabled and camera_url:
                                camera_id = str(camera.get('id'))
                                camera_type = camera.get('type', 'rtsp')
                                
                                # Criar configuração unificada do pipeline GStreamer
                                camera_config = {
                                    'url': camera_url,
                                    'type': camera_type,
                                    'fps_limit': min(camera.get('fps_limit', 10), 15),
                                    'enabled': is_enabled,
                                    'width': 640,
                                    'height': 480,
                                    # Configuração específica do pipeline unificado
                                    'rtsp_url': camera_url,
                                    'source_type': 'video_file' if camera_type == 'video_file' or 
                                                  (camera_url and any(camera_url.endswith(ext) for ext in ['.mp4', '.avi', '.mov', '.mkv'])) 
                                                  else 'rtsp',
                                    'video_file_path': camera_url if camera_type == 'video_file' or 
                                                      (camera_url and any(camera_url.endswith(ext) for ext in ['.mp4', '.avi', '.mov', '.mkv']))
                                                      else '',
                                    'video_file_loop': True,
                                    'video_file_fps': 25 if camera_type == 'video_file' else 30,
                                    'use_hardware_decode': True,
                                    'use_hardware_encode': True,
                                    'enable_recognition': True
                                }
                                
                                logger.info(f"Adicionando câmera {camera_id} ao sistema de performance (Pipeline Unificado)")
                                logger.info(f"  - Tipo: {camera_config['source_type']}")
                                logger.info(f"  - URL/Arquivo: {camera_url}")
                                logger.info(f"  - FPS: {camera_config['video_file_fps' if camera_config['source_type'] == 'video_file' else 'fps_limit']}")
                                
                                if self.performance_manager.add_camera(camera_id, camera_config):
                                    self.stats['cameras_loaded'] += 1
                                    logger.info(f"✅ Câmera {camera_id} adicionada ao pipeline unificado")
                                else:
                                    logger.error(f"❌ Falha ao adicionar câmera {camera_id} ao pipeline unificado")
                            else:
                                logger.warning(f"Câmera {camera.get('id')} pulada - enabled={is_enabled}, url={camera_url}")
                        
                        logger.info(f"Carregamento concluído. {self.stats['cameras_loaded']} câmeras ativas")
                    else:
                        logger.error(f"Erro ao carregar câmeras: status {response.status}")
        
        except Exception as e:
            logger.error(f"Erro ao carregar câmeras: {e}")
    
    def _on_recognition_result(self, frame_data: FrameData):
        """Callback para processar resultados de reconhecimento"""
        try:
            loop = None
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                # Cria novo loop se nenhum estiver ativo (ex: thread nova)
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                logger.debug("Criado novo event loop para callback")
            
            # Enviar para recognition worker se disponível
            if self.recognition_available and self.recognition_client:
                loop.create_task(self._send_to_recognition_worker(frame_data))
            else:
                logger.warning("Recognition worker não disponível para envio")
            
            # Enviar frame processado para WebRTC
            loop.create_task(self._send_to_webrtc(frame_data))
            
            # Log de reconhecimentos importantes
            for recognition in frame_data.recognitions:
                if not recognition.is_unknown and recognition.confidence > 0.8:
                    logger.info(f"👤 {recognition.person_name} reconhecido na câmera {frame_data.camera_id}")
            
        except Exception as e:
            logger.error(f"Erro ao processar resultado: {e}")
    
    async def _send_to_recognition_worker(self, frame_data: FrameData):
        """Enviar frame para o recognition worker processar"""
        try:
            if not self.recognition_client:
                logger.warning("Recognition client não disponível")
                return
            
            if not self.recognition_available:
                logger.warning("Recognition worker não conectado")
                return
            
            # Se não há frame, não há o que processar
            if not hasattr(frame_data, 'frame') or frame_data.frame is None:
                logger.warning(f"Frame vazio da câmera {frame_data.camera_id}, pulando reconhecimento")
                return
            
            # Converter frame para base64 para envio via Socket.IO
            import base64
            import cv2
            
            # Comprimir frame para reduzir tamanho
            _, buffer = cv2.imencode('.jpg', frame_data.frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            frame_base64 = base64.b64encode(buffer).decode('utf-8')
            
            # Criar dados para envio (seguindo protocolo exato)
            data = {
                'frame_base64': frame_base64,  # Protocolo correto
                'camera_id': frame_data.camera_id,
                'timestamp': frame_data.timestamp.isoformat(),
                'frame_id': str(frame_data.frame_id)
            }
            
            # Enviar frame para processamento
            await self.recognition_client.emit('process_frame', data)
            self.stats['total_frames_sent'] += 1
            logger.debug(f"Frame {frame_data.frame_id} da câmera {frame_data.camera_id} enviado para reconhecimento")
            
        except Exception as e:
            logger.error(f"Erro ao enviar para recognition worker: {e}")
    
    async def _send_to_webrtc(self, frame_data: FrameData):
        """Enviar frame processado com overlay para WebRTC"""
        try:
            # Verificar se há frame e se há WebRTC clients conectados
            if not hasattr(frame_data, 'frame') or frame_data.frame is None:
                return
            
            # Aplicar overlay com reconhecimentos no frame
            processed_frame = await self._apply_recognition_overlay(frame_data)
            
            # Converter frame para base64 para envio via Socket.IO
            import base64
            import cv2
            
            # Comprimir frame para WebRTC (qualidade maior que recognition worker)
            _, buffer = cv2.imencode('.jpg', processed_frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
            frame_base64 = base64.b64encode(buffer).decode('utf-8')
            
            # Criar dados para WebRTC
            webrtc_data = {
                'camera_id': frame_data.camera_id,
                'frame_data': frame_base64,
                'timestamp': frame_data.timestamp.isoformat(),
                'recognition_count': len(frame_data.recognitions),
                'frame_shape': processed_frame.shape
            }
            
            # Enviar via Socket.IO para WebRTC bridge
            if self.webrtc_available and self.webrtc_client:
                try:
                    await self.webrtc_client.emit('processed_frame', webrtc_data)
                    logger.debug(f"Frame enviado para WebRTC: câmera {frame_data.camera_id} "
                                f"({len(frame_data.recognitions)} reconhecimentos)")
                except Exception as e:
                    logger.error(f"Erro ao enviar frame para WebRTC: {e}")
            else:
                logger.debug(f"WebRTC não disponível - frame processado da câmera {frame_data.camera_id} "
                            f"({len(frame_data.recognitions)} reconhecimentos)")
            
        except Exception as e:
            logger.error(f"Erro ao enviar para WebRTC: {e}")
    
    async def _apply_recognition_overlay(self, frame_data: FrameData):
        """Aplicar overlay futurístico com reconhecimentos"""
        try:
            import cv2
            import numpy as np
            
            # Copiar frame original
            frame = frame_data.frame.copy()
            height, width = frame.shape[:2]
            
            # Aplicar overlay para cada reconhecimento
            for recognition in frame_data.recognitions:
                if hasattr(recognition, 'bbox') and recognition.bbox:
                    x1, y1, x2, y2 = map(int, recognition.bbox)
                    
                    # Cores baseadas no status do reconhecimento
                    if recognition.is_unknown:
                        color = (0, 100, 255)  # Laranja para desconhecidos
                        label_bg = (0, 50, 128)
                    else:
                        color = (0, 255, 100)  # Verde para conhecidos
                        label_bg = (0, 128, 50)
                    
                    # Bounding box principal
                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                    
                    # Cantos do bounding box (estilo futurístico)
                    corner_length = 20
                    corner_thickness = 3
                    
                    # Canto superior esquerdo
                    cv2.line(frame, (x1, y1), (x1 + corner_length, y1), color, corner_thickness)
                    cv2.line(frame, (x1, y1), (x1, y1 + corner_length), color, corner_thickness)
                    
                    # Canto superior direito
                    cv2.line(frame, (x2, y1), (x2 - corner_length, y1), color, corner_thickness)
                    cv2.line(frame, (x2, y1), (x2, y1 + corner_length), color, corner_thickness)
                    
                    # Canto inferior esquerdo
                    cv2.line(frame, (x1, y2), (x1 + corner_length, y2), color, corner_thickness)
                    cv2.line(frame, (x1, y2), (x1, y2 - corner_length), color, corner_thickness)
                    
                    # Canto inferior direito
                    cv2.line(frame, (x2, y2), (x2 - corner_length, y2), color, corner_thickness)
                    cv2.line(frame, (x2, y2), (x2, y2 - corner_length), color, corner_thickness)
                    
                    # Label com nome e confiança
                    name = getattr(recognition, 'person_name', 'Unknown')
                    confidence = getattr(recognition, 'confidence', 0.0)
                    label = f"{name} ({confidence:.2f})"
                    
                    # Tamanho do texto
                    font = cv2.FONT_HERSHEY_SIMPLEX
                    font_scale = 0.6
                    thickness = 2
                    (label_width, label_height), baseline = cv2.getTextSize(label, font, font_scale, thickness)
                    
                    # Fundo do label
                    label_y = max(y1 - 10, label_height + 10)
                    cv2.rectangle(frame, 
                                (x1, label_y - label_height - 10), 
                                (x1 + label_width + 10, label_y + 5), 
                                label_bg, -1)
                    
                    # Texto do label
                    cv2.putText(frame, label, (x1 + 5, label_y - 5), 
                              font, font_scale, (255, 255, 255), thickness)
            
            # Adicionar informações do sistema no canto superior esquerdo
            info_text = f"Camera: {frame_data.camera_id} | FPS: {getattr(frame_data, 'fps', 'N/A')}"
            cv2.putText(frame, info_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            
            # Timestamp
            timestamp = frame_data.timestamp.strftime("%H:%M:%S")
            cv2.putText(frame, timestamp, (10, height - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            
            return frame
            
        except Exception as e:
            logger.error(f"Erro ao aplicar overlay: {e}")
            return frame_data.frame  # Retornar frame original em caso de erro
    
    def _start_monitoring(self):
        """Iniciar thread de monitoramento"""
        self.monitor_stop.clear()
        self.monitor_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self.monitor_thread.start()
        logger.info("Thread de monitoramento iniciada")
    
    def _monitoring_loop(self):
        """Loop de monitoramento de estatísticas"""
        while not self.monitor_stop.is_set():
            try:
                # Log de estatísticas a cada 30 segundos
                stats = self.get_stats()
                active_cameras = stats['performance_manager']['active_cameras']
                total_frames = stats['performance_manager']['total_frames_processed']
                avg_time = stats['performance_manager']['average_processing_time_ms']
                
                if total_frames > 0:
                    logger.info(f"📊 Câmeras ativas: {active_cameras}, "
                              f"Frames processados: {total_frames}, "
                              f"Tempo médio: {avg_time:.1f}ms")
                
                time.sleep(30)  # Log a cada 30 segundos
                
            except Exception as e:
                logger.error(f"Erro no monitoramento: {e}")
                time.sleep(10)
    
    async def run(self):
        """Executar o worker principal"""
        try:
            if not self.is_running:
                logger.error("Worker não está inicializado")
                return
            
            logger.info("📹 Performance Worker em execução")
            
            # Configurar signal handlers
            def signal_handler(signum, frame):
                logger.info(f"Recebido sinal {signum}, parando...")
                self.stop()
            
            signal.signal(signal.SIGTERM, signal_handler)
            signal.signal(signal.SIGINT, signal_handler)
            
            # Loop principal - manter worker vivo
            while self.is_running:
                await asyncio.sleep(1)
                
                # Verificar saúde do sistema
                if not self.performance_manager.is_running:
                    logger.error("Performance Manager parou inesperadamente")
                    break
            
        except KeyboardInterrupt:
            logger.info("Interrompido pelo usuário")
        except Exception as e:
            logger.error(f"Erro no loop principal: {e}")
        finally:
            self.stop()
    
    def stop(self):
        """Parar o worker"""
        try:
            logger.info("Parando Performance Worker...")
            
            self.is_running = False
            
            # Parar monitoramento
            self.monitor_stop.set()
            if self.monitor_thread:
                self.monitor_thread.join(timeout=5)
            
            # Desconectar recognition worker
            if self.recognition_client:
                asyncio.create_task(self.recognition_client.disconnect())
            
            # Parar performance manager
            self.performance_manager.stop()
            
            logger.info("✅ Performance Worker parado")
            
        except Exception as e:
            logger.error(f"Erro ao parar Performance Worker: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Obter estatísticas completas"""
        stats = self.stats.copy()
        
        # Adicionar estatísticas do performance manager
        stats['performance_manager'] = self.performance_manager.get_stats()
        
        # Adicionar tempo de execução
        if stats['start_time']:
            runtime = datetime.now() - stats['start_time']
            stats['runtime_seconds'] = runtime.total_seconds()
        
        # Status da conexão
        stats['recognition_worker_connected'] = self.recognition_available
        
        return stats


async def main():
    """Função principal"""
    # Configurar logging
    logger.remove()
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | <white>{message}</white>",
        level="INFO"
    )
    
    # Adicionar log para arquivo
    logger.add(
        "logs/performance_worker.log",
        rotation="1 day",
        retention="30 days",
        level="INFO",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{function}:{line} | {message}"
    )
    
    logger.info("🚀 Iniciando Performance Worker Main...")
    
    worker = PerformanceWorkerMain()
    
    try:
        # Inicializar
        if not await worker.initialize():
            logger.error("❌ Falha na inicialização")
            return
        
        # Executar
        await worker.run()
        
    except Exception as e:
        logger.error(f"❌ Erro no Performance Worker: {e}")
    finally:
        worker.stop()


if __name__ == "__main__":
    asyncio.run(main())