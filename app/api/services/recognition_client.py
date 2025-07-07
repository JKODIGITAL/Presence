"""
Cliente Socket.IO para comunicação com Recognition Worker
"""

import asyncio
import socketio
import base64
import numpy as np
import time
from typing import Optional, Dict, Any, List
from loguru import logger
import os


class RecognitionWorkerClient:
    """Cliente para comunicação com Recognition Worker via Socket.IO"""
    
    def __init__(self):
        self.client = socketio.AsyncClient()
        self.connected = False
        self.recognition_worker_url = os.environ.get(
            'RECOGNITION_WORKER_URL', 
            'http://127.0.0.1:17235'
        )
        self._setup_events()
    
    def _setup_events(self):
        """Configurar eventos do Socket.IO"""
        
        @self.client.event
        async def connect():
            logger.info("[OK] API conectada ao Recognition Worker")
            self.connected = True
        
        @self.client.event
        async def disconnect():
            logger.warning("[WARNING] API desconectada do Recognition Worker")
            self.connected = False
    
    async def connect_to_worker(self) -> bool:
        """Conectar ao Recognition Worker"""
        try:
            if not self.connected:
                # Verificar se o client está em estado válido
                if self.client.connected:
                    await self.client.disconnect()
                    await asyncio.sleep(0.5)
                
                await self.client.connect(self.recognition_worker_url, wait_timeout=5)
                await asyncio.sleep(1)  # Aguardar conexão estabilizar
            return self.connected
        except Exception as e:
            logger.error(f"Erro ao conectar ao Recognition Worker: {e}")
            logger.warning("[WARNING] Recognition Worker não disponível - sistema funcionará em modo limitado")
            return False
    
    async def disconnect_from_worker(self):
        """Desconectar do Recognition Worker"""
        try:
            if self.connected:
                await self.client.disconnect()
        except Exception as e:
            logger.error(f"Erro ao desconectar do Recognition Worker: {e}")
    
    async def extract_face_embedding(self, image_data: bytes) -> Optional[np.ndarray]:
        """Extrair embedding de face usando Recognition Worker"""
        try:
            if not await self.connect_to_worker():
                logger.warning("Recognition Worker não disponível para extração de embedding")
                return None
            
            # Converter imagem para base64
            image_base64 = base64.b64encode(image_data).decode('utf-8')
            
            # Preparar dados para envio
            request_data = {
                'image_data': image_base64,
                'request_type': 'extract_embedding'
            }
            
            # Usar Future para aguardar resposta
            response_future = asyncio.Future()
            request_id = f"embed_{asyncio.get_event_loop().time()}"
            
            # Callback para resposta
            @self.client.event
            async def embedding_response(data):
                if data.get('request_id') == request_id:
                    if not response_future.done():
                        response_future.set_result(data)
            
            # Enviar solicitação
            await self.client.emit('extract_embedding', {
                **request_data,
                'request_id': request_id
            })
            
            # Aguardar resposta com timeout
            try:
                response = await asyncio.wait_for(response_future, timeout=10.0)
                
                if response.get('success') and response.get('embedding'):
                    # Converter embedding de volta para numpy
                    embedding_data = response['embedding']
                    if isinstance(embedding_data, list):
                        return np.array(embedding_data, dtype=np.float32)
                    else:
                        return np.frombuffer(
                            base64.b64decode(embedding_data), 
                            dtype=np.float32
                        )
                else:
                    logger.warning(f"Falha na extração de embedding: {response.get('error', 'Erro desconhecido')}")
                    return None
                    
            except asyncio.TimeoutError:
                logger.warning("Timeout ao extrair embedding do Recognition Worker")
                return None
                
        except Exception as e:
            logger.error(f"Erro ao extrair embedding: {e}")
            return None
    
    async def add_known_face(self, person_id: str, embedding: np.ndarray, person_name: str = "") -> bool:
        """Adicionar face conhecida ao Recognition Worker"""
        try:
            if not await self.connect_to_worker():
                logger.warning("Recognition Worker não disponível para adicionar face")
                return False
            
            # Converter embedding para base64
            embedding_base64 = base64.b64encode(embedding.tobytes()).decode('utf-8')
            
            # Preparar dados
            request_data = {
                'person_id': person_id,
                'person_name': person_name,
                'embedding': embedding_base64,
                'request_type': 'add_known_face'
            }
            
            # Usar Future para aguardar resposta
            response_future = asyncio.Future()
            request_id = f"add_{asyncio.get_event_loop().time()}"
            
            # Callback para resposta
            @self.client.event
            async def add_face_response(data):
                if data.get('request_id') == request_id:
                    if not response_future.done():
                        response_future.set_result(data)
            
            # Enviar solicitação
            await self.client.emit('add_known_face', {
                **request_data,
                'request_id': request_id
            })
            
            # Aguardar resposta
            try:
                response = await asyncio.wait_for(response_future, timeout=5.0)
                success = response.get('success', False)
                if success:
                    logger.info(f"[OK] Face adicionada ao Recognition Worker: {person_name} ({person_id})")
                else:
                    logger.warning(f"Falha ao adicionar face: {response.get('error', 'Erro desconhecido')}")
                return success
                
            except asyncio.TimeoutError:
                logger.warning("Timeout ao adicionar face ao Recognition Worker")
                return False
                
        except Exception as e:
            logger.error(f"Erro ao adicionar face conhecida: {e}")
            return False
    
    async def reload_known_faces(self) -> bool:
        """Solicitar reload das faces conhecidas no Recognition Worker"""
        try:
            if not await self.connect_to_worker():
                return False
            
            await self.client.emit('reload_faces', {})
            logger.info("[OK] Solicitado reload das faces conhecidas")
            return True
            
        except Exception as e:
            logger.error(f"Erro ao solicitar reload das faces: {e}")
            return False
    
    async def recognize_faces(self, frame_bytes: bytes) -> List[Dict[str, Any]]:
        """Enviar frame para o Recognition Worker para processamento"""
        try:
            if not await self.connect_to_worker():
                logger.warning("Recognition Worker não disponível para reconhecimento")
                return []
            
            # Converter frame para base64
            frame_base64 = base64.b64encode(frame_bytes).decode('utf-8')
            
            # Preparar dados da solicitação
            request_data = {
                'frame_data': frame_base64,
                'request_type': 'recognize_frame'
            }
            
            # Usar Future para resposta
            response_future = asyncio.Future()
            request_id = f"recognize_{time.time()}"
            
            # Callback para resposta
            @self.client.event
            async def recognition_response(data):
                if data.get('request_id') == request_id:
                    if not response_future.done():
                        response_future.set_result(data)
            
            # Enviar solicitação
            await self.client.emit('recognize_frame', {
                **request_data,
                'request_id': request_id
            })
            
            # Aguardar resposta
            try:
                response = await asyncio.wait_for(response_future, timeout=10.0)
                return response.get('recognitions', [])
            except asyncio.TimeoutError:
                logger.warning("Timeout aguardando resposta de reconhecimento")
                return []
                
        except Exception as e:
            logger.error(f"Erro no reconhecimento de faces: {e}")
            return []


# Instância global do cliente
recognition_client = RecognitionWorkerClient()