"""
Pipeline GStreamer otimizado para alta performance
RTSP → NVDEC → InsightFace+FAISS → OpenCV Overlay → NVENC → WebRTC
"""

import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstApp', '1.0')
gi.require_version('GstWebRTC', '1.0')

from gi.repository import Gst, GstApp, GObject, GLib
import numpy as np
import cv2
import threading
import time
from typing import Optional, Callable, Dict, Any
from loguru import logger
from dataclasses import dataclass

@dataclass
class PipelineConfig:
    """Configuração do pipeline"""
    rtsp_url: str
    camera_id: str
    output_width: int = 1280
    output_height: int = 720
    fps: int = 30
    use_hardware_decode: bool = True
    use_hardware_encode: bool = True
    webrtc_port: int = 8554
    # Configuração Janus
    use_janus: bool = True
    janus_video_port: int = 5004
    janus_audio_port: int = 5005
    janus_host: str = "127.0.0.1"
    # Configuração Recognition Worker
    recognition_worker_url: str = "http://127.0.0.1:17235"
    api_base_url: str = "http://127.0.0.1:17234"
    enable_recognition: bool = True
    # Configuração para video files
    source_type: str = "rtsp"  # "rtsp" or "video_file"
    video_file_path: str = ""
    video_file_loop: bool = True
    video_file_fps: int = 30

