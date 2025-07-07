"""
WebRTC Server com aiortc + GStreamer CUDA/NVDEC
Para streaming de baixa latência com reconhecimento facial em tempo real
"""

import asyncio
import json
import time
import uuid
import weakref
import sys
import os
from typing import Dict, Optional, Any, List
from datetime import datetime
from multiprocessing import Queue, Process, Event
import threading
import aiohttp
import ssl
from concurrent.futures import ThreadPoolExecutor
import socket

import numpy as np
from aiohttp import web, WSMsgType
from aiohttp.web_ws import WebSocketResponse
from loguru import logger
import socketio

# APLICAR PATCH GLOBAL DE PORTAS UDP ANTES DE IMPORTAR AIORTC
def apply_global_udp_port_patch():
    """Aplicar patch global ANTES de qualquer import do aiortc usando subclassing"""
    import os
    import socket
    
    udp_range = os.environ.get('AIORTC_UDP_PORT_RANGE', '40000-40100')
    min_port, max_port = map(int, udp_range.split('-'))
    
    if not hasattr(socket, '_global_udp_patch_applied'):
        socket._global_udp_patch_applied = True
        OriginalSocket = socket.socket
        
        class PortControlledSocket(OriginalSocket):
            """Socket wrapper que controla portas UDP"""
            
            def __init__(self, family=socket.AF_INET, type=socket.SOCK_STREAM, proto=0, fileno=None):
                super().__init__(family, type, proto, fileno)
                self._is_udp = (family == socket.AF_INET and type == socket.SOCK_DGRAM)
            
            def bind(self, address):
                if self._is_udp:
                    host, port = address
                    
                    if port == 0:
                        # Porta automática - escolher do range
                        for try_port in range(min_port, max_port + 1):
                            try:
                                super().bind((host, try_port))
                                print(f"🎯 UDP AUTO-BIND: {host}:{try_port}")
                                return
                            except OSError:
                                continue
                        # Fallback se range esgotado
                        print(f"⚠️ Range {udp_range} esgotado, usando porta automática")
                        super().bind(address)
                    elif not (min_port <= port <= max_port):
                        # Porta fora do range - forçar para range
                        forced_port = min_port
                        print(f"🚫 UDP FORA DO RANGE: {host}:{port} → FORÇADO para {host}:{forced_port}")
                        super().bind((host, forced_port))
                    else:
                        # Porta no range - permitir
                        print(f"✅ UDP NO RANGE: {host}:{port}")
                        super().bind(address)
                else:
                    # Não é UDP - bind normal
                    super().bind(address)
        
        # Substituir globalmente
        socket.socket = PortControlledSocket
        print(f"[UDP-PATCH] GLOBAL UDP PATCH (SUBCLASS) APLICADO: {udp_range}")

# Aplicar patch IMEDIATAMENTE
apply_global_udp_port_patch()

# PATCH CRÍTICO: Interceptar asyncio.create_datagram_endpoint
def apply_asyncio_patch():
    """Patch direto no asyncio.create_datagram_endpoint que é usado pelo aioice"""
    import asyncio
    import os
    
    udp_range = os.environ.get('AIORTC_UDP_PORT_RANGE', '40000-40100')
    min_port, max_port = map(int, udp_range.split('-'))
    
    if not hasattr(asyncio, '_original_create_datagram_endpoint'):
        # Salvar função original
        asyncio._original_create_datagram_endpoint = asyncio.get_event_loop().create_datagram_endpoint
        
        async def patched_create_datagram_endpoint(protocol_factory, local_addr=None, remote_addr=None, **kwargs):
            # Se tem local_addr com porta 0, forçar para nosso range
            if local_addr and len(local_addr) == 2 and local_addr[1] == 0:
                host = local_addr[0]
                
                # Tentar portas do nosso range
                for try_port in range(min_port, max_port + 1):
                    try:
                        result = await asyncio._original_create_datagram_endpoint(
                            protocol_factory, 
                            local_addr=(host, try_port), 
                            remote_addr=remote_addr, 
                            **kwargs
                        )
                        print(f"🎯 ASYNCIO INTERCEPTADO: UDP {host}:{try_port}")
                        return result
                    except OSError:
                        continue
                
                # Se falhou, usar original
                print(f"⚠️ Range {udp_range} esgotado, usando porta automática")
            
            return await asyncio._original_create_datagram_endpoint(
                protocol_factory, local_addr=local_addr, remote_addr=remote_addr, **kwargs
            )
        
        # Aplicar patch em todas as instâncias de loop
        loop = asyncio.get_event_loop()
        loop.create_datagram_endpoint = patched_create_datagram_endpoint
        
        # Patch também no módulo para novos loops
        original_new_event_loop = asyncio.new_event_loop
        def patched_new_event_loop():
            loop = original_new_event_loop()
            loop.create_datagram_endpoint = patched_create_datagram_endpoint
            return loop
        asyncio.new_event_loop = patched_new_event_loop
        
        print(f"[ASYNCIO-PATCH] DATAGRAM ENDPOINT PATCHED: {udp_range}")

apply_asyncio_patch()

# Enable detailed RTP/SRTP logging for debugging
import logging
logging.basicConfig(level=logging.DEBUG)
aiortc_logger = logging.getLogger('aiortc')
aiortc_logger.setLevel(logging.DEBUG)
# Habilitar logs específicos para DTLS
dtls_logger = logging.getLogger('aiortc.dtls')
dtls_logger.setLevel(logging.DEBUG)
# Habilitar logs específicos para RTP
rtp_logger = logging.getLogger('aiortc.rtp')
rtp_logger.setLevel(logging.DEBUG)

# aiortc imports
from aiortc import RTCPeerConnection, RTCSessionDescription, MediaStreamTrack, RTCIceCandidate, RTCConfiguration, RTCIceServer
from aiortc.contrib.media import MediaRelay
import av
from aiortc.rtcrtpsender import RTCRtpSender

# GStreamer imports (opcional)
GSTREAMER_AVAILABLE = False
Gst = None
GstApp = None
GLib = None

if not os.environ.get('DISABLE_GSTREAMER', '').lower() == 'true':
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
        logger.warning(f"GStreamer não disponível (fallback aiortc ativo): {e}")
        GSTREAMER_AVAILABLE = False
        # Ensure GStreamer objects are None if import fails
        Gst = None
        GstApp = None
        GLib = None
else:
    logger.info("GStreamer DESABILITADO por configuração (DISABLE_GSTREAMER=true)")


# Base VideoTrack classes
class FallbackVideoTrack(MediaStreamTrack):
    """Fallback video track for when GStreamer is not available"""
    kind = "video"
    
    def __init__(self, camera_config: Dict[str, Any], recognition_queue: Queue):
        super().__init__()
        self.camera_config = camera_config
        self.recognition_queue = recognition_queue
        self.is_running = True
        self.frame_count = 0
        self.use_gstreamer = False
        logger.info(f"Using fallback video track for {camera_config.get('id', 'unknown')}")
        
    def stop(self):
        """Stop the track"""
        self.is_running = False
        logger.info("Fallback video track stopped")
        
    async def recv(self):
        """Generate test frames"""
        if not self.is_running:
            raise Exception("Track is stopped")
            
        # Generate a simple test frame (solid color)
        import time
        pts, time_base = await self.next_timestamp()
        
        # Create a simple colored frame using PyAV
        frame = av.VideoFrame.from_ndarray(
            np.full((480, 640, 3), [0, 100, 200], dtype=np.uint8), format='rgb24'
        )
        frame.pts = pts
        frame.time_base = time_base
        
        self.frame_count += 1
        
        # Small delay to simulate camera frame rate
        await asyncio.sleep(1/15)  # ~15 FPS
        
        return frame

