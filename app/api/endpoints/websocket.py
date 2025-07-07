"""
WebSocket endpoints for real-time communication
"""

from fastapi import WebSocket, WebSocketDisconnect, Depends
from fastapi.routing import APIRouter
from sqlalchemy.orm import Session
from typing import List, Dict, Any
import json
import asyncio
from datetime import datetime
import logging

from app.database.database import get_db, get_db_dependency
from app.api.services.camera_service import CameraService
from app.api.services.person_service import PersonService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["websocket"])

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.recognition_subscribers: List[WebSocket] = []

    async def connect(self, websocket: WebSocket, connection_type: str = "general"):
        await websocket.accept()
        self.active_connections.append(websocket)
        
        if connection_type == "recognition":
            self.recognition_subscribers.append(websocket)
        
        logger.info(f"Nova conexão WebSocket: {connection_type}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        if websocket in self.recognition_subscribers:
            self.recognition_subscribers.remove(websocket)
        logger.info("Conexão WebSocket desconectada")

    async def send_personal_message(self, message: str, websocket: WebSocket):
        try:
            await websocket.send_text(message)
        except Exception as e:
            logger.error(f"Erro ao enviar mensagem pessoal: {e}")
            self.disconnect(websocket)

    async def broadcast_to_recognition_subscribers(self, message: Dict[str, Any]):
        disconnected = []
        for connection in self.recognition_subscribers:
            try:
                await connection.send_text(json.dumps(message))
            except Exception as e:
                logger.error(f"Erro ao broadcast para reconhecimento: {e}")
                disconnected.append(connection)
        
        # Remove conexões desconectadas
        for conn in disconnected:
            self.disconnect(conn)

    async def broadcast(self, message: Dict[str, Any]):
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(json.dumps(message))
            except Exception as e:
                logger.error(f"Erro ao fazer broadcast: {e}")
                disconnected.append(connection)
        
        # Remove conexões desconectadas
        for conn in disconnected:
            self.disconnect(conn)

manager = ConnectionManager()

@router.websocket("/recognition")
async def websocket_recognition_feed(websocket: WebSocket, db: Session = Depends(get_db_dependency)):
    """WebSocket para feed de reconhecimentos em tempo real"""
    await manager.connect(websocket, "recognition")
    
    try:
        # Enviar mensagem de boas-vindas
        welcome_message = {
            "type": "connected",
            "message": "Conectado ao feed de reconhecimentos",
            "timestamp": datetime.now().isoformat()
        }
        await manager.send_personal_message(json.dumps(welcome_message), websocket)
        
        while True:
            # Manter conexão viva
            data = await websocket.receive_text()
            
            # Processar comandos se necessário
            try:
                command = json.loads(data)
                if command.get("type") == "ping":
                    pong_message = {
                        "type": "pong",
                        "timestamp": datetime.now().isoformat()
                    }
                    await manager.send_personal_message(json.dumps(pong_message), websocket)
            except json.JSONDecodeError:
                # Ignorar mensagens mal formadas
                pass
            
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info("Cliente desconectado do feed de reconhecimentos")
    except Exception as e:
        logger.error(f"Erro na conexão WebSocket de reconhecimentos: {e}")
        manager.disconnect(websocket)

@router.websocket("/system")
async def websocket_system_status(websocket: WebSocket, db: Session = Depends(get_db_dependency)):
    """WebSocket para status do sistema em tempo real"""
    await manager.connect(websocket, "system")
    
    try:
        # Enviar status inicial
        initial_status = {
            "type": "system_status",
            "data": {
                "api": "online",
                "database": "online",
                "recognition_engine": "online",
                "camera_worker": "online"
            },
            "timestamp": datetime.now().isoformat()
        }
        await manager.send_personal_message(json.dumps(initial_status), websocket)
        
        while True:
            # Aguardar mensagens do cliente
            data = await websocket.receive_text()
            
            # Enviar heartbeat a cada 30 segundos
            await asyncio.sleep(30)
            heartbeat = {
                "type": "heartbeat",
                "timestamp": datetime.now().isoformat()
            }
            await manager.send_personal_message(json.dumps(heartbeat), websocket)
            
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info("Cliente desconectado do status do sistema")
    except Exception as e:
        logger.error(f"Erro na conexão WebSocket do sistema: {e}")
        manager.disconnect(websocket)

# Função para ser chamada quando um reconhecimento acontece
async def broadcast_recognition_event(recognition_data: Dict[str, Any]):
    """Broadcast um evento de reconhecimento para todos os subscribers"""
    message = {
        "type": "recognition",
        "result": recognition_data,
        "timestamp": datetime.now().isoformat()
    }
    await manager.broadcast_to_recognition_subscribers(message)

# Função para broadcast de eventos do sistema
async def broadcast_system_event(event_type: str, data: Dict[str, Any]):
    """Broadcast um evento do sistema"""
    message = {
        "type": event_type,
        "data": data,
        "timestamp": datetime.now().isoformat()
    }
    await manager.broadcast(message)

# Função para obter o manager (para usar em outros módulos)
def get_websocket_manager() -> ConnectionManager:
    return manager