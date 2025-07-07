"""
NVENC Encoder for Camera Worker
Integra encoding NVENC ao pipeline existente do Camera Worker
"""

import threading
import time
import queue
import numpy as np
from typing import Optional, Callable, Dict, Any
from loguru import logger
import asyncio

# Importação compatível do GStreamer (MSYS2 + Conda)
try:
    # Tentar módulo centralizado primeiro (Conda)
    from app.core.gstreamer_init import initialize_gstreamer, safe_import_gstreamer
    
    initialize_gstreamer()
    Gst, GstApp, GLib, GSTREAMER_AVAILABLE, gstreamer_error = safe_import_gstreamer()
    
    if not GSTREAMER_AVAILABLE:
        raise ImportError(f"GStreamer módulo centralizado falhou: {gstreamer_error}")
        
except ImportError:
    # Fallback para módulo simplificado (MSYS2)
    try:
        from app.camera_worker.simple_gstreamer_init import (
            initialize_gstreamer, safe_import_gstreamer,
            Gst, GstApp, GLib, GSTREAMER_AVAILABLE, gstreamer_error
        )
        logger.info("NVENC: GStreamer importado via módulo simplificado (MSYS2)")
        
        if not GSTREAMER_AVAILABLE:
            raise ImportError(f"GStreamer não disponível: {gstreamer_error}")
            
    except ImportError as e:
        logger.error(f"NVENC Encoder: GStreamer não disponível (ambos módulos): {e}")
        GSTREAMER_AVAILABLE = False
        Gst = None
        GstApp = None
        GLib = None