if GSTREAMER_AVAILABLE:
    class GStreamerVideoTrack(MediaStreamTrack):
        """
        Track de vídeo usando GStreamer com CUDA/NVDEC para decodificação
        """
        kind = "video"

        def __init__(self, camera_config: Dict[str, Any], recognition_queue: Queue):
        super().__init__()
        self.camera_config = camera_config
        self.recognition_queue = recognition_queue
        self.pipeline = None
        self.appsink = None
        self.is_running = False
        self.frame_count = 0
        self.recognition_frame_skip = 15  # Enviar 1 a cada 15 frames para reconhecimento
        
        # Configurações de performance profissional
        self.target_fps = camera_config.get('fps_limit', 25)  # 25 FPS para melhor qualidade
        self.width = 1280  # Resolução HD para melhor qualidade
        self.height = 720
        self.use_cuda = False
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 5
        self.pipeline_health_check_interval = 30  # segundos
        
        # Inicializar frame atual
        self._current_frame = None
        self._frame_received = False
        
        # Determinar se usar GStreamer ou frames de teste
        camera_type = camera_config.get('type', 'test')
        
        if camera_type == 'test' or not GSTREAMER_AVAILABLE:
            self.use_gstreamer = False
            self.is_running = True  # Marcar como rodando para frames de teste
            logger.info(f"Usando frames de teste para {camera_config.get('id', 'unknown')}")
        else:
            self.use_gstreamer = True
            # Inicializar pipeline GStreamer para RTSP
            self._setup_gstreamer_pipeline()
            logger.info(f"Pipeline GStreamer configurado para {camera_type}: {camera_config.get('url', 'N/A')}")
        
    def _setup_gstreamer_pipeline(self):
        """Configurar pipeline GStreamer otimizado com CUDA"""
        if not GSTREAMER_AVAILABLE:
            logger.error("GStreamer não disponível")
            return
            
        camera_url = self.camera_config.get('url', '')
        camera_type = self.camera_config.get('type', 'rtsp')
        use_test_fallback = self.camera_config.get('use_test_source_fallback', False)
        
        # Força usar test source se solicitado, para debug, ou se não há câmera real
        if camera_type == 'test' or camera_url == 'test://source' or use_test_fallback:
            # Pipeline de teste com videotestsrc
            pipeline_str = f"""
                videotestsrc pattern=0 is-live=true
                ! video/x-raw,width={self.width},height={self.height},framerate={self.target_fps}/1,format=RGB
                ! appsink name=sink 
                    emit-signals=true 
                    max-buffers=2 
                    drop=true 
                    sync=false
            """
        elif camera_type == 'webcam':
            # Pipeline para webcam
            device = camera_url if camera_url.startswith('/dev/') else f'/dev/video{camera_url}'
            pipeline_str = f"""
                v4l2src device={device}
                ! video/x-raw,width={self.width},height={self.height},framerate={self.target_fps}/1
                ! videoconvert
                ! video/x-raw,format=RGB
                ! appsink name=sink 
                    emit-signals=true 
                    max-buffers=2 
                    drop=true 
                    sync=false
            """
        else:
            # Pipeline RTSP PROFISSIONAL com baixa latência e alta estabilidade
            pipeline_str = f"""
                rtspsrc location="{camera_url}"
                    latency=50
                    buffer-mode=0
                    drop-on-latency=true
                    retry=5
                    timeout=10
                    udp-reconnect=true
                    tcp-timeout=20000000
                    do-retransmission=true
                ! rtph264depay
                ! h264parse
                    config-interval=-1
                ! nvh264dec
                    max-display-delay=0
                ! nvvideoconvert
                ! video/x-raw,format=RGB,width={self.width},height={self.height}
                ! videorate
                    max-rate={self.target_fps}
                    drop-only=true
                ! video/x-raw,framerate={self.target_fps}/1
                ! appsink name=sink 
                    emit-signals=true 
                    max-buffers=1
                    drop=true 
                    sync=false
                    async=false
            """
            
            # Fallback CPU com otimizações de latência
            fallback_pipeline = f"""
                rtspsrc location="{camera_url}"
                    latency=50
                    buffer-mode=0
                    drop-on-latency=true
                    retry=5
                    timeout=10
                    udp-reconnect=true
                    tcp-timeout=20000000
                ! rtph264depay
                ! h264parse
                    config-interval=-1
                ! avdec_h264
                    max-threads=2
                    output-corrupt=false
                ! videoconvert
                    n-threads=2
                ! video/x-raw,format=RGB,width={self.width},height={self.height}
                ! videorate
                    max-rate={self.target_fps}
                    drop-only=true
                ! video/x-raw,framerate={self.target_fps}/1
                ! appsink name=sink 
                    emit-signals=true 
                    max-buffers=1
                    drop=true 
                    sync=false
                    async=false
            """
        
        # Tentar pipeline otimizado com detecção inteligente de CUDA
        cuda_available = self._check_cuda_availability()
        
        if cuda_available and camera_type == 'rtsp':
            try:
                self.pipeline = Gst.parse_launch(pipeline_str.strip())
                self.use_cuda = True
                logger.info(f"✨ Pipeline CUDA/NVDEC criado para {self.camera_config.get('id', 'unknown')}")
                logger.info(f"🚀 Aceleração GPU ativa - latência ultra-baixa")
            except Exception as e:
                logger.warning(f"⚠️ CUDA pipeline falhou, usando CPU fallback: {e}")
                try:
                    self.pipeline = Gst.parse_launch(fallback_pipeline.strip())
                    self.use_cuda = False
                    logger.info(f"🔄 Pipeline CPU fallback criado para {self.camera_config.get('id', 'unknown')}")
                except Exception as e2:
                    logger.error(f"❌ Falha crítica ao criar pipeline: {e2}")
                    self._create_error_pipeline()
                    return
        else:
            try:
                if camera_type == 'rtsp':
                    self.pipeline = Gst.parse_launch(fallback_pipeline.strip())
                else:
                    self.pipeline = Gst.parse_launch(pipeline_str.strip())
                self.use_cuda = False
                logger.info(f"📺 Pipeline {camera_type} criado para {self.camera_config.get('id', 'unknown')}")
            except Exception as e:
                logger.error(f"❌ Falha ao criar pipeline {camera_type}: {e}")
                self._create_error_pipeline()
                return
        
        # Configurar appsink
        self.appsink = self.pipeline.get_by_name('sink')
        if not self.appsink:
            logger.error("Falha ao obter appsink")
            return
            
        # Conectar callback
        self.appsink.connect('new-sample', self._on_new_sample)
        
        # Configurar bus para monitorar erros
        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect('message', self._on_bus_message)
        
        logger.info(f"🎬 Pipeline GStreamer configurado: {camera_type} | CUDA: {getattr(self, 'use_cuda', False)}")
        
        # Configurar pipeline para baixa latência se solicitado
        if camera_config.get('low_latency', True):
            self._configure_low_latency_pipeline()
        
        # Configurar timeouts e health checks
        self._setup_health_monitoring()
    
    def _on_bus_message(self, bus, message):
        """Callback para mensagens do bus GStreamer"""
        msg_type = message.type
        camera_info = f"{self.camera_config.get('type', 'unknown')}:{self.camera_config.get('id', 'unknown')}"
        
        if msg_type == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            logger.error(f"❌ Erro no pipeline GStreamer [{camera_info}]: {err}")
            logger.debug(f"Debug info: {debug}")
            
            # Sistema inteligente de fallback para erros
            if self.camera_config.get('type') == 'rtsp':
                logger.warning(f"⚠️ RTSP falhou para {camera_info}, ativando sistema de reconexão")
                
                # Tentar reconexão automática
                if self.reconnect_attempts < self.max_reconnect_attempts:
                    logger.info(f"🔄 Agendando reconexão automática em 5 segundos...")
                    import threading
                    threading.Timer(5.0, self._attempt_pipeline_reconnect).start()
                else:
                    logger.error(f"❌ Máximo de tentativas atingido, alternando para fallback")
                    self._switch_to_fallback_mode()
            else:
                self.stop()
        elif msg_type == Gst.MessageType.WARNING:
            warn, debug = message.parse_warning()
            logger.warning(f"⚠️ Warning no pipeline [{camera_info}]: {warn}")
        elif msg_type == Gst.MessageType.EOS:
            logger.info(f"📺 End of stream no pipeline [{camera_info}]")
            self.stop()
        elif msg_type == Gst.MessageType.STATE_CHANGED:
            old_state, new_state, pending_state = message.parse_state_changed()
            if message.src == self.pipeline:
                logger.info(f"🔄 Pipeline [{camera_info}] state: {old_state.value_name} → {new_state.value_name}")
        
        return True
    
    def _configure_low_latency_pipeline(self):
        """Configurar pipeline para latência ultra-baixa"""
        try:
            if not self.pipeline:
                return
            
            # Configurar elementos para baixa latência
            elements_to_configure = [
                ('nvh264dec', {'max-display-delay': 0, 'low-latency': True}),
                ('avdec_h264', {'max-threads': 1, 'skip-frame': 0}),
                ('x264enc', {'tune': 'zerolatency', 'speed-preset': 'ultrafast', 'bitrate': 2000}),
                ('nvh264enc', {'preset': 'low-latency-hq', 'rc-mode': 'cbr', 'bitrate': 2000}),
                ('videorate', {'max-rate': self.target_fps, 'drop-only': True}),
                ('queue', {'max-size-buffers': 1, 'max-size-time': 0, 'max-size-bytes': 0, 'leaky': 'downstream'}),
            ]
            
            # Iterar através dos elementos do pipeline
            iterator = self.pipeline.iterate_elements()
            while True:
                result, element = iterator.next()
                if result != Gst.IteratorResult.OK:
                    break
                
                element_name = element.get_factory().get_name()
                
                # Configurar elemento se estiver na lista
                for target_name, properties in elements_to_configure:
                    if target_name in element_name:
                        for prop_name, prop_value in properties.items():
                            try:
                                if element.get_property(prop_name) is not None:
                                    element.set_property(prop_name, prop_value)
                                    logger.debug(f"🚀 {element_name}.{prop_name} = {prop_value}")
                            except Exception as e:
                                logger.debug(f"⚠️ Não foi possível configurar {element_name}.{prop_name}: {e}")
            
            logger.info("🚀 Pipeline configurado para LATÊNCIA ULTRA-BAIXA")
            
        except Exception as e:
            logger.warning(f"⚠️ Erro ao configurar baixa latência: {e}")
    
    def _check_cuda_availability(self):
        """Verificar se CUDA/NVDEC está disponível"""
        try:
            # Verificar se os plugins NVIDIA estão disponíveis
            nvh264dec = Gst.ElementFactory.find('nvh264dec')
            nvvideoconvert = Gst.ElementFactory.find('nvvideoconvert')
            
            if nvh264dec and nvvideoconvert:
                logger.info("✨ CUDA/NVDEC plugins disponíveis")
                return True
            else:
                logger.info("💻 CUDA/NVDEC não disponível, usando CPU")
                return False
        except Exception as e:
            logger.warning(f"⚠️ Erro ao verificar CUDA: {e}")
            return False
    
    def _create_error_pipeline(self):
        """Criar pipeline de erro como fallback final"""
        try:
            error_pipeline = f"""
                videotestsrc pattern=2 is-live=true
                ! video/x-raw,width={self.width},height={self.height},framerate={self.target_fps}/1,format=RGB
                ! textoverlay text="ERRO: Câmera {self.camera_config.get('id', 'ERR')} indisponível"
                    valignment=center halignment=center font-desc="Sans 24"
                ! appsink name=sink 
                    emit-signals=true 
                    max-buffers=1
                    drop=true 
                    sync=false
            """
            self.pipeline = Gst.parse_launch(error_pipeline.strip())
            self.use_cuda = False
            logger.warning(f"⚠️ Pipeline de erro criado para {self.camera_config.get('id')}")
        except Exception as e:
            logger.error(f"❌ Falha crítica ao criar pipeline de erro: {e}")
    
    def _setup_health_monitoring(self):
        """Configurar monitoramento de saúde do pipeline"""
        self.last_frame_time = time.time()
        self.frames_received = 0
        self.connection_stable = False
        
        # Agendar verificação periódica de saúde
        import threading
        def health_check():
            while self.is_running:
                time.sleep(self.pipeline_health_check_interval)
                self._check_pipeline_health()
        
        health_thread = threading.Thread(target=health_check, daemon=True)
        health_thread.start()
        logger.info("👨‍⚕️ Monitoramento de saúde do pipeline ativado")
    
    def _check_pipeline_health(self):
        """Verificar saúde do pipeline e reconectar se necessário"""
        try:
            current_time = time.time()
            time_since_last_frame = current_time - self.last_frame_time
            
            # Se não recebeu frames por mais de 15 segundos
            if time_since_last_frame > 15 and self.use_gstreamer:
                logger.warning(f"⚠️ Pipeline sem frames por {time_since_last_frame:.1f}s")
                
                if self.reconnect_attempts < self.max_reconnect_attempts:
                    self._attempt_reconnect()
                else:
                    logger.error("❌ Máximo de tentativas de reconexão atingido")
                    self._switch_to_fallback_mode()
            
            # Log periódico de estatísticas
            if time_since_last_frame < 5:
                fps = self.frames_received / max(1, current_time - (self.last_frame_time - time_since_last_frame))
                logger.info(f"📊 Pipeline saudável: {fps:.1f} FPS | {self.frames_received} frames")
                self.connection_stable = True
            else:
                self.connection_stable = False
                
        except Exception as e:
            logger.error(f"❌ Erro no health check: {e}")
    
    def _attempt_reconnect(self):
        """Tentar reconectar o pipeline RTSP"""
        self.reconnect_attempts += 1
        logger.info(f"🔄 Tentativa de reconexão {self.reconnect_attempts}/{self.max_reconnect_attempts}")
        
        try:
            # Parar pipeline atual
            if self.pipeline:
                self.pipeline.set_state(Gst.State.NULL)
                time.sleep(1)
            
            # Recriar pipeline
            self._setup_gstreamer_pipeline()
            
            # Reiniciar
            if self.pipeline:
                ret = self.pipeline.set_state(Gst.State.PLAYING)
                if ret == Gst.StateChangeReturn.SUCCESS:
                    logger.info("✅ Reconexão bem-sucedida")
                    self.reconnect_attempts = 0
                    self.last_frame_time = time.time()
                else:
                    logger.error("❌ Falha na reconexão")
        except Exception as e:
            logger.error(f"❌ Erro durante reconexão: {e}")
    
    def _attempt_pipeline_reconnect(self):
        """Tentar reconexão do pipeline (método thread-safe)"""
        try:
            self.reconnect_attempts += 1
            camera_info = f"{self.camera_config.get('type')}:{self.camera_config.get('id', 'unknown')}"
            logger.info(f"🔄 Reconexão automática {self.reconnect_attempts}/{self.max_reconnect_attempts} para {camera_info}")
            
            # Parar pipeline atual completamente
            if self.pipeline:
                self.pipeline.set_state(Gst.State.NULL)
                time.sleep(2)  # Aguardar limpeza completa
            
            # Resetar variáveis de estado
            self._current_frame = None
            self._frame_received = False
            
            # Recriar pipeline do zero
            self._setup_gstreamer_pipeline()
            
            # Tentar iniciar novamente
            if self.pipeline:
                ret = self.pipeline.set_state(Gst.State.PLAYING)
                if ret == Gst.StateChangeReturn.SUCCESS:
                    logger.info(f"✅ Reconexão automática bem-sucedida para {camera_info}")
                    self.reconnect_attempts = 0
                    self.last_frame_time = time.time()
                    self.connection_stable = True
                    return True
                else:
                    logger.error(f"❌ Falha na reconexão automática para {camera_info}")
            
            # Se ainda temos tentativas, agendar próxima
            if self.reconnect_attempts < self.max_reconnect_attempts:
                retry_delay = min(10 * self.reconnect_attempts, 60)  # Backoff exponencial limitado
                logger.info(f"🔄 Próxima tentativa em {retry_delay} segundos...")
                import threading
                threading.Timer(retry_delay, self._attempt_pipeline_reconnect).start()
            else:
                logger.error(f"❌ Esgotadas tentativas de reconexão para {camera_info}")
                self._switch_to_fallback_mode()
                
        except Exception as e:
            logger.error(f"❌ Erro crítico na reconexão automática: {e}")
            self._switch_to_fallback_mode()
    
    def _switch_to_fallback_mode(self):
        """Alternar para modo de fallback (frames de teste)"""
        logger.warning("⚠️ Alternando para modo fallback - frames de teste")
        self.use_gstreamer = False
        self.is_running = True
        
        # Parar pipeline GStreamer
        if self.pipeline:
            self.pipeline.set_state(Gst.State.NULL)
            self.pipeline = None
    
    def _on_new_sample(self, appsink):
        """Callback para novos frames do GStreamer"""
        try:
            sample = appsink.emit('pull-sample')
            if not sample:
                return Gst.FlowReturn.ERROR
            
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
                
                # Converter para numpy array
                frame = np.ndarray(
                    shape=(height, width, 3),
                    dtype=np.uint8,
                    buffer=map_info.data
                ).copy()
                
                # Adicionar frame na fila interna para WebRTC
                self._add_frame_to_queue(frame)
                
                # Enviar frame para reconhecimento (com skip)
                self.frame_count += 1
                if self.frame_count % self.recognition_frame_skip == 0:
                    self._send_frame_for_recognition(frame)
                
            finally:
                buffer.unmap(map_info)
            
            return Gst.FlowReturn.OK
            
        except Exception as e:
            logger.error(f"Erro no callback de frame: {e}")
            return Gst.FlowReturn.ERROR
    
    def _add_frame_to_queue(self, frame):
        """Adicionar frame na fila interna para WebRTC"""
        # Implementação específica para envio WebRTC
        # Frame será enviado via recv() method
        self._current_frame = frame.copy()
        if not self._frame_received:
            self._frame_received = True
            logger.info(f"Primeiro frame recebido para câmera {self.camera_config.get('id')} - {frame.shape}")
    
    def _send_frame_for_recognition(self, frame):
        """Enviar frame para processamento de reconhecimento facial"""
        try:
            if not self.recognition_queue.full():
                # Adicionar metadata do frame
                frame_data = {
                    'camera_id': self.camera_config.get('id'),
                    'timestamp': time.time(),
                    'frame': frame,
                    'frame_id': self.frame_count
                }
                self.recognition_queue.put_nowait(frame_data)
        except Exception as e:
            logger.debug(f"Não foi possível enviar frame para reconhecimento: {e}")
    
    async def start(self):
        """Iniciar track de vídeo"""
        if not self.use_gstreamer:
            # Para tracks de teste, apenas marcar como rodando
            self.is_running = True
            logger.info(f"Test video track iniciado para câmera {self.camera_config.get('id', 'test')}")
            return True
            
        if not self.pipeline:
            logger.error("Pipeline não configurado")
            return False
            
        ret = self.pipeline.set_state(Gst.State.PLAYING)
        if ret == Gst.StateChangeReturn.FAILURE:
            logger.error("Falha ao iniciar pipeline")
            return False
        
        # Aguardar estado PLAYING
        ret = self.pipeline.get_state(timeout=10 * Gst.SECOND)
        if ret[0] != Gst.StateChangeReturn.SUCCESS:
            logger.error(f"Pipeline não conseguiu atingir estado PLAYING: {ret[0]}")
            return False
        
        self.is_running = True
        logger.info(f"Pipeline iniciado para câmera {self.camera_config.get('id')}")
        return True
    
    def stop(self):
        """Parar pipeline GStreamer"""
        self.is_running = False
        if self.pipeline:
            self.pipeline.set_state(Gst.State.NULL)
        logger.info(f"Pipeline parado para câmera {self.camera_config.get('id')}")
    
    async def recv(self):
        """Método requerido pelo aiortc para enviar frames via WebRTC"""
        if not self.is_running:
            raise StopIteration()
            
        pts, time_base = await self.next_timestamp()
        
        try:
            if self.use_gstreamer and self._current_frame is not None:
                # Usar frame do GStreamer (RTSP) se disponível
                frame_rgb = self._current_frame.copy()
                if self.frame_count % 150 == 0:  # Log ocasional
                    logger.info(f"📹 [RTSP] Frame GStreamer #{self.frame_count} - {frame_rgb.shape}")
            else:
                # Usar frame de teste (indicação visual de que é teste)
                frame_rgb = self._generate_test_frame()
                if self.frame_count % 150 == 0:  # Log ocasional
                    camera_type = self.camera_config.get('type', 'unknown')
                    logger.info(f"📹 [TEST] Frame teste #{self.frame_count} para camera {camera_type}")
            
            # Garantir dimensões corretas
            if frame_rgb.shape[0] != self.height or frame_rgb.shape[1] != self.width:
                import cv2
                frame_rgb = cv2.resize(frame_rgb, (self.width, self.height))
            
            # Converter para formato av com YUV420p
            av_frame = av.VideoFrame.from_ndarray(frame_rgb, format="rgb24")
            av_frame = av_frame.reformat(format="yuv420p")
            av_frame.pts = pts
            av_frame.time_base = time_base
            
            # Keyframe a cada 30 frames
            if self.frame_count % 30 == 0:
                av_frame.key_frame = True
                if self.frame_count % 90 == 0:  # Log keyframes ocasionalmente
                    source_type = "RTSP" if (self.use_gstreamer and self._current_frame is not None) else "TEST"
                    logger.info(f"🔑 [RTP] Keyframe {source_type} #{self.frame_count}")
            
            self.frame_count += 1
            return av_frame
            
        except Exception as e:
            logger.error(f"❌ Erro ao gerar frame: {e}")
            # Fallback para frame de erro visível
            error_frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
            error_frame[:, :] = [255, 0, 0]  # Vermelho para indicar erro
            av_frame = av.VideoFrame.from_ndarray(error_frame, format="rgb24")
            av_frame.pts = pts
            av_frame.time_base = time_base
            return av_frame
    
    def _generate_test_frame(self):
        """Gerar frame de teste que indica claramente que é um stream de teste"""
        frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        
        # Identificação visual de que é TESTE vs RTSP
        camera_type = self.camera_config.get('type', 'test')
        camera_id = self.camera_config.get('id', 'unknown')
        
        if camera_type == 'test':
            # Fundo azul para teste
            frame[:, :] = [0, 100, 200]
            
            # Faixa horizontal animada
            t = self.frame_count * 0.2
            y_pos = int(self.height/2 + 50 * np.sin(t))
            if 0 <= y_pos < self.height:
                frame[max(0, y_pos-10):min(self.height, y_pos+10), :] = [255, 255, 0]
            
            # Texto "TEST CAMERA" 
            center_y, center_x = self.height // 2, self.width // 2
            frame[center_y-30:center_y+30, center_x-100:center_x+100] = [255, 255, 255]
            
        else:
            # Para casos onde deveria ser RTSP mas não está funcionando
            frame[:, :] = [200, 100, 0]  # Laranja
            
            # Indicador de "aguardando RTSP"
            center_y, center_x = self.height // 2, self.width // 2
            frame[center_y-20:center_y+20, center_x-80:center_x+80] = [255, 255, 255]
        
        # Contador visual no canto (pisca a cada segundo)
        color = [0, 255, 0] if (self.frame_count // 30) % 2 else [255, 0, 0]
        frame[10:40, 10:60] = color
        
        # Frame counter textual
        frame[self.height-40:self.height-10, 10:150] = [0, 0, 0]  # Fundo preto
        
        # ID da câmera no topo
        if len(camera_id) > 8:  # Se for UUID
            display_id = camera_id[:8] + "..."
        else:
            display_id = camera_id
        frame[10:30, self.width-120:self.width-10] = [255, 255, 255]  # Fundo branco para ID
        
        return frame


async def monitor_rtp_stats(pc: RTCPeerConnection, session_id: str):
    """Monitorar estatísticas RTP do servidor"""
    try:
        for _ in range(20):  # Monitorar por 20 ciclos (60 segundos)
            await asyncio.sleep(3)
            
            if pc.connectionState != "connected":
                logger.warning(f"📡 [RTP] {session_id}: Conexão não está mais ativa, parando monitoramento")
                break
                
            try:
                stats = await pc.getStats()
                rtp_sent = 0
                bytes_sent = 0
                
                for stat in stats:
                    if hasattr(stat, 'type') and stat.type == 'outbound-rtp' and hasattr(stat, 'kind') and stat.kind == 'video':
                        rtp_sent = getattr(stat, 'packetsSent', 0)
                        bytes_sent = getattr(stat, 'bytesSent', 0)
                        break
                
                logger.info(f"📡 [RTP] {session_id}: Pacotes enviados: {rtp_sent}, Bytes: {bytes_sent}")
                
                if rtp_sent == 0:
                    logger.error(f"💥 [RTP] {session_id}: PROBLEMA - Nenhum pacote RTP enviado!")
                    
            except Exception as e:
                logger.error(f"❌ [RTP] {session_id}: Erro ao obter stats: {e}")
                
        except Exception as e:
            logger.error(f"❌ [RTP] Monitor error para {session_id}: {e}")

else:
    # If GStreamer is not available, define a dummy GStreamerVideoTrack 
    # that's actually the FallbackVideoTrack to maintain compatibility
    GStreamerVideoTrack = FallbackVideoTrack

# Type alias for video tracks
VideoTrackType = GStreamerVideoTrack if GSTREAMER_AVAILABLE else FallbackVideoTrack


class WebRTCConnectionManager:
    """Gerenciador de conexões WebRTC"""
    
    def __init__(self, recognition_queue: Queue):
        self.recognition_queue = recognition_queue
        self.connections: Dict[str, RTCPeerConnection] = {}
        self.video_tracks: Dict[str, GStreamerVideoTrack] = {}
        self.relay = MediaRelay()
        self._port_patch_applied = False
        
        # Aplicar patch IMEDIATAMENTE na inicialização
        self._apply_immediate_port_patch()
        
    async def create_peer_connection(self, session_id: str, camera_config: Dict[str, Any]) -> RTCPeerConnection:
        """Criar nova conexão WebRTC"""
        from aiortc import RTCConfiguration, RTCIceServer
        
        # Configuração melhorada para WebRTC local
        import os
        from aiortc import RTCIceServer
        
        # Configuração para forçar candidatos IPv4 locais
        ice_servers = [
            RTCIceServer(urls="stun:stun.l.google.com:19302")  # Restaurar STUN para gerar candidatos
        ]
        
        # Configurar forçadamente o IP público para evitar problemas com Docker
        public_ip = os.environ.get('WEBRTC_PUBLIC_IP') or os.environ.get('AIORTC_FORCE_HOST_IP')
        if public_ip:
            logger.info(f"🌍 Forçando IP público nos candidatos ICE: {public_ip}")
            os.environ['AIORTC_FORCE_HOST_IP'] = public_ip
        
        # Adicionar TURN server se configurado (para NAT traversal)
        turn_server = os.environ.get('TURN_SERVER_URL')
        turn_username = os.environ.get('TURN_USERNAME')
        turn_password = os.environ.get('TURN_PASSWORD')
        
        if turn_server and turn_username and turn_password:
            ice_servers.append(RTCIceServer(
                urls=turn_server,
                username=turn_username,
                credential=turn_password
            ))
            logger.info(f"🔄 TURN server configurado: {turn_server}")
        
        # Configurar política de transporte ICE baseada no ambiente
        if os.environ.get('WEBRTC_HOST_NETWORK', 'false').lower() == 'true':
            # Se estamos em Docker com host network, usar relay para garantir que apenas candidatos públicos são usados
            logger.info(f"🐳 Configuração WebRTC otimizada para Docker network_mode: host")
            # Preferir candidatos srflx em vez de host para evitar IPs Docker internos
            logger.info(f"🔧 Configuração otimizada para evitar IPs Docker internos")
            
        # Configuração compatível com aiortc (sem parâmetros não suportados)
        config = RTCConfiguration(iceServers=ice_servers)
        
        logger.info(f"🌐 WebRTC configurado para produção: {len(ice_servers)} ICE servers")
        
        # Log da versão do aiortc para debugging
        try:
            import aiortc
            logger.info(f"📦 aiortc version: {aiortc.__version__}")
        except:
            logger.warning("⚠️ Não foi possível obter versão do aiortc")
        
        # Verificar se está em host network mode
        host_network = os.getenv('WEBRTC_HOST_NETWORK', 'false').lower() == 'true'
        if host_network:
            logger.info(f"WebRTC em modo host network - candidatos ICE usarão localhost")

        # Configuração CRÍTICA para forçar IPv4 e portas UDP fixas
        fixed_udp_range = os.environ.get('AIORTC_UDP_PORT_RANGE', '40000-40100')
        os.environ['AIORTC_UDP_PORT_RANGE'] = fixed_udp_range
        logger.info(f"🔌 Portas UDP FORÇADAS para: {fixed_udp_range}")
        
        # FORÇAR IPv4 E PORTAS UDP FIXAS DIRETAMENTE NO SOCKET
        import socket
        
        # Monkey patch para forçar apenas IPv4
        original_getaddrinfo = socket.getaddrinfo
        def ipv4_only_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
            return original_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
        socket.getaddrinfo = ipv4_only_getaddrinfo
        
        # PATCH CRÍTICO: Forçar aiortc a usar apenas portas específicas
        self._apply_system_level_port_patch()
        
        # Configurar aiortc para IPv4
        bind_ip = '172.21.15.83'  # IP WSL2 específico
        os.environ['AIORTC_HOST'] = bind_ip
        os.environ['AIORTC_FORCE_HOST_IP'] = bind_ip
        
        logger.info(f"🚫 IPv6 desabilitado via monkey patch")
        logger.info(f"🔧 Forçando aiortc bind IP: {bind_ip}")
        logger.info(f"🎯 IP público forçado: {bind_ip}")

        # Importar RTCPeerConnection com suporte para certificados
        from aiortc import RTCPeerConnection
        import OpenSSL

        # Gerar certificados manualmente para DTLS
        key = OpenSSL.crypto.PKey()
        key.generate_key(OpenSSL.crypto.TYPE_RSA, 2048)

        cert = OpenSSL.crypto.X509()
        cert.get_subject().CN = "presence-webrtc-server"
        cert.gmtime_adj_notBefore(0)
        cert.gmtime_adj_notAfter(365 * 24 * 60 * 60)  # 1 ano de validade
        cert.set_pubkey(key)
        cert.set_serial_number(1000)
        cert.set_issuer(cert.get_subject())
        cert.sign(key, 'sha256')
        
        # Configuração melhorada para compatibilidade DTLS
        cert.add_extensions([
            OpenSSL.crypto.X509Extension(
                b'subjectAltName',
                False,
                b'DNS:localhost, IP:127.0.0.1, IP:0.0.0.0'
            ),
            OpenSSL.crypto.X509Extension(
                b'extendedKeyUsage', 
                False, 
                b'serverAuth,clientAuth'
            ),
            OpenSSL.crypto.X509Extension(
                b'keyUsage',
                True,
                b'keyEncipherment,dataEncipherment,digitalSignature'
            )
        ])

        # Converter para o formato esperado pelo aiortc
        try:
            from aiortc import RTCCertificate
            
            # Extrair chave privada e certificado
            key_pem = OpenSSL.crypto.dump_privatekey(OpenSSL.crypto.FILETYPE_PEM, key)
            cert_pem = OpenSSL.crypto.dump_certificate(OpenSSL.crypto.FILETYPE_PEM, cert)
            
            # Para aiortc 1.6.0+, usar RTCCertificate.generateCertificate() ou criar sem parâmetros
            rtc_certificate = RTCCertificate.generateCertificate()
            logger.info("🔐 Certificado DTLS gerado automaticamente para WebRTC")
            
            # Criar RTCPeerConnection com certificado
            pc = RTCPeerConnection(configuration=config)
            # Não é mais necessário passar o certificado manualmente
            
        except Exception as e:
            logger.warning(f"⚠️ Erro ao criar certificado personalizado: {e}, usando padrão do aiortc")
            # Fallback: criar RTCPeerConnection sem certificado customizado
            pc = RTCPeerConnection(configuration=config)
        logger.info(f"🔐 PeerConnection criado para {session_id}")
            
        logger.info(f"🔐 WebRTC inicializado com certificado DTLS para {session_id}")
        
        # Monitoramento PROFISSIONAL de candidatos ICE com filtro IPv4
        ice_candidates = []
        
        # Configurar ICE candidate filtering para IPv4 apenas
        def ice_candidate_filter(candidate):
            """Filtrar apenas candidatos IPv4"""
            if hasattr(candidate, 'address') and candidate.address:
                # Bloquear IPv6 (contém ':' múltiplos)
                if '::' in candidate.address or candidate.address.count(':') > 1:
                    logger.warning(f"🚫 BLOQUEANDO candidate IPv6: {candidate.address}")
                    return False
                # Aceitar apenas IPv4
                logger.info(f"✅ ACEITANDO candidate IPv4: {candidate.address}:{candidate.port}")
                return True
            return False
        
        @pc.on("icecandidate")
        def on_icecandidate(candidate):
            if candidate:
                # Aplicar filtro IPv4 PRIMEIRO
                if '::' in candidate.candidate or candidate.candidate.count(':') > 2:
                    logger.warning(f"🚫 REJEITANDO candidate IPv6: {candidate.candidate[:50]}...")
                    return
                
                ice_candidates.append(candidate.candidate)
                candidate_type = self._analyze_ice_candidate(candidate.candidate)
                logger.info(f"✅ [{session_id}] ICE IPv4 {candidate_type}: {candidate.candidate[:50]}...")
                
                # Filtrar candidatos Docker internos
                if self._is_docker_internal_candidate(candidate.candidate):
                    logger.warning(f"🚫 [{session_id}] Candidato Docker interno filtrado: {candidate.candidate}")
                    # Não adicionar candidatos Docker internos à lista
                    return
            else:
                # Análise final dos candidatos
                stats = self._analyze_ice_candidates(ice_candidates)
                logger.info(f"🏁 [{session_id}] ICE gathering completo: {stats}")
        
        # Configurar range de portas UDP FIXO para produção
        udp_port_range = os.environ.get('AIORTC_UDP_PORT_RANGE', '40000-40100')
        webrtc_port_range = os.environ.get('WEBRTC_UDP_PORT_RANGE', '40000-40100')
        
        # Forçar range consistente
        os.environ['AIORTC_UDP_PORT_RANGE'] = udp_port_range
        os.environ['WEBRTC_UDP_PORT_RANGE'] = webrtc_port_range
        
        # Ativar modo strict para garantir que apenas essas portas sejam usadas
        if os.environ.get('AIORTC_STRICT_PORT_RANGE', 'false').lower() == 'true':
            logger.info(f"🔒 Modo STRICT ativado - apenas portas {udp_port_range} serão usadas")
        
        logger.info(f"🔌 Range de portas UDP FIXO configurado: {udp_port_range}")
        
        # Configurar IP público se definido
        public_ip = os.environ.get('WEBRTC_PUBLIC_IP')
        if public_ip:
            os.environ['AIORTC_FORCE_HOST_IP'] = public_ip
            logger.info(f"🌍 IP público configurado: {public_ip}")
        
        # Salvar referência da conexão
        self.connections[session_id] = pc
        
        # Configurar handlers PROFISSIONAIS com monitoramento avançado
        @pc.on("connectionstatechange")
        async def on_connectionstatechange():
            state = pc.connectionState
            logger.info(f"🔗 Connection state para {session_id}: {state}")
            
            if state == "connected":
                # Log detalhado da conexão estabelecida (compatível com versões antigas)
                try:
                    # Tentar usar métodos novos do aiortc
                    senders = pc.getSenders()
                    receivers = pc.getReceivers()
                    logger.info(f"   ✅ CONECTADO! Senders: {len(senders)} | Receivers: {len(receivers)}")
                    
                    # Log das capacidades negociadas
                    for i, sender in enumerate(senders):
                        if sender and hasattr(sender, 'track') and sender.track:
                            track_info = f"{sender.track.kind} (ID: {getattr(sender.track, 'id', 'unknown')[:8]})"
                            logger.info(f"      📡 [RTP] Sender {i}: {track_info}")
                            
                except AttributeError:
                    # Fallback para versões antigas do aiortc
                    try:
                        transceivers = pc.getTransceivers()
                        senders = [t.sender for t in transceivers if t.sender]
                        receivers = [t.receiver for t in transceivers if t.receiver]
                        logger.info(f"   ✅ CONECTADO! Senders: {len(senders)} | Receivers: {len(receivers)} (legacy)")
                    except:
                        logger.info(f"   ✅ CONECTADO! (versão simplificada - não foi possível obter detalhes)")
                
                # Iniciar monitoramento de qualidade
                asyncio.create_task(self._monitor_connection_quality(pc, session_id))
                        
            elif state == "connecting":
                logger.info(f"   🔄 Estabelecendo conexão WebRTC...")
                
            elif state == "failed":
                logger.error(f"   ❌ FALHA na conexão para {session_id}")
                await self._handle_connection_failure(session_id)
                
            elif state == "disconnected":
                logger.warning(f"   ⚠️ Conexão desconectada para {session_id}")
                
            elif state == "closed":
                logger.info(f"   🚪 Conexão fechada para {session_id}")
                await self.cleanup_connection(session_id)
        
        @pc.on("iceconnectionstatechange")
        async def on_iceconnectionstatechange():
            state = pc.iceConnectionState
            logger.info(f"🧊 ICE connection state para {session_id}: {state}")
            if state == "failed":
                logger.error(f"❌ ICE connection failed para {session_id}")
            elif state == "connected":
                logger.info(f"✅ ICE connection established para {session_id}")
            elif state == "disconnected":
                logger.warning(f"⚠️ ICE connection disconnected para {session_id}")
        
        @pc.on("icegatheringstatechange")
        async def on_icegatheringstatechange():
            state = pc.iceGatheringState
            logger.info(f"🔍 ICE gathering state para {session_id}: {state}")
        
        @pc.on("icecandidate")
        async def on_icecandidate(candidate):
            if candidate:
                logger.info(f"🎯 ICE candidate para {session_id}: {candidate.candidate}")
            else:
                logger.info(f"✅ ICE gathering complete para {session_id}")
        
        @pc.on("track")
        async def on_track(track):
            logger.info(f"📹 Track received for {session_id}: {track.kind}")
        
        @pc.on("datachannel")
        async def on_datachannel(channel):
            logger.info(f"📡 Data channel opened for {session_id}: {channel.label}")
        
        logger.info(f"🚀 Conexão WebRTC PROFISSIONAL criada: {session_id}")
        return pc
    
    def _apply_system_level_port_patch(self):
        """Aplicar patch AGRESSIVO no sistema para forçar uso de portas específicas"""
        if self._port_patch_applied:
            return
        
        import os
        import socket
        import threading
        from threading import Lock
        
        # Obter range de portas configurado
        udp_range = os.environ.get('AIORTC_UDP_PORT_RANGE', '40000-40100')
        min_port, max_port = map(int, udp_range.split('-'))
        
        logger.info(f"🔧 Aplicando patch AGRESSIVO de portas UDP: {udp_range}")
        
        # Pool de portas disponíveis com thread-safety
        available_ports = list(range(min_port, max_port + 1))
        port_lock = Lock()
        used_ports = set()
        
        def get_next_port():
            """Obter próxima porta disponível do pool"""
            with port_lock:
                for port in available_ports:
                    if port not in used_ports:
                        used_ports.add(port)
                        return port
                # Se todas estão em uso, reciclar
                used_ports.clear()
                used_ports.add(min_port)
                return min_port
        
        def release_port(port):
            """Liberar porta de volta ao pool"""
            with port_lock:
                used_ports.discard(port)
        
        try:
            # PATCH NÍVEL 1: Interceptar socket.socket
            original_socket = socket.socket
            
            def aggressive_socket_patch(family=socket.AF_INET, type=socket.SOCK_DGRAM, proto=0, fileno=None):
                sock = original_socket(family, type, proto, fileno)
                
                if type == socket.SOCK_DGRAM and family == socket.AF_INET:
                    original_bind = sock.bind
                    original_close = sock.close
                    bound_port = None
                    
                    def forced_bind(address):
                        nonlocal bound_port
                        host, port = address
                        
                        # SEMPRE forçar porta do nosso range
                        if port == 0 or not (min_port <= port <= max_port):
                            forced_port = get_next_port()
                            try:
                                result = original_bind((host, forced_port))
                                bound_port = forced_port
                                logger.info(f"🎯 FORÇADO: Socket UDP {host}:{forced_port}")
                                return result
                            except OSError as e:
                                logger.warning(f"⚠️ Falha ao bind {forced_port}: {e}")
                                # Tentar próxima porta
                                for try_port in range(min_port, max_port + 1):
                                    try:
                                        result = original_bind((host, try_port))
                                        bound_port = try_port
                                        logger.info(f"🎯 RETRY: Socket UDP {host}:{try_port}")
                                        return result
                                    except OSError:
                                        continue
                                raise OSError(f"Nenhuma porta UDP disponível no range {udp_range}")
                        else:
                            bound_port = port
                            return original_bind(address)
                    
                    def tracked_close():
                        if bound_port:
                            release_port(bound_port)
                        return original_close()
                    
                    sock.bind = forced_bind
                    sock.close = tracked_close
                
                return sock
            
            socket.socket = aggressive_socket_patch
            logger.info("✅ Patch AGRESSIVO de socket aplicado")
            
            # PATCH NÍVEL 2: Interceptar imports do aiortc
            import sys
            from types import ModuleType
            
            class PortControlledModule(ModuleType):
                """Módulo wrapper que intercepta criação de transports"""
                def __init__(self, original_module):
                    self._original = original_module
                    self.__dict__.update(original_module.__dict__)
                
                def __getattr__(self, name):
                    attr = getattr(self._original, name)
                    
                    # Interceptar classes que criam sockets UDP
                    if name in ['RTCIceTransport', 'RTCDtlsTransport']:
                        logger.info(f"🔍 Interceptando {name}")
                        
                        class WrappedTransport(attr):
                            def __init__(self, *args, **kwargs):
                                # Forçar configurações específicas antes de inicializar
                                os.environ['AIORTC_UDP_PORT_RANGE'] = udp_range
                                super().__init__(*args, **kwargs)
                        
                        return WrappedTransport
                    
                    return attr
            
            # Interceptar módulos relevantes do aiortc
            modules_to_patch = [
                'aiortc.rtcicetransport',
                'aiortc.rtcdtlstransport',
                'aiortc'
            ]
            
            for module_name in modules_to_patch:
                if module_name in sys.modules:
                    original_module = sys.modules[module_name]
                    sys.modules[module_name] = PortControlledModule(original_module)
                    logger.info(f"✅ Módulo {module_name} interceptado")
            
            # PATCH NÍVEL 3: Variáveis de ambiente CRÍTICAS
            os.environ.update({
                'AIORTC_UDP_PORT_RANGE': udp_range,
                'WEBRTC_UDP_PORT_RANGE': udp_range,
                'AIORTC_STRICT_PORT_RANGE': 'true',
                'AIORTC_FORCE_PORT_RANGE': 'true',
                'AIORTC_BIND_PORT_MIN': str(min_port),
                'AIORTC_BIND_PORT_MAX': str(max_port)
            })
            
            logger.info("🚀 Patch AGRESSIVO COMPLETO aplicado com sucesso!")
            logger.info(f"🎯 TODAS as portas UDP serão FORÇADAS para range {udp_range}")
            
            self._port_patch_applied = True
            
        except Exception as e:
            logger.error(f"💥 ERRO CRÍTICO no patch agressivo: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            logger.warning("⚠️ Sistema pode usar portas aleatórias")
    
    def _apply_immediate_port_patch(self):
        """Aplicar patch IMEDIATO de portas UDP antes de qualquer uso do aiortc"""
        import os
        import socket
        
        udp_range = os.environ.get('AIORTC_UDP_PORT_RANGE', '40000-40100')
        min_port, max_port = map(int, udp_range.split('-'))
        
        logger.info(f"[PATCH] INTERCEPTANDO TODOS os sockets UDP para range {udp_range}")
        
        # Salvar função original antes de qualquer import do aiortc
        if not hasattr(socket, '_original_socket_backup'):
            socket._original_socket_backup = socket.socket
            
            def ultimate_socket_override(family=socket.AF_INET, type=socket.SOCK_DGRAM, proto=0, fileno=None):
                sock = socket._original_socket_backup(family, type, proto, fileno)
                
                # Interceptar APENAS sockets UDP IPv4
                if family == socket.AF_INET and type == socket.SOCK_DGRAM:
                    original_bind = sock.bind
                    
                    def ultimate_bind_override(address):
                        host, port = address
                        
                        # SEMPRE usar nosso range, independente do que foi solicitado
                        if port == 0:
                            # Porta automática - escolher do nosso range
                            for test_port in range(min_port, max_port + 1):
                                try:
                                    result = original_bind((host, test_port))
                                    logger.info(f"🎯 UDP INTERCEPTADO: {host}:{test_port} (era auto)")
                                    return result
                                except OSError:
                                    continue
                            # Se nenhuma funcionou, tentar original
                            logger.warning(f"⚠️ Range {udp_range} esgotado, usando porta automática")
                            return original_bind(address)
                        else:
                            # Porta específica - verificar se está no range
                            if min_port <= port <= max_port:
                                logger.info(f"✅ UDP PERMITIDO: {host}:{port}")
                                return original_bind(address)
                            else:
                                # Forçar para nosso range
                                forced_port = min_port
                                logger.info(f"🚫 UDP REJEITADO: {host}:{port} → FORÇADO para {host}:{forced_port}")
                                return original_bind((host, forced_port))
                    
                    sock.bind = ultimate_bind_override
                
                return sock
            
            # Aplicar o override GLOBALMENTE
            socket.socket = ultimate_socket_override
            logger.info("[PATCH] ULTIMATE aplicado - TODOS os sockets UDP serao interceptados!")
        else:
            logger.info("⚠️ Patch ultimate já estava aplicado")
    
    def _analyze_ice_candidate(self, candidate_str: str) -> str:
        """Analisar tipo de candidato ICE"""
        if "typ host" in candidate_str:
            if "127.0.0.1" in candidate_str or "::1" in candidate_str:
                return "HOST-LOCAL"
            # Ignorar candidatos Docker internos
            elif any(docker_ip in candidate_str for docker_ip in ["172.17.", "172.18.", "172.19.", "192.168.65."]):
                logger.warning(f"🚫 Ignorando candidato Docker interno: {candidate_str[:50]}...")
                return "HOST-DOCKER-IGNORED"
            else:
                return "HOST-LAN"
        elif "typ srflx" in candidate_str:
            # Priorizar candidatos SRFLX para facilitar conexões NAT
            return "SRFLX-NAT"
        elif "typ relay" in candidate_str:
            return "RELAY-TURN"
        elif "typ prflx" in candidate_str:
            return "PRFLX-PEER"
        else:
            return "UNKNOWN"
    
    def _analyze_ice_candidates(self, candidates: list) -> str:
        """Analisar estatísticas dos candidatos ICE"""
        stats = {
            "host": 0,
            "host_docker": 0,
            "srflx": 0, 
            "relay": 0,
            "total": len(candidates)
        }
        
        for candidate in candidates:
            if "typ host" in candidate:
                if self._is_docker_internal_candidate(candidate):
                    stats["host_docker"] += 1
                else:
                    stats["host"] += 1
            elif "typ srflx" in candidate:
                stats["srflx"] += 1
            elif "typ relay" in candidate:
                stats["relay"] += 1
        
        return f"HOST:{stats['host']} HOST_DOCKER:{stats['host_docker']} SRFLX:{stats['srflx']} RELAY:{stats['relay']} TOTAL:{stats['total']}"
    
    def _filter_sdp_candidates(self, sdp: str) -> str:
        """Filter out Docker internal IP candidates from SDP"""
        lines = sdp.split('\n')
        filtered_lines = []
        filtered_count = 0
        
        for line in lines:
            # Check if this is an ICE candidate line
            if line.startswith('a=candidate:'):
                # Check if this candidate contains Docker internal IPs
                if not self._is_docker_internal_candidate(line):
                    filtered_lines.append(line)
                else:
                    logger.info(f"🚫 Filtered Docker internal candidate: {line[:50]}...")
                    filtered_count += 1
            else:
                filtered_lines.append(line)
        
        if filtered_count > 0:
            logger.info(f"🔍 Filtered {filtered_count} Docker internal candidates from SDP")
        
        return '\n'.join(filtered_lines)
    
    def _is_docker_internal_candidate(self, candidate_str: str) -> bool:
        """Verificar se o candidato ICE é um IP Docker interno"""
        # IMPORTANTE: WSL IP (172.21.15.83) NÃO é Docker interno - é o IP válido do WSL
        # Apenas bloquear IPs realmente internos do Docker
        docker_ips = [
            "172.17.", "172.18.", "172.19.", "172.20.",
            # 172.21. removido para permitir WSL
            "172.22.", "172.23.", "172.24.", "172.25.", "172.26.", "172.27.", "172.28.", "172.29.", "172.30.", "172.31.",
            "192.168.65.", "192.168.66.", "192.168.67.", "192.168.68.", "192.168.69.",
            "10.0.0.", "10.0.1.", "10.0.2.", "10.0.3.", "10.0.4.", "10.0.5.", "10.0.6.", "10.0.7.", "10.0.8.", "10.0.9.",
            "169.254.",  # Link-local
            "fe80:",     # IPv6 link-local
        ]
        
        # Especificamente permitir o IP do WSL
        if "172.21.15.83" in candidate_str:
            return False
            
        for docker_ip in docker_ips:
            if docker_ip in candidate_str:
                return True
        return False
    
    async def _monitor_connection_quality(self, pc: RTCPeerConnection, session_id: str):
        """Monitorar qualidade da conexão WebRTC (compatível com versões antigas)"""
        try:
            # Verificar se getStats está disponível
            if not hasattr(pc, 'getStats'):
                logger.warning(f"⚠️ [{session_id}] getStats() não disponível nesta versão do aiortc")
                return
            
            for i in range(60):  # Monitor por 5 minutos
                await asyncio.sleep(5)
                
                if pc.connectionState != "connected":
                    break
                
                try:
                    # Obter estatísticas com tratamento de erro
                    stats = await pc.getStats()
                    if not stats:
                        continue
                    
                    rtp_stats = {"packets_sent": 0, "bytes_sent": 0, "packets_lost": 0}
                    ice_stats = {"bytes_sent": 0, "bytes_received": 0}
                    
                    for stat in stats:
                        if not hasattr(stat, 'type'):
                            continue
                        
                        stat_type = getattr(stat, 'type', '')
                        
                        # RTP statistics (with multiple property name attempts)
                        if stat_type == 'outbound-rtp' and getattr(stat, 'kind', '') == 'video':
                            rtp_stats["packets_sent"] = self._get_stat_value(stat, ['packetsSent', 'packets_sent'])
                            rtp_stats["bytes_sent"] = self._get_stat_value(stat, ['bytesSent', 'bytes_sent'])
                            rtp_stats["packets_lost"] = self._get_stat_value(stat, ['packetsLost', 'packets_lost'])
                        
                        # ICE statistics
                        elif stat_type == 'candidate-pair' and getattr(stat, 'state', '') == 'succeeded':
                            ice_stats["bytes_sent"] = self._get_stat_value(stat, ['bytesSent', 'bytes_sent'])
                            ice_stats["bytes_received"] = self._get_stat_value(stat, ['bytesReceived', 'bytes_received'])
                    
                    # Log estatísticas a cada 30 segundos
                    if i % 6 == 0:
                        logger.info(f"📊 [{session_id}] RTP: {rtp_stats['packets_sent']} pkts | "
                                  f"{rtp_stats['bytes_sent']} bytes | {rtp_stats['packets_lost']} lost")
                        
                except Exception as stats_error:
                    logger.debug(f"⚠️ [{session_id}] Erro ao obter stats: {stats_error}")
                    continue
                    
        except Exception as e:
            logger.error(f"❌ Erro no monitoramento de qualidade para {session_id}: {e}")
    
    def _get_stat_value(self, stat, property_names, default=0):
        """Obter valor de estatística com múltiplas tentativas de nome de propriedade"""
        for prop_name in property_names:
            if hasattr(stat, prop_name):
                return getattr(stat, prop_name, default)
        return default
    
    async def _handle_connection_failure(self, session_id: str):
        """Lidar com falha de conexão"""
        logger.error(f"[ERROR] Tratando falha de conexao para {session_id}")
        
        # Tentar limpeza e eventual reconexão
        try:
            await self.cleanup_connection(session_id)
        except Exception as e:
            logger.error(f"❌ Erro durante limpeza de conexão falhada: {e}")
    
    async def cleanup_connection(self, session_id: str):
        """Limpar conexão WebRTC"""
        if session_id in self.video_tracks:
            self.video_tracks[session_id].stop()
            del self.video_tracks[session_id]
        
        if session_id in self.connections:
            await self.connections[session_id].close()
            del self.connections[session_id]
        
        logger.info(f"Conexão WebRTC limpa: {session_id}")
    
    async def cleanup_all(self):
        """Limpar todas as conexões"""
        session_ids = list(self.connections.keys())
        for session_id in session_ids:
            await self.cleanup_connection(session_id)


class WebRTCServer:
    """Servidor WebRTC principal"""
    
    def __init__(self, host: str = "0.0.0.0", port: int = None):
        self.host = host
        # Usar variável de ambiente WEBRTC_PORT se disponível
        import os
        self.port = port or int(os.environ.get("WEBRTC_PORT", 8080))
        self.app = web.Application()
        self.recognition_queue = Queue(maxsize=10)
        self.connection_manager = WebRTCConnectionManager(self.recognition_queue)
        
        # Socket.IO para comunicação com recognition worker - usando namespace específico
        self.sio = socketio.AsyncServer(cors_allowed_origins="*", async_mode='aiohttp', namespaces=['/rtc'])
        
        # Configurar rotas
        self._setup_routes()
        self._setup_cors()
        
        # Configurar socketio de forma segura
        self.sio.attach(self.app, socketio_path='socket')
        
        # Configurar socketio handlers
        self._setup_socketio()
        
        logger.info(f"🚀 WebRTC Server PROFISSIONAL inicializado em {host}:{port}")
    
    def _setup_detailed_logging(self):
        """Configurar logging detalhado para debugging"""
        try:
            # Configurar logging específico para aiortc
            aiortc_logger = logging.getLogger('aiortc')
            aiortc_logger.setLevel(logging.INFO)
            
            # Configurar logging para GStreamer
            gst_logger = logging.getLogger('gi.repository.Gst')
            gst_logger.setLevel(logging.WARNING)
            
            # Configurar logging para ICE
            ice_logger = logging.getLogger('aiortc.rtcicetransport')
            ice_logger.setLevel(logging.INFO)
            
            # Configurar logging para DTLS
            dtls_logger = logging.getLogger('aiortc.rtcdtlstransport')
            dtls_logger.setLevel(logging.INFO)
            
            # Log de configuração
            logger.info("🔍 Logging detalhado configurado para debugging")
            logger.info("📊 Componentes monitorados: aiortc, GStreamer, ICE, DTLS")
            
        except Exception as e:
            logger.warning(f"⚠️ Erro ao configurar logging detalhado: {e}")
    
    def _setup_routes(self):
        """Configurar rotas HTTP"""
        self.app.router.add_post("/offer", self.handle_offer)
        self.app.router.add_get("/health", self.health_check)
        self.app.router.add_get("/status", self.get_status)
        self.app.router.add_get("/test", self.test_endpoint)
    
    def _setup_cors(self):
        """Configurar CORS ULTRA SIMPLES"""
        from aiohttp.web import middleware
        
        @middleware
        async def simple_cors_middleware(request, handler):
            # Log da requisição para debug
            logger.info(f"🌐 CORS: {request.method} {request.path}")
            
            # Se for OPTIONS, responder diretamente
            if request.method == "OPTIONS":
                response = web.Response(status=200)
                response.headers['Access-Control-Allow-Origin'] = '*'
                response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
                response.headers['Access-Control-Allow-Headers'] = '*'
                response.headers['Access-Control-Max-Age'] = '86400'
                return response
            else:
                try:
                    response = await handler(request)
                except Exception as e:
                    logger.error(f"💥 Handler error: {e}")
                    response = web.json_response({"error": f"Handler failed: {str(e)}"}, status=500)
            
            # Headers CORS para todas as respostas
            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
            response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With'
            
            return response
        
        # Adicionar middleware
        self.app.middlewares.append(simple_cors_middleware)
    
    def _setup_socketio(self):
        """Configurar Socket.IO"""
        @self.sio.event(namespace='/rtc')
        async def connect(sid, environ):
            logger.info(f"Cliente Socket.IO conectado: {sid}")
        
        @self.sio.event(namespace='/rtc')
        async def disconnect(sid):
            logger.info(f"Cliente Socket.IO desconectado: {sid}")
        
        @self.sio.event(namespace='/rtc')
        async def recognition_result(sid, data):
            """Receber resultado de reconhecimento do recognition worker"""
            logger.info(f"Resultado de reconhecimento recebido: {data}")
            # Broadcast para clientes WebSocket se necessário
        
    async def handle_offer(self, request):
        """Handle WebRTC offer"""
        request_id = str(uuid.uuid4())[:8]
        
        try:
            # Parse JSON data
            data = await request.json()
            logger.info(f"🔍 DEBUG: Incoming offer data keys: {list(data.keys())}")
            
            offer_sdp = data.get("sdp")
            offer_type = data.get("type")
            session_id = data.get("session_id", "video")
            
            logger.info(f"🔍 DEBUG: Session ID: {session_id}")
            if 'camera' in data:
                logger.info(f"🔍 DEBUG: Camera data: {data['camera']}")
            else:
                logger.info(f"🔍 DEBUG: No camera field in data")
            
            if not offer_sdp or not offer_type:
                return web.json_response({"error": "SDP e type são obrigatórios"}, status=400)
            
            logger.info(f"✅ Criando conexão WebRTC: {session_id}")
            
            # Criar PeerConnection
            pc = await self.connection_manager.create_peer_connection(session_id, {})
            
            # Extrair camera_id do campo camera na requisição ou do session_id
            try:
                logger.info(f"🔍 DEBUG: Starting camera config processing")
                camera_data = data.get("camera")
                camera_id = None
                camera_config = {'type': 'test', 'id': session_id}
                logger.info(f"🔍 DEBUG: Initial camera_config created: {camera_config}")
            except Exception as e:
                logger.error(f"🔍 DEBUG: Error in initial camera config setup: {e}")
                logger.error(f"🔍 DEBUG: Error type: {type(e)}")
                import traceback
                logger.error(f"🔍 DEBUG: Traceback: {traceback.format_exc()}")
                raise
            
            if camera_data and isinstance(camera_data, dict):
                # Camera data enviado diretamente pelo frontend
                camera_id = camera_data.get('id')
                logger.info(f"🎯 Camera data recebido: {camera_data.get('name', 'Unknown')} (ID: {camera_id})")
                
                # Usar os dados da câmera recebidos
                camera_config = {
                    'id': camera_id,
                    'name': camera_data.get('name', 'Camera'),
                    'url': camera_data.get('url', ''),
                    'type': 'rtsp' if camera_data.get('url', '').startswith('rtsp://') else 'test',
                    'rtsp_url': camera_data.get('url') if camera_data.get('url', '').startswith('rtsp://') else None,
                    'resolution_width': camera_data.get('resolution_width'),
                    'resolution_height': camera_data.get('resolution_height'),
                    'fps_limit': camera_data.get('fps_limit', 25)
                }
                logger.info(f"📹 Camera config criada: {camera_config.get('name')} - {camera_config.get('type')}")
                logger.info(f"🔗 URL: {camera_config.get('url', 'N/A')}")
                
            elif session_id.startswith("camera_"):
                # Formato legado: camera_<uuid>_<timestamp>
                parts = session_id.split("_")
                if len(parts) >= 2:
                    camera_id = parts[1]  # UUID da câmera
                    logger.info(f"🎯 Extraindo camera_id: {camera_id}")
                    
                    # Buscar configuração da câmera
                    try:
                        camera_config = await self._get_camera_config(camera_id)
                        if camera_config:
                            logger.info(f"📹 Camera config encontrada: {camera_config.get('name', 'Unknown')}")
                            logger.info(f"🔗 RTSP URL: {camera_config.get('rtsp_url', 'N/A')}")
                        else:
                            logger.warning(f"⚠️ Camera config não encontrada para {camera_id}, usando teste")
                            camera_config = {'type': 'test', 'id': camera_id, 'url': 'test://source'}
                    except Exception as e:
                        logger.error(f"❌ Erro ao buscar camera config: {e}")
                        camera_config = {'type': 'test', 'id': camera_id, 'url': 'test://source'}
            
            # Criar track de vídeo ANTES de processar o offer
            logger.info(f"📹 Criando track de vídeo para {camera_config.get('type', 'test')}")
            
            # TEMPORÁRIO: Usar sempre TestVideoTrack para garantir estabilidade
            logger.info(f"🧪 MODO DEBUG: Usando TestVideoTrack para garantir estabilidade")
            video_track = self._create_test_video_track()
            logger.info(f"📹 TestVideoTrack criado")
            
            # Adicionar track ao PeerConnection
            pc.addTrack(video_track)
            
            # Salvar referência do track
            self.connection_manager.video_tracks[session_id] = video_track
            logger.info(f"✅ Video track adicionado ao PeerConnection")
            
            # Processar offer recebido DEPOIS de adicionar o track
            offer = RTCSessionDescription(sdp=offer_sdp, type=offer_type)
            await pc.setRemoteDescription(offer)
            logger.info(f"📨 Offer processado para {session_id}")
            
            # Criar answer
            answer = await pc.createAnswer()
            await pc.setLocalDescription(answer)
            logger.info(f"📩 Answer criado")
            
            # Aguardar ICE gathering
            for _ in range(10):  # Até 1 segundo
                if pc.iceGatheringState == "complete":
                    break
                await asyncio.sleep(0.1)
            
            logger.info(f"ICE gathering: {pc.iceGatheringState}")
            
            # Preparar resposta com SDP filtrado (remover candidatos Docker internos)
            filtered_sdp = self.connection_manager._filter_sdp_candidates(pc.localDescription.sdp)
            response_data = {
                "sdp": filtered_sdp,
                "type": pc.localDescription.type,
                "session_id": session_id
            }
            
            logger.info(f"Answer SDP original: {pc.localDescription.sdp.count('a=candidate')} candidatos ICE")
            logger.info(f"Answer SDP filtrado: {filtered_sdp.count('a=candidate')} candidatos ICE")
            
            return web.json_response(response_data)
            
        except Exception as e:
            logger.error(f"💥 Erro ao processar offer: {e}")
            return web.json_response({"error": str(e)}, status=500)
    
    async def health_check(self, request):
        """Health check endpoint"""
        return web.json_response({
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "gstreamer_available": GSTREAMER_AVAILABLE,
            "active_connections": len(self.connection_manager.connections)
        })
    
    async def get_status(self, request):
        """Status endpoint"""
        return web.json_response({
            "active_connections": len(self.connection_manager.connections),
            "video_tracks": len(self.connection_manager.video_tracks),
            "recognition_queue_size": self.recognition_queue.qsize() if hasattr(self.recognition_queue, 'qsize') else 0,
            "gstreamer_available": GSTREAMER_AVAILABLE
        })
    
    async def test_endpoint(self, request):
        """Test endpoint to verify WebRTC server is running"""
        logger.info("🧪 Test endpoint acessado!")
        return web.json_response({
            "message": "WebRTC Server está funcionando!",
            "timestamp": datetime.now().isoformat(),
            "server_info": {
                "gstreamer_available": GSTREAMER_AVAILABLE,
                "active_connections": len(self.connection_manager.connections),
                "python_version": str(sys.version),
                "working_dir": str(os.getcwd()) if hasattr(os, 'getcwd') else "unknown"
            }
        })
    
    async def start_recognition_worker_process(self):
        """Iniciar processo de reconhecimento facial"""
        from app.webrtc_worker.recognition_worker import start_recognition_worker
        
        try:
            # Iniciar worker em processo separado
            recognition_process = Process(
                target=start_recognition_worker,
                args=(self.recognition_queue,)
            )
            recognition_process.daemon = True
            recognition_process.start()
            
            logger.info("Processo de reconhecimento facial iniciado")
            return recognition_process
            
        except Exception as e:
            logger.error(f"Erro ao iniciar processo de reconhecimento: {e}")
            return None
    
    async def _get_camera_config(self, camera_id: str):
        """Buscar configuração da câmera no banco de dados via API"""
        try:
            api_url = os.environ.get('API_BASE_URL', 'http://localhost:9000')
            url = f"{api_url}/api/v1/cameras/{camera_id}"
            logger.info(f"🔍 Buscando config da câmera em: {url}")
            
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        camera_data = await response.json()
                        logger.info(f"✅ Camera data recebido: {list(camera_data.keys())}")
                        
                        # Tentar diferentes formatos de resposta da API
                        camera_config = None
                        if 'camera' in camera_data:
                            camera_config = camera_data['camera']
                        elif 'data' in camera_data:
                            camera_config = camera_data['data']
                        else:
                            # Se a resposta é diretamente a config da câmera
                            camera_config = camera_data
                        
                        if camera_config and 'id' in camera_config:
                            logger.info(f"✅ Config da câmera encontrada: {camera_config.get('name', 'Unknown')}")
                            return camera_config
                        else:
                            logger.warning(f"⚠️ Formato de resposta inesperado: {camera_data}")
                            return None
                    elif response.status == 404:
                        logger.warning(f"⚠️ Câmera {camera_id} não encontrada (404)")
                        return None
                    else:
                        logger.error(f"❌ Erro HTTP ao buscar câmera {camera_id}: {response.status}")
                        response_text = await response.text()
                        logger.error(f"Response: {response_text[:200]}...")
                        return None
        except asyncio.TimeoutError:
            logger.error(f"⏰ Timeout ao conectar com API para câmera {camera_id}")
            return None
        except Exception as e:
            logger.error(f"❌ Erro ao conectar com API para câmera {camera_id}: {e}")
            return None
    
    async def _create_rtsp_video_track(self, camera_config: Dict[str, Any], session_id: str):
        """Criar video track RTSP usando MediaPlayer do aiortc (recomendação WebRTC)"""
        try:
            from aiortc.contrib.media import MediaPlayer
            camera_url = camera_config.get('url', '')
            
            logger.info(f"🎥 Criando MediaPlayer WebRTC para {camera_url}")
            
            # Pipeline GStreamer otimizado para WebRTC (seguindo recomendações)
            gst_pipeline = (
                f"rtspsrc location={camera_url} latency=100 ! "
                f"rtph264depay ! h264parse ! avdec_h264 ! videoconvert ! videoscale ! "
                f"video/x-raw,width=640,height=480 ! queue ! x264enc tune=zerolatency bitrate=512 speed-preset=ultrafast ! "
                f"rtph264pay config-interval=1 pt=96 name=pay0"
            )
            
            # Criar MediaPlayer com pipeline otimizado
            player = MediaPlayer(gst_pipeline, format="gst")
            
            if player and player.video:
                logger.info(f"✅ MediaPlayer WebRTC criado com sucesso para {session_id}")
                logger.info(f"🎯 Pipeline: {gst_pipeline}")
                return player.video
            else:
                logger.warning(f"⚠️ MediaPlayer falhou, usando fallback de teste")
                return self._create_test_video_track()
                
        except Exception as e:
            logger.error(f"❌ Erro ao criar MediaPlayer RTSP: {e}")
            logger.error(f"🔄 Usando fallback de teste para {session_id}")
            return self._create_test_video_track()
    
    def _create_test_video_track(self):
        """Criar video track de teste funcional - VERSÃO SIMPLIFICADA PARA DEBUG"""
        logger.info(f"🧪 CRIANDO TEST VIDEO TRACK SIMPLIFICADO")
        
        # Versão simplificada sem MediaPlayer para debug
        class TestVideoTrack(MediaStreamTrack):
            kind = "video"
            def __init__(self):
                super().__init__()
                self.counter = 0
            
            async def start(self):
                """Start method for compatibility with GStreamerVideoTrack"""
                return True  # Test tracks are always ready
            
            async def recv(self):
                # Log para verificar se está enviando frames
                if self.counter % 30 == 0:  # Log a cada 30 frames para não sobrecarregar
                    print(f"🌀 TEST TRACK: Enviando frame {self.counter}")
                    logger.info(f"🌀 TEST TRACK: Frame {self.counter} sendo enviado via WebRTC")
                
                pts, time_base = await self.next_timestamp()
                
                # Criar frame colorido animado MAIS VISÍVEL
                import numpy as np
                width, height = 640, 480
                
                # Frame com gradiente colorido que muda
                frame_data = np.zeros((height, width, 3), dtype=np.uint8)
                
                # Fundo gradiente animado
                for y in range(height):
                    for x in range(width):
                        r = int((x / width) * 255)
                        g = int((y / height) * 255) 
                        b = int(((x + y + self.counter * 2) % 256))
                        frame_data[y, x] = [r, g, b]
                
                # Círculo central animado GRANDE
                center_y = height // 2 + int(100 * np.sin(self.counter * 0.05))
                center_x = width // 2 + int(100 * np.cos(self.counter * 0.05))
                radius = 80
                
                # Desenhar círculo branco grande
                for y in range(max(0, center_y - radius), min(height, center_y + radius)):
                    for x in range(max(0, center_x - radius), min(width, center_x + radius)):
                        if (x - center_x) ** 2 + (y - center_y) ** 2 <= radius ** 2:
                            frame_data[y, x] = [255, 255, 255]
                
                # Texto grande do contador
                import cv2
                text = f"TEST FRAME {self.counter}"
                cv2.putText(frame_data, text, (50, 100), cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 0), 4)
                cv2.putText(frame_data, "WEBRTC TEST", (50, 400), cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 0), 4)
                
                # Converter para av.VideoFrame
                frame = av.VideoFrame.from_ndarray(frame_data, format='rgb24')
                frame = frame.reformat(format='yuv420p')
                frame.pts = pts
                frame.time_base = time_base
                
                # Keyframe a cada 30 frames
                if self.counter % 30 == 0:
                    frame.key_frame = True
                    if self.counter % 90 == 0:  # Log keyframes ocasionalmente
                        logger.info(f"🔑 TEST TRACK: Keyframe #{self.counter} enviado")
                
                self.counter += 1
                return frame
        
        return TestVideoTrack()
    
    async def run(self):
        """Iniciar o servidor"""
        try:
            # Configurar logging de WebRTC
            logging.basicConfig(level=logging.DEBUG)
            
            # Configurar range de portas UDP FIXO para WebRTC com monitoramento
            import os
            udp_range = os.environ.get('AIORTC_UDP_PORT_RANGE', '40000-40100')
            os.environ['AIORTC_UDP_PORT_RANGE'] = udp_range
            
            # Aplicar configurações strict se ativado
            if os.environ.get('AIORTC_STRICT_PORT_RANGE', 'false').lower() == 'true':
                logger.info(f"🔒 Modo STRICT: Apenas portas {udp_range} permitidas para ICE")
            
            logger.info(f"🔧 Range de portas UDP FIXO configurado: {udp_range}")
            
            # Configurar logging detalhado para debugging
            self._setup_detailed_logging()
            
            # Exibir informações do ambiente
            host_network = os.getenv('WEBRTC_HOST_NETWORK', 'false').lower() == 'true'
            public_ip = os.getenv('WEBRTC_PUBLIC_IP', '127.0.0.1')
            logger.info(f"🌐 WebRTC Server em modo host network: {host_network}")
            logger.info(f"🌐 WebRTC Public IP configurado: {public_ip}")
            
            # Configuração simples de rede
            logger.info("🌐 Configurando WebRTC para conectividade local")
            
            # Iniciar processo de reconhecimento
            await self.start_recognition_worker_process()
            
            # Iniciar servidor HTTP
            runner = web.AppRunner(self.app)
            await runner.setup()
            
            site = web.TCPSite(runner, self.host, self.port)
            await site.start()
            
            logger.info(f"🚀 WebRTC Server rodando em http://{self.host}:{self.port}")
            
            # Manter o servidor rodando
            while True:
                await asyncio.sleep(3600)  # 1 hora
                
        except KeyboardInterrupt:
            logger.info("WebRTC Server interrompido pelo usuário")
        except Exception as e:
            logger.error(f"Erro ao iniciar WebRTC Server: {e}")
            raise


