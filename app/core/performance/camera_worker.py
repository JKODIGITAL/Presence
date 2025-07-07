"""
Camera Worker - Processo dedicado para cada câmera IP usando GStreamer + GPU
Sem OpenCV na captura para máxima performance
"""

import os
import sys
import time
import signal
import numpy as np
from typing import Dict, Any, Optional, Tuple, List
from multiprocessing import Queue, Process, Event
from loguru import logger
from dataclasses import dataclass
from datetime import datetime
import threading
import weakref

# Import utility functions
from app.core.utils import convert_bbox_to_python_ints, safe_float_conversion

# Configurar ambiente CUDA antes de qualquer importação
os.environ.pop('CUDA_VISIBLE_DEVICES', None)
os.environ.pop('DISABLE_GPU', None)

# Importações GStreamer
try:
    import gi
    gi.require_version('Gst', '1.0')
    gi.require_version('GstApp', '1.0') 
    from gi.repository import Gst, GstApp, GLib
    
    if not Gst.is_initialized():
        Gst.init(None)
    
    GSTREAMER_AVAILABLE = True
    logger.info(f"GStreamer inicializado: {Gst.version_string()}")
except Exception as e:
    logger.error(f"GStreamer não disponível: {e}")
    GSTREAMER_AVAILABLE = False
    Gst = None
    GstApp = None
    GLib = None


@dataclass
class RecognitionResult:
    """Resultado do reconhecimento facial"""
    person_id: Optional[str]
    person_name: Optional[str]
    confidence: float
    bbox: Tuple[int, int, int, int]  # x, y, width, height
    embedding: Optional[np.ndarray]
    is_unknown: bool = False
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


@dataclass
class FrameData:
    """Dados do frame processado"""
    camera_id: str
    frame_id: int
    timestamp: datetime
    recognitions: List[RecognitionResult]
    frame_shape: Tuple[int, int, int]  # height, width, channels
    processing_time_ms: float
    frame: Optional[np.ndarray] = None  # Frame atual (para envio ao Recognition Worker)


