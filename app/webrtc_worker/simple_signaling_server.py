"""
Servidor de sinalização WebRTC simples
Usando apenas bibliotecas padrão do Python
"""

import asyncio
import json
import websockets
import logging
from typing import Dict, Set
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SimpleSignalingServer:
    """Servidor de sinalização WebRTC simples usando websockets"""
    
    def __init__(self, host: str = "127.0.0.1", port: int = 17237):
        self.host = host
        self.port = port
        self.clients: Dict[str, websockets.WebSocketServerProtocol] = {}
        self.sessions: Dict[str, Dict] = {}
        
        logger.info(f"Servidor de sinalização inicializado em {host}:{port}")
    
    async def register_client(self, websocket: websockets.WebSocketServerProtocol, camera_id: str):
        """Registrar cliente WebSocket"""
        session_id = f"{camera_id}_{datetime.now().timestamp()}"
        
        self.clients[session_id] = websocket
        self.sessions[session_id] = {
            "camera_id": camera_id,
            "created_at": datetime.now().isoformat(),
            "websocket": websocket
        }
        
        logger.info(f"Cliente registrado: {camera_id} (session: {session_id})")
        return session_id
    
    async def unregister_client(self, session_id: str):
        """Desregistrar cliente WebSocket"""
        if session_id in self.clients:
            del self.clients[session_id]
        if session_id in self.sessions:
            del self.sessions[session_id]
        
        logger.info(f"Cliente desregistrado: {session_id}")
    
    async def handle_client(self, websocket: websockets.WebSocketServerProtocol, path: str):
        """Gerenciar conexão de cliente WebSocket"""
        # Extrair camera_id do path: /ws/camera_id
        camera_id = path.split('/')[-1] if '/' in path else path
        
        session_id = await self.register_client(websocket, camera_id)
        
        try:
            async for message in websocket:
                await self.handle_message(session_id, message)
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"Cliente {camera_id} desconectado")
        except Exception as e:
            logger.error(f"Erro na conexão {camera_id}: {e}")
        finally:
            await self.unregister_client(session_id)
    
    async def handle_message(self, session_id: str, message: str):
        """Processar mensagem WebSocket"""
        try:
            data = json.loads(message)
            msg_type = data.get('type')
            
            logger.info(f"Mensagem recebida de {session_id}: {msg_type}")
            
            if msg_type == 'get-offer':
                # Cliente solicita offer
                await self.request_offer(session_id)
            elif msg_type == 'answer':
                # Cliente envia answer
                await self.handle_answer(session_id, data.get('sdp'))
            elif msg_type == 'ice-candidate':
                # Cliente envia ICE candidate
                await self.handle_ice_candidate(session_id, data.get('candidate'))
            else:
                logger.warning(f"Tipo de mensagem desconhecido: {msg_type}")
                
        except json.JSONDecodeError:
            logger.error(f"JSON inválido recebido de {session_id}: {message}")
        except Exception as e:
            logger.error(f"Erro ao processar mensagem de {session_id}: {e}")
    
    async def request_offer(self, session_id: str):
        """Cliente solicita offer do pipeline"""
        logger.info(f"Offer solicitado por {session_id}")
        
        # TODO: Integrar com pipeline GStreamer
        # Por enquanto, enviar resposta dummy
        
        await self.send_to_client(session_id, {
            "type": "offer",
            "sdp": "v=0\r\no=- 0 0 IN IP4 127.0.0.1\r\ns=-\r\nt=0 0\r\n"  # SDP dummy
        })
    
    async def handle_answer(self, session_id: str, sdp: str):
        """Processar answer do cliente"""
        logger.info(f"Answer recebido de {session_id}")
        
        # TODO: Enviar answer para pipeline GStreamer
        
    async def handle_ice_candidate(self, session_id: str, candidate: Dict):
        """Processar ICE candidate do cliente"""
        logger.info(f"ICE candidate recebido de {session_id}")
        
        # TODO: Enviar ICE candidate para pipeline GStreamer
    
    async def send_to_client(self, session_id: str, message: Dict):
        """Enviar mensagem para cliente"""
        if session_id in self.clients:
            websocket = self.clients[session_id]
            try:
                await websocket.send(json.dumps(message))
                logger.info(f"Mensagem enviada para {session_id}: {message.get('type')}")
            except Exception as e:
                logger.error(f"Erro ao enviar mensagem para {session_id}: {e}")
    
    async def send_offer(self, session_id: str, sdp: str):
        """Enviar offer para cliente"""
        await self.send_to_client(session_id, {
            "type": "offer",
            "sdp": sdp
        })
    
    async def send_ice_candidate(self, session_id: str, candidate: Dict):
        """Enviar ICE candidate para cliente"""
        await self.send_to_client(session_id, {
            "type": "ice-candidate",
            "candidate": candidate
        })
    
    async def start_server(self):
        """Iniciar servidor WebSocket"""
        logger.info(f"Iniciando servidor WebSocket em ws://{self.host}:{self.port}")
        
        async with websockets.serve(
            self.handle_client,
            self.host,
            self.port,
            logger=logger
        ):
            await asyncio.Future()  # Run forever
    
    def get_stats(self) -> Dict:
        """Obter estatísticas do servidor"""
        return {
            "active_sessions": len(self.sessions),
            "connected_clients": len(self.clients),
            "sessions": [
                {
                    "session_id": sid,
                    "camera_id": session["camera_id"],
                    "created_at": session["created_at"]
                }
                for sid, session in self.sessions.items()
            ]
        }

# Instância global do servidor
signaling_server = SimpleSignalingServer()

async def main():
    """Função principal para execução standalone"""
    try:
        await signaling_server.start_server()
    except KeyboardInterrupt:
        logger.info("Servidor interrompido pelo usuário")

if __name__ == "__main__":
    asyncio.run(main())