class NVENCEncoder:
    """Encoder NVENC integrado ao Camera Worker"""
    
    def __init__(self, camera_id: str, width: int = 1920, height: int = 1080, fps: int = 30):
        self.camera_id = camera_id
        self.width = width
        self.height = height
        self.fps = fps
        
        # Pipeline components
        self.pipeline = None
        self.appsrc = None
        self.appsink = None
        
        # Threading
        self.is_running = False
        self.encoder_thread = None
        self.main_loop = None
        
        # Buffers
        self.input_queue = queue.Queue(maxsize=10)
        self.output_queue = queue.Queue(maxsize=10)
        
        # Statistics
        self.stats = {
            'frames_input': 0,
            'frames_encoded': 0,
            'frames_output': 0,
            'encoding_errors': 0,
            'queue_drops': 0,
            'last_encode_time': 0
        }
        
        # Callbacks
        self.encoded_frame_callback = None
        
        self.gstreamer_available = GSTREAMER_AVAILABLE
        
    def initialize(self) -> bool:
        """Inicializar encoder NVENC"""
        if not self.gstreamer_available:
            logger.error(f"NVENC Encoder {self.camera_id}: GStreamer não disponível")
            return False
            
        try:
            logger.info(f"🚀 Inicializando NVENC Encoder para câmera {self.camera_id}")
            
            # Pipeline NVENC otimizado
            pipeline_str = f"""
            appsrc name=frame_source format=3 
                caps=video/x-raw,format=NV12,width={self.width},height={self.height},framerate={self.fps}/1
                stream-type=0 is-live=true do-timestamp=true min-latency=0 max-latency=0
                ! queue leaky=2 max-size-buffers=5 max-size-bytes=0 max-size-time=0
                ! nvh264enc preset=low-latency-hq bitrate=2000 gop-size={self.fps} 
                    rc-mode=cbr-ld-hq qp-min=18 qp-max=32 aud=false
                ! video/x-h264,profile=baseline,level=3.1,stream-format=byte-stream
                ! h264parse config-interval=-1
                ! queue leaky=2 max-size-buffers=5 max-size-bytes=0 max-size-time=0
                ! appsink name=encoded_sink emit-signals=true max-buffers=5 drop=true sync=false
            """
            
            # Criar pipeline
            self.pipeline = Gst.parse_launch(pipeline_str.strip())
            if not self.pipeline:
                raise RuntimeError("Falha ao criar pipeline NVENC")
            
            # Obter elementos
            self.appsrc = self.pipeline.get_by_name("frame_source")
            self.appsink = self.pipeline.get_by_name("encoded_sink")
            
            if not self.appsrc or not self.appsink:
                raise RuntimeError("Falha ao obter elementos do pipeline")
            
            # Configurar callbacks
            self.appsink.connect("new-sample", self._on_encoded_sample)
            
            # Configurar bus
            bus = self.pipeline.get_bus()
            bus.add_signal_watch()
            bus.connect("message", self._on_bus_message)
            
            logger.info(f"✅ NVENC Encoder inicializado para câmera {self.camera_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Erro ao inicializar NVENC Encoder {self.camera_id}: {e}")
            return False
    
    def start(self) -> bool:
        """Iniciar encoder"""
        if not self.gstreamer_available:
            return False
            
        try:
            # Iniciar pipeline
            ret = self.pipeline.set_state(Gst.State.PLAYING)
            if ret == Gst.StateChangeReturn.FAILURE:
                raise RuntimeError("Falha ao iniciar pipeline NVENC")
            
            # Iniciar thread de processamento
            self.is_running = True
            self.encoder_thread = threading.Thread(target=self._encoder_thread_func, daemon=True)
            self.encoder_thread.start()
            
            logger.info(f"✅ NVENC Encoder iniciado para câmera {self.camera_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Erro ao iniciar NVENC Encoder {self.camera_id}: {e}")
            return False
    
    def _encoder_thread_func(self):
        """Thread de processamento do encoder"""
        try:
            # Criar main loop
            self.main_loop = GLib.MainLoop()
            
            # Executar main loop
            self.main_loop.run()
            
        except Exception as e:
            logger.error(f"❌ Erro na thread do encoder {self.camera_id}: {e}")
        finally:
            self.is_running = False
    
    def encode_frame(self, frame: np.ndarray) -> bool:
        """Enviar frame para encoding (thread-safe)"""
        if not self.is_running or not self.gstreamer_available:
            return False
            
        try:
            # Verificar se a queue está cheia
            if self.input_queue.full():
                # Remover frame mais antigo
                try:
                    self.input_queue.get_nowait()
                    self.stats['queue_drops'] += 1
                except queue.Empty:
                    pass
            
            # Adicionar novo frame
            self.input_queue.put_nowait(frame.copy())
            self.stats['frames_input'] += 1
            
            # Processar frames da queue
            self._process_input_queue()
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Erro ao enviar frame para encoding {self.camera_id}: {e}")
            return False
    
    def _process_input_queue(self):
        """Processar frames da queue de entrada"""
        try:
            while not self.input_queue.empty() and self.is_running:
                try:
                    frame = self.input_queue.get_nowait()
                    self._push_frame_to_pipeline(frame)
                except queue.Empty:
                    break
                    
        except Exception as e:
            logger.error(f"❌ Erro ao processar queue de entrada {self.camera_id}: {e}")
    
    def _push_frame_to_pipeline(self, frame: np.ndarray):
        """Enviar frame para o pipeline GStreamer"""
        try:
            # Verificar formato do frame
            if len(frame.shape) == 3 and frame.shape[2] == 3:
                # Frame BGR, converter para NV12
                import cv2
                frame_nv12 = cv2.cvtColor(frame, cv2.COLOR_BGR2YUV_I420)
                frame_data = frame_nv12.tobytes()
            elif len(frame.shape) == 2:
                # Frame já em formato YUV
                frame_data = frame.tobytes()
            else:
                logger.error(f"❌ Formato de frame não suportado: {frame.shape}")
                return
            
            # Criar buffer GStreamer
            buffer = Gst.Buffer.new_allocate(None, len(frame_data), None)
            buffer.fill(0, frame_data)
            
            # Definir timestamp
            buffer.pts = self.stats['frames_input'] * Gst.SECOND // self.fps
            buffer.dts = buffer.pts
            buffer.duration = Gst.SECOND // self.fps
            
            # Enviar para appsrc
            ret = self.appsrc.emit('push-buffer', buffer)
            
            if ret == Gst.FlowReturn.OK:
                self.stats['frames_encoded'] += 1
                self.stats['last_encode_time'] = time.time()
            else:
                self.stats['encoding_errors'] += 1
                logger.warning(f"⚠️ NVENC push-buffer falhou para {self.camera_id}: {ret}")
                
        except Exception as e:
            logger.error(f"❌ Erro ao enviar frame para pipeline {self.camera_id}: {e}")
            self.stats['encoding_errors'] += 1
    
    def _on_encoded_sample(self, appsink):
        """Callback para frames codificados"""
        try:
            sample = appsink.emit('pull-sample')
            if not sample:
                return Gst.FlowReturn.ERROR
            
            buffer = sample.get_buffer()
            if not buffer:
                return Gst.FlowReturn.ERROR
            
            # Mapear buffer
            success, map_info = buffer.map(Gst.MapFlags.READ)
            if not success:
                return Gst.FlowReturn.ERROR
            
            # Obter dados codificados
            encoded_data = bytes(map_info.data)
            
            # Liberar buffer
            buffer.unmap(map_info)
            
            # Atualizar estatísticas
            self.stats['frames_output'] += 1
            
            # Armazenar na queue de saída
            if not self.output_queue.full():
                self.output_queue.put_nowait({
                    'data': encoded_data,
                    'timestamp': time.time(),
                    'size': len(encoded_data)
                })
            
            # Chamar callback se definido
            if self.encoded_frame_callback:
                try:
                    # Executar callback em thread separada para não bloquear
                    threading.Thread(
                        target=self.encoded_frame_callback,
                        args=(self.camera_id, encoded_data),
                        daemon=True
                    ).start()
                except Exception as e:
                    logger.error(f"❌ Erro no callback de frame codificado: {e}")
            
            return Gst.FlowReturn.OK
            
        except Exception as e:
            logger.error(f"❌ Erro no processamento de frame codificado {self.camera_id}: {e}")
            return Gst.FlowReturn.ERROR
    
    def _on_bus_message(self, bus, message):
        """Processar mensagens do bus"""
        t = message.type
        
        if t == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            logger.error(f"❌ NVENC Encoder {self.camera_id}: {err}")
            self.stats['encoding_errors'] += 1
            
        elif t == Gst.MessageType.WARNING:
            warn, debug = message.parse_warning()
            logger.warning(f"⚠️ NVENC Encoder {self.camera_id}: {warn}")
            
        elif t == Gst.MessageType.EOS:
            logger.info(f"📺 NVENC Encoder {self.camera_id}: End of stream")
            
        return True
    
    def get_encoded_frame(self) -> Optional[Dict[str, Any]]:
        """Obter frame codificado da queue de saída"""
        try:
            if not self.output_queue.empty():
                return self.output_queue.get_nowait()
            return None
        except queue.Empty:
            return None
    
    def set_encoded_frame_callback(self, callback: Callable[[str, bytes], None]):
        """Definir callback para frames codificados"""
        self.encoded_frame_callback = callback
    
    def get_stats(self) -> Dict[str, Any]:
        """Obter estatísticas do encoder"""
        return {
            'camera_id': self.camera_id,
            'is_running': self.is_running,
            'gstreamer_available': self.gstreamer_available,
            'input_queue_size': self.input_queue.qsize(),
            'output_queue_size': self.output_queue.qsize(),
            **self.stats
        }
    
    def stop(self):
        """Parar encoder"""
        try:
            self.is_running = False
            
            # Parar pipeline
            if self.pipeline:
                self.pipeline.set_state(Gst.State.NULL)
            
            # Parar main loop
            if self.main_loop and self.main_loop.is_running():
                self.main_loop.quit()
            
            # Aguardar thread terminar
            if self.encoder_thread and self.encoder_thread.is_alive():
                self.encoder_thread.join(timeout=5)
            
            logger.info(f"✅ NVENC Encoder parado para câmera {self.camera_id}")
            
        except Exception as e:
            logger.error(f"❌ Erro ao parar NVENC Encoder {self.camera_id}: {e}")


