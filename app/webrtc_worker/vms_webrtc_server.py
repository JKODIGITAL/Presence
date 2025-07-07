#!/usr/bin/env python3
"""
VMS WebRTC Server - Sistema de Video Management com WebRTC para múltiplas câmeras
Baseado no GstWebRTC_Python mas adaptado para integração com o sistema Presence
"""

import asyncio
import json
import ssl
import websockets
import logging
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Set
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import uvicorn

from .gst_webrtc_pipeline_builder import VMS_WebRTCManager, RTSPPipelineBuilder, check_gstreamer_plugins

logger = logging.getLogger(__name__)

class WebRTCConnection:
    """Representação de uma conexão WebRTC"""
    
    def __init__(self, connection_id: str, websocket: WebSocket, camera_id: str = None):
        self.connection_id = connection_id
        self.websocket = websocket
        self.camera_id = camera_id
        self.pipeline: Optional[RTSPPipelineBuilder] = None
        self.is_connected = True
        self.created_at = datetime.now()
    
    async def send_message(self, message: dict):
        """Enviar mensagem via WebSocket"""
        if self.is_connected:
            try:
                await self.websocket.send_text(json.dumps(message))
            except Exception as e:
                logger.error(f"Error sending message to {self.connection_id}: {e}")
                self.is_connected = False
    
    async def close(self):
        """Fechar conexão"""
        self.is_connected = False
        try:
            await self.websocket.close()
        except:
            pass


