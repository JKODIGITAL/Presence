"""
Bridge melhorado para conectar múltiplos tipos de mídia → WebRTC
Mantém compatibilidade com o sistema existente + adiciona suporte a MP4
"""

import asyncio
import logging
import os
from typing import Dict, Any, Optional
from loguru import logger

from .enhanced_video_track import EnhancedVideoTrack
from .media_adapter import MediaType

class EnhancedGStreamerBridge:
    """
    Bridge melhorado que suporta:
    - RTSP streams (original)
    - Arquivos MP4/AVI/MOV  
    - Webcams
    - Imagens estáticas
    - Fallback inteligente
    """
    
    def __init__(self):
        self.active_tracks: Dict[str, EnhancedVideoTrack] = {}
        self.track_configs: Dict[str, Dict[str, Any]] = {}
        logger.info("🌉 EnhancedGStreamerBridge inicializado")
    
    async def create_track(
        self, 
        camera_id: str, 
        source: str,  # Pode ser RTSP URL, arquivo MP4, webcam ID, etc.
        enable_recognition: bool = True,
        enable_hwaccel: bool = True,
        enable_recording: bool = False,
        target_fps: int = 30
    ) -> Optional[EnhancedVideoTrack]:
        """Criar novo track para qualquer tipo de mídia"""
        try:
            # Parar track existente se houver
            if camera_id in self.active_tracks:
                await self.stop_track(camera_id)
            
            logger.info(f"🎬 Criando track para câmera {camera_id}: {source}")
            
            # Criar track melhorado
            track = EnhancedVideoTrack(
                source=source,
                camera_id=camera_id,
                enable_recognition=enable_recognition,
                enable_hwaccel=enable_hwaccel,
                enable_recording=enable_recording,
                target_fps=target_fps
            )
            
            # Tentar inicializar
            success = await track.start()
            
            if success:
                self.active_tracks[camera_id] = track
                self.track_configs[camera_id] = {
                    'source': source,
                    'media_type': track.media_adapter.media_type,
                    'enable_recognition': enable_recognition,
                    'enable_hwaccel': enable_hwaccel,
                    'enable_recording': enable_recording,
                    'target_fps': target_fps
                }
                
                logger.info(f"✅ Track criado para câmera {camera_id} ({track.media_adapter.media_type})")
                return track
            else:
                logger.error(f"❌ Falha ao inicializar track para câmera {camera_id}")
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
            
            if camera_id in self.track_configs:
                del self.track_configs[camera_id]
            
            logger.info(f"🛑 Track parado para câmera {camera_id}")
    
    async def stop_all_tracks(self):
        """Parar todos os tracks"""
        camera_ids = list(self.active_tracks.keys())
        for camera_id in camera_ids:
            await self.stop_track(camera_id)
        logger.info("🛑 Todos os tracks parados")
    
    def get_track(self, camera_id: str) -> Optional[EnhancedVideoTrack]:
        """Obter track específico"""
        return self.active_tracks.get(camera_id)
    
    def get_stats(self) -> Dict[str, Any]:
        """Obter estatísticas de todos os tracks"""
        stats = {
            'active_tracks': len(self.active_tracks),
            'tracks': {}
        }
        
        for camera_id, track in self.active_tracks.items():
            stats['tracks'][camera_id] = track.get_stats()
        
        return stats
    
    def get_track_info(self, camera_id: str) -> Dict[str, Any]:
        """Obter informações detalhadas de um track"""
        if camera_id not in self.active_tracks:
            return {'error': 'Track não encontrado'}
        
        track = self.active_tracks[camera_id]
        config = self.track_configs.get(camera_id, {})
        
        return {
            'camera_id': camera_id,
            'config': config,
            'stats': track.get_stats(),
            'media_info': track.media_adapter.get_media_info()
        }
    
    async def restart_track(self, camera_id: str) -> bool:
        """Reiniciar track específico"""
        if camera_id not in self.track_configs:
            logger.error(f"Configuração não encontrada para câmera {camera_id}")
            return False
        
        config = self.track_configs[camera_id]
        
        logger.info(f"🔄 Reiniciando track para câmera {camera_id}")
        
        # Parar track atual
        await self.stop_track(camera_id)
        
        # Aguardar um momento
        await asyncio.sleep(1)
        
        # Recriar track
        track = await self.create_track(
            camera_id=camera_id,
            source=config['source'],
            enable_recognition=config.get('enable_recognition', True),
            enable_hwaccel=config.get('enable_hwaccel', True),
            enable_recording=config.get('enable_recording', False),
            target_fps=config.get('target_fps', 30)
        )
        
        return track is not None
    
    def list_supported_formats(self) -> Dict[str, list]:
        """Listar formatos suportados"""
        return {
            'streaming': ['rtsp://', 'rtmp://', 'http://'],
            'video_files': ['.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv'],
            'image_files': ['.jpg', '.jpeg', '.png', '.bmp'],
            'devices': ['webcam (número)', 'file:// URLs']
        }
    
    async def enable_recording_for_track(self, camera_id: str, output_path: str) -> bool:
        """Habilitar gravação para track específico"""
        if camera_id not in self.active_tracks:
            return False
        
        track = self.active_tracks[camera_id]
        track.enable_video_recording(output_path)
        
        # Atualizar configuração
        if camera_id in self.track_configs:
            self.track_configs[camera_id]['enable_recording'] = True
        
        return True
    
    async def disable_recording_for_track(self, camera_id: str) -> bool:
        """Desabilitar gravação para track específico"""
        if camera_id not in self.active_tracks:
            return False
        
        track = self.active_tracks[camera_id]
        track.disable_video_recording()
        
        # Atualizar configuração
        if camera_id in self.track_configs:
            self.track_configs[camera_id]['enable_recording'] = False
        
        return True