class HighPerformancePipeline:
    """Pipeline GStreamer de alta performance para reconhecimento facial"""
    
    def __init__(self, config: PipelineConfig):
        self.config = config
        self.pipeline = None
        self.bus = None
        self.appsrc = None
        self.appsink = None
        self.main_loop = None
        self.recognition_callback: Optional[Callable] = None
        self.overlay_callback: Optional[Callable] = None
        self.is_running = False
        self.frame_count = 0
        self.fps_counter = 0
        self.last_fps_time = time.time()
        
        # Buffer para frame processing
        self.frame_buffer = None
        self.processing_thread = None
        
        # Recognition integration
        self.recognition_results = []
        self.recognition_lock = threading.Lock()
        
        # HTTP client para Recognition Worker
        import aiohttp
        self.session = None
        
        # Janus integration
        self.janus_port_assigned = None
        
        # Initialize GStreamer
        Gst.init(None)
    
    async def _get_janus_port(self) -> int:
        """Obtém porta Janus dinamicamente do WebRTC server"""
        try:
            if not self.session:
                import aiohttp
                self.session = aiohttp.ClientSession()
            
            # Verificar se WebRTC server tem Janus ativo
            async with self.session.get(f"{self.config.api_base_url.replace('17234', '17236')}/health") as resp:
                if resp.status == 200:
                    health = await resp.json()
                    if health.get('janus_available'):
                        # Buscar porta específica para esta câmera
                        async with self.session.get(f"{self.config.api_base_url.replace('17234', '17236')}/janus/streams") as resp:
                            if resp.status == 200:
                                streams_data = await resp.json()
                                for stream in streams_data.get('streams', []):
                                    if stream.get('camera_id') == self.config.camera_id:
                                        logger.info(f"Porta Janus encontrada para {self.config.camera_id}: {stream['rtp_port']}")
                                        return stream['rtp_port']
            
            # Fallback para porta padrão
            return self.config.janus_video_port
            
        except Exception as e:
            logger.warning(f"Erro ao obter porta Janus: {e}")
            return self.config.janus_video_port
        
    def build_pipeline(self) -> str:
        """Construir pipeline GStreamer otimizado"""
        
        # Decode pipeline (RTSP → NVDEC)
        decode_pipeline = self._build_decode_pipeline()
        
        # Processing pipeline (Frame extraction)
        processing_pipeline = self._build_processing_pipeline()
        
        # Encode pipeline (NVENC → WebRTC)
        encode_pipeline = self._build_encode_pipeline()
        
        # Complete pipeline
        pipeline_str = f"""
        {decode_pipeline} !
        tee name=split
        
        split. ! queue ! {processing_pipeline}
        split. ! queue ! {encode_pipeline}
        """
        
        return pipeline_str.replace('\n', ' ').strip()
    
    def _build_decode_pipeline(self) -> str:
        """Pipeline de decodificação com suporte a RTSP e arquivos de vídeo"""
        
        if self.config.source_type == "video_file":
            # Pipeline para arquivos de vídeo (MP4, AVI, etc.)
            if self.config.use_hardware_decode:
                # NVIDIA hardware decoding para arquivos
                decode = f"""
                filesrc location={self.config.video_file_path} !
                decodebin !
                nvvideoconvert !
                videorate !
                video/x-raw,format=RGBA,width={self.config.output_width},height={self.config.output_height},framerate={self.config.video_file_fps}/1 !
                """
                # Adicionar loop se configurado
                if self.config.video_file_loop:
                    decode += "queue ! "
            else:
                # Software fallback para arquivos
                decode = f"""
                filesrc location={self.config.video_file_path} !
                decodebin !
                videoconvert !
                videorate !
                video/x-raw,format=RGBA,width={self.config.output_width},height={self.config.output_height},framerate={self.config.video_file_fps}/1 !
                """
                # Adicionar loop se configurado  
                if self.config.video_file_loop:
                    decode += "queue ! "
        else:
            # Pipeline RTSP original
            if self.config.use_hardware_decode:
                # NVIDIA hardware decoding
                decode = f"""
                rtspsrc location={self.config.rtsp_url} latency=0 buffer-mode=auto !
                rtph264depay !
                h264parse !
                nvh264dec !
                nvvideoconvert !
                video/x-raw,format=RGBA,width={self.config.output_width},height={self.config.output_height},framerate={self.config.fps}/1 !
                """
            else:
                # Software fallback
                decode = f"""
                rtspsrc location={self.config.rtsp_url} latency=0 !
                rtph264depay !
                h264parse !
                avdec_h264 !
                videoconvert !
                video/x-raw,format=RGBA,width={self.config.output_width},height={self.config.output_height},framerate={self.config.fps}/1 !
                """
            
        return decode.replace('\n', ' ').strip()
    
    def _build_processing_pipeline(self) -> str:
        """Pipeline para extração de frames (IA processing)"""
        
        return f"""
        videoconvert !
        video/x-raw,format=RGB !
        appsink name=appsink emit-signals=true sync=false max-buffers=1 drop=true
        """
    
    def _build_encode_pipeline(self) -> str:
        """Pipeline de encoding com hardware acceleration"""
        
        # Usar porta Janus dinâmica se disponível
        janus_port = self.janus_port_assigned or self.config.janus_video_port
        
        if self.config.use_janus:
            # Pipeline para Janus SFU
            if self.config.use_hardware_encode:
                # NVIDIA hardware encoding → Janus
                encode = f"""
                appsrc name=appsrc format=time is-live=true do-timestamp=true !
                video/x-raw,format=RGBA,width={self.config.output_width},height={self.config.output_height},framerate={self.config.fps}/1 !
                nvvideoconvert !
                nvh264enc bitrate=4000 preset=low-latency-hq gop-size=30 rc-mode=cbr zerolatency=true !
                h264parse config-interval=-1 !
                rtph264pay config-interval=-1 pt=96 !
                udpsink host={self.config.janus_host} port={janus_port}
                """
            else:
                # Software encoding → Janus
                encode = f"""
                appsrc name=appsrc format=time is-live=true do-timestamp=true !
                video/x-raw,format=RGBA,width={self.config.output_width},height={self.config.output_height},framerate={self.config.fps}/1 !
                videoconvert !
                x264enc bitrate=4000 tune=zerolatency speed-preset=ultrafast key-int-max=30 !
                h264parse config-interval=-1 !
                rtph264pay config-interval=-1 pt=96 !
                udpsink host={self.config.janus_host} port={janus_port}
                """
        else:
            # Pipeline WebRTC direto (fallback)
            if self.config.use_hardware_encode:
                encode = f"""
                appsrc name=appsrc format=time is-live=true do-timestamp=true !
                video/x-raw,format=RGBA,width={self.config.output_width},height={self.config.output_height},framerate={self.config.fps}/1 !
                nvvideoconvert !
                nvh264enc bitrate=4000 preset=low-latency-hq !
                h264parse !
                rtph264pay config-interval=1 pt=96 !
                webrtcbin name=webrtcbin
                """
            else:
                encode = f"""
                appsrc name=appsrc format=time is-live=true do-timestamp=true !
                video/x-raw,format=RGBA,width={self.config.output_width},height={self.config.output_height},framerate={self.config.fps}/1 !
                videoconvert !
                x264enc bitrate=4000 tune=zerolatency speed-preset=ultrafast !
                h264parse !
                rtph264pay config-interval=1 pt=96 !
                webrtcbin name=webrtcbin
                """
            
        return encode.replace('\n', ' ').strip()
    
    async def start(self) -> bool:
        """Iniciar pipeline"""
        try:
            # Obter porta Janus se configurado
            if self.config.use_janus:
                self.janus_port_assigned = await self._get_janus_port()
                logger.info(f"Pipeline conectará à porta Janus: {self.janus_port_assigned}")
            
            # Build and create pipeline
            pipeline_str = self.build_pipeline()
            logger.info(f"Iniciando pipeline: {pipeline_str[:100]}...")
            
            self.pipeline = Gst.parse_launch(pipeline_str)
            if not self.pipeline:
                logger.error("❌ Falha ao criar pipeline")
                return False
            
            # Get elements
            self.appsink = self.pipeline.get_by_name("appsink")
            self.appsrc = self.pipeline.get_by_name("appsrc")
            
            if not self.appsink:
                logger.error("❌ AppSink não encontrado")
                return False
                
            # Configure appsink callback
            self.appsink.connect("new-sample", self._on_new_sample)
            
            # Configure bus
            self.bus = self.pipeline.get_bus()
            self.bus.add_signal_watch()
            self.bus.connect("message", self._on_message)
            
            # Start pipeline
            ret = self.pipeline.set_state(Gst.State.PLAYING)
            if ret == Gst.StateChangeReturn.FAILURE:
                logger.error("❌ Falha ao iniciar pipeline")
                return False
            
            self.is_running = True
            
            # Start main loop in thread
            self.main_loop = GLib.MainLoop()
            self.loop_thread = threading.Thread(target=self.main_loop.run, daemon=True)
            self.loop_thread.start()
            
            # Start frame processing thread
            self.processing_thread = threading.Thread(target=self._processing_loop, daemon=True)
            self.processing_thread.start()
            
            logger.info("Pipeline iniciado com sucesso")
            return True
            
        except Exception as e:
            logger.error(f"Erro ao iniciar pipeline: {e}")
            return False
    
    def stop(self):
        """Parar pipeline"""
        self.is_running = False
        
        if self.pipeline:
            self.pipeline.set_state(Gst.State.NULL)
            
        if self.main_loop:
            self.main_loop.quit()
            
        logger.info("🛑 Pipeline parado")
    
    def _on_new_sample(self, appsink) -> Gst.FlowReturn:
        """Callback para novos frames (execução em thread separada)"""
        try:
            sample = appsink.emit("pull-sample")
            if not sample:
                return Gst.FlowReturn.ERROR
            
            # Extract frame data
            buffer = sample.get_buffer()
            caps = sample.get_caps()
            
            # Get frame info
            structure = caps.get_structure(0)
            width = structure.get_int("width")[1]
            height = structure.get_int("height")[1]
            
            # Map buffer to numpy array
            success, map_info = buffer.map(Gst.MapFlags.READ)
            if not success:
                return Gst.FlowReturn.ERROR
            
            # Convert to numpy array
            frame_data = np.frombuffer(map_info.data, dtype=np.uint8)
            frame = frame_data.reshape((height, width, 3))  # RGB format
            
            # Store frame for processing
            self.frame_buffer = frame.copy()
            self.frame_count += 1
            
            # Cleanup
            buffer.unmap(map_info)
            
            return Gst.FlowReturn.OK
            
        except Exception as e:
            logger.error(f"❌ Erro ao processar frame: {e}")
            return Gst.FlowReturn.ERROR
    
    async def _send_frame_to_recognition(self, frame: np.ndarray) -> List[Dict]:
        """Envia frame para Recognition Worker e retorna resultados"""
        if not self.config.enable_recognition:
            return []
            
        try:
            # Converter frame para bytes (JPEG)
            import cv2
            _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            frame_bytes = buffer.tobytes()
            
            # Criar sessão HTTP se não existir
            if not self.session:
                import aiohttp
                self.session = aiohttp.ClientSession()
            
            # Enviar para Recognition Worker
            data = aiohttp.FormData()
            data.add_field('image', frame_bytes, filename='frame.jpg', content_type='image/jpeg')
            data.add_field('camera_id', self.config.camera_id)
            
            async with self.session.post(
                f"{self.config.recognition_worker_url}/recognize",
                data=data,
                timeout=aiohttp.ClientTimeout(total=0.5)  # 500ms timeout
            ) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    return result.get('detections', [])
                else:
                    logger.warning(f"Recognition Worker error: {resp.status}")
                    return []
                    
        except Exception as e:
            logger.warning(f"Erro ao comunicar com Recognition Worker: {e}")
            return []
    
    def _apply_overlay(self, frame: np.ndarray, detections: List[Dict]) -> np.ndarray:
        """Aplica overlay com detecções no frame"""
        if not detections:
            return frame
            
        try:
            import cv2
            overlay_frame = frame.copy()
            
            for detection in detections:
                # Extrair informações da detecção
                bbox = detection.get('bbox', [])
                name = detection.get('name', 'Unknown')
                confidence = detection.get('confidence', 0.0)
                
                if len(bbox) >= 4:
                    x1, y1, x2, y2 = map(int, bbox[:4])
                    
                    # Desenhar retângulo
                    color = (0, 255, 0) if name != 'Unknown' else (0, 0, 255)
                    cv2.rectangle(overlay_frame, (x1, y1), (x2, y2), color, 2)
                    
                    # Desenhar nome e confiança
                    label = f"{name} ({confidence:.2f})"
                    label_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)[0]
                    
                    # Fundo do texto
                    cv2.rectangle(overlay_frame, 
                                (x1, y1 - label_size[1] - 10), 
                                (x1 + label_size[0], y1), 
                                color, -1)
                    
                    # Texto
                    cv2.putText(overlay_frame, label, 
                              (x1, y1 - 5), 
                              cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            
            return overlay_frame
            
        except Exception as e:
            logger.error(f"Erro ao aplicar overlay: {e}")
            return frame

    def _processing_loop(self):
        """Loop de processamento de IA (thread separada)"""
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        while self.is_running:
            try:
                if self.frame_buffer is not None:
                    frame = self.frame_buffer.copy()
                    
                    # 1. Reconhecimento facial via Recognition Worker
                    detections = []
                    if self.config.enable_recognition:
                        try:
                            detections = loop.run_until_complete(
                                self._send_frame_to_recognition(frame)
                            )
                        except Exception as e:
                            logger.warning(f"Erro no reconhecimento: {e}")
                    
                    # 2. Aplicar overlay com OpenCV
                    processed_frame = self._apply_overlay(frame, detections)
                    
                    # 3. Enviar frame processado para encoder
                    self._push_frame_to_encoder(processed_frame)
                    
                    # Armazenar resultados para callback
                    with self.recognition_lock:
                        self.recognition_results = detections
                    
                    # FPS counter
                    self._update_fps_counter()
                
                # Control processing rate (processar a cada 3 frames para performance)
                time.sleep(1/10)  # 10 FPS processing
                
            except Exception as e:
                logger.error(f"Erro no loop de processamento: {e}")
                time.sleep(0.1)
        
        # Cleanup
        if self.session:
            loop.run_until_complete(self.session.close())
    
    def _push_frame_to_encoder(self, frame: np.ndarray):
        """Enviar frame processado para o encoder"""
        try:
            if not self.appsrc or not self.is_running:
                return
            
            # Convert RGB to RGBA (required by appsrc)
            if frame.shape[2] == 3:
                frame_rgba = cv2.cvtColor(frame, cv2.COLOR_RGB2RGBA)
            else:
                frame_rgba = frame
            
            # Create GStreamer buffer
            buffer = Gst.Buffer.new_allocate(None, frame_rgba.nbytes, None)
            buffer.fill(0, frame_rgba.tobytes())
            
            # Set timestamp
            buffer.pts = self.frame_count * Gst.SECOND // self.config.fps
            buffer.dts = buffer.pts
            buffer.duration = Gst.SECOND // self.config.fps
            
            # Push buffer
            ret = self.appsrc.emit("push-buffer", buffer)
            if ret != Gst.FlowReturn.OK:
                logger.warning(f"⚠️ Push buffer falhou: {ret}")
                
        except Exception as e:
            logger.error(f"❌ Erro ao enviar frame para encoder: {e}")
    
    def _update_fps_counter(self):
        """Atualizar contador de FPS"""
        self.fps_counter += 1
        current_time = time.time()
        
        if current_time - self.last_fps_time >= 5.0:  # Log FPS a cada 5 segundos
            fps = self.fps_counter / (current_time - self.last_fps_time)
            logger.info(f"📊 Pipeline FPS: {fps:.1f}")
            self.fps_counter = 0
            self.last_fps_time = current_time
    
    def _on_message(self, bus, message):
        """Handle GStreamer messages"""
        msg_type = message.type
        
        if msg_type == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            logger.error(f"❌ GStreamer Error: {err} - {debug}")
            self.stop()
            
        elif msg_type == Gst.MessageType.WARNING:
            warn, debug = message.parse_warning()
            logger.warning(f"⚠️ GStreamer Warning: {warn} - {debug}")
            
        elif msg_type == Gst.MessageType.EOS:
            logger.info("🏁 End of stream")
            # Se for arquivo de vídeo e loop está habilitado, reiniciar
            if self.config.source_type == "video_file" and self.config.video_file_loop:
                logger.info("🔄 Reiniciando arquivo de vídeo...")
                try:
                    # Seek para o início do arquivo
                    self.pipeline.seek_simple(Gst.Format.TIME, Gst.SeekFlags.FLUSH, 0)
                except Exception as e:
                    logger.error(f"Erro ao reiniciar arquivo: {e}")
                    self.stop()
            else:
                self.stop()
    
    def set_recognition_callback(self, callback: Callable):
        """Definir callback para reconhecimento facial"""
        self.recognition_callback = callback
    
    def set_overlay_callback(self, callback: Callable):
        """Definir callback para overlay"""
        self.overlay_callback = callback
    
    def get_stats(self) -> Dict[str, Any]:
        """Obter estatísticas do pipeline"""
        return {
            "is_running": self.is_running,
            "frame_count": self.frame_count,
            "config": {
                "width": self.config.output_width,
                "height": self.config.output_height,
                "fps": self.config.fps,
                "hardware_decode": self.config.use_hardware_decode,
                "hardware_encode": self.config.use_hardware_encode,
                "source_type": self.config.source_type
            }
        }


def create_pipeline_config(camera_data: Dict[str, Any]) -> PipelineConfig:
    """
    Cria configuração de pipeline baseada nos dados da câmera
    Suporta tanto RTSP quanto arquivos de vídeo
    """
    camera_id = camera_data.get('id', 'unknown')
    rtsp_url = camera_data.get('rtsp_url', '')
    camera_type = camera_data.get('type', 'rtsp')
    
    # Determinar tipo de source e configurações
    if camera_type == 'video_file' or (rtsp_url and any(rtsp_url.endswith(ext) for ext in ['.mp4', '.avi', '.mov', '.mkv'])):
        # Configuração para arquivo de vídeo
        config = PipelineConfig(
            rtsp_url=rtsp_url,  # Manter para compatibilidade
            camera_id=camera_id,
            source_type="video_file",
            video_file_path=rtsp_url,  # URL é o caminho do arquivo
            video_file_loop=True,
            video_file_fps=25,  # FPS controlado para arquivos
            fps=25  # FPS de saída
        )
    else:
        # Configuração para RTSP
        config = PipelineConfig(
            rtsp_url=rtsp_url,
            camera_id=camera_id,
            source_type="rtsp",
            fps=30  # FPS padrão para RTSP
        )
    
    return config