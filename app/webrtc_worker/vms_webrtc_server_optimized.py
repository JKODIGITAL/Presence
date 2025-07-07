#!/usr/bin/env python3
"""
VMS WebRTC Server Optimized - Versão otimizada com correções de performance
"""

import asyncio
import json
import logging
import os
import sys
from typing import Dict, List, Optional, Any
from datetime import datetime
import uuid

# Importar otimizações antes de qualquer outro import WebRTC
from .webrtc_optimizations import webrtc_optimizer, WebRTCDiagnostics
from .h264_fixes import h264_fixes

# Aplicar otimizações logo no início
webrtc_optimizer.apply_all_optimizations()

# Agora importar aiortc com otimizações aplicadas
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCConfiguration, RTCIceServer
from aiortc.contrib.media import MediaPlayer
import aiohttp
from aiohttp import web, WSMsgType
import aiohttp_cors

logger = logging.getLogger(__name__)

class OptimizedWebRTCConnection:
    """Conexão WebRTC otimizada com melhor tratamento de erros"""
    
    def __init__(self, connection_id: str, websocket, camera_id: str = None):
        self.connection_id = connection_id
        self.websocket = websocket
        self.camera_id = camera_id
        self.peer_connection: Optional[RTCPeerConnection] = None
        self.media_player: Optional[MediaPlayer] = None
        self.is_connected = True
        self.created_at = datetime.now()
        self.last_error = None
        self.diagnostics = WebRTCDiagnostics()
        
        # Criar peer connection otimizada
        self._create_optimized_peer_connection()
    
    def _create_optimized_peer_connection(self):
        """Criar peer connection com configuração otimizada"""
        try:
            # Usar configuração otimizada do optimizer
            rtc_config = webrtc_optimizer.get_optimized_rtc_configuration()
            
            # Converter para aiortc RTCConfiguration
            ice_servers = [RTCIceServer(urls=server["urls"]) for server in rtc_config["iceServers"]]
            configuration = RTCConfiguration(iceServers=ice_servers)
            
            self.peer_connection = RTCPeerConnection(configuration=configuration)
            
            # Configurar event handlers otimizados
            self._setup_optimized_event_handlers()
            
            logger.info(f"✅ Optimized peer connection created for {self.connection_id}")
            
        except Exception as e:
            logger.error(f"❌ Failed to create optimized peer connection: {e}")
            self.last_error = str(e)
    
    def _setup_optimized_event_handlers(self):
        """Configurar event handlers com melhor tratamento de erros"""
        
        @self.peer_connection.on("icecandidate")
        async def on_ice_candidate(candidate):
            if candidate:
                try:
                    self.diagnostics.log_ice_candidate_details(candidate)
                    await self.send_ice_candidate(candidate)
                except Exception as e:
                    logger.error(f"❌ Error handling ICE candidate: {e}")
        
        @self.peer_connection.on("connectionstatechange")
        async def on_connection_state_change():
            state_info = self.diagnostics.analyze_connection_state(self.peer_connection)
            logger.info(f"🔗 Connection state for {self.connection_id}: {state_info}")
            
            # Diagnosticar problemas se necessário
            if state_info.get('connection_state') in ['failed', 'disconnected']:
                diagnosis = self.diagnostics.diagnose_connection_failure(state_info)
                logger.warning(f"⚠️ Connection issue: {diagnosis}")
                await self.handle_connection_failure(diagnosis)
        
        @self.peer_connection.on("iceconnectionstatechange")
        async def on_ice_connection_state_change():
            ice_state = self.peer_connection.iceConnectionState
            logger.info(f"🧊 ICE state for {self.connection_id}: {ice_state}")
            
            if ice_state == "failed":
                logger.error(f"❌ ICE connection failed for {self.connection_id}")
                await self.handle_ice_failure()
    
    async def create_optimized_media_player(self, rtsp_url: str):
        """Criar media player otimizado com pipeline robusto"""
        try:
            # Usar pipeline otimizado do h264_fixes
            optimized_pipeline = h264_fixes.get_error_recovery_pipeline(rtsp_url)
            
            # Criar MediaPlayer com configurações otimizadas
            self.media_player = MediaPlayer(
                optimized_pipeline,
                format='gstreamer',
                options={
                    'fflags': '+genpts',
                    'avoid_negative_ts': 'make_zero',
                    'max_delay': '5000000',  # 5 seconds max delay
                }
            )
            
            logger.info(f"✅ Optimized media player created for {self.connection_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to create optimized media player: {e}")
            self.last_error = str(e)
            return False
    
    async def handle_offer(self, offer_sdp: str) -> Optional[str]:
        """Processar offer WebRTC com otimizações"""
        try:
            if not self.peer_connection:
                raise Exception("Peer connection not initialized")
            
            # Criar session description
            offer = RTCSessionDescription(sdp=offer_sdp, type="offer")
            await self.peer_connection.setRemoteDescription(offer)
            
            # Adicionar track de vídeo se media player estiver disponível
            if self.media_player and self.media_player.video:
                self.peer_connection.addTrack(self.media_player.video)
                logger.info(f"📹 Video track added for {self.connection_id}")
            
            # Criar answer
            answer = await self.peer_connection.createAnswer()
            
            # Otimizar SDP com correções H.264
            optimized_sdp = webrtc_optimizer.optimize_h264_sdp(answer.sdp)
            optimized_answer = RTCSessionDescription(sdp=optimized_sdp, type="answer")
            
            await self.peer_connection.setLocalDescription(optimized_answer)
            
            logger.info(f"✅ Optimized answer created for {self.connection_id}")
            return optimized_answer.sdp
            
        except Exception as e:
            logger.error(f"❌ Error handling offer for {self.connection_id}: {e}")
            self.last_error = str(e)
            return None
    
    async def send_ice_candidate(self, candidate):
        """Enviar ICE candidate via WebSocket"""
        try:
            message = {
                'type': 'ice-candidate',
                'candidate': {
                    'candidate': candidate.candidate,
                    'sdpMid': candidate.sdpMid,
                    'sdpMLineIndex': candidate.sdpMLineIndex
                }
            }
            await self.send_message(message)
        except Exception as e:
            logger.error(f"❌ Error sending ICE candidate: {e}")
    
    async def send_message(self, message: dict):
        """Enviar mensagem via WebSocket com tratamento de erro"""
        if self.is_connected:
            try:
                await self.websocket.send_str(json.dumps(message))
            except Exception as e:
                logger.error(f"❌ Error sending message to {self.connection_id}: {e}")
                self.is_connected = False
    
    async def handle_connection_failure(self, diagnosis: str):
        """Tratar falhas de conexão"""
        error_message = {
            'type': 'error',
            'message': 'Connection failed',
            'diagnosis': diagnosis,
            'timestamp': datetime.now().isoformat()
        }
        await self.send_message(error_message)
    
    async def handle_ice_failure(self):
        """Tratar falhas de ICE connection"""
        error_message = {
            'type': 'ice-failure',
            'message': 'ICE connection failed - check network configuration',
            'recommendations': [
                'Verify STUN/TURN server configuration',
                'Check firewall and NAT settings',
                'Ensure UDP ports 40000-40100 are open'
            ],
            'timestamp': datetime.now().isoformat()
        }
        await self.send_message(error_message)
    
    async def cleanup(self):
        """Limpeza de recursos"""
        try:
            if self.media_player:
                self.media_player.audio = None
                self.media_player.video = None
                
            if self.peer_connection:
                await self.peer_connection.close()
                
            self.is_connected = False
            logger.info(f"🧹 Cleaned up connection {self.connection_id}")
            
        except Exception as e:
            logger.error(f"❌ Error during cleanup: {e}")


