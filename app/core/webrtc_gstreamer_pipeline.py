"""
Pipeline GStreamer com webrtcbin direto
RTSP → NVDEC → Recognition → Overlay → NVENC → webrtcbin → Frontend
"""

import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstApp', '1.0')
gi.require_version('GstWebRTC', '1.0')
gi.require_version('GstSdp', '1.0')

from gi.repository import Gst, GstApp, GstWebRTC, GstSdp, GObject, GLib
import numpy as np
import cv2
import threading
import time
import json
import asyncio
from typing import Optional, Callable, Dict, Any, List
from loguru import logger
from dataclasses import dataclass

@dataclass
class WebRTCPipelineConfig:
    """Configuração do pipeline WebRTC"""
    rtsp_url: str
    camera_id: str
    output_width: int = 1280
    output_height: int = 720
    fps: int = 30
    use_hardware_decode: bool = True
    use_hardware_encode: bool = True
    # Recognition Worker
    recognition_worker_url: str = "http://127.0.0.1:17235"
    api_base_url: str = "http://127.0.0.1:17234"
    enable_recognition: bool = True
    # WebRTC
    stun_server: str = "stun://stun.l.google.com:19302"
    turn_server: Optional[str] = None

class WebRTCGStreamerPipeline:
    """Pipeline GStreamer com webrtcbin para WebRTC direto"""
    
    def __init__(self, config: WebRTCPipelineConfig):
        self.config = config
        self.pipeline = None
        self.webrtcbin = None
        self.bus = None
        self.appsrc = None
        self.appsink = None
        self.main_loop = None
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
        self.session = None
        
        # WebRTC callbacks
        self.on_offer_created = None
        self.on_ice_candidate = None
        self.on_answer_received = None
        
        # Initialize GStreamer
        Gst.init(None)
        logger.info("GStreamer WebRTC Pipeline inicializado")
    
    def build_pipeline(self) -> str:
        """Construir pipeline GStreamer com webrtcbin"""
        
        # Source: RTSP com NVDEC
        source_pipeline = self._build_source_pipeline()
        
        # Processing: Frame extraction para IA
        processing_pipeline = self._build_processing_pipeline()
        
        # WebRTC: NVENC + webrtcbin
        webrtc_pipeline = self._build_webrtc_pipeline()
        
        # Complete pipeline
        pipeline_str = f"""
        {source_pipeline} !
        tee name=split
        
        split. ! queue max-size-buffers=2 leaky=downstream ! {processing_pipeline}
        split. ! queue max-size-buffers=10 ! {webrtc_pipeline}
        """
        
        return pipeline_str.replace('\n', ' ').strip()
    
    def _build_source_pipeline(self) -> str:
        """Pipeline de source RTSP com NVDEC"""
        
        if self.config.use_hardware_decode:
            # NVIDIA hardware decoding
            source = f"""
            rtspsrc location={self.config.rtsp_url} latency=0 buffer-mode=auto !
            rtph264depay !
            h264parse !
            nvh264dec !
            nvvideoconvert !
            video/x-raw,format=RGBA,width={self.config.output_width},height={self.config.output_height},framerate={self.config.fps}/1
            """
        else:
            # Software fallback
            source = f"""
            rtspsrc location={self.config.rtsp_url} latency=0 !
            rtph264depay !
            h264parse !
            avdec_h264 !
            videoconvert !
            video/x-raw,format=RGBA,width={self.config.output_width},height={self.config.output_height},framerate={self.config.fps}/1
            """
            
        return source.replace('\n', ' ').strip()
    
    def _build_processing_pipeline(self) -> str:
        """Pipeline para extração de frames (IA processing)"""
        
        return f"""
        videoconvert !
        video/x-raw,format=RGB !
        appsink name=appsink emit-signals=true sync=false max-buffers=1 drop=true
        """
    
    def _build_webrtc_pipeline(self) -> str:
        """Pipeline WebRTC com appsrc para overlay"""
        
        if self.config.use_hardware_encode:
            # NVIDIA hardware encoding
            webrtc = f"""
            appsrc name=appsrc format=time is-live=true do-timestamp=true !
            video/x-raw,format=RGBA,width={self.config.output_width},height={self.config.output_height},framerate={self.config.fps}/1 !
            nvvideoconvert !
            nvh264enc bitrate=4000 preset=low-latency-hq gop-size=30 rc-mode=cbr zerolatency=true !
            h264parse config-interval=-1 !
            rtph264pay config-interval=-1 pt=96 !
            webrtcbin name=webrtcbin stun-server={self.config.stun_server}
            """
        else:
            # Software encoding
            webrtc = f"""
            appsrc name=appsrc format=time is-live=true do-timestamp=true !
            video/x-raw,format=RGBA,width={self.config.output_width},height={self.config.output_height},framerate={self.config.fps}/1 !
            videoconvert !
            x264enc bitrate=4000 tune=zerolatency speed-preset=ultrafast key-int-max=30 !
            h264parse config-interval=-1 !
            rtph264pay config-interval=-1 pt=96 !
            webrtcbin name=webrtcbin stun-server={self.config.stun_server}
            """
            
        return webrtc.replace('\n', ' ').strip()
    
    async def start(self) -> bool:
        """Iniciar pipeline"""
        try:
            # Build and create pipeline
            pipeline_str = self.build_pipeline()
            logger.info(f"Iniciando WebRTC pipeline: {pipeline_str[:100]}...")
            
            self.pipeline = Gst.parse_launch(pipeline_str)
            if not self.pipeline:
                logger.error("❌ Falha ao criar pipeline")
                return False
            
            # Get elements
            self.appsink = self.pipeline.get_by_name("appsink")
            self.appsrc = self.pipeline.get_by_name("appsrc")
            self.webrtcbin = self.pipeline.get_by_name("webrtcbin")
            
            if not self.appsink or not self.appsrc or not self.webrtcbin:
                logger.error("❌ Elementos não encontrados")
                return False
            
            # Configure WebRTC callbacks
            self._setup_webrtc_callbacks()
                
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
            
            logger.info("✅ WebRTC Pipeline iniciado com sucesso")
            return True
            
        except Exception as e:
            logger.error(f"❌ Erro ao iniciar pipeline: {e}")
            return False
    
    def _setup_webrtc_callbacks(self):
        """Configurar callbacks do WebRTC"""
        
        # TURN server se configurado
        if self.config.turn_server:
            self.webrtcbin.set_property("turn-server", self.config.turn_server)
        
        # Callbacks de sinalização
        self.webrtcbin.connect("on-negotiation-needed", self._on_negotiation_needed)
        self.webrtcbin.connect("on-ice-candidate", self._on_ice_candidate)
        self.webrtcbin.connect("pad-added", self._on_pad_added)
        
        logger.info("✅ WebRTC callbacks configurados")
    
    def _on_negotiation_needed(self, webrtcbin):
        """Callback quando negociação é necessária (criar offer)"""
        logger.info("🤝 Negociação WebRTC necessária, criando offer...")
        
        promise = Gst.Promise.new_with_change_callback(self._on_offer_created_callback, webrtcbin, None)
        webrtcbin.emit("create-offer", None, promise)
    
    def _on_offer_created_callback(self, promise, webrtcbin, user_data):
        """Callback quando offer é criado"""
        try:
            reply = promise.get_reply()
            offer = reply.get_value("offer")
            
            # Set local description
            promise2 = Gst.Promise.new()
            webrtcbin.emit("set-local-description", offer, promise2)
            
            # Send offer to external handler
            if self.on_offer_created:
                sdp = offer.sdp.as_text()
                logger.info(f"📤 Offer criado: {sdp[:100]}...")
                self.on_offer_created(sdp)
                
        except Exception as e:
            logger.error(f"❌ Erro ao criar offer: {e}")
    
    def _on_ice_candidate(self, webrtcbin, mline_index, candidate):
        """Callback para ICE candidates"""
        logger.debug(f"🧊 ICE candidate: {mline_index} {candidate}")
        
        if self.on_ice_candidate:
            self.on_ice_candidate(mline_index, candidate)
    
    def _on_pad_added(self, webrtcbin, pad):
        """Callback quando novo pad é adicionado"""
        logger.info(f"📎 Novo pad adicionado: {pad.get_name()}")
    
    def set_remote_description(self, sdp_text: str, sdp_type: str = "answer"):
        """Definir descrição remota (answer do cliente)"""
        try:
            logger.info(f"📥 Recebendo {sdp_type}: {sdp_text[:100]}...")
            
            sdp = GstSdp.SDPMessage()
            GstSdp.sdp_message_parse_buffer(sdp_text.encode(), sdp)
            
            if sdp_type == "answer":
                answer = GstWebRTC.WebRTCSessionDescription.new(GstWebRTC.WebRTCSDPType.ANSWER, sdp)
                promise = Gst.Promise.new()
                self.webrtcbin.emit("set-remote-description", answer, promise)
                logger.info("✅ Remote description (answer) definida")
            else:
                logger.warning(f"⚠️ Tipo SDP não suportado: {sdp_type}")
                
        except Exception as e:
            logger.error(f"❌ Erro ao definir remote description: {e}")
    
    def add_ice_candidate(self, mline_index: int, candidate: str):
        """Adicionar ICE candidate"""
        try:
            logger.debug(f"➕ Adicionando ICE candidate: {mline_index} {candidate}")
            self.webrtcbin.emit("add-ice-candidate", mline_index, candidate)
        except Exception as e:
            logger.error(f"❌ Erro ao adicionar ICE candidate: {e}")
    
    def stop(self):
        """Parar pipeline"""
        self.is_running = False
        
        if self.pipeline:
            self.pipeline.set_state(Gst.State.NULL)
            
        if self.main_loop:
            self.main_loop.quit()
            
        if self.session:
            # Close session in event loop
            try:
                loop = asyncio.get_event_loop()
                loop.create_task(self.session.close())
            except:
                pass
            
        logger.info("🛑 WebRTC Pipeline parado")
    
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
                    
                    # 3. Enviar frame processado para webrtcbin
                    self._push_frame_to_webrtc(processed_frame)
                    
                    # Armazenar resultados para callback
                    with self.recognition_lock:
                        self.recognition_results = detections
                    
                    # FPS counter
                    self._update_fps_counter()
                
                # Control processing rate (10 FPS processing)
                time.sleep(1/10)
                
            except Exception as e:
                logger.error(f"Erro no loop de processamento: {e}")
                time.sleep(0.1)
        
        # Cleanup
        if self.session:
            loop.run_until_complete(self.session.close())
    
    def _push_frame_to_webrtc(self, frame: np.ndarray):
        """Enviar frame processado para webrtcbin"""
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
            logger.error(f"❌ Erro ao enviar frame para WebRTC: {e}")
    
    def _update_fps_counter(self):
        """Atualizar contador de FPS"""
        self.fps_counter += 1
        current_time = time.time()
        
        if current_time - self.last_fps_time >= 5.0:  # Log FPS a cada 5 segundos
            fps = self.fps_counter / (current_time - self.last_fps_time)
            logger.info(f"📊 WebRTC Pipeline FPS: {fps:.1f}")
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
            self.stop()
    
    def get_stats(self) -> Dict[str, Any]:
        """Obter estatísticas do pipeline"""
        return {
            "is_running": self.is_running,
            "frame_count": self.frame_count,
            "webrtc_state": "connected" if self.webrtcbin else "disconnected",
            "config": {
                "width": self.config.output_width,
                "height": self.config.output_height,
                "fps": self.config.fps,
                "hardware_decode": self.config.use_hardware_decode,
                "hardware_encode": self.config.use_hardware_encode,
                "recognition_enabled": self.config.enable_recognition
            }
        }