# Compatibilidade com o sistema existente
# Manter a interface do simple_gstreamer_bridge

class SimpleGStreamerTrack:
    """Wrapper de compatibilidade para o sistema existente"""
    
    def __init__(self, rtsp_url: str, camera_id: str, enable_recognition: bool = True):
        # Mapear para o novo sistema
        self.enhanced_track = None
        self.rtsp_url = rtsp_url
        self.camera_id = camera_id
        self.enable_recognition = enable_recognition
        
        logger.info(f"🔗 SimpleGStreamerTrack (compatibilidade) para câmera {camera_id}")
    
    async def recv(self):
        """Compatibilidade com a interface antiga"""
        if not self.enhanced_track:
            # Criar track sob demanda
            bridge = enhanced_gstreamer_bridge
            self.enhanced_track = await bridge.create_track(
                camera_id=self.camera_id,
                source=self.rtsp_url,
                enable_recognition=self.enable_recognition
            )
        
        if self.enhanced_track:
            return await self.enhanced_track.recv()
        else:
            # Fallback para frame de teste
            import numpy as np
            import cv2
            import av
            import time
            
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(frame, f"Camera {self.camera_id}", (50, 240), 
                       cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
            cv2.putText(frame, "Compatibility Mode", (50, 280), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, (200, 200, 200), 2)
            
            av_frame = av.VideoFrame.from_ndarray(frame, format='rgb24')
            av_frame.pts = int(time.time() * 90000)
            av_frame.time_base = av.time_base.Fraction(1, 90000)
            
            return av_frame

class SimpleGStreamerBridge:
    """Bridge de compatibilidade para o sistema existente"""
    
    def __init__(self):
        self.tracks = {}
        logger.info("🔗 SimpleGStreamerBridge (compatibilidade) inicializado")
    
    async def create_track(self, camera_id: str, rtsp_url: str, enable_recognition: bool = True):
        """Criar track com interface de compatibilidade"""
        track = SimpleGStreamerTrack(rtsp_url, camera_id, enable_recognition)
        self.tracks[camera_id] = track
        return track
    
    async def stop_track(self, camera_id: str):
        """Parar track"""
        if camera_id in self.tracks:
            del self.tracks[camera_id]
            # Também parar no bridge principal
            await enhanced_gstreamer_bridge.stop_track(camera_id)
    
    async def stop_all_tracks(self):
        """Parar todos os tracks"""
        self.tracks.clear()
        await enhanced_gstreamer_bridge.stop_all_tracks()
    
    def get_stats(self):
        """Estatísticas"""
        return {
            'active_tracks': len(self.tracks),
            'camera_ids': list(self.tracks.keys())
        }

# Instâncias globais
enhanced_gstreamer_bridge = EnhancedGStreamerBridge()

# Manter compatibilidade com o sistema existente
simple_gstreamer_bridge = SimpleGStreamerBridge()