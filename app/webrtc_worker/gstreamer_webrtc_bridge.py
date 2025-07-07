"""
Bridge para conectar pipeline GStreamer → WebRTC
Pipeline: RTSP → NVDEC → InsightFace+FAISS → OpenCV Overlay → NVENC → WebRTC
"""

import asyncio
import logging
import numpy as np
import cv2
from typing import Optional, Callable, Dict, Any
from aiortc.mediastreams import VideoStreamTrack
from aiortc.contrib.media import MediaPlayer
import av
import time
from loguru import logger

# Import do pipeline GStreamer de alta performance
# from app.core.gstreamer_pipeline import HighPerformancePipeline, PipelineConfig
# Temporariamente comentado - implementar versão simplificada

class GStreamerWebRTCTrack(VideoStreamTrack):
    """
    VideoTrack que recebe frames do pipeline GStreamer de alta performance
    e os entrega para WebRTC com zero-copy quando possível
    """
    
    def __init__(self, rtsp_url: str, camera_id: str, enable_recognition: bool = True):
        super().__init__()
        self.camera_id = camera_id
        self.rtsp_url = rtsp_url
        self.enable_recognition = enable_recognition
        self._pts = 0
        self._fps = 30
        self._frame_time = 1.0 / self._fps
        
        # Frame buffer (double buffering para performance)
        self._current_frame: Optional[np.ndarray] = None
        self._frame_lock = asyncio.Lock()
        self._frame_ready = asyncio.Event()
        
        # Pipeline GStreamer (simplificado para funcionar)
        self.pipeline = None
        self._use_test_mode = True  # Usar modo de teste por enquanto
        # self._setup_pipeline()  # Comentado temporariamente
        
    def _setup_pipeline(self):
        """Configurar pipeline GStreamer (implementação futura)"""
        # TODO: Implementar pipeline GStreamer completo
        logger.info(f"🚧 Pipeline GStreamer será implementado - usando modo teste para câmera {self.camera_id}")
        self._use_test_mode = True
    
    def _setup_frame_callback(self):
        """Configurar callback para receber frames do pipeline"""
        if not self.pipeline:
            return
            
        # Monkey patch para capturar frames processados
        original_push_frame = self.pipeline._push_frame_to_encoder
        
        async def frame_interceptor(frame: np.ndarray):
            """Interceptar frame antes do encoder e enviar para WebRTC"""
            try:
                async with self._frame_lock:
                    # Converter RGBA → RGB se necessário
                    if frame.shape[2] == 4:
                        self._current_frame = cv2.cvtColor(frame, cv2.COLOR_RGBA2RGB)
                    else:
                        self._current_frame = frame.copy()
                    
                    self._frame_ready.set()
                    
                logger.debug(f"📹 Frame interceptado para WebRTC: {frame.shape}")
                
            except Exception as e:
                logger.error(f"❌ Erro ao interceptar frame: {e}")
        
        # Substituir o método original
        self.pipeline._push_frame_to_encoder = frame_interceptor
    
    def _recognition_callback(self, frame: np.ndarray) -> list:
        """Callback para reconhecimento facial"""
        try:
            # Conectar com Recognition Worker ou Recognition Engine local
            # Por enquanto, retorna lista vazia (será implementado conforme necessário)
            return []
            
        except Exception as e:
            logger.error(f"❌ Erro no reconhecimento facial: {e}")
            return []
    
    def _overlay_callback(self, frame: np.ndarray, recognition_results: list) -> np.ndarray:
        """Callback para overlay com OpenCV (zero-copy otimizado)"""
        try:
            if not recognition_results:
                return frame
            
            # Overlay otimizado - modificar frame in-place quando possível
            overlay_frame = frame.copy()  # Apenas se necessário
            
            for result in recognition_results:
                # Desenhar bounding box e nome
                if 'bbox' in result and 'name' in result:
                    x1, y1, x2, y2 = result['bbox']
                    name = result['name']
                    confidence = result.get('confidence', 0.0)
                    
                    # Bounding box
                    cv2.rectangle(overlay_frame, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 0), 2)
                    
                    # Nome e confiança
                    label = f"{name} ({confidence:.2f})"
                    cv2.putText(overlay_frame, label, (int(x1), int(y1-10)), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            
            return overlay_frame
            
        except Exception as e:
            logger.error(f"❌ Erro no overlay: {e}")
            return frame
    
    async def start(self):
        """Iniciar pipeline"""
        logger.info(f"🚀 Iniciando bridge para câmera {self.camera_id} (modo teste)")
        return True  # Sempre sucesso em modo teste
    
    async def stop(self):
        """Parar pipeline"""
        logger.info(f"🛑 Bridge parado para câmera {self.camera_id}")
    
    async def recv(self):
        """
        Método principal - entrega frames para WebRTC
        Este é chamado pelo WebRTC para obter cada frame
        """
        try:
            # Modo teste - sempre gerar frame de teste
            if self._use_test_mode:
                return await self._generate_test_frame()
            
            # Código original (para quando pipeline estiver implementado)
            # try:
            #     await asyncio.wait_for(self._frame_ready.wait(), timeout=1.0)
            # except asyncio.TimeoutError:
            #     return await self._generate_test_frame()
            
            # Em modo teste, já retorna o frame de teste
            # (o código de conversão será usado quando pipeline real estiver pronto)
            return await self._generate_test_frame()
            
        except Exception as e:
            logger.error(f"❌ Erro ao gerar frame WebRTC: {e}")
            return await self._generate_test_frame()
    
    async def _numpy_to_videoframe(self, frame: np.ndarray):
        """Converter numpy array para VideoFrame (otimizado)"""
        try:
            # Garantir que frame está em RGB
            if len(frame.shape) == 3 and frame.shape[2] == 3:
                # Criar av.VideoFrame diretamente do numpy array (zero-copy quando possível)
                av_frame = av.VideoFrame.from_ndarray(frame, format='rgb24')
                
                # Retornar av_frame diretamente (aiortc aceita av.VideoFrame)
                video_frame = av_frame
                
                return video_frame
            else:
                raise ValueError(f"Frame format inválido: {frame.shape}")
                
        except Exception as e:
            logger.error(f"❌ Erro na conversão numpy→VideoFrame: {e}")
            # Fallback para frame de teste
            return await self._generate_test_frame()
    
    async def _generate_test_frame(self):
        """Gerar frame de teste quando não há stream real"""
        # Frame de teste simples (640x480 RGB)
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        
        # Adicionar texto informativo
        text = f"Camera {self.camera_id}"
        cv2.putText(frame, text, (50, 240), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        
        timestamp = time.strftime("%H:%M:%S")
        cv2.putText(frame, timestamp, (50, 280), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (200, 200, 200), 2)
        
        # Criar av.VideoFrame (aiortc aceita diretamente)
        av_frame = av.VideoFrame.from_ndarray(frame, format='rgb24')
        video_frame = av_frame
        
        # PTS
        self._pts += int(90000 / self._fps)
        video_frame.pts = self._pts
        video_frame.time_base = av.time_base.Fraction(1, 90000)
        
        return video_frame


class GStreamerWebRTCBridge:
    """
    Bridge principal para gerenciar conexões GStreamer → WebRTC
    """
    
    def __init__(self):
        self.active_tracks: Dict[str, GStreamerWebRTCTrack] = {}
        
    async def create_track(self, camera_id: str, rtsp_url: str, enable_recognition: bool = True) -> GStreamerWebRTCTrack:
        """Criar novo track para câmera"""
        try:
            # Parar track existente se houver
            if camera_id in self.active_tracks:
                await self.stop_track(camera_id)
            
            # Criar novo track
            track = GStreamerWebRTCTrack(rtsp_url, camera_id, enable_recognition)
            
            # Iniciar pipeline
            success = await track.start()
            if success:
                self.active_tracks[camera_id] = track
                logger.info(f"✅ Bridge criado para câmera {camera_id}")
                return track
            else:
                logger.error(f"❌ Falha ao criar bridge para câmera {camera_id}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Erro ao criar track para câmera {camera_id}: {e}")
            return None
    
    async def stop_track(self, camera_id: str):
        """Parar track específico"""
        if camera_id in self.active_tracks:
            track = self.active_tracks[camera_id]
            await track.stop()
            del self.active_tracks[camera_id]
            logger.info(f"🛑 Bridge parado para câmera {camera_id}")
    
    async def stop_all_tracks(self):
        """Parar todos os tracks"""
        for camera_id in list(self.active_tracks.keys()):
            await self.stop_track(camera_id)
        logger.info("🛑 Todos os bridges parados")
    
    def get_stats(self) -> Dict[str, Any]:
        """Obter estatísticas"""
        return {
            "active_tracks": len(self.active_tracks),
            "camera_ids": list(self.active_tracks.keys())
        }


# Instância global do bridge
gstreamer_webrtc_bridge = GStreamerWebRTCBridge()