class NVENCEncoderManager:
    """Gerenciador de encoders NVENC para múltiplas câmeras"""
    
    def __init__(self):
        self.encoders: Dict[str, NVENCEncoder] = {}
        self.manager_lock = threading.Lock()
        
    def create_encoder(self, camera_id: str, width: int = 1920, height: int = 1080, fps: int = 30) -> bool:
        """Criar encoder para câmera"""
        with self.manager_lock:
            if camera_id in self.encoders:
                logger.warning(f"Encoder já existe para câmera {camera_id}")
                return True
            
            try:
                encoder = NVENCEncoder(camera_id, width, height, fps)
                
                if encoder.initialize() and encoder.start():
                    self.encoders[camera_id] = encoder
                    logger.info(f"✅ NVENC Encoder criado para câmera {camera_id}")
                    return True
                else:
                    logger.error(f"❌ Falha ao criar encoder para câmera {camera_id}")
                    return False
                    
            except Exception as e:
                logger.error(f"❌ Erro ao criar encoder para câmera {camera_id}: {e}")
                return False
    
    def get_encoder(self, camera_id: str) -> Optional[NVENCEncoder]:
        """Obter encoder de uma câmera"""
        with self.manager_lock:
            return self.encoders.get(camera_id)
    
    def encode_frame(self, camera_id: str, frame: np.ndarray) -> bool:
        """Enviar frame para encoding"""
        encoder = self.get_encoder(camera_id)
        if encoder:
            return encoder.encode_frame(frame)
        return False
    
    def set_callback(self, camera_id: str, callback: Callable[[str, bytes], None]) -> bool:
        """Definir callback para frames codificados"""
        encoder = self.get_encoder(camera_id)
        if encoder:
            encoder.set_encoded_frame_callback(callback)
            return True
        return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Obter estatísticas de todos os encoders"""
        with self.manager_lock:
            stats = {}
            for camera_id, encoder in self.encoders.items():
                stats[camera_id] = encoder.get_stats()
            return stats
    
    def stop_encoder(self, camera_id: str):
        """Parar encoder de uma câmera"""
        with self.manager_lock:
            if camera_id in self.encoders:
                encoder = self.encoders[camera_id]
                encoder.stop()
                del self.encoders[camera_id]
                logger.info(f"✅ NVENC Encoder removido para câmera {camera_id}")
    
    def stop_all(self):
        """Parar todos os encoders"""
        with self.manager_lock:
            for camera_id in list(self.encoders.keys()):
                self.stop_encoder(camera_id)
            logger.info("✅ Todos os NVENC Encoders parados")


# Instância global do gerenciador
nvenc_manager = NVENCEncoderManager()