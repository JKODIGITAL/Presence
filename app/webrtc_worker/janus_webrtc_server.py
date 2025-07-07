#!/usr/bin/env python3
"""
Janus WebRTC Server - Solução escalável para múltiplas câmeras
Usando Janus Gateway como SFU (Selective Forwarding Unit)
"""

import asyncio
import json
import logging
import os
import sys
import time
import uuid
from typing import Dict, List, Optional, Any
from pathlib import Path
import aiohttp
import subprocess
from dataclasses import dataclass
from datetime import datetime

# FastAPI para interface
from fastapi import FastAPI, WebSocket, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class JanusStream:
    """Representa uma stream no Janus"""
    id: int
    camera_id: str
    name: str
    description: str
    rtsp_url: str
    audio_port: int
    video_port: int
    gstreamer_process: Optional[subprocess.Popen] = None
    created_at: datetime = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()

class JanusWebRTCServer:
    """
    Servidor WebRTC usando Janus Gateway para distribuição eficiente
    de múltiplas câmeras via WebRTC
    """
    
    def __init__(self, 
                 janus_http_url: str = "http://localhost:8088/janus",
                 janus_ws_url: str = "ws://localhost:8188",
                 api_url: str = "http://localhost:17234"):
        
        self.janus_http_url = janus_http_url
        self.janus_ws_url = janus_ws_url
        self.api_url = api_url
        
        # Estado das streams
        self.streams: Dict[str, JanusStream] = {}
        self.next_stream_id = 1
        self.base_rtp_port = 5000
        
        # FastAPI app
        self.app = FastAPI(title="Janus WebRTC Server")
        self.setup_routes()
        
        logger.info(f"[JANUS] Servidor inicializado")
        logger.info(f"[JANUS] HTTP API: {janus_http_url}")
        logger.info(f"[JANUS] WebSocket: {janus_ws_url}")
    
    def setup_routes(self):
        """Configura rotas FastAPI"""
        
        # CORS
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
        @self.app.get("/health")
        async def health():
            """Health check endpoint"""
            janus_ok = await self.check_janus_health()
            return {
                "status": "healthy" if janus_ok else "degraded",
                "mode": "janus_sfu",
                "janus_connected": janus_ok,
                "active_streams": len(self.streams),
                "streams": list(self.streams.keys())
            }
        
        @self.app.get("/streams")
        async def list_streams():
            """Lista todas as streams disponíveis"""
            return {
                "streams": [
                    {
                        "id": stream.id,
                        "camera_id": stream.camera_id,
                        "name": stream.name,
                        "description": stream.description,
                        "created_at": stream.created_at.isoformat()
                    }
                    for stream in self.streams.values()
                ]
            }
        
        @self.app.post("/streams/{camera_id}/start")
        async def start_stream(camera_id: str):
            """Inicia stream para uma câmera"""
            if camera_id in self.streams:
                return {"status": "already_streaming", "stream_id": self.streams[camera_id].id}
            
            # Buscar info da câmera
            camera_info = await self.get_camera_info(camera_id)
            if not camera_info:
                raise HTTPException(status_code=404, detail="Camera not found")
            
            # Criar stream no Janus
            stream = await self.create_janus_stream(camera_id, camera_info)
            
            return {
                "status": "streaming",
                "stream_id": stream.id,
                "janus_info": {
                    "ws_url": self.janus_ws_url,
                    "stream_id": stream.id
                }
            }
        
        @self.app.post("/streams/{camera_id}/stop")
        async def stop_stream(camera_id: str):
            """Para stream de uma câmera"""
            if camera_id not in self.streams:
                raise HTTPException(status_code=404, detail="Stream not found")
            
            await self.destroy_janus_stream(camera_id)
            return {"status": "stopped"}
        
        @self.app.websocket("/ws/{camera_id}")
        async def websocket_endpoint(websocket: WebSocket, camera_id: str):
            """
            WebSocket endpoint para compatibilidade com frontend existente
            Redireciona para Janus
            """
            await websocket.accept()
            logger.info(f"[WS] Cliente conectado para câmera {camera_id}")
            
            try:
                # Garantir que a stream existe no Janus
                if camera_id not in self.streams:
                    camera_info = await self.get_camera_info(camera_id)
                    if camera_info:
                        await self.create_janus_stream(camera_id, camera_info)
                
                # Enviar info de conexão do Janus
                if camera_id in self.streams:
                    stream = self.streams[camera_id]
                    await websocket.send_json({
                        "type": "janus_redirect",
                        "janus_ws": self.janus_ws_url,
                        "stream_id": stream.id,
                        "plugin": "janus.plugin.streaming"
                    })
                else:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Failed to create stream"
                    })
                
                # Manter conexão aberta para compatibilidade
                while True:
                    data = await websocket.receive_text()
                    # Processar comandos se necessário
                    
            except Exception as e:
                logger.error(f"[WS] Erro: {e}")
            finally:
                await websocket.close()
    
    async def check_janus_health(self) -> bool:
        """Verifica se o Janus está rodando"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.janus_http_url + "/info") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        logger.info(f"[JANUS] Versão: {data.get('version_string', 'unknown')}")
                        return True
        except Exception as e:
            logger.error(f"[JANUS] Health check falhou: {e}")
        return False
    
    async def get_camera_info(self, camera_id: str) -> Optional[Dict]:
        """Busca informações da câmera da API"""
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.api_url}/api/v1/cameras/{camera_id}"
                async with session.get(url) as resp:
                    if resp.status == 200:
                        return await resp.json()
        except Exception as e:
            logger.error(f"[API] Erro ao buscar câmera {camera_id}: {e}")
        return None
    
    async def create_janus_stream(self, camera_id: str, camera_info: Dict) -> JanusStream:
        """Cria uma nova stream no Janus"""
        
        # Configurar portas RTP
        stream_id = self.next_stream_id
        self.next_stream_id += 1
        
        audio_port = self.base_rtp_port + (stream_id * 2)
        video_port = audio_port + 1
        
        rtsp_url = camera_info.get('rtsp_url') or camera_info.get('url')
        
        # Criar objeto stream
        stream = JanusStream(
            id=stream_id,
            camera_id=camera_id,
            name=camera_info.get('name', f'Camera {camera_id}'),
            description=camera_info.get('description', ''),
            rtsp_url=rtsp_url,
            audio_port=audio_port,
            video_port=video_port
        )
        
        # Iniciar GStreamer pipeline
        await self.start_gstreamer_pipeline(stream)
        
        # Registrar stream no Janus
        await self.register_stream_in_janus(stream)
        
        # Salvar no estado
        self.streams[camera_id] = stream
        
        logger.info(f"[JANUS] Stream criada: {camera_id} (ID: {stream_id})")
        return stream
    
    async def start_gstreamer_pipeline(self, stream: JanusStream):
        """Inicia pipeline GStreamer para enviar RTP ao Janus"""
        
        # Pipeline para arquivos MP4
        if stream.rtsp_url.endswith('.mp4'):
            pipeline = f"""
                filesrc location={stream.rtsp_url} ! 
                qtdemux ! h264parse ! rtph264pay config-interval=-1 pt=96 ! 
                udpsink host=127.0.0.1 port={stream.video_port}
            """
        # Pipeline para RTSP
        else:
            pipeline = f"""
                rtspsrc location={stream.rtsp_url} latency=100 ! 
                rtph264depay ! h264parse ! rtph264pay config-interval=-1 pt=96 ! 
                udpsink host=127.0.0.1 port={stream.video_port}
            """
        
        # Remover quebras de linha
        pipeline = pipeline.replace('\n', ' ').strip()
        
        logger.info(f"[GST] Iniciando pipeline para {stream.camera_id}")
        logger.info(f"[GST] Pipeline: {pipeline}")
        
        # Executar GStreamer
        try:
            process = subprocess.Popen([
                'gst-launch-1.0', '-v'
            ] + pipeline.split(), 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE)
            
            stream.gstreamer_process = process
            
            # Aguardar um pouco para garantir que iniciou
            await asyncio.sleep(2)
            
            if process.poll() is None:
                logger.info(f"[GST] Pipeline rodando para {stream.camera_id}")
            else:
                logger.error(f"[GST] Pipeline falhou para {stream.camera_id}")
                
        except Exception as e:
            logger.error(f"[GST] Erro ao iniciar pipeline: {e}")
    
    async def register_stream_in_janus(self, stream: JanusStream):
        """Registra a stream no plugin streaming do Janus"""
        
        # Configuração da stream para o Janus
        stream_config = {
            "request": "create",
            "type": "rtp",
            "id": stream.id,
            "name": stream.name,
            "description": stream.description,
            "audio": False,  # Apenas vídeo por enquanto
            "video": True,
            "videoport": stream.video_port,
            "videopt": 96,
            "videortpmap": "H264/90000",
            "videofmtp": "profile-level-id=42e01f;packetization-mode=1"
        }
        
        try:
            # Criar sessão no Janus
            session_id = await self.create_janus_session()
            
            # Attach ao plugin streaming
            handle_id = await self.attach_to_streaming_plugin(session_id)
            
            # Criar a stream
            async with aiohttp.ClientSession() as session:
                url = f"{self.janus_http_url}/{session_id}/{handle_id}"
                payload = {
                    "janus": "message",
                    "body": stream_config,
                    "transaction": str(uuid.uuid4())
                }
                
                async with session.post(url, json=payload) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        logger.info(f"[JANUS] Stream registrada: {result}")
                    else:
                        logger.error(f"[JANUS] Erro ao registrar stream: {resp.status}")
                        
        except Exception as e:
            logger.error(f"[JANUS] Erro ao registrar stream: {e}")
    
    async def create_janus_session(self) -> int:
        """Cria uma sessão no Janus"""
        async with aiohttp.ClientSession() as session:
            payload = {
                "janus": "create",
                "transaction": str(uuid.uuid4())
            }
            async with session.post(self.janus_http_url, json=payload) as resp:
                data = await resp.json()
                return data["data"]["id"]
    
    async def attach_to_streaming_plugin(self, session_id: int) -> int:
        """Attach ao plugin streaming do Janus"""
        async with aiohttp.ClientSession() as session:
            url = f"{self.janus_http_url}/{session_id}"
            payload = {
                "janus": "attach",
                "plugin": "janus.plugin.streaming",
                "transaction": str(uuid.uuid4())
            }
            async with session.post(url, json=payload) as resp:
                data = await resp.json()
                return data["data"]["id"]
    
    async def destroy_janus_stream(self, camera_id: str):
        """Remove uma stream do Janus"""
        if camera_id not in self.streams:
            return
        
        stream = self.streams[camera_id]
        
        # Parar GStreamer
        if stream.gstreamer_process:
            stream.gstreamer_process.terminate()
            await asyncio.sleep(1)
            if stream.gstreamer_process.poll() is None:
                stream.gstreamer_process.kill()
        
        # TODO: Remover stream do Janus via API
        
        # Remover do estado
        del self.streams[camera_id]
        
        logger.info(f"[JANUS] Stream removida: {camera_id}")
    
    async def initialize(self):
        """Inicializa o servidor"""
        # Verificar Janus
        if not await self.check_janus_health():
            logger.error("[JANUS] Janus Gateway não está rodando!")
            logger.info("[JANUS] Instale e inicie o Janus:")
            logger.info("  sudo apt install janus")
            logger.info("  janus -F /etc/janus")
            return False
        
        # Carregar câmeras ativas
        await self.load_active_cameras()
        
        return True
    
    async def load_active_cameras(self):
        """Carrega câmeras ativas da API"""
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.api_url}/api/v1/cameras/active"
                async with session.get(url) as resp:
                    if resp.status == 200:
                        cameras = await resp.json()
                        logger.info(f"[JANUS] {len(cameras)} câmeras encontradas")
                        
                        # Auto-iniciar streams
                        for camera in cameras[:2]:  # Limitar a 2 para teste
                            await self.create_janus_stream(
                                camera['id'], 
                                camera
                            )
                            
        except Exception as e:
            logger.error(f"[JANUS] Erro ao carregar câmeras: {e}")
    
    async def run(self, host: str = "0.0.0.0", port: int = 17236):
        """Executa o servidor"""
        if not await self.initialize():
            return
        
        config = uvicorn.Config(
            app=self.app,
            host=host,
            port=port,
            log_level="info",
            access_log=True
        )
        server = uvicorn.Server(config)
        await server.serve()


async def main():
    """Main function"""
    server = JanusWebRTCServer()
    await server.run()


if __name__ == "__main__":
    asyncio.run(main())