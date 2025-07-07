"""
Servidor de sinalização WebRTC para webrtcbin
Gerencia troca de SDP e ICE candidates entre GStreamer e Frontend
"""

import asyncio
import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import JSONResponse
from typing import Dict, Set, Optional, Any
from loguru import logger
from dataclasses import dataclass, asdict
import uvicorn
import threading
from datetime import datetime

@dataclass
class WebRTCSession:
    """Sessão WebRTC"""
    session_id: str
    camera_id: str
    websocket: Optional[WebSocket] = None
    created_at: datetime = None
    is_active: bool = False
    local_description: Optional[str] = None
    remote_description: Optional[str] = None
    ice_candidates: list = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.ice_candidates is None:
            self.ice_candidates = []

class WebRTCSignalingServer:
    """Servidor de sinalização WebRTC"""
    
    def __init__(self, host: str = "127.0.0.1", port: int = 17237):
        self.host = host
        self.port = port
        self.app = FastAPI(title="WebRTC Signaling Server")
        self.sessions: Dict[str, WebRTCSession] = {}
        self.connected_clients: Set[WebSocket] = set()
        self.pipeline_callbacks: Dict[str, Any] = {}
        
        # Setup routes
        self._setup_routes()
        
        logger.info(f"WebRTC Signaling Server inicializado em {host}:{port}")
    
    def _setup_routes(self):
        """Configurar rotas da API"""
        
        @self.app.get("/health")
        async def health():
            """Health check"""
            return {
                "status": "healthy",
                "active_sessions": len(self.sessions),
                "connected_clients": len(self.connected_clients),
                "timestamp": datetime.now().isoformat()
            }
        
        @self.app.get("/sessions")
        async def get_sessions():
            """Listar sessões ativas"""
            return {
                "sessions": [
                    {
                        "session_id": session.session_id,
                        "camera_id": session.camera_id,
                        "is_active": session.is_active,
                        "created_at": session.created_at.isoformat(),
                        "has_local_description": session.local_description is not None,
                        "has_remote_description": session.remote_description is not None,
                        "ice_candidates_count": len(session.ice_candidates)
                    }
                    for session in self.sessions.values()
                ]
            }
        
        @self.app.delete("/sessions/{session_id}")
        async def delete_session(session_id: str):
            """Remover sessão"""
            if session_id in self.sessions:
                session = self.sessions[session_id]
                if session.websocket:
                    await session.websocket.close()
                del self.sessions[session_id]
                logger.info(f"🗑️ Sessão removida: {session_id}")
                return {"message": "Session deleted"}
            else:
                raise HTTPException(status_code=404, detail="Session not found")
        
        @self.app.websocket("/ws/{camera_id}")
        async def websocket_endpoint(websocket: WebSocket, camera_id: str):
            """WebSocket endpoint para sinalização"""
            await self._handle_websocket_connection(websocket, camera_id)
    
    async def _handle_websocket_connection(self, websocket: WebSocket, camera_id: str):
        """Gerenciar conexão WebSocket"""
        await websocket.accept()
        
        # Criar sessão
        session_id = f"{camera_id}_{datetime.now().timestamp()}"
        session = WebRTCSession(
            session_id=session_id,
            camera_id=camera_id,
            websocket=websocket,
            is_active=True
        )
        
        self.sessions[session_id] = session
        self.connected_clients.add(websocket)
        
        logger.info(f"🔌 Nova conexão WebSocket: {camera_id} (session: {session_id})")
        
        try:
            # Notificar pipeline que cliente conectou
            if camera_id in self.pipeline_callbacks:
                callback = self.pipeline_callbacks[camera_id].get('on_client_connected')
                if callback:
                    await callback(session_id)
            
            # Loop de mensagens
            async for message in websocket.iter_text():
                await self._handle_websocket_message(session, message)
                
        except WebSocketDisconnect:
            logger.info(f"🔌 Cliente desconectado: {camera_id}")
        except Exception as e:
            logger.error(f"❌ Erro na conexão WebSocket: {e}")
        finally:
            # Cleanup
            self.connected_clients.discard(websocket)
            if session_id in self.sessions:
                del self.sessions[session_id]
            
            # Notificar pipeline que cliente desconectou
            if camera_id in self.pipeline_callbacks:
                callback = self.pipeline_callbacks[camera_id].get('on_client_disconnected')
                if callback:
                    await callback(session_id)
    
    async def _handle_websocket_message(self, session: WebRTCSession, message: str):
        """Processar mensagem WebSocket"""
        try:
            data = json.loads(message)
            msg_type = data.get('type')
            
            logger.debug(f"📨 Mensagem recebida: {msg_type} para {session.camera_id}")
            
            if msg_type == 'offer':
                await self._handle_offer(session, data)
            elif msg_type == 'answer':
                await self._handle_answer(session, data)
            elif msg_type == 'ice-candidate':
                await self._handle_ice_candidate(session, data)
            elif msg_type == 'get-offer':
                await self._handle_get_offer_request(session)
            else:
                logger.warning(f"⚠️ Tipo de mensagem desconhecido: {msg_type}")
                
        except json.JSONDecodeError:
            logger.error(f"❌ JSON inválido recebido: {message}")
        except Exception as e:
            logger.error(f"❌ Erro ao processar mensagem: {e}")
    
    async def _handle_offer(self, session: WebRTCSession, data: Dict):
        """Processar offer do cliente"""
        logger.info(f"📤 Offer recebido do cliente: {session.camera_id}")
        
        session.remote_description = data.get('sdp')
        
        # Enviar offer para pipeline
        if session.camera_id in self.pipeline_callbacks:
            callback = self.pipeline_callbacks[session.camera_id].get('on_offer_received')
            if callback:
                await callback(session.session_id, data.get('sdp'))
    
    async def _handle_answer(self, session: WebRTCSession, data: Dict):
        """Processar answer do cliente"""
        logger.info(f"📥 Answer recebido do cliente: {session.camera_id}")
        
        session.remote_description = data.get('sdp')
        
        # Enviar answer para pipeline
        if session.camera_id in self.pipeline_callbacks:
            callback = self.pipeline_callbacks[session.camera_id].get('on_answer_received')
            if callback:
                await callback(session.session_id, data.get('sdp'))
    
    async def _handle_ice_candidate(self, session: WebRTCSession, data: Dict):
        """Processar ICE candidate do cliente"""
        candidate = data.get('candidate')
        session.ice_candidates.append(candidate)
        
        logger.debug(f"🧊 ICE candidate recebido: {session.camera_id}")
        
        # Enviar ICE candidate para pipeline
        if session.camera_id in self.pipeline_callbacks:
            callback = self.pipeline_callbacks[session.camera_id].get('on_ice_candidate_received')
            if callback:
                await callback(session.session_id, candidate)
    
    async def _handle_get_offer_request(self, session: WebRTCSession):
        """Processar solicitação de offer"""
        logger.info(f"🤝 Solicitação de offer: {session.camera_id}")
        
        # Solicitar offer ao pipeline
        if session.camera_id in self.pipeline_callbacks:
            callback = self.pipeline_callbacks[session.camera_id].get('on_offer_requested')
            if callback:
                await callback(session.session_id)
    
    async def send_offer(self, session_id: str, sdp: str):
        """Enviar offer para cliente"""
        if session_id in self.sessions:
            session = self.sessions[session_id]
            session.local_description = sdp
            
            message = {
                "type": "offer",
                "sdp": sdp
            }
            
            if session.websocket:
                await session.websocket.send_text(json.dumps(message))
                logger.info(f"📤 Offer enviado para cliente: {session.camera_id}")
    
    async def send_ice_candidate(self, session_id: str, candidate: Dict):
        """Enviar ICE candidate para cliente"""
        if session_id in self.sessions:
            session = self.sessions[session_id]
            
            message = {
                "type": "ice-candidate",
                "candidate": candidate
            }
            
            if session.websocket:
                await session.websocket.send_text(json.dumps(message))
                logger.debug(f"🧊 ICE candidate enviado: {session.camera_id}")
    
    def register_pipeline_callbacks(self, camera_id: str, callbacks: Dict[str, Any]):
        """Registrar callbacks do pipeline"""
        self.pipeline_callbacks[camera_id] = callbacks
        logger.info(f"📋 Callbacks registrados para câmera: {camera_id}")
    
    def unregister_pipeline_callbacks(self, camera_id: str):
        """Desregistrar callbacks do pipeline"""
        if camera_id in self.pipeline_callbacks:
            del self.pipeline_callbacks[camera_id]
            logger.info(f"📋 Callbacks removidos para câmera: {camera_id}")
    
    async def start_server(self):
        """Iniciar servidor"""
        config = uvicorn.Config(
            app=self.app,
            host=self.host,
            port=self.port,
            log_level="info"
        )
        
        server = uvicorn.Server(config)
        await server.serve()
    
    def start_in_thread(self):
        """Iniciar servidor em thread separada"""
        def run_server():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.start_server())
        
        thread = threading.Thread(target=run_server, daemon=True)
        thread.start()
        logger.info(f"🚀 WebRTC Signaling Server iniciado em thread separada")
        return thread

# Instância global do servidor
signaling_server = WebRTCSignalingServer()

if __name__ == "__main__":
    import sys
    
    host = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 17237
    
    server = WebRTCSignalingServer(host, port)
    
    logger.info(f"🚀 Iniciando WebRTC Signaling Server em {host}:{port}")
    
    try:
        asyncio.run(server.start_server())
    except KeyboardInterrupt:
        logger.info("🛑 Servidor interrompido pelo usuário")