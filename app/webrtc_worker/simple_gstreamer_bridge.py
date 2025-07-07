"""
Bridge simplificado para conectar GStreamer → WebRTC
Versão que funciona sem imports complexos
"""

import asyncio
import time
import numpy as np
import cv2
from typing import Optional, Dict, Any
from loguru import logger

try:
    from aiortc.mediastreams import VideoStreamTrack
    import av
    AIORTC_AVAILABLE = True
except ImportError:
    logger.warning("aiortc não disponível - bridge será simulado")
    AIORTC_AVAILABLE = False
    
    # Mock classes
    class VideoStreamTrack:
        def __init__(self):
            pass

class SimpleGStreamerTrack(VideoStreamTrack):
    """
    VideoTrack simplificado que gera frames de teste
    Preparado para conectar ao pipeline GStreamer futuramente
    """
    
    def __init__(self, rtsp_url: str, camera_id: str, enable_recognition: bool = True):
        super().__init__()
        self.camera_id = camera_id
        self.rtsp_url = rtsp_url
        self.enable_recognition = enable_recognition
        self._pts = 0
        self._fps = 30
        self._frame_time = 1.0 / self._fps
        
        # Detectar tipo de mídia
        self._media_type = self._detect_media_type(rtsp_url)
        self._media_player = None
        self._opencv_capture = None
        
        logger.info(f"🎥 SimpleGStreamerTrack criado para câmera {camera_id}")
        logger.info(f"📡 Source: {rtsp_url}")
        logger.info(f"🎬 Tipo: {self._media_type}")
        logger.info(f"🧠 Reconhecimento: {enable_recognition}")
        
        # Configurar mídia
        self._setup_media()
    
    def _detect_media_type(self, url: str) -> str:
        """Detectar tipo de mídia"""
        import os
        
        if url.startswith("rtsp://") or url.startswith("rtmp://"):
            return "stream"
        elif url.endswith((".mp4", ".avi", ".mov")) or os.path.exists(url):
            return "file" 
        else:
            return "test"
    
    def _setup_media(self):
        """Configurar player de mídia"""
        try:
            if self._media_type == "file" and AIORTC_AVAILABLE:
                # Usar MediaPlayer para arquivos de vídeo
                from aiortc.contrib.media import MediaPlayer
                
                # Detectar formato automaticamente
                format_hint = None
                if self.rtsp_url.endswith('.mp4'):
                    format_hint = 'mp4'
                elif self.rtsp_url.endswith('.avi'):
                    format_hint = 'avi'
                elif self.rtsp_url.endswith('.mov'):
                    format_hint = 'mov'
                
                self._media_player = MediaPlayer(self.rtsp_url, format=format_hint)
                logger.info(f"✅ MediaPlayer configurado para arquivo: {self.rtsp_url}")
                
            elif self._media_type == "stream" and AIORTC_AVAILABLE:
                # Usar MediaPlayer para RTSP
                from aiortc.contrib.media import MediaPlayer
                self._media_player = MediaPlayer(self.rtsp_url, format='rtsp')
                logger.info(f"✅ MediaPlayer configurado para RTSP: {self.rtsp_url}")
                
            else:
                logger.info(f"🔄 Usando modo de teste para: {self.rtsp_url}")
                
        except Exception as e:
            logger.warning(f"⚠️ Erro ao configurar MediaPlayer: {e}")
            logger.info("🔄 Fallback para modo teste")
        
    async def recv(self):
        """Obter próximo frame (de arquivo, RTSP ou teste)"""
        try:
            # Tentar obter frame do MediaPlayer primeiro
            if self._media_player and hasattr(self._media_player, 'video'):
                try:
                    frame = await self._media_player.video.recv()
                    # Frame já é um av.VideoFrame, retornar diretamente
                    return frame
                except Exception as e:
                    logger.debug(f"MediaPlayer frame error: {e}")
                    # Se chegou ao fim do vídeo, reiniciar
                    if self._media_type == "file":
                        logger.info(f"🔄 Reiniciando vídeo: {self.rtsp_url}")
                        self._setup_media()  # Reconfigurar MediaPlayer
            
            # Fallback para frame de teste
            await asyncio.sleep(self._frame_time)
            frame = self._generate_test_frame()
            
            if AIORTC_AVAILABLE:
                # Criar av.VideoFrame
                av_frame = av.VideoFrame.from_ndarray(frame, format='rgb24')
                
                # Configurar timing
                self._pts += int(90000 / self._fps)  # 90kHz timebase
                av_frame.pts = self._pts
                av_frame.time_base = av.time_base.Fraction(1, 90000)
                
                return av_frame
            else:
                # Retorno mock se aiortc não disponível
                return frame
                
        except Exception as e:
            logger.error(f"❌ Erro ao obter frame: {e}")
            # Fallback final para frame de teste
            frame = self._generate_test_frame()
            av_frame = av.VideoFrame.from_ndarray(frame, format='rgb24')
            self._pts += int(90000 / self._fps)
            av_frame.pts = self._pts
            av_frame.time_base = av.time_base.Fraction(1, 90000)
            return av_frame
    
    def _generate_test_frame(self) -> np.ndarray:
        """Gerar frame de teste animado"""
        # Frame base (640x480 RGB)
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        
        # Background gradiente
        for y in range(480):
            frame[y, :, 0] = int(50 + (y / 480) * 100)  # Red gradient
            frame[y, :, 2] = int(100 - (y / 480) * 50)  # Blue gradient
        
        # Informações da câmera
        timestamp = time.strftime("%H:%M:%S")
        
        # Texto principal
        cv2.putText(frame, f"Camera {self.camera_id}", (50, 80), 
                   cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 255), 2)
        
        # Tipo de mídia
        media_type_text = f"Tipo: {self._media_type.upper()}"
        cv2.putText(frame, media_type_text, (50, 120), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (100, 255, 100), 2)
        
        # Source (truncado)
        source_short = self.rtsp_url[:50] + "..." if len(self.rtsp_url) > 50 else self.rtsp_url
        cv2.putText(frame, source_short, (50, 150), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
        
        # Timestamp
        cv2.putText(frame, timestamp, (50, 190), 
                   cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)
        
        # Status do reconhecimento
        rec_status = "ON" if self.enable_recognition else "OFF"
        cv2.putText(frame, f"Recognition: {rec_status}", (50, 230), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)
        
        # Animação - círculo pulsante
        pulse = int(50 + 30 * abs(np.sin(time.time() * 2)))
        cv2.circle(frame, (540, 80), pulse, (255, 255, 255), 2)
        cv2.putText(frame, "LIVE", (520, 85), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        # FPS counter
        cv2.putText(frame, f"FPS: {self._fps}", (50, 240), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        
        # Status da conexão
        cv2.putText(frame, "🔗 Pipeline GStreamer", (50, 280), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (100, 255, 100), 1)
        cv2.putText(frame, "   → WebRTC Bridge", (50, 300), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (100, 255, 100), 1)
        
        # TODO indicator
        cv2.putText(frame, "TODO: Connect to", (50, 350), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 100, 100), 1)
        cv2.putText(frame, "GStreamer Pipeline", (50, 370), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 100, 100), 1)
        
        return frame


class SimpleGStreamerBridge:
    """Bridge simplificado para gerenciar tracks"""
    
    def __init__(self):
        self.active_tracks: Dict[str, SimpleGStreamerTrack] = {}
        logger.info("🌉 SimpleGStreamerBridge inicializado")
        
    async def create_track(self, camera_id: str, rtsp_url: str, enable_recognition: bool = True) -> Optional[SimpleGStreamerTrack]:
        """Criar novo track"""
        try:
            # Limpar track existente
            if camera_id in self.active_tracks:
                await self.stop_track(camera_id)
            
            # Criar novo track
            track = SimpleGStreamerTrack(rtsp_url, camera_id, enable_recognition)
            self.active_tracks[camera_id] = track
            
            logger.info(f"✅ Track criado para câmera {camera_id}")
            return track
            
        except Exception as e:
            logger.error(f"❌ Erro ao criar track para {camera_id}: {e}")
            return None
    
    async def stop_track(self, camera_id: str):
        """Parar track"""
        if camera_id in self.active_tracks:
            del self.active_tracks[camera_id]
            logger.info(f"🛑 Track removido para câmera {camera_id}")
    
    async def stop_all_tracks(self):
        """Parar todos os tracks"""
        camera_ids = list(self.active_tracks.keys())
        for camera_id in camera_ids:
            await self.stop_track(camera_id)
        logger.info("🛑 Todos os tracks removidos")
    
    def get_stats(self) -> Dict[str, Any]:
        """Estatísticas"""
        return {
            "active_tracks": len(self.active_tracks),
            "camera_ids": list(self.active_tracks.keys()),
            "aiortc_available": AIORTC_AVAILABLE
        }


# Instância global
simple_gstreamer_bridge = SimpleGStreamerBridge()