class CameraWorker:
    """
    Worker de alta performance para uma câmera específica
    - 1 processo por câmera
    - GStreamer com decodificação por hardware (NVDEC/CUDA)
    - InsightFace GPU para reconhecimento
    - FAISS GPU para busca vetorial
    - Zero OpenCV na captura
    """
    
    def __init__(self, camera_id: str, camera_config: Dict[str, Any], 
                 result_queue: Queue, stop_event: Event):
        self.camera_id = camera_id
        self.camera_config = camera_config
        self.result_queue = result_queue
        self.stop_event = stop_event
        
        # Estado do worker
        self.is_running = False
        self.pipeline = None
        self.main_loop = None
        
        # Estatísticas
        self.stats = {
            'frames_processed': 0,
            'faces_detected': 0,
            'recognitions_made': 0,
            'errors': 0,
            'start_time': None,
            'last_frame_time': None
        }
        
        # Frame management
        self.frame_counter = 0
        self.fps_limit = camera_config.get('fps_limit', 10)
        self.frame_skip = max(1, 30 // self.fps_limit)  # Calcular skip baseado no FPS desejado
        
        # Configurações de performance
        self.max_buffers = 2  # Buffer mínimo para baixa latência
        self.drop_threshold = 0.8  # Drop frames se buffer > 80%
        
        logger.info(f"Worker para câmera {camera_id} criado (FPS: {self.fps_limit}, skip: {self.frame_skip})")
    
    def _setup_signal_handlers(self):
        """Configurar handlers para sinais do sistema"""
        def signal_handler(signum, frame):
            logger.info(f"Worker {self.camera_id}: Recebido sinal {signum}, parando...")
            self.stop_event.set()
            if self.main_loop:
                self.main_loop.quit()
        
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
    
    
    def _build_gstreamer_pipeline(self) -> str:
        """
        Construir pipeline GStreamer UNIFICADO com suporte para RTSP e arquivos de vídeo
        - Suporte para MP4, AVI, MOV via filesrc + decodebin
        - NVDEC para decodificação H.264/H.265 por hardware
        - Buffer mínimo para baixa latência
        - Controle de FPS nativo
        """
        rtsp_url = self.camera_config.get('url', '')
        camera_type = self.camera_config.get('type', 'rtsp')
        source_type = self.camera_config.get('source_type', 'rtsp')
        video_file_path = self.camera_config.get('video_file_path', '')
        
        if camera_type == 'webcam':
            # Pipeline para webcam local
            device = rtsp_url if rtsp_url.startswith('/dev/') else f'/dev/video{rtsp_url}'
            pipeline_str = f"""
                v4l2src device={device}
                ! video/x-raw,width=640,height=480,framerate={self.fps_limit}/1
                ! videoconvert
                ! video/x-raw,format=BGR
                ! appsink name=appsink 
                    emit-signals=true 
                    max-buffers={self.max_buffers} 
                    drop=true 
                    sync=false
            """
        elif camera_type == 'test':
            # Pipeline para fonte de teste (para desenvolvimento)
            pipeline_str = f"""
                videotestsrc pattern=ball
                ! video/x-raw,width=640,height=480,framerate={self.fps_limit}/1
                ! videoconvert
                ! video/x-raw,format=BGR
                ! appsink name=appsink 
                    emit-signals=true 
                    max-buffers={self.max_buffers} 
                    drop=true 
                    sync=false
            """
        elif source_type == 'video_file' or (rtsp_url and any(rtsp_url.endswith(ext) for ext in ['.mp4', '.avi', '.mov', '.mkv'])):
            # *** PIPELINE UNIFICADO PARA ARQUIVOS DE VÍDEO ***
            video_path = video_file_path or rtsp_url
            logger.info(f"Câmera {self.camera_id}: Usando pipeline unificado para arquivo de vídeo: {video_path}")
            
            # Verificar se arquivo existe e corrigir caminho
            import os
            
            # Lista de caminhos possíveis para o arquivo
            possible_paths = [
                video_path,  # Caminho original
                os.path.abspath(video_path),  # Caminho absoluto
                os.path.join(os.path.dirname(os.getcwd()), video_path),  # Diretório pai
                os.path.join(os.path.dirname(os.getcwd()), 'data', 'videos', video_path),  # data/videos
                os.path.join(os.path.dirname(os.getcwd()), 'data', video_path),  # data/
            ]
            
            found_path = None
            for path in possible_paths:
                if os.path.exists(path):
                    found_path = path
                    logger.info(f"Arquivo de vídeo encontrado: {found_path}")
                    break
            
            if not found_path:
                logger.error(f"Arquivo de vídeo não encontrado em nenhum dos caminhos:")
                for i, path in enumerate(possible_paths, 1):
                    logger.error(f"  {i}. {path}")
                logger.error(f"Diretório atual: {os.getcwd()}")
                
                # Listar arquivos MP4 em diretórios comuns
                search_dirs = [
                    os.getcwd(),
                    os.path.dirname(os.getcwd()),
                    os.path.join(os.path.dirname(os.getcwd()), 'data'),
                    os.path.join(os.path.dirname(os.getcwd()), 'data', 'videos')
                ]
                
                for search_dir in search_dirs:
                    try:
                        if os.path.exists(search_dir):
                            files = os.listdir(search_dir)
                            mp4_files = [f for f in files if f.endswith('.mp4')]
                            if mp4_files:
                                logger.error(f"Arquivos MP4 em {search_dir}: {mp4_files}")
                    except Exception as e:
                        logger.debug(f"Erro ao listar {search_dir}: {e}")
                
                return None
            
            video_path = found_path
            
            # Pipeline com decodificação por hardware
            pipeline_str = f"""
                filesrc location="{video_path}"
                ! decodebin
                ! nvvideoconvert
                ! videoscale method=nearest-neighbour
                ! videorate
                ! video/x-raw,format=BGR,width=640,height=480,framerate={self.fps_limit}/1
                ! appsink name=appsink 
                    emit-signals=true 
                    max-buffers={self.max_buffers} 
                    drop=true 
                    sync=false
            """
            
            # Fallback para decodificação por software
            fallback_pipeline = f"""
                filesrc location="{video_path}"
                ! decodebin
                ! videoconvert
                ! videoscale method=nearest-neighbour
                ! videorate
                ! video/x-raw,format=BGR,width=640,height=480,framerate={self.fps_limit}/1
                ! appsink name=appsink 
                    emit-signals=true 
                    max-buffers={self.max_buffers} 
                    drop=true 
                    sync=false
            """
            
            # Tentar primeiro com hardware decode, depois software
            try:
                test_pipeline = Gst.parse_launch(pipeline_str.strip())
                if test_pipeline:
                    test_pipeline.set_state(Gst.State.NULL)  # Limpar teste
                    logger.info(f"Câmera {self.camera_id}: Usando decodificação por hardware para arquivo de vídeo")
                    return pipeline_str.strip()
            except Exception as e:
                logger.warning(f"Câmera {self.camera_id}: NVDEC não disponível para arquivo, usando software decode: {e}")
                pipeline_str = fallback_pipeline
        else:
            # *** PIPELINE PARA RTSP (ORIGINAL) ***
            logger.info(f"Câmera {self.camera_id}: Usando pipeline para RTSP: {rtsp_url}")
            
            # Pipeline RTSP com decodificação por hardware quando disponível
            pipeline_str = f"""
                rtspsrc location={rtsp_url}
                    latency=200
                    drop-on-latency=true
                    retry=3
                    timeout=10
                    udp-reconnect=true
                ! rtph264depay
                ! h264parse
                ! nvh264dec ! videoconvert
                ! videoscale method=nearest-neighbour
                ! videorate
                ! video/x-raw,format=BGR,width=640,height=480,framerate={self.fps_limit}/1
                ! appsink name=appsink 
                    emit-signals=true 
                    max-buffers={self.max_buffers} 
                    drop=true 
                    sync=false
            """
            
            # Fallback para decodificação por software se NVDEC não estiver disponível
            fallback_pipeline = f"""
                rtspsrc location={rtsp_url}
                    latency=200
                    drop-on-latency=true
                    retry=3
                    timeout=10
                    udp-reconnect=true
                ! rtph264depay
                ! h264parse
                ! avdec_h264 max-threads=2
                ! videoconvert
                ! videoscale method=nearest-neighbour
                ! videorate
                ! video/x-raw,format=BGR,width=640,height=480,framerate={self.fps_limit}/1
                ! appsink name=appsink 
                    emit-signals=true 
                    max-buffers={self.max_buffers} 
                    drop=true 
                    sync=false
            """
            
            # Tentar primeiro com NVDEC, depois software decode
            try:
                test_pipeline = Gst.parse_launch(pipeline_str.strip())
                if test_pipeline:
                    logger.info(f"Câmera {self.camera_id}: Usando decodificação por hardware (NVDEC)")
                    return pipeline_str.strip()
            except Exception as e:
                logger.warning(f"Câmera {self.camera_id}: NVDEC não disponível, usando software decode: {e}")
                pipeline_str = fallback_pipeline
        
        return pipeline_str.strip()
    
    def _on_new_sample(self, appsink):
        """
        Callback para novos frames - Otimizado para máxima performance
        - Conversão direta para NumPy
        - Skip de frames para controle de FPS
        - Processamento assíncrono
        """
        if self.stop_event.is_set():
            return Gst.FlowReturn.EOS
            
        try:
            # Obter sample
            sample = appsink.emit('pull-sample')
            if not sample:
                return Gst.FlowReturn.ERROR
            
            # Skip de frames para controlar FPS
            self.frame_counter += 1
            if self.frame_counter % self.frame_skip != 0:
                return Gst.FlowReturn.OK
            
            logger.debug(f"Frame {self.frame_counter} capturado, processando...")
            
            start_time = time.time()
            
            # Obter buffer e caps
            buffer = sample.get_buffer()
            caps = sample.get_caps()
            
            if not buffer or not caps:
                return Gst.FlowReturn.ERROR
            
            # Map buffer para leitura
            success, map_info = buffer.map(Gst.MapFlags.READ)
            if not success:
                return Gst.FlowReturn.ERROR
            
            try:
                # Obter dimensões
                structure = caps.get_structure(0)
                width = structure.get_value("width")
                height = structure.get_value("height")
                
                # Converter diretamente para NumPy array (BGR)
                frame = np.ndarray(
                    shape=(height, width, 3),
                    dtype=np.uint8,
                    buffer=map_info.data
                ).copy()  # Copy para liberar o buffer
                
                # Processar frame de forma assíncrona
                self._process_frame_async(frame, start_time)
                
                # Atualizar estatísticas
                self.stats['frames_processed'] += 1
                self.stats['last_frame_time'] = time.time()
                
            finally:
                buffer.unmap(map_info)
            
            return Gst.FlowReturn.OK
            
        except Exception as e:
            logger.error(f"Erro no callback de frame da câmera {self.camera_id}: {e}")
            self.stats['errors'] += 1
            return Gst.FlowReturn.ERROR
    
    def _process_frame_async(self, frame: np.ndarray, start_time: float):
        """Processar frame de forma assíncrona - apenas captura, sem reconhecimento local"""
        def process():
            try:
                # Camera Worker não faz reconhecimento - apenas envia frame capturado
                recognitions = []
                
                # Calcular tempo de processamento (apenas captura)
                processing_time = (time.time() - start_time) * 1000
                
                # Criar dados do frame (sem reconhecimentos)
                frame_data = FrameData(
                    camera_id=self.camera_id,
                    frame_id=self.frame_counter,
                    timestamp=datetime.now(),
                    recognitions=recognitions,  # Vazio - reconhecimento será feito pelo Recognition Worker
                    frame_shape=frame.shape,
                    processing_time_ms=processing_time
                )
                
                # Adicionar frame como atributo (para envio ao Recognition Worker)
                frame_data.frame = frame
                
                # Enviar resultado para fila (non-blocking)
                try:
                    self.result_queue.put_nowait(frame_data)
                    self.stats['frames_processed'] += 1
                    logger.debug(f"Frame {self.frame_counter} colocado na fila para processamento")
                except Exception as e:
                    # Fila cheia, drop resultado (para evitar bloqueio)
                    logger.warning(f"Fila cheia, dropando frame {self.frame_counter}: {e}")
                    
            except Exception as e:
                logger.error(f"Erro ao processar frame da câmera {self.camera_id}: {e}")
                self.stats['errors'] += 1
        
        # Executar em thread separada para não bloquear o pipeline
        threading.Thread(target=process, daemon=True).start()
    
    def _on_bus_message(self, bus, message):
        """Callback para mensagens do bus GStreamer"""
        msg_type = message.type
        
        if msg_type == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            logger.error(f"Erro no pipeline da câmera {self.camera_id}: {err}")
            logger.debug(f"Debug info: {debug}")
            self.stop_event.set()
            if self.main_loop:
                self.main_loop.quit()
        elif msg_type == Gst.MessageType.WARNING:
            warn, debug = message.parse_warning()
            logger.warning(f"Warning na câmera {self.camera_id}: {warn}")
            # Se é erro de recurso, câmera pode estar offline mas pipeline continua
            if "resource" in str(warn).lower():
                logger.info("Pipeline continua rodando apesar do warning de recurso")
        elif msg_type == Gst.MessageType.EOS:
            logger.info(f"End of stream para câmera {self.camera_id}")
            self.stop_event.set()
            if self.main_loop:
                self.main_loop.quit()
        
        return True
    
    def run(self):
        """
        Executar worker principal
        - Configurar processo
        - Inicializar GStreamer
        - Executar main loop
        """
        try:
            # Configurar processo
            self._setup_signal_handlers()
            
            # Configurar logging para o processo
            logger.remove()
            logger.add(
                sys.stdout,
                format="<green>{time:HH:mm:ss}</green> | <cyan>CAM-" + self.camera_id + "</cyan> | <level>{level}</level> | {message}",
                level="INFO"
            )
            worker_logger = logger
            
            worker_logger.info("Iniciando camera worker")
            
            if not GSTREAMER_AVAILABLE:
                worker_logger.error("GStreamer não disponível")
                return
            
            # Camera Worker não faz reconhecimento - apenas captura e envia frames
            worker_logger.info("Camera Worker configurado para captura apenas (sem reconhecimento local)")
            
            # Construir pipeline
            pipeline_str = self._build_gstreamer_pipeline()
            worker_logger.info(f"Pipeline: {pipeline_str}")
            
            # Criar pipeline
            try:
                self.pipeline = Gst.parse_launch(pipeline_str)
                if not self.pipeline:
                    worker_logger.error("Falha ao criar pipeline")
                    return
            except Exception as e:
                worker_logger.error(f"Erro ao criar pipeline: {e}")
                worker_logger.error(f"Pipeline string: {pipeline_str}")
                return
            
            # Configurar appsink
            appsink = self.pipeline.get_by_name('appsink')
            if not appsink:
                worker_logger.error("Falha ao obter appsink")
                return
            
            appsink.connect('new-sample', self._on_new_sample)
            
            # Configurar bus
            bus = self.pipeline.get_bus()
            bus.add_signal_watch()
            bus.connect('message', self._on_bus_message)
            
            # Iniciar pipeline
            worker_logger.info("Iniciando pipeline...")
            ret = self.pipeline.set_state(Gst.State.PLAYING)
            if ret == Gst.StateChangeReturn.FAILURE:
                worker_logger.error("Falha ao iniciar pipeline - erro imediato")
                # Tentar obter mais informações do erro
                bus_msg = bus.timed_pop_filtered(5 * Gst.SECOND, Gst.MessageType.ERROR)
                if bus_msg:
                    err, debug = bus_msg.parse_error()
                    worker_logger.error(f"Erro detalhado: {err}")
                    worker_logger.error(f"Debug info: {debug}")
                return
            
            worker_logger.info("Pipeline iniciado, aguardando estado PLAYING...")
            
            # Aguardar estado PLAYING com timeout maior para arquivos de vídeo
            timeout_seconds = 60 if self.camera_config.get('source_type') == 'video_file' else 30
            ret = self.pipeline.get_state(timeout=timeout_seconds * Gst.SECOND)
            if ret[0] != Gst.StateChangeReturn.SUCCESS:
                worker_logger.error(f"Pipeline não conseguiu atingir estado PLAYING: {ret[0]}")
                worker_logger.error(f"Estado atual: {ret[1]}")
                worker_logger.error(f"Estado pendente: {ret[2]}")
                
                # Tentar obter mensagens de erro do bus
                bus_msg = bus.timed_pop_filtered(5 * Gst.SECOND, Gst.MessageType.ERROR)
                if bus_msg:
                    err, debug = bus_msg.parse_error()
                    worker_logger.error(f"Erro do pipeline: {err}")
                    worker_logger.error(f"Debug info: {debug}")
                return
            
            worker_logger.info("Pipeline em estado PLAYING, iniciando captura")
            
            self.is_running = True
            self.stats['start_time'] = datetime.now()
            
            # Executar main loop
            self.main_loop = GLib.MainLoop()
            
            # Executar até receber stop event
            while not self.stop_event.is_set():
                try:
                    # Run main loop por pouco tempo para verificar stop_event
                    context = self.main_loop.get_context()
                    if context.pending():
                        context.iteration(False)
                    time.sleep(0.01)  # 10ms
                except KeyboardInterrupt:
                    break
            
            worker_logger.info("Parando camera worker")
            
        except Exception as e:
            logger.error(f"Erro no camera worker: {e}")
            logger.exception("Detalhes do erro:")
        finally:
            self._cleanup()
    
    def _cleanup(self):
        """Limpeza de recursos"""
        try:
            self.is_running = False
            
            if self.pipeline:
                self.pipeline.set_state(Gst.State.NULL)
                self.pipeline = None
            
            if self.main_loop:
                self.main_loop.quit()
                self.main_loop = None
            
            logger.info(f"Camera worker {self.camera_id} finalizado")
            
        except Exception as e:
            logger.error(f"Erro na limpeza do camera worker {self.camera_id}: {e}")


def start_camera_worker(camera_id: str, camera_config: Dict[str, Any], 
                       result_queue: Queue, stop_event: Event):
    """
    Função para iniciar worker em processo separado
    """
    worker = CameraWorker(camera_id, camera_config, result_queue, stop_event)
    worker.run()