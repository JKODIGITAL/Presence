#!/usr/bin/env python3
"""
VMS WebRTC Server Nativo com Janus Integration
Servidor WebRTC completo para múltiplas câmeras com GStreamer nativo
Suporte opcional para Janus Gateway como SFU
"""

import asyncio
import json
import logging
import os
import sys
from typing import Dict, List, Optional, Any
from pathlib import Path
from datetime import datetime
import uuid
import gc
import aiohttp
import numpy as np
import cv2

# Determinar caminho de log compatível com Windows e Linux
def get_debug_log_path():
    """Retorna um caminho de log compatível com o sistema operacional atual"""
    # Verificar se estamos no Windows
    if sys.platform.startswith('win'):
        # Criar pasta logs na raiz do projeto se não existir
        log_dir = os.path.join(os.getcwd(), 'logs')
        if not os.path.exists(log_dir):
            try:
                os.makedirs(log_dir, exist_ok=True)
            except Exception:
                # Fallback para o diretório atual se não conseguir criar logs
                return os.path.join(os.getcwd(), 'vms_debug.log')
        return os.path.join(log_dir, 'vms_debug.log')
    else:
        # No Linux, usar o /tmp padrão
        return '/tmp/vms_debug.log'

# Caminho global para o arquivo de log de debug
DEBUG_LOG_PATH = get_debug_log_path()

# Configuração simplificada para LAN (patches Docker removidos)
def apply_global_udp_port_patch():
    """Placeholder - patches UDP Docker removidos para uso em LAN"""
    logger.info("[CONFIG] Patches UDP Docker foram removidos (usando LAN apenas)")
    pass

def apply_asyncio_patch():
    """Placeholder - patches asyncio Docker removidos para uso em LAN"""
    logger.info("[CONFIG] Patches asyncio Docker foram removidos (usando LAN apenas)")
    pass

# Não aplicar patches para uso em LAN
# apply_global_udp_port_patch()
# apply_asyncio_patch()

# Usar aiortc em vez do GStreamer webrtcbin
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCConfiguration, RTCIceServer
from aiortc.contrib.media import MediaPlayer, MediaRelay
from aiortc.mediastreams import VideoStreamTrack
import av
import numpy as np
import cv2
from fractions import Fraction

# Import do bridge GStreamer (melhorado + compatibilidade)
from app.webrtc_worker.enhanced_gstreamer_bridge import enhanced_gstreamer_bridge, simple_gstreamer_bridge

from fastapi import FastAPI, WebSocket, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.websockets import WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import requests

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def fix_sdp_payload_types(sdp_text):
    """Corrigir payload types inválidos no SDP"""
    import re
    
    # Corrigir m=video line
    sdp_text = re.sub(r'm=video 9 UDP/TLS/RTP/SAVPF (\d{4,})', r'm=video 9 UDP/TLS/RTP/SAVPF 96', sdp_text)
    
    # Corrigir a=rtpmap lines
    sdp_text = re.sub(r'a=rtpmap:(\d{4,}) H264/90000', r'a=rtpmap:96 H264/90000', sdp_text)
    
    # Corrigir a=rtcp-fb lines
    sdp_text = re.sub(r'a=rtcp-fb:(\d{4,}) nack pli', r'a=rtcp-fb:96 nack pli', sdp_text)
    sdp_text = re.sub(r'a=rtcp-fb:(\d{4,}) transport-cc', r'a=rtcp-fb:96 transport-cc', sdp_text)
    
    return sdp_text

