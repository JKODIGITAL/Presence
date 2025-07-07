"""
Bridge para conectar WebRTC Server com Camera Worker Pipeline
Permite que o WebRTC Server receba frames processados do Camera Worker
"""

import asyncio
import json
import logging
import numpy as np
import cv2
from typing import Dict, Optional, Callable, Any
from aiortc.mediastreams import VideoStreamTrack
import av
import socketio
from loguru import logger
import time
from fractions import Fraction

class CameraWorkerVideoTrack(VideoStreamTrack):
    """
    VideoTrack que recebe frames processados do Camera Worker pipeline
    através de Socket.IO ou shared memory
    """
    
    def __init__(self, camera_id: str, camera_worker_url: str = "http://127.0.0.1:17235"):
        super().__init__()
        self.camera_id = camera_id
        self.camera_worker_url = camera_worker_url
        self._pts = 0
        self._fps = 30
        self._frame_time = 1.0 / self._fps
        
        # Frame buffer
        self._current_frame: Optional[np.ndarray] = None
        self._frame_lock = asyncio.Lock()
        self._frame_ready = asyncio.Event()
        self._last_frame_time = 0
        
        # Socket.IO client para receber frames do Camera Worker
        self._sio_client = None
        self._connected = False
        self._use_test_mode = True  # Começar em modo teste
        
        # Statistics
        self._frame_count = 0
        self._last_fps_time = time.time()
        self._fps_counter = 0
    
    async def start(self):
        """Iniciar conexão com Camera Worker"""
        try:
            # Inicializar Socket.IO client
            self._sio_client = socketio.AsyncClient()
            
            @self._sio_client.event
            async def connect():
                logger.info(f"✅ [BRIDGE] WebRTC conectado ao Camera Worker - câmera {self.camera_id}")
                self._connected = True
                self._use_test_mode = False
                
                # Solicitar stream da câmera específica
                await self._sio_client.emit('request_stream', {'camera_id': self.camera_id})
            
            @self._sio_client.event
            async def disconnect():
                logger.warning(f"🔌 [BRIDGE] WebRTC desconectado do Camera Worker - câmera {self.camera_id}")
                self._connected = False
                self._use_test_mode = True
            
            @self._sio_client.event
            async def processed_frame(data):
                """Receber frame processado com overlay do Camera Worker"""
                try:
                    if 'camera_id' in data and data['camera_id'] == self.camera_id:
                        frame_data = data.get('frame_data')
                        if frame_data:
                            # Decodificar frame (base64 ou bytes)
                            import base64
                            if isinstance(frame_data, str):
                                frame_bytes = base64.b64decode(frame_data)
                            else:
                                frame_bytes = frame_data
                            
                            # Converter para numpy array
                            nparr = np.frombuffer(frame_bytes, np.uint8)
                            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                            
                            if frame is not None:
                                # Converter BGR para RGB
                                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                                
                                async with self._frame_lock:
                                    self._current_frame = frame_rgb
                                    self._frame_ready.set()
                                    self._frame_count += 1
                                
                                self._update_fps_counter()
                
                except Exception as e:
                    logger.error(f"❌ [BRIDGE] Erro ao processar frame: {e}")
            
            # Conectar ao Camera Worker
            await self._sio_client.connect(self.camera_worker_url)
            logger.info(f"🔌 [BRIDGE] Conectando WebRTC ao Camera Worker para câmera {self.camera_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ [BRIDGE] Erro ao conectar com Camera Worker: {e}")
            self._use_test_mode = True
            return False
    
    async def stop(self):
        """Parar conexão"""
        if self._sio_client and self._connected:
            await self._sio_client.disconnect()
        logger.info(f"🛑 [BRIDGE] Bridge parado para câmera {self.camera_id}")
    
    async def recv(self):
        """Receber próximo frame para WebRTC"""
        try:
            # Se não conectado ao Camera Worker, usar modo teste
            if self._use_test_mode or not self._connected:
                if not self._connected:
                    logger.debug(f"🔍 [BRIDGE] Câmera {self.camera_id}: Não conectado ao Camera Worker, usando frame de teste")
                return await self._generate_test_frame()
            
            # Aguardar frame do Camera Worker
            try:
                await asyncio.wait_for(self._frame_ready.wait(), timeout=1.0)
                self._frame_ready.clear()
                
                async with self._frame_lock:
                    if self._current_frame is not None:
                        return await self._numpy_to_videoframe(self._current_frame)
                    else:
                        return await self._generate_test_frame()
                        
            except asyncio.TimeoutError:
                # Timeout - usar frame de teste
                return await self._generate_test_frame()
                
        except Exception as e:
            logger.error(f"❌ [BRIDGE] Erro ao receber frame: {e}")
            return await self._generate_test_frame()
    
    async def _numpy_to_videoframe(self, frame: np.ndarray):
        """Converter numpy array para VideoFrame"""
        try:
            # Garantir que está em RGB
            if len(frame.shape) == 3 and frame.shape[2] == 3:
                # Criar av.VideoFrame diretamente
                av_frame = av.VideoFrame.from_ndarray(frame, format='rgb24')
                
                # PTS
                self._pts += int(90000 / self._fps)
                av_frame.pts = self._pts
                av_frame.time_base = Fraction(1, 90000)
                
                return av_frame
            else:
                raise ValueError(f"Frame format inválido: {frame.shape}")
                
        except Exception as e:
            logger.error(f"❌ [BRIDGE] Erro na conversão: {e}")
            return await self._generate_test_frame()
    
    async def _generate_test_frame(self):
        """Gerar frame de teste quando não há conexão com Camera Worker"""
        # Frame de teste
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        
        # Status da conexão
        status = "CONECTADO AO CAMERA WORKER" if self._connected else "AGUARDANDO CAMERA WORKER"
        color = (0, 255, 0) if self._connected else (255, 255, 0)
        
        # Texto informativo
        cv2.putText(frame, f"Camera {self.camera_id}", (50, 200), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        cv2.putText(frame, status, (50, 240), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
        cv2.putText(frame, f"Frames: {self._frame_count}", (50, 280), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 2)
        
        timestamp = time.strftime("%H:%M:%S")
        cv2.putText(frame, timestamp, (50, 320), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 2)
        
        # Criar VideoFrame
        av_frame = av.VideoFrame.from_ndarray(frame, format='rgb24')
        
        # PTS
        self._pts += int(90000 / self._fps)
        av_frame.pts = self._pts
        av_frame.time_base = Fraction(1, 90000)
        
        return av_frame
    
    def _update_fps_counter(self):
        """Atualizar contador de FPS"""
        self._fps_counter += 1
        current_time = time.time()
        
        if current_time - self._last_fps_time >= 5.0:  # Log a cada 5 segundos
            fps = self._fps_counter / (current_time - self._last_fps_time)
            logger.info(f"📊 [BRIDGE] Camera {self.camera_id} FPS: {fps:.1f}")
            self._fps_counter = 0
            self._last_fps_time = current_time


class CameraWorkerBridge:
    """
    Bridge principal para gerenciar conexões WebRTC → Camera Worker
    """
    
    def __init__(self):
        self.active_tracks: Dict[str, CameraWorkerVideoTrack] = {}
        self._camera_worker_url = "http://127.0.0.1:17235"
    
    async def create_track(self, camera_id: str) -> CameraWorkerVideoTrack:
        """Criar novo track conectado ao Camera Worker"""
        try:
            # Parar track existente se houver
            if camera_id in self.active_tracks:
                await self.stop_track(camera_id)
            
            # Criar novo track
            track = CameraWorkerVideoTrack(camera_id, self._camera_worker_url)
            
            # Iniciar conexão
            success = await track.start()
            if success:
                self.active_tracks[camera_id] = track
                logger.info(f"✅ [BRIDGE] Track criado para câmera {camera_id}")
                return track
            else:
                logger.warning(f"⚠️ [BRIDGE] Track criado em modo teste para câmera {camera_id}")
                self.active_tracks[camera_id] = track
                return track
                
        except Exception as e:
            logger.error(f"❌ [BRIDGE] Erro ao criar track para câmera {camera_id}: {e}")
            # Retornar track em modo teste mesmo com erro
            track = CameraWorkerVideoTrack(camera_id, self._camera_worker_url)
            self.active_tracks[camera_id] = track
            return track
    
    async def stop_track(self, camera_id: str):
        """Parar track específico"""
        if camera_id in self.active_tracks:
            track = self.active_tracks[camera_id]
            await track.stop()
            del self.active_tracks[camera_id]
            logger.info(f"🛑 [BRIDGE] Track parado para câmera {camera_id}")
    
    async def stop_all_tracks(self):
        """Parar todos os tracks"""
        for camera_id in list(self.active_tracks.keys()):
            await self.stop_track(camera_id)
        logger.info("🛑 [BRIDGE] Todos os tracks parados")
    
    def get_stats(self) -> Dict[str, Any]:
        """Obter estatísticas"""
        return {
            "active_tracks": len(self.active_tracks),
            "camera_ids": list(self.active_tracks.keys()),
            "camera_worker_url": self._camera_worker_url
        }


# Instância global do bridge
camera_worker_bridge = CameraWorkerBridge()