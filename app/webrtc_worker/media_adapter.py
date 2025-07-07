"""
Adaptador genérico para diferentes tipos de mídia
Suporta: RTSP, MP4, AVI, MOV, imagens, webcam
"""

import os
import asyncio
import logging
from typing import Optional, Union, Dict, Any
from pathlib import Path
from urllib.parse import urlparse
import cv2
import numpy as np

try:
    from aiortc.contrib.media import MediaPlayer
    from aiortc.mediastreams import VideoStreamTrack
    import av
    AIORTC_AVAILABLE = True
except ImportError:
    AIORTC_AVAILABLE = False

logger = logging.getLogger(__name__)

class MediaType:
    """Tipos de mídia suportados"""
    RTSP = "rtsp"
    RTMP = "rtmp" 
    FILE = "file"
    WEBCAM = "webcam"
    TEST = "test"
    IMAGE = "image"

class MediaAdapter:
    """Adaptador para diferentes tipos de entrada de mídia"""
    
    def __init__(self, source: str, enable_hwaccel: bool = True):
        self.source = source
        self.enable_hwaccel = enable_hwaccel
        self.media_type = self._detect_media_type(source)
        self.media_player: Optional[MediaPlayer] = None
        self._retry_count = 0
        self._max_retries = 3
        
        logger.info(f"🎬 MediaAdapter inicializado: {source} -> {self.media_type}")
    
    def _detect_media_type(self, source: str) -> str:
        """Detectar automaticamente o tipo de mídia"""
        if not source:
            return MediaType.TEST
        
        # URLs de rede
        if source.startswith(('rtsp://', 'rtmp://', 'http://', 'https://')):
            if 'rtsp://' in source:
                return MediaType.RTSP
            elif 'rtmp://' in source:
                return MediaType.RTMP
            else:
                return MediaType.FILE  # HTTP streams
        
        # File path ou file:// URL
        if source.startswith('file://'):
            source = source[7:]  # Remove file://
        
        # Webcam (números)
        try:
            int(source)
            return MediaType.WEBCAM
        except ValueError:
            pass
        
        # Arquivos locais
        if os.path.exists(source):
            file_ext = Path(source).suffix.lower()
            if file_ext in ['.jpg', '.jpeg', '.png', '.bmp']:
                return MediaType.IMAGE
            elif file_ext in ['.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv']:
                return MediaType.FILE
        
        # Fallback para teste
        logger.warning(f"Tipo de mídia não identificado para '{source}', usando TEST")
        return MediaType.TEST
    
    def get_media_info(self) -> Dict[str, Any]:
        """Obter informações sobre a mídia"""
        return {
            'source': self.source,
            'media_type': self.media_type,
            'hwaccel_enabled': self.enable_hwaccel,
            'aiortc_available': AIORTC_AVAILABLE,
            'retry_count': self._retry_count,
            'max_retries': self._max_retries
        }
    
    async def setup_media_player(self) -> Optional[MediaPlayer]:
        """Configurar MediaPlayer baseado no tipo de mídia"""
        if not AIORTC_AVAILABLE:
            logger.error("aiortc não disponível")
            return None
        
        try:
            if self.media_type == MediaType.RTSP:
                return await self._setup_rtsp_player()
            elif self.media_type == MediaType.FILE:
                return await self._setup_file_player()
            elif self.media_type == MediaType.WEBCAM:
                return await self._setup_webcam_player()
            elif self.media_type == MediaType.IMAGE:
                return await self._setup_image_player()
            else:
                logger.warning(f"Tipo de mídia {self.media_type} não suportado para MediaPlayer")
                return None
                
        except Exception as e:
            logger.error(f"Erro ao configurar MediaPlayer: {e}")
            self._retry_count += 1
            
            if self._retry_count < self._max_retries:
                logger.info(f"Tentativa {self._retry_count}/{self._max_retries} em 2 segundos...")
                await asyncio.sleep(2)
                return await self.setup_media_player()
            else:
                logger.error(f"Falha após {self._max_retries} tentativas")
                return None
    
    async def _setup_rtsp_player(self) -> MediaPlayer:
        """Configurar player para RTSP"""
        logger.info(f"📡 Configurando RTSP player: {self.source}")
        
        # Opções RTSP otimizadas
        options = {
            'rtsp_transport': 'tcp',  # TCP mais confiável que UDP
            'rtsp_flags': 'prefer_tcp',
            'stimeout': '5000000',    # 5s timeout
            'max_delay': '0',         # Baixa latência
        }
        
        if self.enable_hwaccel:
            # Tentar hardware decode
            options.update({
                'hwaccel': 'cuda',
                'hwaccel_device': '0',
                'c:v': 'h264_cuvid'  # NVIDIA decoder
            })
        
        try:
            player = MediaPlayer(self.source, format='rtsp', options=options)
            logger.info(f"✅ RTSP player configurado com hardware accel: {self.enable_hwaccel}")
            return player
        except Exception as e:
            if self.enable_hwaccel:
                logger.warning(f"Hardware accel falhou, tentando software: {e}")
                # Fallback para software
                return MediaPlayer(self.source, format='rtsp', options={
                    'rtsp_transport': 'tcp',
                    'stimeout': '5000000'
                })
            else:
                raise e
    
    async def _setup_file_player(self) -> MediaPlayer:
        """Configurar player para arquivos de vídeo"""
        logger.info(f"📁 Configurando file player: {self.source}")
        
        if not os.path.exists(self.source):
            raise FileNotFoundError(f"Arquivo não encontrado: {self.source}")
        
        # Detectar formato automaticamente
        file_ext = Path(self.source).suffix.lower()
        format_map = {
            '.mp4': 'mp4',
            '.avi': 'avi', 
            '.mov': 'mov',
            '.mkv': 'matroska',
            '.webm': 'webm'
        }
        
        format_hint = format_map.get(file_ext, None)
        
        options = {}
        if self.enable_hwaccel:
            # Hardware decode para arquivos
            options.update({
                'hwaccel': 'cuda',
                'hwaccel_device': '0'
            })
        
        try:
            player = MediaPlayer(self.source, format=format_hint, options=options)
            logger.info(f"✅ File player configurado: {self.source}")
            return player
        except Exception as e:
            if self.enable_hwaccel:
                logger.warning(f"Hardware decode falhou, usando software: {e}")
                return MediaPlayer(self.source, format=format_hint)
            else:
                raise e
    
    async def _setup_webcam_player(self) -> MediaPlayer:
        """Configurar player para webcam"""
        webcam_id = int(self.source)
        logger.info(f"📷 Configurando webcam player: device {webcam_id}")
        
        # Formato V4L2 no Linux, DirectShow no Windows
        import platform
        if platform.system() == "Linux":
            device_path = f"/dev/video{webcam_id}"
            return MediaPlayer(device_path, format='v4l2')
        else:
            # Windows DirectShow
            device_name = f"video={webcam_id}"
            return MediaPlayer(device_name, format='dshow')
    
    async def _setup_image_player(self) -> Optional[MediaPlayer]:
        """Para imagens, não usar MediaPlayer (será tratado diferente)"""
        logger.info(f"🖼️ Imagem detectada: {self.source}")
        return None
    
    async def create_opencv_capture(self) -> Optional[cv2.VideoCapture]:
        """Criar OpenCV VideoCapture como fallback"""
        try:
            if self.media_type == MediaType.WEBCAM:
                cap = cv2.VideoCapture(int(self.source))
            elif self.media_type in [MediaType.FILE, MediaType.RTSP]:
                cap = cv2.VideoCapture(self.source)
            else:
                return None
            
            if cap.isOpened():
                logger.info(f"✅ OpenCV capture criado para {self.media_type}")
                return cap
            else:
                cap.release()
                return None
                
        except Exception as e:
            logger.error(f"Erro ao criar OpenCV capture: {e}")
            return None
    
    def is_loop_capable(self) -> bool:
        """Verificar se a mídia pode fazer loop (arquivos)"""
        return self.media_type in [MediaType.FILE, MediaType.IMAGE]
    
    def get_suggested_fps(self) -> int:
        """FPS sugerido baseado no tipo de mídia"""
        fps_map = {
            MediaType.RTSP: 30,
            MediaType.FILE: 30,   # Será detectado do arquivo
            MediaType.WEBCAM: 30,
            MediaType.IMAGE: 1,   # 1 FPS para imagens estáticas
            MediaType.TEST: 30
        }
        return fps_map.get(self.media_type, 30)