class VMS_WebRTCServer:
    """Servidor WebRTC para Video Management System"""
    
    def __init__(self, port: int = 17236):
        self.port = port
        self.vms_manager = VMS_WebRTCManager()
        self.connections: Dict[str, WebRTCConnection] = {}
        self.camera_subscribers: Dict[str, Set[str]] = {}  # camera_id -> set of connection_ids
        
        # FastAPI app para REST endpoints
        self.app = FastAPI(title="VMS WebRTC Server", version="1.0.0")
        self._setup_fastapi_routes()
        
    def _setup_fastapi_routes(self):
        """Configurar rotas REST da API"""
        
        # Configurar CORS
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
        @self.app.get("/")
        async def root():
            return {"message": "VMS WebRTC Server", "version": "1.0.0"}
        
        @self.app.get("/cameras")
        async def get_cameras():
            """Listar câmeras disponíveis"""
            stats = self.vms_manager.get_stats()
            return {
                "cameras": list(stats['cameras'].keys()),
                "total": stats['total_cameras'],
                "active": stats['active_cameras']
            }
        
        @self.app.post("/cameras/{camera_id}")
        async def add_camera(camera_id: str, camera_data: dict):
            """Adicionar nova câmera"""
            rtsp_url = camera_data.get('rtsp_url')
            if not rtsp_url:
                raise HTTPException(status_code=400, detail="rtsp_url is required")
            
            success = self.vms_manager.add_camera(camera_id, rtsp_url)
            if not success:
                raise HTTPException(status_code=400, detail="Failed to add camera")
            
            return {"message": f"Camera {camera_id} added successfully"}
        
        @self.app.delete("/cameras/{camera_id}")
        async def remove_camera(camera_id: str):
            """Remover câmera"""
            success = self.vms_manager.remove_camera(camera_id)
            if not success:
                raise HTTPException(status_code=404, detail="Camera not found")
            
            return {"message": f"Camera {camera_id} removed successfully"}
        
        @self.app.post("/cameras/{camera_id}/start")
        async def start_camera(camera_id: str):
            """Iniciar stream de câmera"""
            success = self.vms_manager.start_camera_stream(camera_id)
            if not success:
                raise HTTPException(status_code=400, detail="Failed to start camera stream")
            
            return {"message": f"Camera {camera_id} stream started"}
        
        @self.app.post("/cameras/{camera_id}/stop")
        async def stop_camera(camera_id: str):
            """Parar stream de câmera"""
            success = self.vms_manager.stop_camera_stream(camera_id)
            if not success:
                raise HTTPException(status_code=404, detail="Camera not found")
            
            return {"message": f"Camera {camera_id} stream stopped"}
        
        @self.app.get("/stats")
        async def get_stats():
            """Obter estatísticas do sistema"""
            stats = self.vms_manager.get_stats()
            stats.update({
                "active_connections": len(self.connections),
                "camera_subscribers": {
                    cam_id: len(subs) for cam_id, subs in self.camera_subscribers.items()
                }
            })
            return stats
        
        @self.app.websocket("/ws/{camera_id}")
        async def websocket_endpoint(websocket: WebSocket, camera_id: str):
            """WebSocket endpoint para conexão WebRTC por câmera"""
            await self.handle_websocket_connection(websocket, camera_id)
        
        @self.app.get("/demo")
        async def demo_page():
            """Página de demonstração"""
            return HTMLResponse(content=self._get_demo_html())
    
    def _get_demo_html(self) -> str:
        """HTML de demonstração do VMS WebRTC"""
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <title>VMS WebRTC Demo</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 20px; }
                .camera-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 20px; }
                .camera-container { border: 1px solid #ddd; padding: 10px; border-radius: 5px; }
                video { width: 100%; height: 240px; background: #000; }
                .controls { margin-top: 10px; }
                button { margin: 5px; padding: 8px 16px; }
                .status { margin: 10px 0; padding: 10px; background: #f0f0f0; border-radius: 3px; }
            </style>
        </head>
        <body>
            <h1>VMS WebRTC - Video Management System</h1>
            
            <div class="status">
                <h3>System Status</h3>
                <div id="stats">Loading...</div>
            </div>
            
            <div class="controls">
                <button onclick="loadCameras()">Refresh Cameras</button>
                <button onclick="connectAll()">Connect All Cameras</button>
                <button onclick="disconnectAll()">Disconnect All</button>
            </div>
            
            <div id="camera-grid" class="camera-grid">
                <!-- Cameras will be loaded here -->
            </div>
            
            <script>
                let connections = {};
                let peerConnections = {};
                
                async function loadStats() {
                    try {
                        const response = await fetch('/stats');
                        const stats = await response.json();
                        document.getElementById('stats').innerHTML = `
                            <p>Total Cameras: ${stats.total_cameras}</p>
                            <p>Active Cameras: ${stats.active_cameras}</p>
                            <p>Active Connections: ${stats.active_connections}</p>
                        `;
                    } catch (error) {
                        console.error('Error loading stats:', error);
                    }
                }
                
                async function loadCameras() {
                    try {
                        const response = await fetch('/cameras');
                        const data = await response.json();
                        
                        const grid = document.getElementById('camera-grid');
                        grid.innerHTML = '';
                        
                        data.cameras.forEach(cameraId => {
                            const container = document.createElement('div');
                            container.className = 'camera-container';
                            container.innerHTML = `
                                <h3>Camera: ${cameraId}</h3>
                                <video id="video-${cameraId}" autoplay muted playsinline></video>
                                <div class="controls">
                                    <button onclick="connectCamera('${cameraId}')">Connect</button>
                                    <button onclick="disconnectCamera('${cameraId}')">Disconnect</button>
                                    <span id="status-${cameraId}">Disconnected</span>
                                </div>
                            `;
                            grid.appendChild(container);
                        });
                        
                        loadStats();
                    } catch (error) {
                        console.error('Error loading cameras:', error);
                    }
                }
                
                async function connectCamera(cameraId) {
                    try {
                        if (connections[cameraId]) {
                            console.log(`Already connected to ${cameraId}`);
                            return;
                        }
                        
                        const ws = new WebSocket(`ws://localhost:17236/ws/${cameraId}`);
                        const pc = new RTCPeerConnection({
                            iceServers: [{ urls: 'stun:stun.l.google.com:19302' }]
                        });
                        
                        connections[cameraId] = ws;
                        peerConnections[cameraId] = pc;
                        
                        // Handle incoming stream
                        pc.ontrack = (event) => {
                            const video = document.getElementById(`video-${cameraId}`);
                            video.srcObject = event.streams[0];
                        };
                        
                        // Handle ICE candidates
                        pc.onicecandidate = (event) => {
                            if (event.candidate) {
                                ws.send(JSON.stringify({
                                    type: 'ice-candidate',
                                    candidate: event.candidate
                                }));
                            }
                        };
                        
                        // WebSocket message handler
                        ws.onmessage = async (event) => {
                            const message = JSON.parse(event.data);
                            
                            if (message.type === 'offer') {
                                await pc.setRemoteDescription(new RTCSessionDescription(message));
                                const answer = await pc.createAnswer();
                                await pc.setLocalDescription(answer);
                                
                                ws.send(JSON.stringify({
                                    type: 'answer',
                                    answer: answer
                                }));
                            } else if (message.type === 'ice-candidate') {
                                await pc.addIceCandidate(new RTCIceCandidate(message.candidate));
                            }
                        };
                        
                        ws.onopen = () => {
                            document.getElementById(`status-${cameraId}`).textContent = 'Connected';
                            ws.send(JSON.stringify({ type: 'request-offer' }));
                        };
                        
                        ws.onclose = () => {
                            document.getElementById(`status-${cameraId}`).textContent = 'Disconnected';
                            delete connections[cameraId];
                            delete peerConnections[cameraId];
                        };
                        
                    } catch (error) {
                        console.error(`Error connecting to camera ${cameraId}:`, error);
                    }
                }
                
                function disconnectCamera(cameraId) {
                    if (connections[cameraId]) {
                        connections[cameraId].close();
                    }
                    if (peerConnections[cameraId]) {
                        peerConnections[cameraId].close();
                    }
                }
                
                function connectAll() {
                    const cameras = document.querySelectorAll('[id^="video-"]');
                    cameras.forEach(video => {
                        const cameraId = video.id.replace('video-', '');
                        connectCamera(cameraId);
                    });
                }
                
                function disconnectAll() {
                    Object.keys(connections).forEach(cameraId => {
                        disconnectCamera(cameraId);
                    });
                }
                
                // Load cameras on page load
                window.onload = loadCameras;
                
                // Refresh stats every 5 seconds
                setInterval(loadStats, 5000);
            </script>
        </body>
        </html>
        """
    
    async def handle_websocket_connection(self, websocket: WebSocket, camera_id: str):
        """Handle WebSocket connection para uma câmera específica"""
        await websocket.accept()
        
        connection_id = str(uuid.uuid4())
        connection = WebRTCConnection(connection_id, websocket, camera_id)
        self.connections[connection_id] = connection
        
        # Add to camera subscribers
        if camera_id not in self.camera_subscribers:
            self.camera_subscribers[camera_id] = set()
        self.camera_subscribers[camera_id].add(connection_id)
        
        logger.info(f"WebSocket connection {connection_id} established for camera {camera_id}")
        
        try:
            while True:
                # Receive message from client
                data = await websocket.receive_text()
                message = json.loads(data)
                
                await self._handle_webrtc_message(connection, message)
                
        except WebSocketDisconnect:
            logger.info(f"WebSocket connection {connection_id} disconnected")
        except Exception as e:
            logger.error(f"Error in WebSocket connection {connection_id}: {e}")
        finally:
            await self._cleanup_connection(connection_id)
    
    async def _handle_webrtc_message(self, connection: WebRTCConnection, message: dict):
        """Handle mensagem WebRTC"""
        message_type = message.get('type')
        
        if message_type == 'request-offer':
            await self._handle_request_offer(connection)
        elif message_type == 'answer':
            await self._handle_answer(connection, message)
        elif message_type == 'ice-candidate':
            await self._handle_ice_candidate(connection, message)
        else:
            logger.warning(f"Unknown message type: {message_type}")
    
    async def _handle_request_offer(self, connection: WebRTCConnection):
        """Handle request para criar oferta WebRTC"""
        camera_id = connection.camera_id
        
        # Criar sessão WebRTC para esta câmera
        pipeline = self.vms_manager.create_webrtc_session(connection.connection_id, camera_id)
        if not pipeline:
            await connection.send_message({
                'type': 'error',
                'message': f'Camera {camera_id} not available'
            })
            return
        
        connection.pipeline = pipeline
        
        # Setup callbacks
        pipeline.on_ice_candidate = lambda mline, candidate: asyncio.create_task(
            connection.send_message({
                'type': 'ice-candidate',
                'candidate': {
                    'candidate': candidate,
                    'sdpMLineIndex': mline
                }
            })
        )
        
        pipeline.on_offer_created = lambda sdp: asyncio.create_task(
            connection.send_message({
                'type': 'offer',
                'sdp': sdp,
                'type': 'offer'
            })
        )
        
        # Iniciar pipeline se ainda não estiver rodando
        if not pipeline.is_running:
            if not self.vms_manager.start_camera_stream(camera_id):
                await connection.send_message({
                    'type': 'error',
                    'message': f'Failed to start camera {camera_id}'
                })
                return
        
        # Criar oferta
        pipeline.create_offer()
    
    async def _handle_answer(self, connection: WebRTCConnection, message: dict):
        """Handle resposta WebRTC"""
        if not connection.pipeline:
            await connection.send_message({
                'type': 'error',
                'message': 'No active pipeline'
            })
            return
        
        answer = message.get('answer')
        if answer and 'sdp' in answer:
            # Set remote description with answer
            # Note: This would need to be implemented in the pipeline
            logger.info(f"Received answer for connection {connection.connection_id}")
    
    async def _handle_ice_candidate(self, connection: WebRTCConnection, message: dict):
        """Handle ICE candidate"""
        if not connection.pipeline:
            return
        
        candidate_data = message.get('candidate')
        if candidate_data:
            mline_index = candidate_data.get('sdpMLineIndex', 0)
            candidate = candidate_data.get('candidate', '')
            connection.pipeline.add_ice_candidate(mline_index, candidate)
    
    async def _cleanup_connection(self, connection_id: str):
        """Limpar conexão"""
        if connection_id in self.connections:
            connection = self.connections[connection_id]
            
            # Remove from camera subscribers
            if connection.camera_id in self.camera_subscribers:
                self.camera_subscribers[connection.camera_id].discard(connection_id)
                if not self.camera_subscribers[connection.camera_id]:
                    del self.camera_subscribers[connection.camera_id]
            
            # Cleanup VMS session
            self.vms_manager.cleanup_session(connection_id)
            
            # Remove connection
            del self.connections[connection_id]
            
            await connection.close()
            
        logger.info(f"Connection {connection_id} cleaned up")
    
    async def initialize_from_presence_cameras(self):
        """Inicializar câmeras a partir do sistema Presence"""
        try:
            # Importar aqui para evitar dependências circulares
            from app.database.database import get_db_sync
            from app.database import models
            
            db = next(get_db_sync())
            cameras = db.query(models.Camera).filter(models.Camera.status == 'active').all()
            
            for camera in cameras:
                if camera.type == 'ip_camera' and camera.url:
                    success = self.vms_manager.add_camera(camera.id, camera.url)
                    if success:
                        logger.info(f"Added camera {camera.name} ({camera.id}) to VMS")
                    else:
                        logger.error(f"Failed to add camera {camera.name} ({camera.id}) to VMS")
            
            db.close()
            
        except Exception as e:
            logger.error(f"Error initializing cameras from Presence system: {e}")
    
    async def start_server(self):
        """Iniciar servidor VMS WebRTC"""
        if not check_gstreamer_plugins():
            logger.error("Missing required GStreamer plugins")
            return False
        
        # Inicializar câmeras do sistema Presence
        await self.initialize_from_presence_cameras()
        
        # Iniciar servidor FastAPI/WebSocket
        config = uvicorn.Config(
            app=self.app,
            host="0.0.0.0",
            port=self.port,
            log_level="info"
        )
        server = uvicorn.Server(config)
        
        logger.info(f"VMS WebRTC Server starting on port {self.port}")
        logger.info(f"Demo available at: http://localhost:{self.port}/demo")
        
        await server.serve()
    
    def cleanup(self):
        """Limpar recursos do servidor"""
        self.vms_manager.cleanup_all()
        self.connections.clear()
        self.camera_subscribers.clear()


async def main():
    """Função principal"""
    logging.basicConfig(level=logging.INFO)
    
    server = VMS_WebRTCServer(port=int(os.environ.get('VMS_WEBRTC_PORT', 17236)))
    
    try:
        await server.start_server()
    except KeyboardInterrupt:
        logger.info("Shutting down VMS WebRTC Server...")
    finally:
        server.cleanup()


if __name__ == "__main__":
    asyncio.run(main())