"""
Enhanced VideoStreamTrack com suporte a múltiplos tipos de mídia
Suporta: RTSP, MP4, webcam, imagens + reconhecimento facial
"""

import asyncio
import time
import logging
import os
import cv2
import numpy as np
from typing import Optional, Dict, Any, Callable
from datetime import datetime
from pathlib import Path

try:
    from aiortc.mediastreams import VideoStreamTrack
    from aiortc.contrib.media import MediaPlayer
    import av
    AIORTC_AVAILABLE = True
except ImportError:
    AIORTC_AVAILABLE = False

from .media_adapter import MediaAdapter, MediaType

logger = logging.getLogger(__name__)

class EnhancedVideoTrack(VideoStreamTrack):
    """
    VideoTrack melhorado com suporte a múltiplos tipos de mídia
    e integração com reconhecimento facial
    """
    
    def __init__(
        self, 
        source: str, 
        camera_id: str,
        enable_recognition: bool = True,
        enable_hwaccel: bool = True,
        enable_recording: bool = False,
        target_fps: int = 30
    ):
        super().__init__()
        self.source = source
        self.camera_id = camera_id
        self.enable_recognition = enable_recognition
        self.enable_hwaccel = enable_hwaccel
        self.enable_recording = enable_recording
        self.target_fps = target_fps
        
        # Adapter de mídia
        self.media_adapter = MediaAdapter(source, enable_hwaccel)
        self.media_player: Optional[MediaPlayer] = None
        self.opencv_capture: Optional[cv2.VideoCapture] = None
        
        # Controle de timing
        self._pts = 0
        self._frame_time = 1.0 / target_fps
        self._last_frame_time = 0
        
        # Estado e controle
        self._current_frame: Optional[np.ndarray] = None
        self._is_playing = False
        self._loop_video = True  # Para arquivos de vídeo
        
        # Gravação (opcional)
        self.video_writer: Optional[cv2.VideoWriter] = None
        
        # Estatísticas
        self.stats = {
            'frames_generated': 0,
            'frames_dropped': 0,
            'recognition_calls': 0,
            'avg_fps': 0,
            'start_time': time.time()
        }
        
        logger.info(f"🎬 EnhancedVideoTrack criado: {source} -> {self.media_adapter.media_type}")
    
    async def start(self) -> bool:
        """Iniciar o track de vídeo"""
        try:
            # Tentar configurar MediaPlayer primeiro
            self.media_player = await self.media_adapter.setup_media_player()
            
            if self.media_player:
                logger.info(f"✅ MediaPlayer configurado para {self.media_adapter.media_type}")
                self._is_playing = True
                return True
            
            # Fallback para OpenCV se MediaPlayer falhar
            if self.media_adapter.media_type in [MediaType.FILE, MediaType.RTSP, MediaType.WEBCAM]:
                self.opencv_capture = await self.media_adapter.create_opencv_capture()
                if self.opencv_capture:
                    logger.info(f"✅ OpenCV capture configurado para {self.media_adapter.media_type}")
                    self._is_playing = True
                    return True
            
            # Para imagens estáticas
            if self.media_adapter.media_type == MediaType.IMAGE:
                self._current_frame = self._load_static_image()
                if self._current_frame is not None:
                    logger.info(f"✅ Imagem estática carregada")
                    self._is_playing = True
                    return True
            
            # Fallback final para vídeo de teste
            logger.warning(f"Fallback para vídeo de teste")
            self._is_playing = True
            return True
            
        except Exception as e:
            logger.error(f"❌ Erro ao iniciar track: {e}")
            return False
    
    async def stop(self):
        """Parar o track"""
        self._is_playing = False
        
        if self.media_player:
            self.media_player.audio.stop()
            self.media_player.video.stop()
            self.media_player = None
        
        if self.opencv_capture:
            self.opencv_capture.release()
            self.opencv_capture = None
        
        if self.video_writer:
            self.video_writer.release()
            self.video_writer = None
        
        logger.info(f"🛑 Track parado: {self.camera_id}")
    
    async def recv(self):
        """Método principal - fornece frames para WebRTC"""
        try:
            # Controle de FPS
            current_time = time.time()
            time_since_last = current_time - self._last_frame_time
            
            if time_since_last < self._frame_time:
                await asyncio.sleep(self._frame_time - time_since_last)
            
            self._last_frame_time = time.time()
            
            # Obter frame baseado no tipo de mídia
            frame = await self._get_next_frame()
            
            if frame is None:
                # Fallback para frame de teste
                frame = self._generate_test_frame()
            
            # Aplicar reconhecimento facial se habilitado
            if self.enable_recognition:
                frame = await self._apply_recognition(frame)
            
            # Salvar para gravação se habilitado
            if self.enable_recording and self.video_writer:
                self.video_writer.write(cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
            
            # Converter para VideoFrame
            av_frame = av.VideoFrame.from_ndarray(frame, format='rgb24')
            
            # Configurar timing
            self._pts += int(90000 / self.target_fps)
            av_frame.pts = self._pts
            av_frame.time_base = av.time_base.Fraction(1, 90000)
            
            # Atualizar estatísticas
            self.stats['frames_generated'] += 1
            self._update_fps_stats()
            
            return av_frame
            
        except Exception as e:
            logger.error(f"❌ Erro ao gerar frame: {e}")
            self.stats['frames_dropped'] += 1
            return await self._generate_fallback_frame()
    
    async def _get_next_frame(self) -> Optional[np.ndarray]:
        """Obter próximo frame baseado no tipo de mídia"""
        if self.media_player:
            return await self._get_frame_from_media_player()
        elif self.opencv_capture:
            return await self._get_frame_from_opencv()
        elif self.media_adapter.media_type == MediaType.IMAGE:
            return self._current_frame.copy() if self._current_frame is not None else None
        else:
            return None
    
    async def _get_frame_from_media_player(self) -> Optional[np.ndarray]:
        """Obter frame do MediaPlayer (aiortc)"""
        try:
            if not self.media_player or not self.media_player.video:
                return None
            
            # Receber frame do MediaPlayer
            frame = await self.media_player.video.recv()
            
            # Converter av.VideoFrame para numpy
            img = frame.to_ndarray(format='rgb24')
            
            return img
            
        except Exception as e:
            logger.debug(f"MediaPlayer frame error: {e}")
            
            # Se chegou ao fim do vídeo e pode fazer loop
            if self.media_adapter.is_loop_capable() and self._loop_video:
                logger.info(f"🔄 Reiniciando vídeo: {self.source}")
                await self._restart_media_player()
            
            return None
    
    async def _get_frame_from_opencv(self) -> Optional[np.ndarray]:
        """Obter frame do OpenCV VideoCapture"""
        try:
            if not self.opencv_capture:
                return None
            
            ret, frame = self.opencv_capture.read()
            
            if not ret:
                # Fim do vídeo ou erro
                if self.media_adapter.is_loop_capable() and self._loop_video:
                    logger.info(f"🔄 Reiniciando vídeo OpenCV: {self.source}")
                    self.opencv_capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    ret, frame = self.opencv_capture.read()
                
                if not ret:
                    return None
            
            # Converter BGR -> RGB
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            return frame_rgb
            
        except Exception as e:
            logger.error(f"OpenCV frame error: {e}")
            return None
    
    def _load_static_image(self) -> Optional[np.ndarray]:
        """Carregar imagem estática"""
        try:
            if not os.path.exists(self.source):
                return None
            
            # Carregar com OpenCV
            img_bgr = cv2.imread(self.source)
            if img_bgr is None:
                return None
            
            # Converter BGR -> RGB
            img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
            
            # Redimensionar se necessário (para performance)
            height, width = img_rgb.shape[:2]
            if width > 1920 or height > 1080:
                scale = min(1920/width, 1080/height)
                new_width = int(width * scale)
                new_height = int(height * scale)
                img_rgb = cv2.resize(img_rgb, (new_width, new_height))
            
            logger.info(f"📷 Imagem carregada: {img_rgb.shape}")
            return img_rgb
            
        except Exception as e:
            logger.error(f"Erro ao carregar imagem: {e}")
            return None
    
    async def _restart_media_player(self):
        """Reiniciar MediaPlayer para loop"""
        try:
            if self.media_player:
                self.media_player.audio.stop()
                self.media_player.video.stop()
            
            # Aguardar um momento
            await asyncio.sleep(0.1)
            
            # Recriar MediaPlayer
            self.media_player = await self.media_adapter.setup_media_player()
            
        except Exception as e:
            logger.error(f"Erro ao reiniciar MediaPlayer: {e}")
    
    async def _apply_recognition(self, frame: np.ndarray) -> np.ndarray:
        """Aplicar reconhecimento facial com overlay futurístico"""
        try:
            self.stats['recognition_calls'] += 1
            
            # Processar reconhecimento a cada N frames para performance
            recognition_interval = 8  # Reconhecer a cada 8 frames
            if self.stats['recognition_calls'] % recognition_interval != 0:
                # Reutilizar últimos resultados com animações suaves
                if hasattr(self, '_last_recognition_results') and self._last_recognition_results:
                    return self._draw_futuristic_overlay(frame, self._last_recognition_results)
                else:
                    return self._draw_scanning_overlay(frame)
            
            # Fazer reconhecimento usando Recognition Worker
            try:
                from app.api.services.recognition_client import recognition_client
                
                # Otimizar frame para reconhecimento
                height, width = frame.shape[:2]
                scale_factor = 1.0
                if width > 640:
                    scale_factor = 640 / width
                    new_width = 640
                    new_height = int(height * scale_factor)
                    frame_resized = cv2.resize(frame, (new_width, new_height))
                else:
                    frame_resized = frame
                
                # Converter para bytes
                _, frame_encoded = cv2.imencode('.jpg', cv2.cvtColor(frame_resized, cv2.COLOR_RGB2BGR))
                frame_bytes = frame_encoded.tobytes()
                
                # Reconhecimento via Socket.IO
                recognitions = await recognition_client.recognize_faces(frame_bytes)
                
                if recognitions:
                    logger.debug(f"WebRTC AI: {len(recognitions)} faces detectadas [{self.camera_id}]")
                    
                    # Escalar bounding boxes de volta
                    if scale_factor != 1.0:
                        scale_back = 1.0 / scale_factor
                        for recognition in recognitions:
                            if 'bbox' in recognition and len(recognition['bbox']) >= 4:
                                bbox = recognition['bbox']
                                recognition['bbox'] = [
                                    int(bbox[0] * scale_back),
                                    int(bbox[1] * scale_back),
                                    int(bbox[2] * scale_back),
                                    int(bbox[3] * scale_back)
                                ]
                    
                    # Salvar resultados com timestamp
                    self._last_recognition_results = recognitions
                    self._last_recognition_time = time.time()
                    
                    return self._draw_futuristic_overlay(frame, recognitions)
                else:
                    # Sem detecções - modo scanning
                    self._last_recognition_results = None
                    return self._draw_scanning_overlay(frame)
                    
            except Exception as e:
                logger.warning(f"Recognition Worker connection error: {e}")
                return self._draw_error_overlay(frame, str(e))
                
        except Exception as e:
            logger.error(f"Critical recognition error: {e}")
            return frame
    
    def _draw_futuristic_overlay(self, frame: np.ndarray, recognitions: list) -> np.ndarray:
        """Desenhar overlay futurístico sofisticado"""
        try:
            height, width = frame.shape[:2]
            overlay = frame.copy()
            
            # Cores futurísticas
            colors = {
                'known': (0, 255, 150),      # Verde ciano
                'unknown': (255, 120, 0),    # Laranja vibrante  
                'accent': (100, 200, 255),   # Azul claro
                'glow': (255, 255, 255),     # Branco brilhante
                'dark': (20, 20, 20),        # Cinza escuro
                'success': (0, 255, 100),    # Verde brilhante
            }
            
            # Contador de faces
            known_count = 0
            unknown_count = 0
            
            for i, recognition in enumerate(recognitions):
                bbox = recognition.get('bbox', [])
                person_name = recognition.get('person_name', 'UNKNOWN')
                confidence = recognition.get('confidence', 0.0)
                is_unknown = recognition.get('is_unknown', False)
                
                if len(bbox) >= 4:
                    x, y, w, h = bbox
                    
                    # Determinar status
                    if is_unknown or not recognition.get('person_id'):
                        status = 'unknown'
                        label = f"UNIDENTIFIED"
                        conf_text = f"CONF: {confidence:.1%}"
                        color = colors['unknown']
                        unknown_count += 1
                    else:
                        status = 'known'
                        label = f"{person_name.upper()}"
                        conf_text = f"VERIFIED: {confidence:.1%}"
                        color = colors['known']
                        known_count += 1
                    
                    # === DESENHO DO FRAME PRINCIPAL ===
                    # Cantos futurísticos
                    corner_size = 25
                    line_thickness = 3
                    
                    # Canto superior esquerdo
                    cv2.line(overlay, (x, y), (x + corner_size, y), color, line_thickness)
                    cv2.line(overlay, (x, y), (x, y + corner_size), color, line_thickness)
                    
                    # Canto superior direito
                    cv2.line(overlay, (x + w - corner_size, y), (x + w, y), color, line_thickness)
                    cv2.line(overlay, (x + w, y), (x + w, y + corner_size), color, line_thickness)
                    
                    # Canto inferior esquerdo
                    cv2.line(overlay, (x, y + h - corner_size), (x, y + h), color, line_thickness)
                    cv2.line(overlay, (x, y + h), (x + corner_size, y + h), color, line_thickness)
                    
                    # Canto inferior direito
                    cv2.line(overlay, (x + w - corner_size, y + h), (x + w, y + h), color, line_thickness)
                    cv2.line(overlay, (x + w, y + h - corner_size), (x + w, y + h), color, line_thickness)
                    
                    # === PAINEL DE INFORMAÇÕES ===
                    panel_height = 60
                    panel_y = max(10, y - panel_height - 10)
                    panel_width = max(200, len(label) * 12)
                    
                    # Fundo semitransparente do painel
                    panel_overlay = overlay.copy()
                    cv2.rectangle(panel_overlay, 
                                 (x, panel_y), 
                                 (x + panel_width, panel_y + panel_height), 
                                 colors['dark'], -1)
                    cv2.addWeighted(overlay, 0.7, panel_overlay, 0.3, 0, overlay)
                    
                    # Borda do painel
                    cv2.rectangle(overlay, 
                                 (x, panel_y), 
                                 (x + panel_width, panel_y + panel_height), 
                                 color, 2)
                    
                    # === TEXTO DO PAINEL ===
                    # Título principal
                    cv2.putText(overlay, label, 
                               (x + 10, panel_y + 20), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.6, colors['glow'], 2)
                    
                    # Confiança
                    cv2.putText(overlay, conf_text, 
                               (x + 10, panel_y + 40), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.4, colors['accent'], 1)
                    
                    # ID único (canto do painel)
                    id_text = f"ID:{i+1:02d}"
                    cv2.putText(overlay, id_text, 
                               (x + panel_width - 50, panel_y + 20), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.4, colors['accent'], 1)
                    
                    # === LINHA DE CONEXÃO ===
                    # Linha conectando painel à face
                    center_x = x + w // 2
                    cv2.line(overlay, 
                            (center_x, panel_y + panel_height), 
                            (center_x, y), 
                            color, 1)
                    
                    # Ponto central
                    cv2.circle(overlay, (center_x, y), 4, color, -1)
                    cv2.circle(overlay, (center_x, y), 6, colors['glow'], 1)
            
            # === HUD PRINCIPAL ===
            self._draw_main_hud(overlay, known_count, unknown_count, colors, width, height)
            
            # === ANIMAÇÕES SUTIS ===
            self._add_scanning_animation(overlay, colors, width, height)
            
            return overlay
            
        except Exception as e:
            logger.error(f"Erro no overlay futurístico: {e}")
            return frame
    
    def _draw_scanning_overlay(self, frame: np.ndarray) -> np.ndarray:
        """Overlay de scanning quando não há faces detectadas"""
        try:
            height, width = frame.shape[:2]
            overlay = frame.copy()
            
            colors = {
                'scan': (100, 200, 255),
                'accent': (0, 255, 200),
                'text': (200, 200, 255)
            }
            
            # Animação de scanning
            current_time = time.time()
            scan_progress = (current_time % 3.0) / 3.0  # Ciclo de 3 segundos
            
            # Linha de scan horizontal
            scan_y = int(height * 0.2 + (height * 0.6) * scan_progress)
            cv2.line(overlay, (50, scan_y), (width - 50, scan_y), colors['scan'], 2)
            
            # Efeito de glow na linha
            for offset in range(1, 4):
                alpha = 0.3 / offset
                scan_overlay = overlay.copy()
                cv2.line(scan_overlay, 
                        (50, scan_y - offset), (width - 50, scan_y - offset), 
                        colors['scan'], 1)
                cv2.line(scan_overlay, 
                        (50, scan_y + offset), (width - 50, scan_y + offset), 
                        colors['scan'], 1)
                cv2.addWeighted(overlay, 1 - alpha, scan_overlay, alpha, 0, overlay)
            
            # HUD de scanning
            self._draw_scanning_hud(overlay, colors, width, height, scan_progress)
            
            return overlay
            
        except Exception as e:
            logger.error(f"Erro no overlay de scanning: {e}")
            return frame
    
    def _draw_error_overlay(self, frame: np.ndarray, error_msg: str) -> np.ndarray:
        """Overlay de erro elegante"""
        try:
            height, width = frame.shape[:2]
            overlay = frame.copy()
            
            colors = {
                'error': (100, 100, 255),
                'warning': (0, 200, 255),
                'text': (255, 255, 255)
            }
            
            # Painel de erro
            panel_width = 300
            panel_height = 80
            panel_x = (width - panel_width) // 2
            panel_y = 50
            
            # Fundo
            error_overlay = overlay.copy()
            cv2.rectangle(error_overlay, 
                         (panel_x, panel_y), 
                         (panel_x + panel_width, panel_y + panel_height), 
                         (20, 20, 40), -1)
            cv2.addWeighted(overlay, 0.6, error_overlay, 0.4, 0, overlay)
            
            # Borda
            cv2.rectangle(overlay, 
                         (panel_x, panel_y), 
                         (panel_x + panel_width, panel_y + panel_height), 
                         colors['error'], 2)
            
            # Texto
            cv2.putText(overlay, "AI CONNECTION ERROR", 
                       (panel_x + 20, panel_y + 30), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, colors['error'], 2)
            
            cv2.putText(overlay, "Retrying...", 
                       (panel_x + 20, panel_y + 55), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, colors['warning'], 1)
            
            return overlay
            
        except Exception as e:
            logger.error(f"Erro no overlay de erro: {e}")
            return frame
    
    def _draw_main_hud(self, overlay, known_count, unknown_count, colors, width, height):
        """Desenhar HUD principal com estatísticas"""
        try:
            # Painel principal do HUD
            hud_width = 280
            hud_height = 90
            hud_x = width - hud_width - 20
            hud_y = 20
            
            # Fundo do HUD
            hud_overlay = overlay.copy()
            cv2.rectangle(hud_overlay, 
                         (hud_x, hud_y), 
                         (hud_x + hud_width, hud_y + hud_height), 
                         (10, 10, 30), -1)
            cv2.addWeighted(overlay, 0.8, hud_overlay, 0.2, 0, overlay)
            
            # Borda do HUD
            cv2.rectangle(overlay, 
                         (hud_x, hud_y), 
                         (hud_x + hud_width, hud_y + hud_height), 
                         colors['accent'], 2)
            
            # Título
            cv2.putText(overlay, "AI SURVEILLANCE", 
                       (hud_x + 10, hud_y + 25), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, colors['glow'], 2)
            
            # Estatísticas
            stats_text = f"VERIFIED: {known_count:02d}  |  UNKNOWN: {unknown_count:02d}"
            cv2.putText(overlay, stats_text, 
                       (hud_x + 10, hud_y + 50), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, colors['success'], 1)
            
            # FPS
            fps_text = f"FPS: {self.stats.get('avg_fps', 0):.1f}"
            cv2.putText(overlay, fps_text, 
                       (hud_x + 10, hud_y + 70), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, colors['accent'], 1)
            
            # Timestamp
            timestamp = time.strftime("%H:%M:%S")
            cv2.putText(overlay, timestamp, 
                       (hud_x + 180, hud_y + 70), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, colors['accent'], 1)
            
        except Exception as e:
            logger.error(f"Erro no HUD principal: {e}")
    
    def _draw_scanning_hud(self, overlay, colors, width, height, progress):
        """HUD para modo de scanning"""
        try:
            # Título central
            title = "FACIAL RECOGNITION ACTIVE"
            title_size = cv2.getTextSize(title, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)[0]
            title_x = (width - title_size[0]) // 2
            title_y = 60
            
            cv2.putText(overlay, title, 
                       (title_x, title_y), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, colors['accent'], 2)
            
            # Barra de progresso de scanning
            bar_width = 200
            bar_height = 8
            bar_x = (width - bar_width) // 2
            bar_y = title_y + 30
            
            # Fundo da barra
            cv2.rectangle(overlay, 
                         (bar_x, bar_y), 
                         (bar_x + bar_width, bar_y + bar_height), 
                         (50, 50, 50), -1)
            
            # Progresso
            progress_width = int(bar_width * progress)
            cv2.rectangle(overlay, 
                         (bar_x, bar_y), 
                         (bar_x + progress_width, bar_y + bar_height), 
                         colors['scan'], -1)
            
            # Status
            status = "SCANNING FOR FACES..."
            status_size = cv2.getTextSize(status, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)[0]
            status_x = (width - status_size[0]) // 2
            
            cv2.putText(overlay, status, 
                       (status_x, bar_y + 30), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, colors['text'], 1)
            
        except Exception as e:
            logger.error(f"Erro no HUD de scanning: {e}")
    
    def _add_scanning_animation(self, overlay, colors, width, height):
        """Adicionar animações sutis de scanning"""
        try:
            current_time = time.time()
            
            # Pulso sutil nos cantos
            pulse_intensity = abs(np.sin(current_time * 2)) * 0.3 + 0.1
            pulse_color = tuple(int(c * pulse_intensity) for c in colors['accent'])
            
            # Pequenos indicadores nos cantos
            corner_size = 8
            
            # Canto superior esquerdo
            cv2.line(overlay, (20, 20), (20 + corner_size, 20), pulse_color, 2)
            cv2.line(overlay, (20, 20), (20, 20 + corner_size), pulse_color, 2)
            
            # Canto superior direito
            cv2.line(overlay, (width - 20 - corner_size, 20), (width - 20, 20), pulse_color, 2)
            cv2.line(overlay, (width - 20, 20), (width - 20, 20 + corner_size), pulse_color, 2)
            
            # Canto inferior esquerdo
            cv2.line(overlay, (20, height - 20 - corner_size), (20, height - 20), pulse_color, 2)
            cv2.line(overlay, (20, height - 20), (20 + corner_size, height - 20), pulse_color, 2)
            
            # Canto inferior direito
            cv2.line(overlay, (width - 20 - corner_size, height - 20), (width - 20, height - 20), pulse_color, 2)
            cv2.line(overlay, (width - 20, height - 20 - corner_size), (width - 20, height - 20), pulse_color, 2)
            
        except Exception as e:
            logger.error(f"Erro na animação de scanning: {e}")
    
    def _generate_test_frame(self) -> np.ndarray:
        """Gerar frame de teste"""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        
        # Background gradiente
        for y in range(480):
            frame[y, :, 0] = int(50 + (y / 480) * 100)  # Red gradient
            frame[y, :, 2] = int(100 - (y / 480) * 50)  # Blue gradient
        
        # Informações
        timestamp = time.strftime("%H:%M:%S")
        
        cv2.putText(frame, f"Camera {self.camera_id}", (50, 80), 
                   cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 255), 2)
        
        cv2.putText(frame, f"Source: {self.media_adapter.media_type.upper()}", (50, 120), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (200, 200, 200), 1)
        
        cv2.putText(frame, timestamp, (50, 160), 
                   cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)
        
        cv2.putText(frame, f"FPS: {self.stats['avg_fps']:.1f}", (50, 200), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        
        # Animação
        pulse = int(50 + 30 * abs(np.sin(time.time() * 2)))
        cv2.circle(frame, (540, 80), pulse, (255, 255, 255), 2)
        cv2.putText(frame, "LIVE", (520, 85), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        return frame
    
    async def _generate_fallback_frame(self):
        """Gerar frame de fallback em caso de erro"""
        frame = self._generate_test_frame()
        
        # Adicionar indicação de erro
        cv2.putText(frame, "ERROR - Fallback Mode", (50, 240), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 100, 100), 2)
        
        av_frame = av.VideoFrame.from_ndarray(frame, format='rgb24')
        self._pts += int(90000 / self.target_fps)
        av_frame.pts = self._pts
        av_frame.time_base = av.time_base.Fraction(1, 90000)
        
        return av_frame
    
    def _update_fps_stats(self):
        """Atualizar estatísticas de FPS"""
        elapsed = time.time() - self.stats['start_time']
        if elapsed > 0:
            self.stats['avg_fps'] = self.stats['frames_generated'] / elapsed
    
    def get_stats(self) -> Dict[str, Any]:
        """Obter estatísticas do track"""
        return {
            **self.stats,
            'media_info': self.media_adapter.get_media_info(),
            'is_playing': self._is_playing,
            'target_fps': self.target_fps,
            'enable_recognition': self.enable_recognition,
            'enable_recording': self.enable_recording
        }
    
    def enable_video_recording(self, output_path: str, fps: int = None):
        """Habilitar gravação de vídeo"""
        try:
            if fps is None:
                fps = self.target_fps
            
            # Criar diretório se necessário
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            
            # Configurar VideoWriter
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            self.video_writer = cv2.VideoWriter(output_path, fourcc, fps, (640, 480))
            
            if self.video_writer.isOpened():
                self.enable_recording = True
                logger.info(f"📹 Gravação habilitada: {output_path}")
            else:
                logger.error(f"Erro ao configurar gravação: {output_path}")
                
        except Exception as e:
            logger.error(f"Erro ao habilitar gravação: {e}")
    
    def disable_video_recording(self):
        """Desabilitar gravação de vídeo"""
        self.enable_recording = False
        if self.video_writer:
            self.video_writer.release()
            self.video_writer = None
            logger.info("📹 Gravação desabilitada")