class OptimizedVMSWebRTCServer:
    """Servidor WebRTC VMS otimizado"""
    
    def __init__(self, port: int = 17236):
        self.port = port
        self.connections: Dict[str, OptimizedWebRTCConnection] = {}
        self.camera_streams: Dict[str, str] = {}  # camera_id -> rtsp_url
        self.app = web.Application()
        self._setup_routes()
        self._setup_cors()
        
        # Estatísticas
        self.stats = {
            'total_connections': 0,
            'active_connections': 0,
            'failed_connections': 0,
            'start_time': datetime.now()
        }
    
    def _setup_cors(self):
        """Configurar CORS"""
        cors = aiohttp_cors.setup(self.app, defaults={
            "*": aiohttp_cors.ResourceOptions(
                allow_credentials=True,
                expose_headers="*",
                allow_headers="*",
                allow_methods="*"
            )
        })
        
        # Adicionar CORS a todas as rotas
        for route in list(self.app.router.routes()):
            cors.add(route)
    
    def _setup_routes(self):
        """Configurar rotas"""
        self.app.router.add_get('/', self.handle_root)
        self.app.router.add_get('/health', self.handle_health)
        self.app.router.add_get('/stats', self.handle_stats)
        self.app.router.add_get('/cameras', self.handle_cameras)
        self.app.router.add_post('/cameras/{camera_id}', self.handle_add_camera)
        self.app.router.add_ws('/ws', self.handle_websocket)
    
    async def handle_root(self, request):
        """Endpoint raiz"""
        return web.json_response({
            'service': 'Optimized VMS WebRTC Server',
            'version': '2.0.0',
            'status': 'running',
            'port': self.port,
            'active_connections': len(self.connections),
            'uptime': str(datetime.now() - self.stats['start_time'])
        })
    
    async def handle_health(self, request):
        """Health check"""
        return web.json_response({
            'status': 'healthy',
            'active_connections': len(self.connections),
            'camera_streams': len(self.camera_streams),
            'timestamp': datetime.now().isoformat()
        })
    
    async def handle_stats(self, request):
        """Estatísticas detalhadas"""
        current_stats = {
            **self.stats,
            'active_connections': len(self.connections),
            'connection_details': [
                {
                    'id': conn.connection_id,
                    'camera_id': conn.camera_id,
                    'created_at': conn.created_at.isoformat(),
                    'connected': conn.is_connected,
                    'last_error': conn.last_error
                }
                for conn in self.connections.values()
            ]
        }
        return web.json_response(current_stats)
    
    async def handle_cameras(self, request):
        """Listar câmeras disponíveis"""
        return web.json_response({
            'cameras': list(self.camera_streams.keys()),
            'total': len(self.camera_streams)
        })
    
    async def handle_add_camera(self, request):
        """Adicionar nova câmera"""
        camera_id = request.match_info['camera_id']
        data = await request.json()
        rtsp_url = data.get('rtsp_url')
        
        if not rtsp_url:
            return web.json_response(
                {'error': 'rtsp_url is required'}, 
                status=400
            )
        
        self.camera_streams[camera_id] = rtsp_url
        logger.info(f"📹 Camera {camera_id} added: {rtsp_url}")
        
        return web.json_response({
            'message': f'Camera {camera_id} added successfully',
            'rtsp_url': rtsp_url
        })
    
    async def handle_websocket(self, request):
        """Handle WebSocket connections"""
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        
        connection_id = str(uuid.uuid4())[:8]
        connection = OptimizedWebRTCConnection(connection_id, ws)
        self.connections[connection_id] = connection
        
        self.stats['total_connections'] += 1
        
        logger.info(f"🔌 New WebSocket connection: {connection_id}")
        
        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    await self.handle_websocket_message(connection, msg.data)
                elif msg.type == WSMsgType.ERROR:
                    logger.error(f"❌ WebSocket error: {ws.exception()}")
                    break
                    
        except Exception as e:
            logger.error(f"❌ WebSocket connection error: {e}")
            self.stats['failed_connections'] += 1
        finally:
            await self.cleanup_connection(connection_id)
        
        return ws
    
    async def handle_websocket_message(self, connection: OptimizedWebRTCConnection, message: str):
        """Processar mensagens WebSocket"""
        try:
            data = json.loads(message)
            msg_type = data.get('type')
            
            if msg_type == 'offer':
                await self.handle_offer_message(connection, data)
            elif msg_type == 'ice-candidate':
                await self.handle_ice_candidate_message(connection, data)
            elif msg_type == 'request-camera':
                await self.handle_camera_request(connection, data)
            else:
                logger.warning(f"⚠️ Unknown message type: {msg_type}")
                
        except json.JSONDecodeError:
            logger.error(f"❌ Invalid JSON message from {connection.connection_id}")
        except Exception as e:
            logger.error(f"❌ Error handling message: {e}")
    
    async def handle_offer_message(self, connection: OptimizedWebRTCConnection, data: dict):
        """Processar offer WebRTC"""
        try:
            offer_sdp = data.get('sdp')
            camera_id = data.get('camera_id')
            
            if not offer_sdp:
                raise Exception("Missing SDP in offer")
            
            # Configurar stream de câmera se especificado
            if camera_id and camera_id in self.camera_streams:
                rtsp_url = self.camera_streams[camera_id]
                success = await connection.create_optimized_media_player(rtsp_url)
                if not success:
                    raise Exception(f"Failed to create media player for camera {camera_id}")
                connection.camera_id = camera_id
            
            # Processar offer
            answer_sdp = await connection.handle_offer(offer_sdp)
            
            if answer_sdp:
                response = {
                    'type': 'answer',
                    'sdp': answer_sdp,
                    'camera_id': camera_id
                }
                await connection.send_message(response)
                logger.info(f"✅ Answer sent for {connection.connection_id}")
            else:
                raise Exception("Failed to create answer")
                
        except Exception as e:
            error_msg = {
                'type': 'error',
                'message': f'Failed to handle offer: {str(e)}'
            }
            await connection.send_message(error_msg)
    
    async def handle_ice_candidate_message(self, connection: OptimizedWebRTCConnection, data: dict):
        """Processar ICE candidate"""
        try:
            candidate_data = data.get('candidate')
            if candidate_data and connection.peer_connection:
                # Processar ICE candidate
                logger.info(f"🧊 Received ICE candidate for {connection.connection_id}")
        except Exception as e:
            logger.error(f"❌ Error handling ICE candidate: {e}")
    
    async def handle_camera_request(self, connection: OptimizedWebRTCConnection, data: dict):
        """Processar requisição de câmera"""
        camera_id = data.get('camera_id')
        
        if camera_id in self.camera_streams:
            response = {
                'type': 'camera-available',
                'camera_id': camera_id,
                'rtsp_url': self.camera_streams[camera_id]
            }
        else:
            response = {
                'type': 'camera-not-found',
                'camera_id': camera_id,
                'available_cameras': list(self.camera_streams.keys())
            }
        
        await connection.send_message(response)
    
    async def cleanup_connection(self, connection_id: str):
        """Limpar conexão"""
        if connection_id in self.connections:
            connection = self.connections[connection_id]
            await connection.cleanup()
            del self.connections[connection_id]
            logger.info(f"🧹 Connection {connection_id} cleaned up")
    
    async def start_server(self):
        """Iniciar servidor"""
        logger.info(f"🚀 Starting Optimized VMS WebRTC Server on port {self.port}")
        
        runner = web.AppRunner(self.app)
        await runner.setup()
        
        site = web.TCPSite(runner, '0.0.0.0', self.port)
        await site.start()
        
        logger.info(f"✅ Optimized VMS WebRTC Server running on http://0.0.0.0:{self.port}")
        
        # Manter servidor rodando
        try:
            await asyncio.Future()  # Run forever
        except KeyboardInterrupt:
            logger.info("🛑 Server stopped by user")
        finally:
            await runner.cleanup()


async def main():
    """Função principal"""
    # Configurar logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)s | %(name)s | %(message)s'
    )
    
    # Configurar port
    port = int(os.environ.get('WEBRTC_PORT', 17236))
    
    # Criar e iniciar servidor
    server = OptimizedVMSWebRTCServer(port)
    await server.start_server()


if __name__ == "__main__":
    asyncio.run(main())