#!/usr/bin/env python3
"""
GStreamer NVENC WebRTC Server - High Performance
Substitui aiortc+PyAV por GStreamer+NVENC para máxima performance
"""

import asyncio
import json
import logging
import os
import sys
import threading
import time
import uuid
from typing import Dict, List, Optional, Any
from datetime import datetime
import socketio
import numpy as np
import cv2
import base64

# Importação segura do GStreamer
try:
    from app.core.gstreamer_init import initialize_gstreamer, safe_import_gstreamer
    
    # Inicializar GStreamer
    initialize_gstreamer()
    Gst, GstApp, GLib, GSTREAMER_AVAILABLE, gstreamer_error = safe_import_gstreamer()
    
    if not GSTREAMER_AVAILABLE:
        raise ImportError(f"GStreamer não disponível: {gstreamer_error}")
        
except ImportError as e:
    print(f"❌ ERRO: GStreamer não disponível: {e}")
    print("❌ Este servidor requer GStreamer com NVENC para funcionar")
    sys.exit(1)

from fastapi import FastAPI, WebSocket, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.websockets import WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class GStreamerNVENCPipeline:
    """Pipeline GStreamer com NVENC para encoding de hardware"""
    
    def __init__(self, camera_id: str, rtsp_url: str, enable_recognition: bool = False):
        self.camera_id = camera_id
        self.rtsp_url = rtsp_url
        self.enable_recognition = enable_recognition
        
        # Pipeline components
        self.input_pipeline = None
        self.output_pipeline = None
        self.appsrc = None
        self.appsink = None
        
        # Recognition integration
        self._recognition_client = None
        self._recognition_connected = False
        self._last_recognition_results = None
        self._last_recognition_time = 0
        self._recognition_interval = 0.5
        
        # Frame buffers
        self._latest_encoded_frame = None
        self._frame_lock = threading.Lock()
        
        # Statistics
        self.stats = {
            'frames_received': 0,
            'frames_encoded': 0,
            'frames_sent': 0,
            'encoding_errors': 0,
            'last_frame_time': 0
        }
        
        self.is_running = False
        
    async def initialize(self) -> bool:
        """Inicializar pipelines GStreamer"""
        try:
            logger.info(f"🚀 Inicializando GStreamer NVENC pipeline para câmera {self.camera_id}")
            
            # Pipeline de entrada (RTSP → Decodificação GPU → Frame callback)
            input_pipeline_str = f"""
            rtspsrc location={self.rtsp_url} protocols=tcp latency=100
                ! rtph264depay
                ! h264parse config-interval=-1
                ! nvh264dec
                ! queue leaky=2 max-size-buffers=10
                ! videoconvert
                ! video/x-raw,format=NV12,width=1920,height=1080
                ! queue leaky=2 max-size-buffers=5
                ! appsink name=input_sink emit-signals=true max-buffers=3 drop=true sync=false
            """
            
            # Pipeline de saída (Frame input → NVENC → RTP → WebRTC)
            output_pipeline_str = """
            appsrc name=frame_source format=3 caps=video/x-raw,format=NV12,width=1920,height=1080,framerate=30/1
                ! queue leaky=2 max-size-buffers=5
                ! nvh264enc preset=low-latency-hq bitrate=2000 gop-size=30 
                ! video/x-h264,profile=baseline,level=3.1
                ! h264parse config-interval=-1
                ! queue leaky=2 max-size-buffers=5
                ! rtph264pay pt=96 ssrc=1234567890 timestamp-offset=0
                ! queue leaky=2 max-size-buffers=3
                ! appsink name=rtp_sink emit-signals=true max-buffers=3 drop=true sync=false
            """
            
            # Criar pipelines
            self.input_pipeline = Gst.parse_launch(input_pipeline_str.strip())
            self.output_pipeline = Gst.parse_launch(output_pipeline_str.strip())
            
            if not self.input_pipeline or not self.output_pipeline:
                raise RuntimeError("Falha ao criar pipelines GStreamer")
            
            # Obter elementos
            self.input_sink = self.input_pipeline.get_by_name("input_sink")
            self.appsrc = self.output_pipeline.get_by_name("frame_source")
            self.rtp_sink = self.output_pipeline.get_by_name("rtp_sink")
            
            # Configurar callbacks
            self.input_sink.connect("new-sample", self._on_input_frame)
            self.rtp_sink.connect("new-sample", self._on_encoded_frame)
            
            # Configurar appsrc
            self.appsrc.set_property("stream-type", 0)  # GST_APP_STREAM_TYPE_STREAM
            self.appsrc.set_property("is-live", True)
            self.appsrc.set_property("do-timestamp", True)
            self.appsrc.set_property("min-latency", 0)
            self.appsrc.set_property("max-latency", 0)
            
            # Inicializar recognition se habilitado
            if self.enable_recognition:
                await self._init_recognition()
            
            # Iniciar pipelines
            self.input_pipeline.set_state(Gst.State.PLAYING)
            self.output_pipeline.set_state(Gst.State.PLAYING)
            
            self.is_running = True
            logger.info(f"✅ GStreamer NVENC pipeline inicializado para câmera {self.camera_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Erro ao inicializar pipeline NVENC: {e}")
            return False
    
    async def _init_recognition(self):
        """Inicializar conexão com Recognition Worker"""
        try:
            logger.info(f"🔌 Conectando ao Recognition Worker para câmera {self.camera_id}")
            
            self._recognition_client = socketio.AsyncClient()
            
            @self._recognition_client.event
            async def connect():
                logger.info(f"✅ WebRTC-NVENC conectado ao Recognition Worker - câmera {self.camera_id}")
                self._recognition_connected = True
            
            @self._recognition_client.event
            async def disconnect():
                logger.warning(f"🔌 WebRTC-NVENC desconectado do Recognition Worker - câmera {self.camera_id}")
                self._recognition_connected = False
            
            @self._recognition_client.event
            async def recognition_result(data):
                """Receber resultado do Recognition Worker"""
                try:
                    self._last_recognition_results = data
                    faces_count = len(data.get('recognitions', []))
                    logger.info(f"🎯 Câmera {self.camera_id}: {faces_count} faces reconhecidas")
                except Exception as e:
                    logger.error(f"❌ Erro ao processar resultado: {e}")
            
            # Conectar
            await self._recognition_client.connect("http://127.0.0.1:17235")
            
        except Exception as e:
            logger.error(f"❌ Falha ao conectar com Recognition Worker: {e}")
            self.enable_recognition = False
    
    def _on_input_frame(self, appsink):
        """Callback para frames de entrada (RTSP decodificado)"""
        try:
            sample = appsink.emit('pull-sample')
            if not sample:
                return Gst.FlowReturn.ERROR
            
            buffer = sample.get_buffer()
            caps = sample.get_caps()
            
            if not buffer or not caps:
                return Gst.FlowReturn.ERROR
            
            # Mapear buffer
            success, map_info = buffer.map(Gst.MapFlags.READ)
            if not success:
                return Gst.FlowReturn.ERROR
            
            # Obter dimensões
            structure = caps.get_structure(0)
            width = structure.get_value("width")
            height = structure.get_value("height")
            format_str = structure.get_value("format")
            
            # Processar frame
            current_time = time.time()
            self.stats['frames_received'] += 1
            self.stats['last_frame_time'] = current_time
            
            # Aplicar recognition overlay se habilitado
            frame_data = None
            if self.enable_recognition:
                # Converter para numpy array
                if format_str == 'NV12':
                    buffer_size = len(map_info.data)
                    expected_size = height * width * 3 // 2
                    
                    if buffer_size >= expected_size:
                        data_array = np.frombuffer(map_info.data, dtype=np.uint8)
                        yuv_frame = data_array[:expected_size].reshape((height * 3 // 2, width))
                        bgr_frame = cv2.cvtColor(yuv_frame, cv2.COLOR_YUV2BGR_NV12)
                        
                        # Aplicar overlay
                        bgr_with_overlay = self._apply_recognition_overlay(bgr_frame, current_time)
                        
                        # Converter de volta para NV12
                        yuv_with_overlay = cv2.cvtColor(bgr_with_overlay, cv2.COLOR_BGR2YUV_NV12)
                        frame_data = yuv_with_overlay.tobytes()
            
            if frame_data is None:
                # Usar frame original
                frame_data = map_info.data
            
            # Criar novo buffer para o appsrc
            out_buffer = Gst.Buffer.new_allocate(None, len(frame_data), None)
            out_buffer.fill(0, frame_data)
            
            # Enviar para pipeline de encoding
            ret = self.appsrc.emit('push-buffer', out_buffer)
            
            # Liberar buffer original
            buffer.unmap(map_info)
            
            return Gst.FlowReturn.OK
            
        except Exception as e:
            logger.error(f"❌ Erro no processamento de frame: {e}")
            return Gst.FlowReturn.ERROR
    
    def _apply_recognition_overlay(self, frame_bgr: np.ndarray, current_time: float) -> np.ndarray:
        """Aplicar overlay de reconhecimento facial"""
        try:
            # Processar recognition apenas no intervalo configurado
            time_since_last = current_time - self._last_recognition_time
            
            if time_since_last >= self._recognition_interval and self._recognition_connected:
                self._last_recognition_time = current_time
                
                # Enviar frame para recognition em background
                asyncio.create_task(self._process_recognition_async(frame_bgr.copy()))
            
            # Aplicar overlay baseado nos últimos resultados
            if self._last_recognition_results:
                return self._draw_recognition_overlay(frame_bgr, self._last_recognition_results)
            else:
                return self._draw_simple_overlay(frame_bgr)
                
        except Exception as e:
            logger.error(f"❌ Erro no overlay: {e}")
            return frame_bgr
    
    async def _process_recognition_async(self, frame_bgr: np.ndarray):
        """Enviar frame para Recognition Worker"""
        try:
            if not self._recognition_connected:
                return
            
            # Redimensionar e codificar
            frame_resized = cv2.resize(frame_bgr, (640, 480))
            _, buffer = cv2.imencode('.jpg', frame_resized, [cv2.IMWRITE_JPEG_QUALITY, 80])
            frame_b64 = base64.b64encode(buffer).decode('utf-8')
            
            # Enviar
            await self._recognition_client.emit('process_frame', {
                'camera_id': self.camera_id,
                'frame_data': frame_b64,
                'timestamp': datetime.now().isoformat()
            })
            
        except Exception as e:
            logger.error(f"❌ Erro ao enviar frame para recognition: {e}")
    
    def _draw_recognition_overlay(self, frame_bgr: np.ndarray, results) -> np.ndarray:
        """Desenhar overlay de reconhecimento"""
        frame_overlay = frame_bgr.copy()
        
        try:
            if results and 'recognitions' in results:
                for face_data in results['recognitions']:
                    bbox = face_data.get('bbox', [])
                    person_name = face_data.get('person_name', 'Desconhecido')
                    confidence = face_data.get('confidence', 0.0)
                    
                    if len(bbox) == 4:
                        x1, y1, x2, y2 = map(int, bbox)
                        
                        # Cor baseada no reconhecimento
                        if person_name != 'Desconhecido':
                            color = (0, 255, 0)  # Verde
                            label = f"{person_name} ({confidence:.2f})"
                        else:
                            color = (0, 0, 255)  # Vermelho
                            label = "Desconhecido"
                        
                        # Desenhar bbox e label
                        cv2.rectangle(frame_overlay, (x1, y1), (x2, y2), color, 2)
                        label_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)[0]
                        cv2.rectangle(frame_overlay, (x1, y1 - label_size[1] - 10), 
                                    (x1 + label_size[0], y1), color, -1)
                        cv2.putText(frame_overlay, label, (x1, y1 - 5), 
                                  cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        except Exception as e:
            logger.error(f"❌ Erro ao desenhar overlay: {e}")
        
        return frame_overlay
    
    def _draw_simple_overlay(self, frame_bgr: np.ndarray) -> np.ndarray:
        """Desenhar overlay simples"""
        cv2.putText(frame_bgr, "NVENC Recognition: ON", (10, 30), 
                  cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.circle(frame_bgr, (20, 60), 8, (0, 255, 0), -1)
        
        cv2.putText(frame_bgr, f"Camera: {self.camera_id}", (10, 100), 
                  cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        status = "CONNECTED" if self._recognition_connected else "DISCONNECTED"
        color = (0, 255, 0) if self._recognition_connected else (0, 0, 255)
        cv2.putText(frame_bgr, f"Recognition: {status}", (10, 120), 
                  cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
        
        return frame_bgr
    
    def _on_encoded_frame(self, appsink):
        """Callback para frames codificados (RTP H.264)"""
        try:
            sample = appsink.emit('pull-sample')
            if not sample:
                return Gst.FlowReturn.ERROR
            
            buffer = sample.get_buffer()
            if not buffer:
                return Gst.FlowReturn.ERROR
            
            # Mapear buffer RTP
            success, map_info = buffer.map(Gst.MapFlags.READ)
            if not success:
                return Gst.FlowReturn.ERROR
            
            # Armazenar frame codificado
            with self._frame_lock:
                self._latest_encoded_frame = bytes(map_info.data)
                self.stats['frames_encoded'] += 1
            
            buffer.unmap(map_info)
            return Gst.FlowReturn.OK
            
        except Exception as e:
            logger.error(f"❌ Erro no frame codificado: {e}")
            self.stats['encoding_errors'] += 1
            return Gst.FlowReturn.ERROR
    
    def get_latest_rtp_frame(self) -> Optional[bytes]:
        """Obter último frame RTP codificado"""
        with self._frame_lock:
            if self._latest_encoded_frame:
                self.stats['frames_sent'] += 1
                return self._latest_encoded_frame
            return None
    
    def get_stats(self) -> dict:
        """Obter estatísticas do pipeline"""
        return {
            'camera_id': self.camera_id,
            'is_running': self.is_running,
            'recognition_enabled': self.enable_recognition,
            'recognition_connected': self._recognition_connected,
            **self.stats
        }
    
    async def stop(self):
        """Parar pipeline"""
        try:
            self.is_running = False
            
            if self.input_pipeline:
                self.input_pipeline.set_state(Gst.State.NULL)
            
            if self.output_pipeline:
                self.output_pipeline.set_state(Gst.State.NULL)
            
            if self._recognition_client:
                await self._recognition_client.disconnect()
            
            logger.info(f"✅ Pipeline NVENC parado para câmera {self.camera_id}")
            
        except Exception as e:
            logger.error(f"❌ Erro ao parar pipeline: {e}")


class GStreamerNVENCWebRTCServer:
    """Servidor WebRTC com GStreamer+NVENC"""
    
    def __init__(self):
        self.app = FastAPI(title="GStreamer NVENC WebRTC Server")
        self.pipelines: Dict[str, GStreamerNVENCPipeline] = {}
        self.websocket_connections: Dict[str, WebSocket] = {}
        
        # Configurar CORS
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
        self.setup_routes()
        
        # Carregar câmeras do sistema
        self.load_cameras()
    
    def load_cameras(self):
        """Carregar câmeras do banco de dados"""
        try:
            # Por enquanto, usar câmera de teste
            test_cameras = {
                "cam1": {
                    "rtsp_url": "rtsp://admin:Extreme%40123@192.168.0.153:554/Streaming/channels/101",
                    "enable_recognition": True
                }
            }
            
            for camera_id, config in test_cameras.items():
                logger.info(f"📹 Carregando câmera {camera_id}: {config['rtsp_url']}")
                
        except Exception as e:
            logger.error(f"❌ Erro ao carregar câmeras: {e}")
    
    def setup_routes(self):
        """Configurar rotas da API"""
        
        @self.app.get("/")
        async def root():
            return {
                "message": "GStreamer NVENC WebRTC Server",
                "version": "1.0.0",
                "active_pipelines": len(self.pipelines),
                "capabilities": ["NVENC", "Recognition", "Low-Latency"]
            }
        
        @self.app.get("/stats")
        async def get_stats():
            """Obter estatísticas de todos os pipelines"""
            stats = {}
            for camera_id, pipeline in self.pipelines.items():
                stats[camera_id] = pipeline.get_stats()
            return stats
        
        @self.app.websocket("/ws/{camera_id}")
        async def websocket_camera_endpoint(websocket: WebSocket, camera_id: str):
            """Endpoint WebSocket para streaming RTP"""
            await websocket.accept()
            
            connection_id = str(uuid.uuid4())
            self.websocket_connections[connection_id] = websocket
            
            logger.info(f"🔌 Nova conexão WebSocket para câmera {camera_id}: {connection_id}")
            
            try:
                # Inicializar pipeline se não existir
                if camera_id not in self.pipelines:
                    await self._create_pipeline(camera_id)
                
                pipeline = self.pipelines.get(camera_id)
                if not pipeline:
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "message": "Pipeline não disponível"
                    }))
                    return
                
                # Enviar confirmação de conexão
                await websocket.send_text(json.dumps({
                    "type": "connected",
                    "camera_id": camera_id,
                    "connection_id": connection_id,
                    "encoding": "NVENC+H264+RTP"
                }))
                
                # Loop de streaming RTP
                while True:
                    # Obter frame RTP codificado
                    rtp_frame = pipeline.get_latest_rtp_frame()
                    if rtp_frame:
                        # Enviar frame RTP via WebSocket (base64)
                        frame_b64 = base64.b64encode(rtp_frame).decode('utf-8')
                        await websocket.send_text(json.dumps({
                            "type": "rtp_frame",
                            "data": frame_b64,
                            "timestamp": time.time()
                        }))
                    
                    # Controle de FPS
                    await asyncio.sleep(1/30)  # 30 FPS
                    
            except WebSocketDisconnect:
                logger.info(f"🔌 Conexão WebSocket desconectada: {connection_id}")
            except Exception as e:
                logger.error(f"❌ Erro na conexão WebSocket: {e}")
            finally:
                if connection_id in self.websocket_connections:
                    del self.websocket_connections[connection_id]
    
    async def _create_pipeline(self, camera_id: str):
        """Criar pipeline NVENC para câmera"""
        try:
            # URL RTSP padrão
            rtsp_url = "rtsp://admin:Extreme%40123@192.168.0.153:554/Streaming/channels/101"
            
            # Criar pipeline
            pipeline = GStreamerNVENCPipeline(
                camera_id=camera_id,
                rtsp_url=rtsp_url,
                enable_recognition=True
            )
            
            # Inicializar
            if await pipeline.initialize():
                self.pipelines[camera_id] = pipeline
                logger.info(f"✅ Pipeline NVENC criado para câmera {camera_id}")
            else:
                logger.error(f"❌ Falha ao criar pipeline para câmera {camera_id}")
                
        except Exception as e:
            logger.error(f"❌ Erro ao criar pipeline: {e}")
    
    async def start_server(self, host: str = "0.0.0.0", port: int = 8767):
        """Iniciar servidor"""
        logger.info(f"🚀 Iniciando GStreamer NVENC WebRTC Server em {host}:{port}")
        
        config = uvicorn.Config(
            app=self.app,
            host=host,
            port=port,
            log_level="info"
        )
        
        server = uvicorn.Server(config)
        await server.serve()


if __name__ == "__main__":
    async def main():
        server = GStreamerNVENCWebRTCServer()
        await server.start_server()
    
    asyncio.run(main())