def configure_udp_bypass():
    """Configuração avançada de rede com teste de portas UDP"""
    import socket
    import os
    
    logger.info("🌐 Configuração de rede WebRTC inicializada")
    
    # Verificar range de portas UDP configurado
    udp_range = os.environ.get('AIORTC_UDP_PORT_RANGE', '40000-40100')
    min_port, max_port = map(int, udp_range.split('-'))
    
    logger.info(f"🔍 Testando disponibilidade de portas UDP: {udp_range}")
    
    # Testar algumas portas do range
    available_ports = []
    test_ports = [min_port, min_port + 1, min_port + 2, max_port - 2, max_port - 1, max_port]
    
    for port in test_ports:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.bind(('0.0.0.0', port))
            available_ports.append(port)
            sock.close()
        except OSError as e:
            logger.warning(f"⚠️ Porta UDP {port} não disponível: {e}")
    
    if available_ports:
        logger.info(f"✅ Portas UDP disponíveis: {available_ports}")
        logger.info(f"🎯 ICE candidates usarão apenas o range {udp_range}")
        return True
    else:
        logger.error(f"❌ Nenhuma porta UDP disponível no range {udp_range}!")
        return False


if __name__ == "__main__":
    import sys
    import os
    
    # Configurar logging
    logger.remove()
    logger.add(
        sys.stdout,
        format="<green>{time:HH:mm:ss}</green> | <cyan>WEBRTC</cyan> | <level>{level}</level> | {message}",
        level="INFO"
    )
    
    logger.info("🚀 Iniciando WebRTC Server...")
    logger.info(f"Python version: {sys.version}")
    logger.info(f"Working directory: {os.getcwd()}")
    
    # Configurar bypass de firewall para UDP
    configure_udp_bypass()
    
    # Verificar dependências
    try:
        import aiortc
        logger.info(f"✅ aiortc version: {aiortc.__version__}")
    except ImportError as e:
        logger.error(f"❌ aiortc not available: {e}")
    
    try:
        import aiohttp
        logger.info(f"✅ aiohttp available")
    except ImportError as e:
        logger.error(f"❌ aiohttp not available: {e}")
    
    # Obter porta da variável de ambiente
    webrtc_port = int(os.environ.get("WEBRTC_PORT", 8080))
    logger.info(f"🔌 Usando porta WebRTC: {webrtc_port}")
    
    # Inicializar e executar servidor
    logger.info("🔧 Inicializando WebRTC Server...")
    server = WebRTCServer(host="0.0.0.0", port=webrtc_port)
    
    try:
        logger.info("▶️  Executando WebRTC Server...")
        asyncio.run(server.run())
    except KeyboardInterrupt:
        logger.info("⏹️  Servidor interrompido pelo usuário")
    except Exception as e:
        logger.error(f"💥 Erro fatal no WebRTC Server: {e}")
        raise