class WebRTCConnection:
    """Representa uma conexão WebRTC com um cliente usando aiortc"""
    
    def __init__(self, connection_id: str, websocket: WebSocket):
        self.connection_id = connection_id
        self.websocket = websocket
        self.pc = None  # RTCPeerConnection
        self.camera_id = None
        self.state = "disconnected"
        self.media_player = None
        self.media_relay = MediaRelay()
        
        # Negotiation state management
        self.negotiation_state = "stable"
        self.offer_pending = False
        self.last_offer_time = None
        self.offer_timeout = 10.0
        
    async def create_peer_connection(self):
        """Cria RTCPeerConnection com configuração de porta UDP fixa"""
        # Configurar range de portas UDP
        udp_range = os.environ.get('AIORTC_UDP_PORT_RANGE', '40000-40100')
        min_port, max_port = map(int, udp_range.split('-'))
        
        # Configurar ICE servers com IP forçado
        forced_ip = os.environ.get('AIORTC_FORCE_HOST_IP', '127.0.0.1')
        
        # Configuração para conexão local (aiortc básico)
        ice_servers = []
        
        # Configuração simples e compatível com aiortc
        configuration = RTCConfiguration(
            iceServers=ice_servers
        )
        
        # Configurar ICE transport com IP específico
        import socket
        
        # Forçar bind em IP específico através de monkey patch do socket
        original_socket_init = socket.socket.__init__
        
        def patched_socket_init(self, family=socket.AF_INET, type=socket.SOCK_STREAM, proto=0, fileno=None):
            original_socket_init(self, family, type, proto, fileno)
            if family == socket.AF_INET and type == socket.SOCK_DGRAM:
                try:
                    # Bind em IP específico para UDP sockets (ICE)
                    self.bind((forced_ip, 0))
                    logger.info(f"[INFO] Socket UDP vinculado a {forced_ip}")
                except Exception as e:
                    logger.warning(f"[ALERTA] Não foi possível vincular socket a {forced_ip}: {e}")
        
        # Aplicar patch temporariamente
        socket.socket.__init__ = patched_socket_init
        
        self.pc = RTCPeerConnection(configuration=configuration)
        
        # Restaurar socket original
        socket.socket.__init__ = original_socket_init
        
        logger.info(f"[OK] RTCPeerConnection criado com IP {forced_ip} e range UDP {udp_range} para {self.connection_id}")
        
        # Configurar callbacks
        @self.pc.on("icecandidate")
        async def on_ice_candidate(candidate):
            if candidate:
                # Filtrar e forçar IP para 172.21.0.1
                filtered_candidate = self.filter_ice_candidate_ip(candidate)
                if filtered_candidate:
                    await self.send_ice_candidate(filtered_candidate)
        
        @self.pc.on("connectionstatechange")
        async def on_connection_state_change():
            logger.info(f"🔗 Connection state: {self.pc.connectionState} para {self.connection_id}")
        
        return self.pc
    
    def optimize_video_codec(self, pc):
        """Otimizar codec de vídeo para performance"""
        try:
            # Configurar transceivers com configurações otimizadas
            for transceiver in pc.getTransceivers():
                if transceiver.kind == "video":
                    # Configurações de RTP para H264 otimizado
                    sender = transceiver.sender
                    if sender and sender.track:
                        # Configurar parâmetros de codec
                        params = sender.getParameters()
                        if params.codecs:
                            for codec in params.codecs:
                                if codec.mimeType.lower() == "video/h264":
                                    # Otimizar para baixa latência
                                    codec.parameters = {
                                        "profile-level-id": "42001f",  # Baseline profile
                                        "level-asymmetry-allowed": "1",
                                        "packetization-mode": "1",
                                        "max-fs": "3600",           # Max frame size
                                        "max-cpb": "3000",          # Buffer size
                                        "max-br": "2000",           # Max bitrate (2Mbps)
                                    }
                        sender.setParameters(params)
                        logger.info(f"[PERF] Codec H264 otimizado para {self.connection_id}")
        except Exception as e:
            logger.warning(f"[PERF] Não foi possível otimizar codec: {e}")
    
    def filter_ice_candidate_ip(self, candidate):
        """Filter ICE candidate IPs for LAN usage (Docker IP forcing removed)"""
        if not candidate or not candidate.candidate:
            return candidate
        
        # Para uso em LAN, não forçamos IPs específicos - deixamos aiortc gerenciar
        candidate_str = candidate.candidate
        logger.info(f"[OK] ICE candidate mantido (LAN): {candidate_str[:50]}...")
        return candidate
        
    async def setup_media_stream(self, camera_id: str):
        """Configura stream de mídia para a câmera"""
        self.camera_id = camera_id
        
        try:
            # Verificar se a câmera existe e obter URL RTSP
            from aiortc import VideoStreamTrack
            import av
            import asyncio
            import numpy as np
            from fractions import Fraction  # Importar Fraction para usar como time_base
            
            # Obter informações da câmera do dicionário active_cameras
            camera_info = None
            rtsp_url = None
            camera_type = None
            
            # Buscar o servidor WebRTC para acessar o dicionário active_cameras
            server = None
            
            # Tentativa 1: Procurar pela instância do servidor nos objetos ativos
            try:
                import gc
                for instance in [obj for obj in gc.get_objects() if isinstance(obj, VMS_WebRTCServerNative)]:
                    server = instance
                    break
            except Exception as e:
                logger.warning(f"[ALERTA] Não foi possível encontrar o servidor via gc: {e}")
            
            # Tentativa 2: Usar URL RTSP diretamente do parâmetro de ambiente
            if not server:
                import os
                default_rtsp = os.environ.get(f"RTSP_URL_{camera_id}", "")
                if default_rtsp:
                    rtsp_url = default_rtsp
                    logger.info(f"[INFO] Usando URL RTSP do ambiente para {camera_id}: {rtsp_url}")
            else:
                # Servidor encontrado, buscar câmera no dicionário
                if camera_id in server.active_cameras:
                    camera_info = server.active_cameras[camera_id]
                    rtsp_url = camera_info.get('rtsp_url')
                    camera_type = camera_info.get('type', 'ip_camera')
                    logger.info(f"[INFO] Encontrada câmera {camera_id} com URL: {rtsp_url}, tipo: {camera_type}")
                else:
                    logger.warning(f"[ALERTA] Câmera {camera_id} não encontrada no servidor")
            
            # Tentativa 3: Usar URL RTSP hardcoded para teste
            if not rtsp_url or rtsp_url == 'test-pattern':
                # URL RTSP de teste (câmera pública)
                test_urls = {
                    # Câmera local do usuário como primeira opção (URL encoding fix)
                    "cam1": "rtsp://admin:Extreme%40123@192.168.0.153:554/Streaming/channels/101",
                    # Câmeras públicas de backup (caso a câmera local não esteja acessível)
                    "cam2": "rtsp://wowzaec2demo.streamlock.net/vod/mp4:BigBuckBunny_115k.mp4",
                    "cam3": "rtsp://demo:demo@ipvmdemo.dyndns.org:5541/onvif-media/media.amp?profile=profile_1_h264&sessiontimeout=60&streamtype=unicast",
                    "cam4": "rtsp://freja.hiof.no:1935/rtplive/definst/hessdalen03.stream"
                }
                rtsp_url = test_urls.get(camera_id, test_urls.get("cam1"))
                logger.info(f"[INFO] Usando URL RTSP de teste para {camera_id}: {rtsp_url}")
            
            # Usar Camera Worker Bridge para TODOS os tipos de fonte (RTSP e video files)
            # Isso garante que tanto RTSP quanto arquivos passem pelo mesmo pipeline unificado
            logger.info(f"[INFO] Configurando Camera Worker bridge para câmera {camera_id}: {rtsp_url} (tipo: {camera_type})")
            
            try:
                # Importar Camera Worker Bridge
                try:
                    from .camera_worker_bridge import camera_worker_bridge
                except ImportError:
                    from app.webrtc_worker.camera_worker_bridge import camera_worker_bridge
                
                # Criar track conectado ao Camera Worker pipeline
                video_track = await camera_worker_bridge.create_track(camera_id)
                
                if video_track:
                    self.pc.addTrack(video_track)
                    logger.info(f"[OK] Camera Worker bridge configurado para câmera {camera_id}")
                    return
                else:
                    logger.error(f"[ERRO] Falha ao criar Camera Worker bridge para câmera {camera_id}")
                    
            except Exception as e:
                logger.error(f"[ERRO] Falha ao configurar Camera Worker bridge: {e}")
                import traceback
                logger.error(f"[ERRO] Traceback: {traceback.format_exc()}")
                
                # Fallback para método original apenas se o bridge falhar
                logger.info(f"[FALLBACK] Usando método direto para câmera {camera_id}")
                
                # Verificar se é arquivo de vídeo para fallback
                if camera_type == 'video_file' or (rtsp_url and (rtsp_url.endswith('.mp4') or rtsp_url.endswith('.avi') or rtsp_url.endswith('.mov'))):
                    logger.info(f"[FALLBACK] Configurando video file track para câmera {camera_id}: {rtsp_url}")
                    
                    try:
                        # Importar EnhancedVideoTrack
                        try:
                            from .enhanced_video_track import EnhancedVideoTrack
                        except ImportError:
                            from app.webrtc_worker.enhanced_video_track import EnhancedVideoTrack
                        
                        # Criar EnhancedVideoTrack para arquivo de vídeo
                        video_track = EnhancedVideoTrack(
                            source=rtsp_url,
                            camera_id=camera_id,
                            enable_recognition=True,
                            enable_hwaccel=False,  # Usar software decode para arquivos locais
                            target_fps=30
                        )
                        
                        # Inicializar o track
                        success = await video_track.start()
                        if success:
                            self.pc.addTrack(video_track)
                            logger.info(f"[OK] Video file track configurado com sucesso para câmera {camera_id}")
                            return
                        else:
                            logger.error(f"[ERRO] Falha ao inicializar video file track para {rtsp_url}")
                            
                    except Exception as e:
                        logger.error(f"[ERRO] Falha ao criar EnhancedVideoTrack para arquivo: {e}")
                        import traceback
                        logger.error(f"[ERRO] Traceback: {traceback.format_exc()}")
            
            # Para streams RTSP, continuar com MediaPlayer (fallback)
            if camera_type in ['ip_camera', 'demo_stream'] or rtsp_url.startswith('rtsp://'):
                logger.info(f"[INFO] Tentando conectar ao stream RTSP para câmera {camera_id}: {rtsp_url}")
                
                # Criar MediaPlayer para RTSP com opções robustas
                options = {
                    'rtsp_transport': 'tcp',  # Usar TCP para RTSP (mais estável)
                    'stimeout': '5000000',    # Timeout em microssegundos (5s)
                    'reconnect': '1',         # Tentar reconectar automaticamente
                    'reconnect_streamed': '1',
                    'reconnect_delay_max': '5', # Máximo delay entre tentativas (segundos)
                    'buffer_size': '1024000',   # Buffer maior para estabilidade
                    'max_delay': '500000',      # Delay máximo para sincronização (500ms)
                }
                
                # Criar MediaPlayer com opções
                try:
                    self.media_player = MediaPlayer(rtsp_url, format='rtsp', options=options)
                    
                    # Obter track de vídeo do MediaPlayer
                    video_track = self.media_player.video
                    if video_track:
                        self.pc.addTrack(video_track)
                        logger.info(f"[OK] Stream RTSP configurado com sucesso para câmera {camera_id}")
                        return
                    else:
                        logger.error(f"[ERRO] MediaPlayer não forneceu track de vídeo para {rtsp_url}")
                        # Continuar para usar o padrão de teste como fallback
                except Exception as e:
                    logger.error(f"[ERRO] Falha ao criar MediaPlayer para {rtsp_url}: {e}")
                    import traceback
                    logger.error(f"[ERRO] Traceback: {traceback.format_exc()}")
                    # Continuar para usar o padrão de teste como fallback
            
            # FALLBACK: Usar padrão de teste apenas se todas as tentativas de RTSP falharem
            logger.warning(f"[ALERTA] TODAS AS TENTATIVAS DE RTSP FALHARAM. Usando padrão de teste para câmera {camera_id}")
            
            class SmartVideoTrack(VideoStreamTrack):
                """VideoTrack inteligente com reconhecimento facial e overlay"""
                kind = "video"
                
                def __init__(self, rtsp_url: str, enable_recognition: bool = False, camera_id: str = None):
                    super().__init__()
                    self._pts = 0
                    self.width = 640
                    self.height = 480
                    self.rtsp_url = rtsp_url
                    self.enable_recognition = enable_recognition
                    self.camera_id = camera_id or "unknown"
                    self._recognition_engine = None
                    self._last_recognition_time = 0
                    self._recognition_interval = 0.5  # Reconhecer a cada 500ms
                    self._last_frame_with_overlay = None
                    self._last_recognition_results = None
                    
                    # Tentar inicializar MediaPlayer com otimizações de performance
                    try:
                        # Configurações otimizadas para máxima performance local
                        performance_options = {
                            'rtsp_transport': 'tcp',
                            'stimeout': '1000000',      # Timeout reduzido para 1s
                            'buffer_size': '256000',    # Buffer menor para ultra baixa latência
                            'max_delay': '50000',       # Máximo delay 50ms
                            'fflags': '+fastseek+discardcorrupt+nobuffer',
                            'flags': '+low_delay',
                            'framedrop': '1',           # Drop frames se necessário
                            'sync': 'video',            # Sync por vídeo
                            'threads': '4',             # Threading otimizado
                            'thread_type': 'frame',     # Frame-level threading
                            'analyzeduration': '100000', # Análise mínima
                            'probesize': '32768',       # Probe size mínimo
                        }
                        
                        # NVDEC otimizado para Windows/NVIDIA com fallback inteligente
                        import platform
                        if platform.system() == "Windows":
                            performance_options.update({
                                'hwaccel': 'nvdec',
                                'hwaccel_output_format': 'cuda',
                                'hwaccel_device': '0',      # GPU 0
                                'c:v': 'h264_nvdec',        # NVIDIA decoder específico
                                'gpu': '0',                 # Force GPU 0
                                'decode_delay_max': '1',    # Máximo 1 frame de delay
                                'extra_hw_frames': '8',     # Pool de frames de hardware
                            })
                            logger.info(f"🚀 [NVDEC] Hardware acceleration enabled for {rtsp_url}")
                        
                        self.media_player = MediaPlayer(rtsp_url, format='rtsp', options=performance_options)
                        self.video_source = self.media_player.video
                        self.use_real_stream = True
                        logger.info(f"✅ [NVDEC] Hardware-accelerated SmartVideoTrack: {rtsp_url}")
                        logger.info(f"🔧 [PERF] Options: buffer={performance_options.get('buffer_size')}, delay={performance_options.get('max_delay')}")
                        
                    except Exception as e:
                        # Fallback sem NVDEC
                        logger.warning(f"[FALLBACK] NVDEC failed, trying software decode: {e}")
                        try:
                            fallback_options = {
                                'rtsp_transport': 'tcp',
                                'stimeout': '1000000',
                                'buffer_size': '256000',
                                'max_delay': '50000',
                                'fflags': '+fastseek+discardcorrupt+nobuffer',
                                'flags': '+low_delay',
                                'framedrop': '1',
                                'threads': '2',             # Fewer threads for software
                                'thread_type': 'frame',
                                'analyzeduration': '100000',
                                'probesize': '32768',
                            }
                            self.media_player = MediaPlayer(rtsp_url, format='rtsp', options=fallback_options)
                            self.video_source = self.media_player.video
                            self.use_real_stream = True
                            logger.info(f"⚡ [SOFTWARE] Optimized software decode: {rtsp_url}")
                            logger.info(f"🔧 [PERF] Fallback options: buffer={fallback_options.get('buffer_size')}, threads={fallback_options.get('threads')}")
                        except Exception as e2:
                            logger.error(f"[ERRO] Erro ao conectar RTSP {rtsp_url}: {e2}")
                            self.use_real_stream = False
                            self.video_source = None
                            self.media_player = None
                    
                    # Inicializar recognition engine se habilitado
                    if self.enable_recognition:
                        asyncio.create_task(self._init_recognition())
                
                async def _init_recognition(self):
                    """Inicializar conexão com Recognition Worker"""
                    try:
                        logger.info(f"🔌 [WEBRTC] Iniciando conexão com Recognition Worker para câmera {self.camera_id}")
                        import socketio
                        self._recognition_client = socketio.AsyncClient()
                        self._recognition_connected = False
                        
                        @self._recognition_client.event
                        async def connect():
                            logger.info(f"✅ [WEBRTC] WebRTC conectado ao Recognition Worker - câmera {self.camera_id}")
                            self._recognition_connected = True
                        
                        @self._recognition_client.event
                        async def disconnect():
                            logger.warning(f"🔌 [WEBRTC] WebRTC desconectado do Recognition Worker - câmera {self.camera_id}")
                            self._recognition_connected = False
                        
                        @self._recognition_client.event
                        async def recognition_result(data):
                            """Receber resultado do Recognition Worker"""
                            try:
                                logger.info(f"📥 [WEBRTC] Resultado recebido para câmera {self.camera_id}")
                                logger.info(f"📥 [WEBRTC] Data keys: {list(data.keys()) if data else 'None'}")
                                
                                self._last_recognition_results = data
                                faces_count = len(data.get('recognitions', []))
                                logger.info(f"🎯 [WEBRTC] Câmera {self.camera_id}: {faces_count} faces reconhecidas")
                                
                                if faces_count > 0:
                                    for i, recognition in enumerate(data.get('recognitions', [])):
                                        person_name = recognition.get('person_name', 'Desconhecido')
                                        confidence = recognition.get('confidence', 0)
                                        bbox = recognition.get('bbox', [])
                                        logger.info(f"   🎯 Face {i+1}: {person_name} (conf: {confidence:.2f}, bbox: {bbox})")
                                else:
                                    logger.info(f"   📭 Nenhuma face reconhecida")
                                    
                            except Exception as e:
                                logger.error(f"❌ [WEBRTC] Erro ao processar resultado: {e}")
                                import traceback
                                logger.error(f"❌ [WEBRTC] Traceback: {traceback.format_exc()}")
                        
                        @self._recognition_client.event
                        async def error(data):
                            """Receber erro do Recognition Worker"""
                            logger.error(f"❌ [WEBRTC] Erro do Recognition Worker para câmera {self.camera_id}: {data}")
                        
                        # Conectar ao Recognition Worker
                        recognition_url = "http://127.0.0.1:17235"
                        logger.info(f"🔌 [WEBRTC] Conectando ao Recognition Worker: {recognition_url}")
                        await self._recognition_client.connect(recognition_url)
                        logger.info(f"✅ [WEBRTC] Conexão estabelecida com Recognition Worker")
                        
                    except Exception as e:
                        logger.error(f"❌ [WEBRTC] Falha ao conectar com Recognition Worker: {e}")
                        import traceback
                        logger.error(f"❌ [WEBRTC] Traceback: {traceback.format_exc()}")
                        self.enable_recognition = False
                
                def _apply_recognition_overlay(self, frame_bgr: np.ndarray) -> np.ndarray:
                    """Aplicar overlay de reconhecimento facial no frame"""
                    try:
                        if not self.enable_recognition:
                            logger.debug(f"🚫 Reconhecimento desabilitado para câmera {self.camera_id}")
                            return frame_bgr
                        
                        if not hasattr(self, '_recognition_connected') or not self._recognition_connected:
                            logger.debug(f"🚫 Recognition Worker não conectado para câmera {self.camera_id}")
                            return frame_bgr
                        
                        import time
                        current_time = time.time()
                        
                        # Processar reconhecimento apenas no intervalo configurado
                        time_since_last = current_time - self._last_recognition_time
                        
                        if time_since_last >= self._recognition_interval:
                            self._last_recognition_time = current_time
                            logger.info(f"⏰ Intervalo atingido para câmera {self.camera_id} - iniciando reconhecimento")
                            
                            # Executar reconhecimento em background (não bloqueante)
                            try:
                                # Criar task para reconhecimento assíncrono
                                if hasattr(self, '_current_recognition_task'):
                                    # Se há um task em andamento, cancelar
                                    if not self._current_recognition_task.done():
                                        self._current_recognition_task.cancel()
                                
                                logger.info(f"🚀 Criando task de reconhecimento para câmera {self.camera_id}")
                                self._current_recognition_task = asyncio.create_task(
                                    self._process_recognition_async(frame_bgr.copy())
                                )
                                logger.info(f"✅ Task de reconhecimento criado para câmera {self.camera_id}")
                            except Exception as e:
                                logger.error(f"[ERRO] Erro ao criar task de reconhecimento: {e}")
                        
                        # Aplicar overlay baseado nos últimos resultados de reconhecimento
                        if self._last_recognition_results:
                            # Usar resultados reais de reconhecimento
                            frame_with_overlay = self._draw_recognition_overlay(frame_bgr, self._last_recognition_results)
                            self._last_frame_with_overlay = frame_with_overlay
                            return frame_with_overlay
                        else:
                            # Aplicar overlay simples quando não há resultados ainda
                            frame_with_overlay = self._draw_simple_overlay(frame_bgr)
                            self._last_frame_with_overlay = frame_with_overlay
                            return frame_with_overlay
                            
                    except Exception as e:
                        logger.error(f"[ERRO] Erro no overlay de reconhecimento: {e}")
                        return frame_bgr
                
                async def _process_recognition_async(self, frame_bgr: np.ndarray):
                    """Enviar frame para Recognition Worker e aguardar resultado"""
                    try:
                        logger.info(f"📤 [WEBRTC] _process_recognition_async iniciado para câmera {self.camera_id}")
                        logger.info(f"📤 [WEBRTC] Frame shape: {frame_bgr.shape}")
                        logger.info(f"📤 [WEBRTC] Recognition connected: {self._recognition_connected}")
                        logger.info(f"📤 [WEBRTC] Recognition client exists: {hasattr(self, '_recognition_client')}")
                        
                        if not self._recognition_connected or not hasattr(self, '_recognition_client'):
                            logger.warning(f"⚠️ [WEBRTC] Recognition Worker não conectado para câmera {self.camera_id}, pulando frame")
                            return
                        
                        # Converter frame para base64 para envio via Socket.IO
                        import cv2
                        import base64
                        
                        logger.info(f"📤 [WEBRTC] Redimensionando e codificando frame...")
                        # Redimensionar frame para otimizar envio (opcional)
                        frame_resized = cv2.resize(frame_bgr, (640, 480))
                        
                        # Codificar frame em JPEG
                        _, buffer = cv2.imencode('.jpg', frame_resized, [cv2.IMWRITE_JPEG_QUALITY, 80])
                        frame_b64 = base64.b64encode(buffer).decode('utf-8')
                        
                        logger.info(f"📤 [WEBRTC] Frame codificado - tamanho: {len(frame_b64)} bytes")
                        
                        # Preparar dados para envio
                        frame_data = {
                            'camera_id': self.camera_id,
                            'frame_data': frame_b64,
                            'timestamp': datetime.now().isoformat()
                        }
                        
                        logger.info(f"📤 [WEBRTC] Enviando frame via Socket.IO...")
                        logger.info(f"📤 [WEBRTC] Camera ID: {self.camera_id}")
                        logger.info(f"📤 [WEBRTC] Timestamp: {frame_data['timestamp']}")
                        
                        # Enviar frame para Recognition Worker
                        await self._recognition_client.emit('process_frame', frame_data)
                        logger.info(f"✅ [WEBRTC] Frame enviado com sucesso para Recognition Worker - câmera {self.camera_id} ({frame_resized.shape})")
                        
                    except Exception as e:
                        logger.error(f"❌ [WEBRTC] Erro ao enviar frame para Recognition Worker: {e}")
                        import traceback
                        logger.error(f"❌ [WEBRTC] Traceback: {traceback.format_exc()}")
                        self._last_recognition_results = None
                
                def _draw_recognition_overlay(self, frame_bgr: np.ndarray, results) -> np.ndarray:
                    """Desenhar bbox, nomes e informações no frame"""
                    import cv2
                    
                    frame_overlay = frame_bgr.copy()
                    
                    try:
                        # Aguardar resultado se for uma corrotina
                        if asyncio.iscoroutine(results):
                            # Criar uma versão simplificada síncrona para o overlay
                            return self._draw_simple_overlay(frame_overlay)
                        
                        if results and 'recognitions' in results:
                            for face_data in results['recognitions']:
                                # Extrair informações da face
                                bbox = face_data.get('bbox', [])
                                person_name = face_data.get('person_name', 'Desconhecido')
                                confidence = face_data.get('confidence', 0.0)
                                
                                if len(bbox) == 4:
                                    x1, y1, x2, y2 = map(int, bbox)
                                    
                                    # Cor baseada no reconhecimento
                                    if person_name != 'Desconhecido':
                                        color = (0, 255, 0)  # Verde para conhecido
                                        label = f"{person_name} ({confidence:.2f})"
                                    else:
                                        color = (0, 0, 255)  # Vermelho para desconhecido
                                        label = "Desconhecido"
                                    
                                    # Desenhar bbox
                                    cv2.rectangle(frame_overlay, (x1, y1), (x2, y2), color, 2)
                                    
                                    # Desenhar label com fundo
                                    label_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)[0]
                                    cv2.rectangle(frame_overlay, (x1, y1 - label_size[1] - 10), 
                                                (x1 + label_size[0], y1), color, -1)
                                    cv2.putText(frame_overlay, label, (x1, y1 - 5), 
                                              cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                    
                    except Exception as e:
                        logger.error(f"[ERRO] Erro ao desenhar overlay: {e}")
                    
                    return frame_overlay
                
                def _draw_simple_overlay(self, frame_bgr: np.ndarray) -> np.ndarray:
                    """Desenhar overlay simples quando reconhecimento está ativo"""
                    import cv2
                    
                    # Adicionar indicador de que o reconhecimento está ativo
                    cv2.putText(frame_bgr, "Face Recognition: ON", (10, 30), 
                              cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                    cv2.circle(frame_bgr, (20, 60), 8, (0, 255, 0), -1)  # Indicador verde
                    
                    # Adicionar informações de debug
                    cv2.putText(frame_bgr, f"Camera: {self.camera_id}", (10, 100), 
                              cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                    
                    connection_status = "CONNECTED" if getattr(self, '_recognition_connected', False) else "DISCONNECTED"
                    status_color = (0, 255, 0) if getattr(self, '_recognition_connected', False) else (0, 0, 255)
                    cv2.putText(frame_bgr, f"Recognition Worker: {connection_status}", (10, 120), 
                              cv2.FONT_HERSHEY_SIMPLEX, 0.5, status_color, 1)
                    
                    return frame_bgr
                    
                async def recv(self):
                    if self.use_real_stream and self.video_source:
                        try:
                            # Receber frame do stream real
                            frame = await self.video_source.recv()
                            
                            # Otimização frame processing - reduzir latência e overhead
                            if self.enable_recognition:
                                current_time = time.time()
                                
                                # Aplicar overlay apenas se há resultados recentes (cache inteligente)
                                if (self._last_recognition_results and 
                                    (current_time - self._last_recognition_time) < 1.5):  # Cache por 1.5s para performance
                                    
                                    # Cache frame overlay para evitar reprocessamento desnecessário
                                    cache_key = f"{self._pts % 30}"  # Cache rotativo a cada 30 frames
                                    
                                    if not hasattr(self, '_overlay_cache'):
                                        self._overlay_cache = {}
                                    
                                    if cache_key not in self._overlay_cache:
                                        # Processar novo overlay apenas quando necessário
                                        frame_bgr = frame.to_ndarray(format='bgr24')
                                        frame_bgr_with_overlay = self._apply_recognition_overlay(frame_bgr)
                                        self._overlay_cache[cache_key] = frame_bgr_with_overlay
                                        frame = av.VideoFrame.from_ndarray(frame_bgr_with_overlay, format='bgr24')
                                    else:
                                        # Reutilizar overlay cache para máxima performance
                                        frame = av.VideoFrame.from_ndarray(self._overlay_cache[cache_key], format='bgr24')
                                    
                                    # Limpar cache antigo para economizar memória
                                    if len(self._overlay_cache) > 10:
                                        oldest_key = min(self._overlay_cache.keys())
                                        del self._overlay_cache[oldest_key]
                                
                                # Timing otimizado para 30 FPS constante
                                frame.pts = self._pts
                                frame.time_base = Fraction(1, 30)
                                self._pts += 1
                            else:
                                # Sem reconhecimento - timing direto para máxima performance
                                frame.pts = self._pts
                                frame.time_base = Fraction(1, 30)
                                self._pts += 1
                            
                            return frame
                            
                        except Exception as e:
                            logger.error(f"[ERRO] Erro no stream real: {e}")
                            # Fallback para padrão de teste
                            self.use_real_stream = False
                    
                    # Padrão de teste otimizado (fallback)
                    await asyncio.sleep(1/20)  # 20 FPS para melhor performance
                    
                    # Cache do frame de teste para evitar regeneração constante
                    if not hasattr(self, '_test_frame_cache'):
                        frame_data = np.zeros((self.height, self.width, 3), dtype=np.uint8)
                        
                        # Padrão de teste otimizado - menos operações custosas
                        w_third = self.width // 3
                        frame_data[:, :w_third, 0] = np.linspace(0, 255, w_third, dtype=np.uint8)
                        frame_data[:, w_third:2*w_third, 1] = np.linspace(0, 255, w_third, dtype=np.uint8)
                        frame_data[:, 2*w_third:, 2] = np.linspace(0, 255, self.width - 2*w_third, dtype=np.uint8)
                        
                        # Adicionar texto de status
                        try:
                            import cv2
                            cv2.putText(frame_data, "NO STREAM - TEST PATTERN", (10, 30), 
                                      cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
                            cv2.putText(frame_data, f"Camera: {self.camera_id}", (10, 70), 
                                      cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
                        except:
                            pass  # Se OpenCV não disponível, continuar sem texto
                        
                        self._test_frame_cache = frame_data
                    else:
                        frame_data = self._test_frame_cache.copy()
                    
                    # Aplicar overlay de reconhecimento se habilitado no fallback
                    if self.enable_recognition:
                        frame_data = self._draw_simple_overlay(frame_data)
                    
                    # Otimização: usar BGR24 para compatibilidade e performance
                    frame = av.VideoFrame.from_ndarray(frame_data, format='bgr24')
                    frame.pts = self._pts
                    frame.time_base = Fraction(1, 20)  # Matching the sleep above
                    self._pts += 1
                    
                    # Garbage collection optimization - clean every 300 frames (15 seconds at 20 FPS)
                    if self._pts % 300 == 0:
                        gc.collect()
                    
                    return frame
                
                def cleanup(self):
                    """Limpar recursos"""
                    try:
                        if self.media_player:
                            # MediaPlayer no aiortc não tem método stop()
                            if hasattr(self.media_player, 'close'):
                                self.media_player.close()
                            self.media_player = None
                    except Exception as e:
                        logger.warning(f"Erro ao limpar SmartVideoTrack MediaPlayer: {e}")
                    
                    # Limpar caches para economizar memória
                    try:
                        if hasattr(self, '_overlay_cache'):
                            self._overlay_cache.clear()
                        if hasattr(self, '_test_frame_cache'):
                            del self._test_frame_cache
                    except Exception as e:
                        logger.warning(f"Erro ao limpar caches: {e}")
                    
                    # Desconectar do Recognition Worker
                    if hasattr(self, '_recognition_client'):
                        try:
                            asyncio.create_task(self._recognition_client.disconnect())
                        except Exception as e:
                            logger.warning(f"Erro ao desconectar Recognition Worker: {e}")
            
            # Verificar se reconhecimento facial está habilitado via parâmetro
            import os  # Import local para garantir disponibilidade
            enable_recognition_env = os.environ.get('ENABLE_RECOGNITION_BY_DEFAULT', 'true').lower() == 'true'
            enable_recognition_server = server.get_camera_recognition_setting(camera_id) if server else enable_recognition_env
            enable_recognition = enable_recognition_server or enable_recognition_env  # Forçar por ambiente se servidor não definir
            
            logger.info(f"🔧 DEBUG Recognition settings para {camera_id}:")
            logger.info(f"   - ENABLE_RECOGNITION_BY_DEFAULT: {enable_recognition_env}")
            logger.info(f"   - Server setting: {enable_recognition_server}")
            logger.info(f"   - Final enable_recognition: {enable_recognition}")
            
            # Usar GStreamer bridge simplificado
            video_track = await simple_gstreamer_bridge.create_track(
                camera_id=camera_id, 
                rtsp_url=rtsp_url, 
                enable_recognition=enable_recognition
            )
            
            if video_track:
                self.pc.addTrack(video_track)
                logger.info(f"✅ [GSTREAMER] Pipeline conectado ao WebRTC para câmera {camera_id}")
            else:
                logger.error(f"❌ [GSTREAMER] Falha ao criar pipeline para câmera {camera_id}")
                # Fallback para SmartVideoTrack se necessário
                video_track = SmartVideoTrack(rtsp_url, enable_recognition=enable_recognition, camera_id=camera_id)
                self.pc.addTrack(video_track)
            
            # Otimizar codec após adicionar track
            self.optimize_video_codec(self.pc)
            
            logger.info(f"[OK] SmartVideoTrack configurado para câmera {camera_id} - Recognition: {enable_recognition}")
                
        except Exception as e:
            logger.error(f"[ERRO] Erro ao configurar stream: {e}")
            import traceback
            logger.error(f"[ERRO] Traceback: {traceback.format_exc()}")
            raise
    
    async def send_ice_candidate(self, candidate):
        """Envia ICE candidate para o cliente"""
        try:
            message = {
                "type": "ice-candidate",
                "candidate": {
                    "candidate": candidate.candidate,
                    "sdpMLineIndex": candidate.sdpMLineIndex,
                    "sdpMid": candidate.sdpMid
                }
            }
            await self.websocket.send_text(json.dumps(message))
            logger.info(f"[INFO] ICE candidate enviado: {candidate.candidate}")
        except Exception as e:
            logger.error(f"[ERRO] Erro ao enviar ICE candidate: {e}")
        
    async def cleanup(self):
        """Limpa recursos da conexão"""
        try:
            # Limpar GStreamer bridge
            await simple_gstreamer_bridge.stop_track(self.connection_id)
        except Exception as e:
            logger.warning(f"Erro ao limpar GStreamer bridge: {e}")
            
        try:
            if self.media_player:
                # MediaPlayer no aiortc não tem método stop(), usar close() se disponível
                if hasattr(self.media_player, 'close'):
                    self.media_player.close()
                elif hasattr(self.media_player, '_close'):
                    await self.media_player._close()
                self.media_player = None
        except Exception as e:
            logger.warning(f"Erro ao limpar MediaPlayer: {e}")
        
        try:
            if self.pc:
                await self.pc.close()
                self.pc = None
        except Exception as e:
            logger.warning(f"Erro ao limpar RTCPeerConnection: {e}")

class JanusIntegration:
    """Integração opcional com Janus Gateway"""
    
    def __init__(self, janus_http_url: str = "http://localhost:8088/janus"):
        self.janus_http_url = janus_http_url
        self.janus_session_id = None
        self.streaming_handle_id = None
        self.is_available = False
        self.registered_streams: Dict[str, int] = {}
        self.next_stream_id = 1
        self.base_rtp_port = 5000
        
    async def check_availability(self) -> bool:
        """Verifica se Janus Gateway está disponível"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.janus_http_url + "/info", timeout=3) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        logger.info(f"Janus Gateway disponível: {data.get('version_string')}")
                        self.is_available = True
                        return True
        except Exception as e:
            logger.info(f"Janus Gateway não disponível: {e}")
            logger.info("Continuando sem Janus - usando WebRTC nativo")
        
        self.is_available = False
        return False
    
    async def initialize_session(self) -> bool:
        """Inicializa sessão Janus se disponível"""
        if not self.is_available:
            return False
            
        try:
            async with aiohttp.ClientSession() as session:
                # Criar sessão
                payload = {
                    "janus": "create",
                    "transaction": str(uuid.uuid4())
                }
                async with session.post(self.janus_http_url, json=payload) as resp:
                    result = await resp.json()
                    if result.get("janus") == "success":
                        self.janus_session_id = result["data"]["id"]
                        logger.info(f"Sessão Janus criada: {self.janus_session_id}")
                    else:
                        logger.warning(f"Erro ao criar sessão Janus: {result}")
                        return False
                
                # Attach ao plugin streaming
                attach_payload = {
                    "janus": "attach",
                    "plugin": "janus.plugin.streaming",
                    "transaction": str(uuid.uuid4())
                }
                url = f"{self.janus_http_url}/{self.janus_session_id}"
                async with session.post(url, json=attach_payload) as resp:
                    result = await resp.json()
                    if result.get("janus") == "success":
                        self.streaming_handle_id = result["data"]["id"]
                        logger.info(f"Plugin streaming anexado: {self.streaming_handle_id}")
                        return True
                    else:
                        logger.warning(f"Erro ao anexar plugin: {result}")
                        return False
                        
        except Exception as e:
            logger.warning(f"Erro ao inicializar Janus: {e}")
            return False
    
    async def register_camera_stream(self, camera_id: str, camera_name: str) -> Optional[int]:
        """Registra uma stream de câmera no Janus"""
        if not self.is_available or not self.janus_session_id:
            return None
            
        try:
            video_port = self.base_rtp_port + (self.next_stream_id * 2)
            
            stream_data = {
                "request": "create",
                "type": "rtp",
                "id": self.next_stream_id,
                "name": camera_name,
                "description": f"Camera {camera_id}",
                "audio": False,
                "video": True,
                "videoport": video_port,
                "videopt": 96,
                "videortpmap": "H264/90000",
                "videofmtp": "profile-level-id=42e01f;packetization-mode=1"
            }
            
            async with aiohttp.ClientSession() as session:
                payload = {
                    "janus": "message",
                    "body": stream_data,
                    "transaction": str(uuid.uuid4())
                }
                
                url = f"{self.janus_http_url}/{self.janus_session_id}/{self.streaming_handle_id}"
                async with session.post(url, json=payload) as resp:
                    result = await resp.json()
                    
                    if result.get("janus") == "ack":
                        self.registered_streams[camera_id] = video_port
                        self.next_stream_id += 1
                        logger.info(f"Stream Janus registrada: {camera_id} -> porta {video_port}")
                        return video_port
                    else:
                        logger.warning(f"Erro ao registrar stream no Janus: {result}")
                        return None
                        
        except Exception as e:
            logger.warning(f"Erro ao registrar stream: {e}")
            return None
    
    def get_stream_port(self, camera_id: str) -> Optional[int]:
        """Retorna a porta RTP para uma câmera"""
        return self.registered_streams.get(camera_id)

class VMS_WebRTCServerNative:
    """Servidor VMS WebRTC usando GStreamer nativo"""
    
    def __init__(self, port: int = 17236):
        self.port = port
        self.app = FastAPI(title="VMS WebRTC Server (Native with Janus)", version="1.0.0")
        self.connections: Dict[str, WebRTCConnection] = {}
        self.active_cameras: Dict[str, dict] = {}
        # self.media_tester = VMSMediaTester()  # Não usado na implementação aiortc
        self.event_loop = None  # Will be set when server starts
        
        # Integração Janus (opcional)
        self.janus = JanusIntegration()
        self.janus_mode = False  # Será definido durante inicialização
        
        # Socket.IO server para comunicação com Camera Worker
        import socketio
        self.sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins="*")
        self.sio_app = None
        
        # Controle de reconhecimento facial por câmera
        self.camera_recognition_settings: Dict[str, bool] = {}
        # Por padrão, habilitar reconhecimento facial em todas as câmeras
        try:
            env_value = os.environ.get('ENABLE_RECOGNITION_BY_DEFAULT', 'true')
            # Remove whitespace that might cause parsing issues
            env_value = env_value.strip()
            logger.info(f"[CONFIG] ENABLE_RECOGNITION_BY_DEFAULT env var: '{env_value}'")
            enable_recognition_by_default = env_value.lower() == 'true'
            self.recognition_enabled_by_default = enable_recognition_by_default
            logger.info(f"[CONFIG] Reconhecimento facial habilitado por padrão: {enable_recognition_by_default}")
                
        except Exception as e:
            logger.error(f"[CONFIG] Erro ao configurar reconhecimento: {e}")
            # Fallback se houver qualquer problema
            self.recognition_enabled_by_default = True
            logger.info(f"[CONFIG] Usando fallback: reconhecimento habilitado = True")
        
        # Configurar CORS
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],  # Em produção, especificar origens específicas
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
        # GStreamer não é mais necessário na implementação aiortc
        # if not Gst.is_initialized():
        #     Gst.init(None)
            
        # Verificar codecs disponíveis
        # self.available_codecs = self.media_tester.check_available_codecs()  # Não usado na implementação aiortc
        self.available_codecs = ['H264']  # Codecs suportados por aiortc
        logger.info(f"[INFO] Codecs disponíveis: {self.available_codecs}")
        
        # Configurar Socket.IO events
        self.setup_socketio_events()
        
        # Carregar câmeras cadastradas no sistema
        self.load_cameras_from_api()
        
        self.setup_routes()
    
    def setup_socketio_events(self):
        """Configurar eventos Socket.IO para comunicação com Camera Worker"""
        
        @self.sio.event
        async def connect(sid, environ):
            logger.info(f"🔌 [SOCKETIO] Camera Worker conectado: {sid}")
        
        @self.sio.event
        async def disconnect(sid):
            logger.info(f"🔌 [SOCKETIO] Camera Worker desconectado: {sid}")
        
        @self.sio.event
        async def processed_frame(sid, data):
            """Receber frame processado do Camera Worker"""
            try:
                camera_id = data.get('camera_id')
                frame_data = data.get('frame_data')
                
                if camera_id and frame_data:
                    # Repassar frame para o Camera Worker bridge
                    from app.webrtc_worker.camera_worker_bridge import camera_worker_bridge
                    
                    # Simular recebimento do frame no bridge
                    if camera_id in camera_worker_bridge.active_tracks:
                        track = camera_worker_bridge.active_tracks[camera_id]
                        
                        # Decodificar frame
                        import base64
                        frame_bytes = base64.b64decode(frame_data)
                        nparr = np.frombuffer(frame_bytes, np.uint8)
                        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                        
                        if frame is not None:
                            # Converter BGR para RGB
                            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                            
                            async with track._frame_lock:
                                track._current_frame = frame_rgb
                                track._frame_ready.set()
                                track._frame_count += 1
                            
                            track._update_fps_counter()
                            
                            logger.debug(f"📥 [SOCKETIO] Frame recebido para câmera {camera_id}")
                
            except Exception as e:
                logger.error(f"❌ [SOCKETIO] Erro ao processar frame: {e}")
        
        @self.sio.event
        async def stream_available(sid, data):
            """Camera Worker confirmou que stream está disponível"""
            try:
                camera_id = data.get('camera_id')
                status = data.get('status')
                logger.info(f"📹 [SOCKETIO] Stream da câmera {camera_id} disponível: {status}")
            except Exception as e:
                logger.error(f"❌ [SOCKETIO] Erro ao processar stream_available: {e}")
    
    def get_camera_recognition_setting(self, camera_id: str) -> bool:
        """Obter configuração de reconhecimento facial para uma câmera"""
        default_value = getattr(self, 'recognition_enabled_by_default', True)
        return self.camera_recognition_settings.get(camera_id, default_value)
    
    def set_camera_recognition_setting(self, camera_id: str, enabled: bool):
        """Definir configuração de reconhecimento facial para uma câmera"""
        self.camera_recognition_settings[camera_id] = enabled
        logger.info(f"[CONFIG] Reconhecimento facial para câmera {camera_id}: {'HABILITADO' if enabled else 'DESABILITADO'}")
    
    def load_cameras_from_api(self):
        """Carrega as câmeras cadastradas no sistema via API"""
        try:
            # URL da API para obter câmeras ativas
            api_url = os.environ.get('API_URL', 'http://127.0.0.1:17234')
            cameras_endpoint = f"{api_url}/api/v1/cameras/active"
            
            logger.info(f"[INFO] Carregando câmeras da API: {cameras_endpoint}")
            print(f"[DIAGNÓSTICO] Carregando câmeras da API: {cameras_endpoint}", flush=True)
            
            # Fazer requisição para a API
            response = requests.get(cameras_endpoint, timeout=10)
            
            if response.status_code == 200:
                cameras_data = response.json()
                logger.info(f"[OK] API retornou {len(cameras_data)} câmeras")
                print(f"[OK] API retornou {len(cameras_data)} câmeras", flush=True)
                
                # Limpar câmeras existentes
                self.active_cameras.clear()
                
                # Processar cada câmera
                for camera in cameras_data:
                    camera_id = camera.get('id') or camera.get('camera_id')
                    camera_name = camera.get('name', f'Camera {camera_id}')
                    
                    # Construir URL baseado no tipo de câmera
                    rtsp_url = None
                    camera_type = camera.get('type', 'ip')
                    
                    # Primeiro, tentar usar URL direta se disponível
                    if camera.get('rtsp_url'):
                        rtsp_url = camera['rtsp_url']
                    elif camera.get('url'):
                        rtsp_url = camera['url']
                    elif camera_type != 'video_file':
                        # Construir URL RTSP a partir das informações da câmera (somente para IP cameras)
                        ip = camera.get('ip_address') or camera.get('ip')
                        port = camera.get('port', 554)
                        username = camera.get('username')
                        password = camera.get('password')
                        stream_path = camera.get('stream_path', '/Streaming/channels/101')
                        
                        if ip:
                            if username and password:
                                rtsp_url = f"rtsp://{username}:{password}@{ip}:{port}{stream_path}"
                            else:
                                rtsp_url = f"rtsp://{ip}:{port}{stream_path}"
                    
                    if rtsp_url and camera_id:
                        self.active_cameras[str(camera_id)] = {
                            'id': camera_id,
                            'name': camera_name,
                            'rtsp_url': rtsp_url,
                            'added_at': datetime.now().isoformat(),
                            'active_connections': 0,
                            'status': 'ready',
                            'type': camera_type,
                            'ip_address': camera.get('ip_address') or camera.get('ip'),
                            'port': camera.get('port', 554),
                            'username': camera.get('username'),
                            'password': camera.get('password')
                        }
                        logger.info(f"[OK] Câmera carregada: {camera_id} ({camera_name}) -> {rtsp_url}")
                        print(f"[OK] Câmera carregada: {camera_id} ({camera_name}) -> {rtsp_url}", flush=True)
                    else:
                        logger.warning(f"[ALERTA] Câmera {camera_id} ignorada - dados incompletos")
                        print(f"[ALERTA] Câmera {camera_id} ignorada - dados incompletos", flush=True)
                
                logger.info(f"[OK] Total de {len(self.active_cameras)} câmeras carregadas com sucesso")
                print(f"[OK] Total de {len(self.active_cameras)} câmeras carregadas com sucesso", flush=True)
                return True
                
            else:
                logger.warning(f"[ALERTA] API retornou status {response.status_code}: {response.text}")
                print(f"[ALERTA] API retornou status {response.status_code}: {response.text}", flush=True)
                
                # Fallback: usar câmera de teste se não conseguir carregar da API
                self._load_fallback_cameras()
                return False
                
        except requests.exceptions.RequestException as e:
            logger.warning(f"[ALERTA] Erro de conexão com API: {e}")
            print(f"[ALERTA] Erro de conexão com API: {e}", flush=True)
            
            # Fallback: usar câmera de teste se não conseguir conectar à API
            self._load_fallback_cameras()
            return False
            
        except Exception as e:
            logger.error(f"[ERRO] Erro ao carregar câmeras: {e}")
            print(f"[DIAGNÓSTICO] Erro ao carregar câmeras: {e}", flush=True)
            import traceback
            logger.error(f"[ERRO] Traceback: {traceback.format_exc()}")
            
            # Fallback: usar câmera de teste se houver erro
            self._load_fallback_cameras()
            return False
    
    def _load_fallback_cameras(self):
        """Carrega câmeras de fallback para teste quando a API não está disponível"""
        logger.info("[FALLBACK] Carregando câmeras de teste (API indisponível)")
        print("[FALLBACK] Carregando câmeras de teste (API indisponível)", flush=True)
        
        # Câmeras de teste/fallback
        fallback_cameras = {
            "cam1": {
                'id': 'cam1',
                'name': 'Câmera Principal (Teste)',
                'rtsp_url': 'rtsp://admin:Extreme@123@192.168.0.153:554/Streaming/channels/101',
                'added_at': datetime.now().isoformat(),
                'active_connections': 0,
                'status': 'ready',
                'type': 'ip_camera',
                'ip_address': '192.168.0.153',
                'port': 554,
                'username': 'admin',
                'password': 'Extreme@123'
            },
            "cam2": {
                'id': 'cam2',
                'name': 'Câmera Demo (BigBuckBunny)',
                'rtsp_url': 'rtsp://wowzaec2demo.streamlock.net/vod/mp4:BigBuckBunny_115k.mp4',
                'added_at': datetime.now().isoformat(),
                'active_connections': 0,
                'status': 'ready',
                'type': 'demo_stream',
                'ip_address': 'wowzaec2demo.streamlock.net',
                'port': 554
            },
            "videoplayback": {
                'id': 'videoplayback',
                'name': 'Video File Demo',
                'rtsp_url': '/mnt/d/Projetopresence/presence/videoplayback.mp4',
                'added_at': datetime.now().isoformat(),
                'active_connections': 0,
                'status': 'ready',
                'type': 'video_file',
                'file_path': '/mnt/d/Projetopresence/presence/videoplayback.mp4'
            }
        }
        
        self.active_cameras.update(fallback_cameras)
        logger.info(f"[FALLBACK] {len(fallback_cameras)} câmeras de teste carregadas")
        print(f"[FALLBACK] {len(fallback_cameras)} câmeras de teste carregadas", flush=True)
    
    async def update_cameras_periodically(self):
        """Atualiza periodicamente a lista de câmeras do banco de dados"""
        while True:
            try:
                # Aguardar 5 minutos entre cada atualização
                await asyncio.sleep(300)
                
                # Recarregar câmeras
                logger.info("[INFO] Atualizando lista de câmeras...")
                print("[INFO] Atualizando lista de câmeras...", flush=True)
                self.load_cameras_from_api()
                
            except asyncio.CancelledError:
                # Tarefa cancelada, sair do loop
                break
            except Exception as e:
                logger.error(f"[ERRO] Erro ao atualizar câmeras: {e}")
                print(f"[ERRO] Erro ao atualizar câmeras: {e}", flush=True)
                # Continuar o loop mesmo com erro
    
    def filter_ice_candidate(self, candidate: str) -> str:
        """
        Filter ICE candidates for LAN usage (Docker filters removed)
        """
        import re
        import os
        
        if not candidate:
            return None
            
        print(f"[FILTRANDO] FILTRO ICE: Analisando candidate: {candidate}", flush=True)
        
        # Bloquear candidatos TCP (usar apenas UDP para melhor performance)
        if 'tcp' in candidate.lower():
            print(f"[BLOQUEIO] FILTRO ICE: Bloqueando candidate TCP: {candidate}", flush=True)
            return None
        
        # Aplicar filtro de tipo ICE se configurado
        ice_filter = os.getenv('AIORTC_ICE_FILTER', 'all')
        if ice_filter == 'host':
            if 'typ host' not in candidate:
                print(f"[BLOQUEIO] FILTRO ICE: Bloqueando candidate não-host: {candidate}", flush=True)
                return None
        elif ice_filter == 'srflx':
            if 'typ srflx' not in candidate:
                print(f"[BLOQUEIO] FILTRO ICE: Bloqueando candidate não-srflx: {candidate}", flush=True)
                return None
        
        print(f"[OK] FILTRO ICE: Candidate APROVADO: {candidate}", flush=True)
        return candidate
        
    def setup_routes(self):
        """Configurar rotas da API"""
        
        @self.app.get("/")
        async def root():
            return {
                "message": "VMS WebRTC Server (Native GStreamer)",
                "version": "1.0.0",
                "active_connections": len(self.connections),
                "active_cameras": len(self.active_cameras),
                "available_codecs": self.available_codecs,
                "webrtc_backend": "aiortc"
            }
        
        @self.app.get("/health")
        async def health():
            mode = "janus_sfu" if self.janus_mode else "native_aiortc"
            backend = "janus_gateway" if self.janus_mode else "aiortc"
            
            return {
                "status": "healthy",
                "mode": mode,
                "webrtc_backend": backend,
                "connections": len(self.connections),
                "cameras": len(self.active_cameras),
                "available_codecs": self.available_codecs,
                "janus_available": self.janus.is_available,
                "janus_streams": len(self.janus.registered_streams) if self.janus_mode else 0,
                "message": "Janus SFU mode" if self.janus_mode else "Native aiortc mode"
            }
        
        @self.app.get("/cameras")
        async def list_cameras():
            """Lista câmeras disponíveis"""
            cameras_info = []
            for camera_id, info in self.active_cameras.items():
                cameras_info.append({
                    "id": info.get("id", camera_id),
                    "camera_id": camera_id,
                    "name": info.get("name", f"Camera {camera_id}"),
                    "rtsp_url": info["rtsp_url"],
                    "added_at": info["added_at"],
                    "active_connections": info["active_connections"],
                    "status": info.get("status", "unknown"),
                    "type": info.get("type", "ip_camera"),
                    "ip_address": info.get("ip_address"),
                    "port": info.get("port", 554)
                })
            
            return {
                "cameras": cameras_info,
                "count": len(self.active_cameras)
            }
        
        @self.app.get("/stats")
        async def get_stats():
            """Retorna estatísticas do servidor"""
            total_connections = len(self.connections)
            active_connections = len([c for c in self.connections.values() if c.state == "connected"])
            
            return {
                "server_status": "running",
                "total_connections": total_connections,
                "active_connections": active_connections,
                "total_cameras": len(self.active_cameras),
                "webrtc_backend": "aiortc",
                "available_codecs": self.available_codecs,
                "uptime": "active"  # TODO: implementar uptime real
            }
        
        @self.app.post("/cameras/{camera_id}")
        async def add_camera(camera_id: str, request: Request):
            """Adiciona uma nova câmera"""
            body = await request.json()
            rtsp_url = body.get('rtsp_url')
            
            if not rtsp_url:
                raise HTTPException(status_code=400, detail="rtsp_url required")
            
            if camera_id in self.active_cameras:
                raise HTTPException(status_code=409, detail="Camera already exists")
            
            # Testar conectividade RTSP
            # NOTA: VMSPipelineBuilder não está definido, então comentamos o teste de conectividade
            # test_builder = VMSPipelineBuilder(camera_id, rtsp_url)
            # if not test_builder.create_pipeline():
            #     raise HTTPException(status_code=400, detail="Failed to create pipeline for RTSP URL")
            
            # # Testar se pipeline pode iniciar
            # if not test_builder.start():
            #     test_builder.cleanup()
            #     raise HTTPException(status_code=400, detail="Failed to start pipeline - RTSP URL may be invalid")
            
            # # Parar pipeline de teste
            # test_builder.stop()
            # test_builder.cleanup()
            
            # Em vez disso, apenas verificar se a URL parece válida
            if not rtsp_url.startswith("rtsp://"):
                raise HTTPException(status_code=400, detail="Invalid RTSP URL format. Must start with rtsp://")
            
            self.active_cameras[camera_id] = {
                'rtsp_url': rtsp_url,
                'added_at': datetime.now().isoformat(),
                'active_connections': 0,
                'status': 'ready'
            }
            
            logger.info(f"[OK] Câmera adicionada: {camera_id} -> {rtsp_url}")
            return {"message": f"Camera {camera_id} added successfully"}
        
        @self.app.delete("/cameras/{camera_id}")
        async def remove_camera(camera_id: str):
            """Remove uma câmera"""
            if camera_id not in self.active_cameras:
                raise HTTPException(status_code=404, detail="Camera not found")
            
            # Desconectar todas as conexões desta câmera
            connections_to_remove = []
            for conn_id, connection in self.connections.items():
                if connection.camera_id == camera_id:
                    connection.cleanup()
                    connections_to_remove.append(conn_id)
            
            for conn_id in connections_to_remove:
                del self.connections[conn_id]
            
            del self.active_cameras[camera_id]
            logger.info(f"[REMOVIDO] Câmera removida: {camera_id}")
            return {"message": f"Camera {camera_id} removed successfully"}
        
        @self.app.post("/reload-cameras")
        async def reload_cameras():
            """Recarrega as câmeras do banco de dados"""
            success = self.load_cameras_from_api()
            if success:
                return {
                    "status": "success", 
                    "message": "Câmeras recarregadas com sucesso", 
                    "count": len(self.active_cameras),
                    "cameras": list(self.active_cameras.keys())
                }
            else:
                return {
                    "status": "warning",
                    "message": "Falha ao conectar à API, usando câmeras de fallback",
                    "count": len(self.active_cameras),
                    "cameras": list(self.active_cameras.keys())
                }
        
        @self.app.get("/cameras/{camera_id}/recognition")
        async def get_camera_recognition_status(camera_id: str):
            """Obter status do reconhecimento facial para uma câmera"""
            if camera_id not in self.active_cameras:
                raise HTTPException(status_code=404, detail="Camera not found")
            
            enabled = self.get_camera_recognition_setting(camera_id)
            return {
                "camera_id": camera_id,
                "recognition_enabled": enabled,
                "status": "enabled" if enabled else "disabled"
            }
        
        @self.app.post("/cameras/{camera_id}/recognition")
        async def set_camera_recognition_status(camera_id: str, request: Request):
            """Configurar reconhecimento facial para uma câmera"""
            if camera_id not in self.active_cameras:
                raise HTTPException(status_code=404, detail="Camera not found")
            
            try:
                body = await request.json()
                enabled = body.get("enabled", False)
                
                self.set_camera_recognition_setting(camera_id, enabled)
                
                return {
                    "camera_id": camera_id,
                    "recognition_enabled": enabled,
                    "message": f"Face recognition {'enabled' if enabled else 'disabled'} for camera {camera_id}",
                    "status": "success"
                }
            except Exception as e:
                logger.error(f"[ERRO] Erro ao configurar reconhecimento para câmera {camera_id}: {e}")
                raise HTTPException(status_code=400, detail=str(e))
        
        @self.app.get("/recognition/status")
        async def get_all_recognition_status():
            """Obter status de reconhecimento de todas as câmeras"""
            camera_statuses = {}
            for camera_id in self.active_cameras.keys():
                camera_statuses[camera_id] = {
                    "camera_id": camera_id,
                    "recognition_enabled": self.get_camera_recognition_setting(camera_id),
                    "camera_name": self.active_cameras[camera_id].get('name', f'Camera {camera_id}')
                }
            
            return {
                "cameras": camera_statuses,
                "total_cameras": len(self.active_cameras),
                "recognition_enabled_count": sum(1 for enabled in self.camera_recognition_settings.values() if enabled)
            }
        
        # === NOVOS ENDPOINTS PARA SISTEMA MELHORADO ===
        
        @self.app.get("/enhanced/media-types")
        async def get_supported_media_types():
            """Listar tipos de mídia suportados pelo sistema melhorado"""
            return enhanced_gstreamer_bridge.list_supported_formats()
        
        @self.app.post("/enhanced/cameras/{camera_id}")
        async def add_enhanced_camera(camera_id: str, request: Request):
            """Adicionar câmera com suporte melhorado (RTSP, MP4, webcam, imagem)"""
            try:
                body = await request.json()
                source = body.get('source')  # URL RTSP, caminho MP4, webcam ID, etc.
                enable_recognition = body.get('enable_recognition', True)
                enable_hwaccel = body.get('enable_hwaccel', True) 
                enable_recording = body.get('enable_recording', False)
                target_fps = body.get('target_fps', 30)
                
                if not source:
                    raise HTTPException(status_code=400, detail="source required")
                
                # Criar track no bridge melhorado
                track = await enhanced_gstreamer_bridge.create_track(
                    camera_id=camera_id,
                    source=source,
                    enable_recognition=enable_recognition,
                    enable_hwaccel=enable_hwaccel,
                    enable_recording=enable_recording,
                    target_fps=target_fps
                )
                
                if track:
                    # Adicionar também às câmeras ativas do servidor
                    self.active_cameras[camera_id] = {
                        'id': camera_id,
                        'name': body.get('name', f'Enhanced Camera {camera_id}'),
                        'rtsp_url': source,  # Para compatibilidade
                        'source': source,
                        'media_type': track.media_adapter.media_type,
                        'added_at': datetime.now().isoformat(),
                        'active_connections': 0,
                        'status': 'ready',
                        'enhanced': True,
                        'enable_recognition': enable_recognition,
                        'enable_hwaccel': enable_hwaccel,
                        'enable_recording': enable_recording,
                        'target_fps': target_fps
                    }
                    
                    logger.info(f"✅ Enhanced camera adicionada: {camera_id} -> {source} ({track.media_adapter.media_type})")
                    return {
                        "message": f"Enhanced camera {camera_id} added successfully",
                        "media_type": track.media_adapter.media_type,
                        "media_info": track.media_adapter.get_media_info()
                    }
                else:
                    raise HTTPException(status_code=400, detail="Failed to create enhanced track")
                    
            except Exception as e:
                logger.error(f"Erro ao adicionar enhanced camera: {e}")
                raise HTTPException(status_code=400, detail=str(e))
        
        @self.app.get("/enhanced/cameras/{camera_id}/info")
        async def get_enhanced_camera_info(camera_id: str):
            """Obter informações detalhadas de uma câmera melhorada"""
            track_info = enhanced_gstreamer_bridge.get_track_info(camera_id)
            
            if 'error' in track_info:
                raise HTTPException(status_code=404, detail="Enhanced camera not found")
            
            return track_info
        
        @self.app.get("/enhanced/cameras/{camera_id}/stats")
        async def get_enhanced_camera_stats(camera_id: str):
            """Obter estatísticas de uma câmera melhorada"""
            track = enhanced_gstreamer_bridge.get_track(camera_id)
            
            if not track:
                raise HTTPException(status_code=404, detail="Enhanced camera not found")
            
            return track.get_stats()
        
        @self.app.post("/enhanced/cameras/{camera_id}/restart")
        async def restart_enhanced_camera(camera_id: str):
            """Reiniciar uma câmera melhorada"""
            success = await enhanced_gstreamer_bridge.restart_track(camera_id)
            
            if success:
                return {"message": f"Enhanced camera {camera_id} restarted successfully"}
            else:
                raise HTTPException(status_code=400, detail="Failed to restart enhanced camera")
        
        @self.app.post("/enhanced/cameras/{camera_id}/recording/enable")
        async def enable_enhanced_recording(camera_id: str, request: Request):
            """Habilitar gravação para uma câmera melhorada"""
            try:
                body = await request.json()
                output_path = body.get('output_path')
                
                if not output_path:
                    raise HTTPException(status_code=400, detail="output_path required")
                
                success = await enhanced_gstreamer_bridge.enable_recording_for_track(camera_id, output_path)
                
                if success:
                    return {"message": f"Recording enabled for camera {camera_id}", "output_path": output_path}
                else:
                    raise HTTPException(status_code=404, detail="Camera not found")
                    
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))
        
        @self.app.post("/enhanced/cameras/{camera_id}/recording/disable")
        async def disable_enhanced_recording(camera_id: str):
            """Desabilitar gravação para uma câmera melhorada"""
            success = await enhanced_gstreamer_bridge.disable_recording_for_track(camera_id)
            
            if success:
                return {"message": f"Recording disabled for camera {camera_id}"}
            else:
                raise HTTPException(status_code=404, detail="Camera not found")
        
        @self.app.get("/enhanced/stats")
        async def get_enhanced_stats():
            """Obter estatísticas do sistema melhorado"""
            return enhanced_gstreamer_bridge.get_stats()
        
        @self.app.delete("/enhanced/cameras/{camera_id}")
        async def remove_enhanced_camera(camera_id: str):
            """Remover uma câmera melhorada"""
            await enhanced_gstreamer_bridge.stop_track(camera_id)
            
            # Remover também das câmeras ativas
            if camera_id in self.active_cameras:
                del self.active_cameras[camera_id]
            
            return {"message": f"Enhanced camera {camera_id} removed successfully"}
        
        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            """Endpoint WebSocket para comunicação WebRTC"""
            await websocket.accept()
            
            connection_id = str(uuid.uuid4())
            connection = WebRTCConnection(connection_id, websocket)
            self.connections[connection_id] = connection
            
            logger.info(f"[NOVA CONEXAO] Nova conexão WebSocket: {connection_id}")
            
            try:
                await self.handle_websocket_messages(connection)
            except WebSocketDisconnect:
                logger.info(f"[DESCONECTADO] Conexão desconectada: {connection_id}")
            except Exception as e:
                logger.error(f"[ERRO] Erro na conexão {connection_id}: {e}")
            finally:
                connection.cleanup()
                if connection_id in self.connections:
                    del self.connections[connection_id]
                
                # Atualizar contador de conexões ativas da câmera
                if connection.camera_id and connection.camera_id in self.active_cameras:
                    self.active_cameras[connection.camera_id]['active_connections'] = max(0, 
                        self.active_cameras[connection.camera_id]['active_connections'] - 1)
        
        @self.app.websocket("/ws/{camera_id}")
        async def websocket_camera_endpoint(websocket: WebSocket, camera_id: str):
            """Endpoint WebSocket específico para uma câmera"""
            logger.info(f"[TENTATIVA] Tentativa de conexão WebSocket para câmera {camera_id}")
            await websocket.accept()
            logger.info(f"[OK] WebSocket aceito para câmera {camera_id}")
            
            connection_id = str(uuid.uuid4())
            connection = WebRTCConnection(connection_id, websocket)
            connection.camera_id = camera_id  # Definir camera_id na conexão
            self.connections[connection_id] = connection
            
            logger.info(f"[NOVA CONEXAO] Nova conexão WebSocket para câmera {camera_id}: {connection_id}")
            print(f"[NOVA CONEXAO] STDOUT: Nova conexão WebSocket para câmera {camera_id}: {connection_id}", flush=True)
            
            # Enviar mensagem de boas-vindas imediatamente
            await connection.websocket.send_text(json.dumps({
                "type": "connected",
                "message": f"Conectado à câmera {camera_id}",
                "connection_id": connection_id
            }))
            
            # Verificar se a câmera existe ou criar uma entrada temporária
            if camera_id not in self.active_cameras:
                # Criar entrada temporária para a câmera com uma URL RTSP real de teste
                # Usar a câmera local do usuário como padrão
                rtsp_url = "rtsp://admin:Extreme@123@192.168.0.153:554/Streaming/channels/101"
                
                self.active_cameras[camera_id] = {
                    'rtsp_url': rtsp_url,  # Usar RTSP real em vez de test pattern
                    'added_at': datetime.now().isoformat(),
                    'active_connections': 0,
                    'status': 'pending'
                }
                logger.info(f"[INFO] Câmera temporária criada com RTSP real: {camera_id} -> {rtsp_url}")
            
            # Incrementar contador de conexões ativas
            self.active_cameras[camera_id]['active_connections'] += 1
            
            try:
                print(f"[ANTES] ANTES de chamar handle_websocket_messages para {connection_id}", flush=True)
                logger.info(f"[ANTES] ANTES de chamar handle_websocket_messages para {connection_id}")
                await self.handle_websocket_messages(connection)
                print(f"[OK] handle_websocket_messages terminou para {connection_id}", flush=True)
            except WebSocketDisconnect:
                print(f"[DESCONECTADO] WebSocket desconectado: {connection_id}")
                logger.info(f"[DESCONECTADO] Conexão da câmera {camera_id} desconectada: {connection_id}")
            except Exception as e:
                print(f"[ERRO] EXCEÇÃO na conexão {connection_id}: {e}")
                logger.error(f"[ERRO] Erro na conexão da câmera {camera_id} ({connection_id}): {e}")
                import traceback
                traceback.print_exc()
            finally:
                await connection.cleanup()
                if connection_id in self.connections:
                    del self.connections[connection_id]
                
                # Atualizar contador de conexões ativas da câmera
                if camera_id in self.active_cameras:
                    self.active_cameras[camera_id]['active_connections'] = max(0, 
                        self.active_cameras[camera_id]['active_connections'] - 1)
        
        @self.app.get("/demo", response_class=HTMLResponse)
        async def demo_page():
            """Página de demonstração"""
            return await self.generate_demo_html()
        
        @self.app.get("/codecs")
        async def get_available_codecs():
            """Lista codecs disponíveis"""
            return {
                "available_codecs": self.available_codecs,
                "webrtc_backend": "aiortc"
            }
    
    async def handle_websocket_messages(self, connection: WebRTCConnection):
        """Processa mensagens WebSocket"""
        print(f"[INICIANDO] INICIANDO handler para {connection.connection_id}", flush=True)
        logger.info(f"[INICIANDO] INICIANDO handler para {connection.connection_id}")
        
        # Escrever no arquivo também para garantir que funciona
        with open(DEBUG_LOG_PATH, 'a') as f:
            f.write(f"[INICIANDO] HANDLER INICIADO: {connection.connection_id}\n")
            f.flush()
        
        try:
            print(f"[INICIANDO] Entrando no loop iter_text para {connection.connection_id}", flush=True)
            with open(DEBUG_LOG_PATH, 'a') as f:
                f.write(f"[INICIANDO] ENTRANDO NO LOOP: {connection.connection_id}\n")
                f.flush()
            
            async for message in connection.websocket.iter_text():
                print(f"[RECEBIDO] RAW message: {message}", flush=True)
                print(f"[RECEBIDO] DIAGNÓSTICO: Mensagem recebida do WebSocket: {message}", flush=True)
                with open(DEBUG_LOG_PATH, 'a') as f:
                    f.write(f"[RECEBIDO] RAW MESSAGE: {message}\n")
                    f.flush()
                
                try:
                    data = json.loads(message)
                    msg_type = data.get('type')
                    logger.info(f"[RECEBIDO] Mensagem recebida: {msg_type} de {connection.connection_id}")
                    print(f"[RECEBIDO] STDOUT: Mensagem recebida: {msg_type} de {connection.connection_id}", flush=True)
                    with open(DEBUG_LOG_PATH, 'a') as f:
                        f.write(f"[RECEBIDO] MSG TYPE: {msg_type} from {connection.connection_id}\n")
                        f.flush()
                    
                    if msg_type == 'request-offer':
                        print(f"[PROCESSANDO] Processando request-offer para {connection.connection_id}", flush=True)
                        with open(DEBUG_LOG_PATH, 'a') as f:
                            f.write(f"[PROCESSANDO] PROCESSANDO REQUEST-OFFER: {connection.connection_id}\n")
                            f.flush()
                        try:
                            await self.handle_request_offer(connection, data)
                            print(f"[OK] Request-offer processado para {connection.connection_id}", flush=True)
                            with open(DEBUG_LOG_PATH, 'a') as f:
                                f.write(f"[OK] REQUEST-OFFER OK: {connection.connection_id}\n")
                                f.flush()
                        except Exception as req_err:
                            print(f"[ERRO] ERRO no request-offer: {req_err}", flush=True)
                            with open(DEBUG_LOG_PATH, 'a') as f:
                                f.write(f"[ERRO] REQUEST-OFFER ERROR: {req_err}\n")
                            import traceback
                            traceback.print_exc()
                    elif msg_type == 'start-stream':
                        await self.handle_start_stream(connection, data)
                    elif msg_type == 'offer':
                        await self.handle_offer(connection, data)
                    elif msg_type == 'answer':
                        await self.handle_answer(connection, data)
                    elif msg_type == 'ice-candidate':
                        await self.handle_ice_candidate(connection, data)
                    elif msg_type == 'stop-stream':
                        await self.handle_stop_stream(connection)
                    else:
                        logger.warning(f"[ALERTA] Tipo de mensagem desconhecido: {msg_type}")
                        print(f"[ALERTA] Tipo de mensagem desconhecido: {msg_type}")
                        
                except json.JSONDecodeError as e:
                    logger.error(f"[ERRO] Erro ao decodificar mensagem JSON: {e}")
                    print(f"[ERRO] Erro JSON: {e}")
                except Exception as e:
                    logger.error(f"[ERRO] Erro ao processar mensagem: {e}")
                    print(f"[ERRO] Erro processar: {e}")
                    
        except Exception as e:
            logger.error(f"[ERRO] Erro no loop WebSocket: {e}")
            print(f"[ERRO] Erro no loop: {e}")
            raise
    
    async def handle_request_offer(self, connection: WebRTCConnection, data: dict):
        """Processa solicitação de offer usando aiortc"""
        camera_id = connection.camera_id
        logger.info(f"[PROCESSANDO] handle_request_offer chamado para câmera {camera_id}")
        
        if not camera_id:
            await self.send_error(connection, "No camera associated with connection")
            return
        
        try:
            # Criar peer connection com range UDP fixo
            if not connection.pc:
                await connection.create_peer_connection()
            
            # Configurar stream de mídia
            await connection.setup_media_stream(camera_id)
            
            # Criar offer
            offer = await connection.pc.createOffer()
            await connection.pc.setLocalDescription(offer)
            
            # Enviar offer para o cliente
            await self.send_message(connection, {
                'type': 'offer',
                'sdp': connection.pc.localDescription.sdp
            })
            
            connection.negotiation_state = "offer-pending"
            logger.info(f"[OK] Offer aiortc criado e enviado para câmera {camera_id}")
            
        except Exception as e:
            logger.error(f"[ERRO] Erro ao criar offer aiortc: {e}")
            await self.send_error(connection, f"Failed to create offer: {e}")
            print(f"[ERRO] DIAGNÓSTICO: Falha ao criar pipeline para {camera_id}", flush=True)
            with open(DEBUG_LOG_PATH, 'a') as f:
                f.write(f"[ERRO] FALHA CRIAR PIPELINE: {camera_id}\n")
                f.flush()
            await self.send_error(connection, "Failed to create pipeline")
            return
        
        print(f"[OK] DIAGNÓSTICO: aiortc offer criado com sucesso para {camera_id}", flush=True)
        
        # aiortc gerencia ICE candidates automaticamente
        # Não precisamos configurar manualmente como no GStreamer
        
        # Atualizar status da câmera
        if camera_id in self.active_cameras:
            self.active_cameras[camera_id]['status'] = 'streaming'
        
        connection.state = "offer-sent"
        print(f"[OK] DIAGNÓSTICO: WebRTC setup concluído para {camera_id}", flush=True)
    
    async def handle_answer(self, connection: WebRTCConnection, data: dict):
        """Processa resposta SDP usando aiortc"""
        if not connection.pc:
            logger.error(f"[ERRO] Não foi possível processar answer: connection.pc não existe")
            return
        
        try:
            answer_data = data.get('answer', {})
            sdp = answer_data.get('sdp')
            
            if not sdp:
                await self.send_error(connection, "Invalid answer: missing SDP")
                return
            
            # Criar RTCSessionDescription a partir do SDP
            from aiortc import RTCSessionDescription
            answer = RTCSessionDescription(sdp=sdp, type="answer")
            
            # Definir descrição remota
            await connection.pc.setRemoteDescription(answer)
            
            connection.negotiation_state = "stable"
            connection.offer_pending = False
            connection.state = "connected"
            
            logger.info(f"[OK] Answer aiortc processada para {connection.connection_id}")
            
        except Exception as e:
            logger.error(f"[ERRO] Erro ao processar answer: {e}")
            await self.send_error(connection, f"Failed to process answer: {e}")
    
    async def handle_ice_candidate(self, connection: WebRTCConnection, data: dict):
        """Processa candidato ICE usando aiortc"""
        if not connection.pc:
            logger.error(f"[ERRO] Não foi possível processar ICE candidate: connection.pc não existe")
            return
        
        try:
            candidate_data = data.get('candidate', {})
            candidate_str = candidate_data.get('candidate')
            sdp_mid = candidate_data.get('sdpMid')
            sdp_mline_index = candidate_data.get('sdpMLineIndex')
            
            logger.info(f"[OK] ICE CANDIDATO RECEBIDO DO CLIENTE: {candidate_str}")
            logger.info(f"[INFO] Detalhes do candidato: mLineIndex={sdp_mline_index}, mid={sdp_mid}")
            
            if not candidate_str:
                logger.error("[ERRO] Candidato ICE inválido: string vazia")
                return
            
            # Parse do candidato ICE string para obter componentes
            try:
                # Exemplo de candidate string: "candidate:1 1 UDP 2113667327 192.168.1.100 54400 typ host"
                parts = candidate_str.split()
                if len(parts) < 8 or not parts[0].startswith('candidate:'):
                    logger.error(f"[ERRO] Formato de candidato ICE inv\u00e1lido: {candidate_str}")
                    return
                
                foundation = parts[0].split(':')[1]
                component = int(parts[1])
                protocol = parts[2].lower()
                priority = int(parts[3])
                ip = parts[4]
                port = int(parts[5])
                typ_idx = parts.index('typ')
                candidate_type = parts[typ_idx + 1]
                
                # Criar RTCIceCandidate com componentes corretos
                from aiortc import RTCIceCandidate
                ice_candidate = RTCIceCandidate(
                    component=component,
                    foundation=foundation,
                    ip=ip,
                    port=port,
                    priority=priority,
                    protocol=protocol,
                    type=candidate_type,
                    sdpMid=sdp_mid,
                    sdpMLineIndex=sdp_mline_index
                )
                
            except (ValueError, IndexError) as parse_error:
                logger.error(f"[ERRO] Erro ao parsear candidato ICE: {parse_error}")
                logger.error(f"[ERRO] Candidate string: {candidate_str}")
                return
            
            # Adicionar candidato ao peer connection
            await connection.pc.addIceCandidate(ice_candidate)
            logger.info(f"[OK] ICE candidate adicionado com sucesso")
            
        except Exception as e:
            logger.error(f"[ERRO] Erro ao processar ICE candidate: {e}")
            import traceback
            logger.error(f"[ERRO] Traceback: {traceback.format_exc()}")
    
    async def handle_start_stream(self, connection: WebRTCConnection, data: dict):
        """Inicia stream para uma câmera usando aiortc"""
        camera_id = data.get('camera_id')
        
        if not camera_id or camera_id not in self.active_cameras:
            await self.send_error(connection, "Camera not found")
            return
        
        try:
            # Criar peer connection com range UDP fixo
            await connection.create_peer_connection()
            
            # Configurar stream de mídia
            await connection.setup_media_stream(camera_id)
            
            # Atualizar contador de conexões
            self.active_cameras[camera_id]['active_connections'] += 1
            self.active_cameras[camera_id]['status'] = 'streaming'
            connection.state = "ready"
            
            await self.send_message(connection, {
                'type': 'stream-started',
                'camera_id': camera_id
            })
            
            logger.info(f"[OK] Stream aiortc iniciado: {camera_id} para {connection.connection_id}")
            
        except Exception as e:
            logger.error(f"[ERRO] Erro ao iniciar stream: {e}")
            await self.send_error(connection, f"Failed to start stream: {e}")

    async def send_message(self, connection: WebRTCConnection, message: dict):
        """Envia mensagem via WebSocket"""
        try:
            print(f"[ENVIANDO] DIAGNÓSTICO: Enviando mensagem tipo '{message.get('type')}' para {connection.connection_id}", flush=True)
            with open(DEBUG_LOG_PATH, 'a') as f:
                f.write(f"[ENVIANDO] ENVIANDO MSG: {message.get('type')} para {connection.connection_id}\n")
                f.flush()
            await connection.websocket.send_text(json.dumps(message))
            print(f"[OK] DIAGNÓSTICO: Mensagem enviada com sucesso para {connection.connection_id}", flush=True)
        except Exception as e:
            logger.error(f"[ERRO] Erro ao enviar mensagem: {e}")
            print(f"[ERRO] DIAGNÓSTICO: Erro ao enviar mensagem para {connection.connection_id}: {e}", flush=True)
    
    async def send_error(self, connection: WebRTCConnection, error_message: str):
        """Envia mensagem de erro"""
        await self.send_message(connection, {
            'type': 'error',
            'message': error_message
        })
    
    async def generate_demo_html(self) -> str:
        """Gera página HTML de demonstração"""
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>VMS WebRTC Demo (Native GStreamer)</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .camera-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(400px, 1fr)); gap: 20px; }}
                .camera-item {{ border: 1px solid #ddd; padding: 15px; border-radius: 8px; }}
                .controls {{ margin-bottom: 20px; padding: 15px; background: #f5f5f5; border-radius: 5px; }}
                .status {{ background: #e8f5e8; padding: 10px; border-radius: 5px; margin-bottom: 15px; }}
                .codec-info {{ background: #f0f8ff; padding: 10px; border-radius: 5px; margin-bottom: 15px; }}
                video {{ width: 100%; max-width: 400px; height: auto; }}
                button {{ margin: 5px; padding: 8px 15px; }}
                input {{ margin: 5px; padding: 5px; width: 200px; }}
                .error {{ background: #ffe6e6; color: #cc0000; padding: 10px; border-radius: 5px; }}
                .success {{ background: #e6ffe6; color: #006600; padding: 10px; border-radius: 5px; }}
            </style>
        </head>
        <body>
            <h1>VMS WebRTC Demo</h1>
        </body>
        </html>
        """
        
        # === JANUS INTEGRATION ENDPOINTS ===
        
        @self.app.get("/janus/streams")
        async def list_janus_streams():
            """Lista streams registradas no Janus"""
            if not self.janus_mode:
                return {
                    "mode": "native_aiortc",
                    "message": "Janus not available - using native aiortc",
                    "streams": []
                }
            
            return {
                "mode": "janus_sfu",
                "streams": [
                    {
                        "camera_id": camera_id,
                        "rtp_port": port,
                        "janus_stream_id": self.janus.next_stream_id - len(self.janus.registered_streams) + i
                    }
                    for i, (camera_id, port) in enumerate(self.janus.registered_streams.items())
                ]
            }
        
        @self.app.get("/janus/info")
        async def janus_info():
            """Informações sobre integração Janus"""
            return {
                "janus_available": self.janus.is_available,
                "janus_mode": self.janus_mode,
                "janus_url": self.janus.janus_http_url,
                "registered_streams": len(self.janus.registered_streams),
                "next_stream_id": self.janus.next_stream_id,
                "base_rtp_port": self.janus.base_rtp_port,
                "session_id": self.janus.janus_session_id,
                "handle_id": self.janus.streaming_handle_id
            }
        
        @self.app.post("/janus/reinitialize")
        async def reinitialize_janus():
            """Reinicializa conexão com Janus Gateway"""
            try:
                # Verificar disponibilidade
                available = await self.janus.check_availability()
                if not available:
                    return {
                        "status": "failed",
                        "message": "Janus Gateway not available",
                        "janus_mode": False
                    }
                
                # Inicializar sessão
                initialized = await self.janus.initialize_session()
                if initialized:
                    self.janus_mode = True
                    
                    # Re-registrar câmeras existentes
                    for camera_id, camera_info in self.active_cameras.items():
                        camera_name = camera_info.get('name', f'Camera {camera_id}')
                        port = await self.janus.register_camera_stream(camera_id, camera_name)
                        if port:
                            logger.info(f"✅ Re-registrada no Janus: {camera_id} → porta {port}")
                    
                    return {
                        "status": "success",
                        "message": "Janus initialized successfully",
                        "janus_mode": True,
                        "registered_streams": len(self.janus.registered_streams)
                    }
                else:
                    return {
                        "status": "failed",
                        "message": "Failed to initialize Janus session",
                        "janus_mode": False
                    }
                    
            except Exception as e:
                logger.error(f"Erro ao reinicializar Janus: {e}")
                return {
                    "status": "error",
                    "message": str(e),
                    "janus_mode": False
                }
    
    async def start_server(self, host: str = "0.0.0.0", port: Optional[int] = None):
        """Inicia o servidor"""
        if port:
            self.port = port
            
        # Store event loop for aiortc callbacks
        self.event_loop = asyncio.get_running_loop()
        
        # Verificar e inicializar Janus Gateway (opcional)
        logger.info("Verificando disponibilidade do Janus Gateway...")
        janus_available = await self.janus.check_availability()
        
        if janus_available:
            logger.info("Janus Gateway encontrado - inicializando integração...")
            initialized = await self.janus.initialize_session()
            if initialized:
                self.janus_mode = True
                logger.info("Modo Janus SFU ativado")
            else:
                logger.warning("Falha na inicialização do Janus - usando modo nativo")
                self.janus_mode = False
        else:
            logger.info("Janus Gateway não disponível - usando modo WebRTC nativo")
            self.janus_mode = False
        
        # Carregar câmeras da API
        self.load_cameras_from_api()
        
        # Se Janus está ativo, registrar câmeras existentes
        if self.janus_mode:
            logger.info("Registrando câmeras no Janus Gateway...")
            for camera_id, camera_info in self.active_cameras.items():
                camera_name = camera_info.get('name', f'Camera {camera_id}')
                port = await self.janus.register_camera_stream(camera_id, camera_name)
                if port:
                    logger.info(f"Camera {camera_name} registrada no Janus - porta RTP {port}")
        
        # Log do modo final
        mode_msg = "Janus SFU" if self.janus_mode else "Native aiortc"
        logger.info(f"Servidor iniciando em modo: {mode_msg}")
        
        # Integrar Socket.IO com FastAPI
        import socketio
        self.sio_app = socketio.ASGIApp(self.sio, other_asgi_app=self.app)
        
        # Iniciar servidor HTTP
        import uvicorn
        config = uvicorn.Config(
            app=self.sio_app,  # Usar a aplicação integrada com Socket.IO
            host=host,
            port=self.port,
            log_level="info"
        )
        server = uvicorn.Server(config)
        await server.serve()
    
    def cleanup(self):
        """Limpeza de recursos"""
        logger.info("Limpando recursos do VMS WebRTC Server")
        
        # Limpar todas as conexões
        for connection in list(self.connections.values()):
            try:
                connection.cleanup()
            except Exception as e:
                logger.error(f"Erro ao limpar conexão: {e}")
        
        self.connections.clear()
    
    async def handle_start_stream(self, connection: WebRTCConnection, data: dict):
        """Inicia stream para uma câmera usando aiortc"""
        camera_id = data.get('camera_id')
        
        if not camera_id or camera_id not in self.active_cameras:
            await self.send_error(connection, "Camera not found")
            return
        
        try:
            # Criar peer connection com range UDP fixo
            await connection.create_peer_connection()
            
            # Configurar stream de mídia
            await connection.setup_media_stream(camera_id)
            
            # Atualizar contador de conexões
            self.active_cameras[camera_id]['active_connections'] += 1
            self.active_cameras[camera_id]['status'] = 'streaming'
            connection.state = "ready"
            
            await self.send_message(connection, {
                'type': 'stream-started',
                'camera_id': camera_id
            })
            
            logger.info(f"[OK] Stream aiortc iniciado: {camera_id} para {connection.connection_id}")
            
        except Exception as e:
            logger.error(f"[ERRO] Erro ao iniciar stream aiortc: {e}")
            await self.send_error(connection, f"Failed to start stream: {e}")
    
    def setup_webrtc_callbacks(self, connection: WebRTCConnection):
        """Configura callbacks WebRTC para uma conexão - MÉTODO ANTIGO (GStreamer)"""
        # Método não usado na implementação aiortc - callbacks são configurados em create_peer_connection()
        logger.info(f"[INFO] WebRTC callbacks configurados para conexão {connection.connection_id} (aiortc nativo)")
        # Método descontinuado - aiortc gerencia callbacks automaticamente
        return
    
    async def handle_ice_candidate(self, connection: WebRTCConnection, data: dict):
        """Processa candidato ICE usando aiortc"""
        if not connection.pc:
            logger.error(f"[ERRO] Não foi possível processar ICE candidate: connection.pc não existe")
            return
        
        try:
            # Verificar formato do candidato (pode estar em formatos diferentes)
            if 'candidate' in data and isinstance(data['candidate'], dict):
                # Formato completo enviado pelo browser
                candidate_data = data['candidate']
                candidate_str = candidate_data.get('candidate')
                sdp_mline_index = candidate_data.get('sdpMLineIndex', 0)
                sdp_mid = candidate_data.get('sdpMid')
            else:
                # Formato simplificado ou alternativo
                candidate_str = data.get('candidate')
                sdp_mline_index = data.get('sdpMLineIndex', 0)
                sdp_mid = data.get('sdpMid')
            
            if candidate_str:
                # Criar ICE candidate aiortc
                ice_candidate = RTCIceCandidate(
                    component=1,
                    foundation=candidate_str.split()[0] if candidate_str.split() else "1",
                    ip=candidate_str.split()[4] if len(candidate_str.split()) > 4 else "127.0.0.1",
                    port=int(candidate_str.split()[5]) if len(candidate_str.split()) > 5 else 9,
                    priority=int(candidate_str.split()[3]) if len(candidate_str.split()) > 3 else 1,
                    protocol=candidate_str.split()[2] if len(candidate_str.split()) > 2 else "udp",
                    type=candidate_str.split()[7] if len(candidate_str.split()) > 7 else "host",
                    sdpMid=sdp_mid,
                    sdpMLineIndex=sdp_mline_index
                )
                
                # Adicionar candidato à peer connection
                await connection.pc.addIceCandidate(ice_candidate)
                logger.debug(f"[OK] ICE candidate adicionado para {connection.connection_id}")
                
        except Exception as e:
            logger.error(f"[ERRO] Erro ao processar ICE candidate: {e}")
    
    def on_negotiation_needed(self, element):
        """Método legacy do GStreamer - não usado na implementação aiortc"""
        logger.info("[INFO] on_negotiation_needed chamado (método legacy - ignorado)")
        pass
    
    async def handle_answer(self, connection: WebRTCConnection, data: dict):
        """Processa candidato ICE usando aiortc"""
        if not connection.pc:
            logger.error(f"[ERRO] Não foi possível processar ICE candidate: connection.pc não existe")
            return
        
        try:
            # Verificar formato do candidato (pode estar em formatos diferentes)
            if 'candidate' in data and isinstance(data['candidate'], dict):
                # Formato completo enviado pelo browser
                candidate_data = data['candidate']
                candidate_str = candidate_data.get('candidate')
                sdp_mline_index = candidate_data.get('sdpMLineIndex', 0)
                sdp_mid = candidate_data.get('sdpMid')
            else:
                # Formato simplificado ou alternativo
                candidate_str = data.get('candidate')
                sdp_mline_index = data.get('sdpMLineIndex', 0)
                sdp_mid = data.get('sdpMid')
            
            if not candidate_str:
                logger.warning(f"[ALERTA] ICE candidate vazio ou inválido: {data}")
                return
                
            logger.info(f"[OK] ICE CANDIDATO RECEBIDO DO CLIENTE: {candidate_str}")
            logger.info(f"[INFO] Detalhes do candidato: mLineIndex={sdp_mline_index}, mid={sdp_mid}")
            
            # Verificar se o candidato parece válido
            if not candidate_str.startswith('candidate:') and not candidate_str.startswith('a=candidate:'):
                if not candidate_str.startswith('candidate:'):
                    candidate_str = f"candidate:{candidate_str}"
                logger.info(f"[OK] Candidato normalizado para: {candidate_str}")
            
            # Parse do candidato ICE string para obter componentes
            try:
                # Exemplo de candidate string: "candidate:1 1 UDP 2113667327 192.168.1.100 54400 typ host"
                parts = candidate_str.split()
                if len(parts) < 8 or not parts[0].startswith('candidate:'):
                    logger.error(f"[ERRO] Formato de candidato ICE inv\u00e1lido: {candidate_str}")
                    return
                
                foundation = parts[0].split(':')[1]
                component = int(parts[1])
                protocol = parts[2].lower()
                priority = int(parts[3])
                ip = parts[4]
                port = int(parts[5])
                typ_idx = parts.index('typ')
                candidate_type = parts[typ_idx + 1]
                
                # Criar RTCIceCandidate com componentes corretos
                from aiortc import RTCIceCandidate
                candidate_obj = RTCIceCandidate(
                    component=component,
                    foundation=foundation,
                    ip=ip,
                    port=port,
                    priority=priority,
                    protocol=protocol,
                    type=candidate_type,
                    sdpMid=sdp_mid,
                    sdpMLineIndex=sdp_mline_index
                )
                
            except (ValueError, IndexError) as parse_error:
                logger.error(f"[ERRO] Erro ao parsear candidato ICE: {parse_error}")
                logger.error(f"[ERRO] Candidate string: {candidate_str}")
                return
            
            # Processar candidato apenas se tivermos uma descrição remota
            if connection.pc.remoteDescription:
                await connection.pc.addIceCandidate(candidate_obj)
                logger.info(f"[OK] ICE candidate adicionado com sucesso")
                
                # Diagnosticar estado atual do ICE após adicionar o candidato
                ice_connection_state = connection.pc.iceConnectionState
                ice_gathering_state = connection.pc.iceGatheringState
                logger.info(f"[INFO] Estado ICE após adicionar candidato: connectionState={ice_connection_state}, gatheringState={ice_gathering_state}")
            else:
                logger.warning(f"[ALERTA] Não é possível adicionar candidato: remoteDescription não está definido")
                
        except Exception as e:
            logger.error(f"[ERRO] Erro ao processar ICE candidate: {e}")
            import traceback
            logger.error(f"[ERRO] Traceback: {traceback.format_exc()}")
    
    async def handle_offer(self, connection: WebRTCConnection, data: dict):
        """Processa oferta WebRTC do cliente usando aiortc"""
        if not connection.pc:
            await self.send_error(connection, "No peer connection available")
            return
        
        sdp_text = data.get('sdp')
        if not sdp_text:
            await self.send_error(connection, "No SDP in offer")
            return
        
        try:
            # Log do SDP offer para diagnóstico
            print(f"[DIAGNÓSTICO] SDP OFFER RECEBIDO:\n{sdp_text}")
            logger.info(f"[INFO] SDP offer recebido com {sdp_text.count('m=')} seções de mídia")
            
            # Verificar se há seção de vídeo no SDP
            if "m=video" in sdp_text:
                logger.info(f"[OK] SDP contém seção de vídeo")
            else:
                logger.warning(f"[ALERTA] SDP não contém seção de vídeo!")
            
            # Definir descrição remota
            offer = RTCSessionDescription(sdp=sdp_text, type="offer")
            await connection.pc.setRemoteDescription(offer)
            
            # Criar answer
            answer = await connection.pc.createAnswer()
            await connection.pc.setLocalDescription(answer)
            
            # Log do SDP answer para diagnóstico
            print(f"[DIAGNÓSTICO] SDP ANSWER ENVIADO:\n{answer.sdp}")
            logger.info(f"[INFO] SDP answer gerado com {answer.sdp.count('m=')} seções de mídia")
            
            # Verificar se há seção de vídeo no SDP answer
            if "m=video" in answer.sdp:
                logger.info(f"[OK] SDP answer contém seção de vídeo")
            else:
                logger.warning(f"[ALERTA] SDP answer não contém seção de vídeo!")
            
            # Enviar answer para o cliente
            await self.send_message(connection, {
                'type': 'answer',
                'sdp': connection.pc.localDescription.sdp
            })
            
            logger.info(f"[OK] Answer aiortc criado e enviado para {connection.connection_id}")
            
        except Exception as e:
            logger.error(f"[ERRO] Erro ao processar offer aiortc: {e}")
            await self.send_error(connection, f"Failed to process offer: {e}")
    
    async def handle_answer(self, connection: WebRTCConnection, data: dict):
        """Processa resposta WebRTC do cliente"""
        if not connection.pc:
            await self.send_error(connection, "No peer connection available")
            return
        
        # Aceitar tanto formato direto quanto nested
        sdp_text = data.get('sdp') or data.get('answer', {}).get('sdp')
        if not sdp_text:
            await self.send_error(connection, "No SDP in answer")
            return
        
        # Definir descrição remota usando aiortc
        try:
            answer = RTCSessionDescription(sdp=sdp_text, type="answer")
            await connection.pc.setRemoteDescription(answer)
            
            # Reset negotiation state after successful answer processing
            connection.negotiation_state = "stable"
            connection.offer_pending = False
            
            logger.info(f"[OK] Answer aiortc processada para {connection.connection_id}")
            
        except Exception as e:
            logger.error(f"[ERRO] Erro ao processar answer aiortc: {e}")
            await self.send_error(connection, f"Failed to set remote description: {e}")
            connection.negotiation_state = "stable"
            connection.offer_pending = False
    
    async def handle_stop_stream(self, connection: WebRTCConnection):
        """Para stream usando aiortc"""
        await connection.cleanup()
        
        if connection.camera_id and connection.camera_id in self.active_cameras:
            self.active_cameras[connection.camera_id]['active_connections'] = max(0,
                self.active_cameras[connection.camera_id]['active_connections'] - 1)
            
            # Se não há mais conexões, marcar como ready
            if self.active_cameras[connection.camera_id]['active_connections'] == 0:
                self.active_cameras[connection.camera_id]['status'] = 'ready'
        
        connection.state = "stopped"
        connection.camera_id = None
        
        await self.send_message(connection, {
            'type': 'stream-stopped'
        })
    
    async def send_message(self, connection: WebRTCConnection, message: dict):
        """Envia mensagem via WebSocket"""
        try:
            print(f"[ENVIANDO] DIAGNÓSTICO: Enviando mensagem tipo '{message.get('type')}' para {connection.connection_id}", flush=True)
            with open(DEBUG_LOG_PATH, 'a') as f:
                f.write(f"[ENVIANDO] ENVIANDO MSG: {message.get('type')} para {connection.connection_id}\n")
                f.flush()
            await connection.websocket.send_text(json.dumps(message))
            print(f"[OK] DIAGNÓSTICO: Mensagem enviada com sucesso para {connection.connection_id}", flush=True)
        except Exception as e:
            logger.error(f"[ERRO] Erro ao enviar mensagem: {e}")
            print(f"[ERRO] DIAGNÓSTICO: Erro ao enviar mensagem para {connection.connection_id}: {e}", flush=True)
    
    async def send_error(self, connection: WebRTCConnection, error_message: str):
        """Envia mensagem de erro"""
        await self.send_message(connection, {
            'type': 'error',
            'message': error_message
        })
    
    async def generate_demo_html(self) -> str:
        """Gera página HTML de demonstração"""
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>VMS WebRTC Demo (Native GStreamer)</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .camera-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(400px, 1fr)); gap: 20px; }}
                .camera-item {{ border: 1px solid #ddd; padding: 15px; border-radius: 8px; }}
                .controls {{ margin-bottom: 20px; padding: 15px; background: #f5f5f5; border-radius: 5px; }}
                .status {{ background: #e8f5e8; padding: 10px; border-radius: 5px; margin-bottom: 15px; }}
                .codec-info {{ background: #f0f8ff; padding: 10px; border-radius: 5px; margin-bottom: 15px; }}
                video {{ width: 100%; max-width: 400px; height: auto; }}
                button {{ margin: 5px; padding: 8px 15px; }}
                input {{ margin: 5px; padding: 5px; width: 200px; }}
                .error {{ background: #ffe6e6; color: #cc0000; padding: 10px; border-radius: 5px; }}
                .success {{ background: #e6ffe6; color: #006600; padding: 10px; border-radius: 5px; }}
            </style>
        </head>
        <body>
            <h1>VMS WebRTC Demo - Native GStreamer</h1>
            
            <div class="status">
                <strong>Modo:</strong> Native GStreamer | 
                <strong>Backend:</strong> aiortc | 
                <strong>Conexões:</strong> <span id="connection-count">{len(self.connections)}</span> | 
                <strong>Câmeras:</strong> <span id="camera-count">{len(self.active_cameras)}</span>
            </div>
            
            <div class="codec-info">
                <h3>Codecs Disponíveis</h3>
                <div id="codec-list">{json.dumps(self.available_codecs, indent=2)}</div>
            </div>
            
            <div class="controls">
                <h3>Gerenciar Câmeras</h3>
                <input type="text" id="camera-id" placeholder="Camera ID (ex: cam1)" />
                <input type="text" id="rtsp-url" placeholder="RTSP URL" />
                <button onclick="addCamera()">Adicionar Câmera</button>
                <button onclick="loadCameras()">Atualizar Lista</button>
                <div id="message-area"></div>
            </div>
            
            <div id="camera-grid" class="camera-grid">
                <!-- Câmeras serão adicionadas aqui dinamicamente -->
            </div>
            
            <script>
                const wsUrl = `ws://${{window.location.host}}/ws`;
                let ws = null;
                let peerConnections = {{}};
                
                function showMessage(message, type = 'info') {{
                    const messageArea = document.getElementById('message-area');
                    const div = document.createElement('div');
                    div.className = type;
                    div.textContent = message;
                    messageArea.appendChild(div);
                    setTimeout(() => messageArea.removeChild(div), 5000);
                }}
                
                function connectWebSocket() {{
                    ws = new WebSocket(wsUrl);
                    
                    ws.onopen = () => {{
                        console.log('✅ WebSocket conectado');
                        showMessage('WebSocket conectado', 'success');
                    }};
                    
                    ws.onmessage = async (event) => {{
                        const data = JSON.parse(event.data);
                        console.log('📨 Mensagem recebida:', data);
                        
                        if (data.type === 'offer') {{
                            await handleOffer(data);
                        }} else if (data.type === 'answer') {{
                            await handleAnswer(data);
                        }} else if (data.type === 'ice-candidate') {{
                            await handleIceCandidate(data);
                        }} else if (data.type === 'stream-started') {{
                            console.log('▶️ Stream iniciado:', data.camera_id);
                            showMessage(`Stream iniciado: ${{data.camera_id}}`, 'success');
                        }} else if (data.type === 'error') {{
                            console.error('❌ Erro:', data.message);
                            showMessage(`Erro: ${{data.message}}`, 'error');
                        }}
                    }};
                    
                    ws.onclose = () => {{
                        console.log('🔌 WebSocket desconectado');
                        showMessage('WebSocket desconectado', 'error');
                        setTimeout(connectWebSocket, 3000);
                    }};
                    
                    ws.onerror = (error) => {{
                        console.error('❌ Erro WebSocket:', error);
                        showMessage('Erro WebSocket', 'error');
                    }};
                }}
                
                async function handleOffer(data) {{
                    // Implementar lógica de offer se necessário
                    console.log('📝 Offer recebida');
                }}
                
                async function handleAnswer(data) {{
                    // Implementar lógica de answer
                    console.log('📝 Answer recebida');
                }}
                
                async function handleIceCandidate(data) {{
                    // Implementar lógica de ICE candidate
                    console.log('🧊 ICE candidate recebido');
                }}
                
                async function addCamera() {{
                    const cameraId = document.getElementById('camera-id').value;
                    const rtspUrl = document.getElementById('rtsp-url').value;
                    
                    if (!cameraId || !rtspUrl) {{
                        showMessage('Preencha Camera ID e RTSP URL', 'error');
                        return;
                    }}
                    
                    try {{
                        const response = await fetch(`/cameras/${{cameraId}}`, {{
                            method: 'POST',
                            headers: {{ 'Content-Type': 'application/json' }},
                            body: JSON.stringify({{ rtsp_url: rtspUrl }})
                        }});
                        
                        if (response.ok) {{
                            document.getElementById('camera-id').value = '';
                            document.getElementById('rtsp-url').value = '';
                            showMessage(`Câmera ${{cameraId}} adicionada com sucesso`, 'success');
                            loadCameras();
                        }} else {{
                            const error = await response.json();
                            showMessage(`Erro: ${{error.detail}}`, 'error');
                        }}
                    }} catch (error) {{
                        showMessage(`Erro ao adicionar câmera: ${{error.message}}`, 'error');
                    }}
                }}
                
                async function loadCameras() {{
                    try {{
                        const response = await fetch('/cameras');
                        const data = await response.json();
                        
                        const grid = document.getElementById('camera-grid');
                        grid.innerHTML = '';
                        
                        data.cameras.forEach(camera => {{
                            const cameraDiv = document.createElement('div');
                            cameraDiv.className = 'camera-item';
                            cameraDiv.innerHTML = `
                                <h3>Câmera: ${{camera.camera_id}}</h3>
                                <p><strong>RTSP:</strong> ${{camera.rtsp_url}}</p>
                                <p><strong>Status:</strong> ${{camera.status}}</p>
                                <p><strong>Conexões:</strong> ${{camera.active_connections}}</p>
                                <video id="video-${{camera.camera_id}}" autoplay muted controls style="width: 100%;"></video>
                                <br>
                                <button onclick="startStream('${{camera.camera_id}}')" id="start-${{camera.camera_id}}">Iniciar Stream</button>
                                <button onclick="stopStream('${{camera.camera_id}}')" id="stop-${{camera.camera_id}}">Parar Stream</button>
                                <button onclick="removeCamera('${{camera.camera_id}}')" style="background: #ff4444; color: white;">Remover</button>
                                <div id="status-${{camera.camera_id}}">Status: Pronto</div>
                            `;
                            grid.appendChild(cameraDiv);
                        }});
                        
                        document.getElementById('camera-count').textContent = data.cameras.length;
                    }} catch (error) {{
                        console.error('Erro ao carregar câmeras:', error);
                        showMessage('Erro ao carregar câmeras', 'error');
                    }}
                }}
                
                function startStream(cameraId) {{
                    if (ws && ws.readyState === WebSocket.OPEN) {{
                        ws.send(JSON.stringify({{
                            type: 'start-stream',
                            camera_id: cameraId
                        }}));
                        
                        document.getElementById(`status-${{cameraId}}`).textContent = 'Status: Iniciando...';
                        document.getElementById(`start-${{cameraId}}`).disabled = true;
                    }} else {{
                        showMessage('WebSocket não conectado', 'error');
                    }}
                }}
                
                function stopStream(cameraId) {{
                    if (ws && ws.readyState === WebSocket.OPEN) {{
                        ws.send(JSON.stringify({{
                            type: 'stop-stream',
                            camera_id: cameraId
                        }}));
                        
                        document.getElementById(`status-${{cameraId}}`).textContent = 'Status: Parando...';
                        document.getElementById(`start-${{cameraId}}`).disabled = false;
                    }}
                }}
                
                async function removeCamera(cameraId) {{
                    if (confirm(`Remover câmera ${{cameraId}}?`)) {{
                        try {{
                            const response = await fetch(`/cameras/${{cameraId}}`, {{
                                method: 'DELETE'
                            }});
                            
                            if (response.ok) {{
                                showMessage(`Câmera ${{cameraId}} removida`, 'success');
                                loadCameras();
                            }} else {{
                                const error = await response.json();
                                showMessage(`Erro: ${{error.detail}}`, 'error');
                            }}
                        }} catch (error) {{
                            showMessage(`Erro ao remover câmera: ${{error.message}}`, 'error');
                        }}
                    }}
                }}
                
                // Inicializar página
                window.onload = () => {{
                    connectWebSocket();
                    loadCameras();
                    
                    // Atualizar lista de câmeras a cada 30 segundos
                    setInterval(loadCameras, 30000);
                }};
            </script>
        </body>
        </html>
        """
    
    async def start_server(self, host: str = "0.0.0.0", port: Optional[int] = None):
        """Inicia o servidor"""
        if port:
            self.port = port
            
        # Store event loop for GStreamer callbacks
        self.event_loop = asyncio.get_running_loop()
            
        logger.info(f"[INICIANDO] Iniciando VMS WebRTC Server (Native) em {host}:{self.port}")
        logger.info(f"[INICIANDO] Demo: http://{host}:{self.port}/demo")
        logger.info(f"[INFO] Codecs disponíveis: {self.available_codecs}")
        
        # Iniciar tarefa de atualização periódica de câmeras
        camera_update_task = asyncio.create_task(self.update_cameras_periodically())
        
        try:
            config = uvicorn.Config(
                self.app,
                host=host,
                port=self.port,
                log_level="info"
            )
            
            server = uvicorn.Server(config)
            await server.serve()
        finally:
            # Cancelar tarefa de atualização de câmeras
            camera_update_task.cancel()
            try:
                await camera_update_task
            except asyncio.CancelledError:
                pass
    
    def cleanup(self):
        """Limpa recursos"""
        for connection in self.connections.values():
            connection.cleanup()
        self.connections.clear()
        logger.info("Recursos limpos")

if __name__ == "__main__":
    import asyncio
    
    async def main():
        # Obter porta do ambiente ou usar padrão
        port = int(os.environ.get('VMS_WEBRTC_PORT', 17236))
        
        # Criar servidor VMS WebRTC
        server = VMS_WebRTCServerNative(port=port)
        
        try:
            # Iniciar servidor
            await server.start_server(host="127.0.0.1", port=port)
        except KeyboardInterrupt:
            logger.info("Servidor interrompido pelo usuário")
        except Exception as e:
            logger.error(f"Erro no servidor: {e}")
        finally:
            # Limpeza
            server.cleanup()
            logger.info("Servidor finalizado")
    
    # Executar servidor
    asyncio.run(main())