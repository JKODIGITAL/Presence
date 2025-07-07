"""
Simple GStreamer Worker para ambiente MSYS2
Focado em estabilidade e compatibilidade máxima
"""

import asyncio
import aiohttp
import base64
import json
import os
import sys
import time
import threading
from typing import Dict, List, Optional
from datetime import datetime
from loguru import logger
import numpy as np
import cv2

# Importar configuração local (MSYS2)
from app.camera_worker.simple_config import settings

# Importar GStreamer simplificado
try:
    from app.camera_worker.simple_gstreamer_init import (
        Gst, GstApp, GLib, GSTREAMER_AVAILABLE, gstreamer_error
    )
except ImportError as e:
    logger.error(f"Erro ao importar GStreamer: {e}")
    GSTREAMER_AVAILABLE = False


class SimpleCameraWorker:
    """Worker simplificado para câmeras usando apenas OpenCV como fallback"""
    
    def __init__(self):
        self.cameras = {}
        self.running = False
        self.api_url = settings.API_BASE_URL
        self.recognition_url = settings.RECOGNITION_WORKER_URL
        self.socket_client = None
        
        logger.info("SimpleCameraWorker inicializado")
    
    async def initialize(self) -> bool:
        """Inicializar o worker"""
        try:
            logger.info("🚀 Inicializando Simple Camera Worker...")
            
            # Aguardar API estar disponível
            await self._wait_for_api()
            
            # Tentar conectar ao Recognition Worker via Socket.IO
            await self._connect_to_recognition_worker()
            
            # Carregar câmeras do banco
            await self._load_cameras()
            
            self.running = True
            logger.info("✅ Simple Camera Worker inicializado com sucesso")
            return True
            
        except Exception as e:
            logger.error(f"❌ Erro ao inicializar Simple Camera Worker: {e}")
            return False
    
    async def _wait_for_api(self):
        """Aguardar API estar disponível"""
        max_retries = 30
        retry_count = 0
        
        logger.info(f"Aguardando API em {self.api_url}")
        
        while retry_count < max_retries:
            try:
                timeout = aiohttp.ClientTimeout(total=10)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(f"{self.api_url}/health") as response:
                        if response.status == 200:
                            data = await response.json()
                            logger.info(f"✅ API disponível: {data.get('status', 'unknown')}")
                            return
                        else:
                            logger.warning(f"API respondeu com status {response.status}")
                            
            except Exception as e:
                logger.debug(f"API não disponível ainda: {e}")
            
            retry_count += 1
            await asyncio.sleep(2)
            
            if retry_count % 5 == 0:
                logger.info(f"API ainda não disponível, aguardando... ({retry_count}/{max_retries})")
        
        logger.warning("⚠️ API não disponível, mas continuando...")
    
    async def _connect_to_recognition_worker(self):
        """Conectar ao Recognition Worker via Socket.IO"""
        try:
            import socketio
            
            logger.info(f"Conectando ao Recognition Worker em {self.recognition_url}")
            
            self.socket_client = socketio.AsyncClient()
            
            @self.socket_client.event
            async def connect():
                logger.info("✅ Conectado ao Recognition Worker")
            
            @self.socket_client.event
            async def disconnect():
                logger.warning("❌ Desconectado do Recognition Worker")
            
            @self.socket_client.event
            async def recognition_result(data):
                """Receber resultado do recognition worker"""
                try:
                    camera_id = data.get('camera_id')
                    faces_detected = data.get('faces_detected', 0)
                    recognitions = data.get('recognitions', [])
                    
                    logger.info(f"🎯 Resultado: Câmera {camera_id}, {faces_detected} faces, {len(recognitions)} reconhecimentos")
                    
                    for recognition in recognitions:
                        if recognition.get('person_id') and not recognition.get('is_unknown', False):
                            person_name = recognition.get('person_name', 'Desconhecido')
                            confidence = recognition.get('confidence', 0)
                            logger.info(f"👤 {person_name} reconhecido (conf: {confidence:.2f})")
                    
                except Exception as e:
                    logger.error(f"Erro ao processar resultado: {e}")
            
            # Conectar
            try:
                await asyncio.wait_for(
                    self.socket_client.connect(self.recognition_url),
                    timeout=10.0
                )
                logger.info("✅ Conexão com Recognition Worker estabelecida")
            except asyncio.TimeoutError:
                logger.warning("⏰ Timeout ao conectar com Recognition Worker")
                
        except ImportError:
            logger.warning("⚠️ Socket.IO não disponível - funcionando sem comunicação com Recognition Worker")
        except Exception as e:
            logger.warning(f"⚠️ Não foi possível conectar ao Recognition Worker: {e}")
    
    async def _load_cameras(self):
        """Carregar câmeras do banco de dados via API"""
        try:
            logger.info("Carregando câmeras do banco de dados...")
            
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(f"{self.api_url}/api/v1/cameras") as response:
                    if response.status == 200:
                        response_data = await response.json()
                        
                        # Verificar formato da resposta
                        if isinstance(response_data, dict) and 'cameras' in response_data:
                            cameras_data = response_data['cameras']
                        elif isinstance(response_data, list):
                            cameras_data = response_data
                        else:
                            cameras_data = []
                        
                        logger.info(f"Encontradas {len(cameras_data)} câmeras no banco")
                        
                        # Processar cada câmera
                        for camera in cameras_data:
                            camera_id = str(camera.get('id'))
                            camera_url = camera.get('url') or camera.get('connection_string')
                            is_enabled = camera.get('status') == 'active' or camera.get('enabled', True)
                            
                            if is_enabled and camera_url:
                                logger.info(f"Câmera {camera_id} encontrada: {camera_url}")
                                self.cameras[camera_id] = {
                                    'id': camera_id,
                                    'url': camera_url,
                                    'name': camera.get('name', f'Camera {camera_id}'),
                                    'active': False
                                }
                            else:
                                logger.warning(f"Câmera {camera_id} desabilitada ou sem URL")
                        
                        logger.info(f"Carregamento concluído. {len(self.cameras)} câmeras ativas")
                        
                    else:
                        logger.error(f"Erro ao carregar câmeras: status {response.status}")
        
        except Exception as e:
            logger.error(f"Erro ao carregar câmeras: {e}")
            
            # Criar câmera de teste se não conseguir carregar do banco
            logger.info("Criando câmera de teste...")
            self.cameras['test'] = {
                'id': 'test',
                'url': '0',  # Câmera padrão (webcam)
                'name': 'Test Camera',
                'active': False
            }
    
    async def start_camera_processing(self):
        """Iniciar processamento de câmeras usando OpenCV"""
        if not self.cameras:
            logger.warning("Nenhuma câmera configurada")
            return
        
        logger.info(f"Iniciando processamento de {len(self.cameras)} câmeras...")
        
        # Iniciar uma thread para cada câmera
        tasks = []
        for camera_id, camera_info in self.cameras.items():
            task = asyncio.create_task(self._process_camera(camera_id, camera_info))
            tasks.append(task)
        
        # Aguardar todas as tarefas
        try:
            await asyncio.gather(*tasks)
        except Exception as e:
            logger.error(f"Erro no processamento de câmeras: {e}")
    
    async def _process_camera(self, camera_id: str, camera_info: dict):
        """Processar uma câmera específica usando OpenCV"""
        logger.info(f"Iniciando processamento da câmera {camera_id}: {camera_info['name']}")
        
        cap = None
        frame_count = 0
        consecutive_failures = 0
        max_failures = 10
        
        try:
            # Abrir câmera com OpenCV
            camera_url = camera_info['url']
            
            # Se for número, converter para int (webcam)
            if camera_url.isdigit():
                camera_url = int(camera_url)
            elif camera_url.endswith('.mp4') or camera_url.endswith('.avi'):
                # Para arquivos de vídeo, verificar se existe
                if not os.path.exists(camera_url):
                    # Tentar caminho relativo a partir do projeto
                    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                    full_path = os.path.join(project_root, camera_url)
                    if os.path.exists(full_path):
                        camera_url = full_path
                        logger.info(f"Arquivo de vídeo encontrado: {camera_url}")
                    else:
                        logger.error(f"❌ Arquivo de vídeo não encontrado: {camera_url}")
                        return
            
            cap = cv2.VideoCapture(camera_url)
            
            if not cap.isOpened():
                logger.error(f"❌ Não foi possível abrir câmera {camera_id}")
                return
            
            # Configurar propriedades da câmera
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, settings.CAMERA_FRAME_WIDTH)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, settings.CAMERA_FRAME_HEIGHT)
            cap.set(cv2.CAP_PROP_FPS, settings.CAMERA_FPS_LIMIT)
            
            logger.info(f"✅ Câmera {camera_id} aberta com sucesso")
            camera_info['active'] = True
            
            # Loop de processamento
            while self.running:
                ret, frame = cap.read()
                
                if not ret:
                    consecutive_failures += 1
                    if consecutive_failures > max_failures:
                        logger.error(f"❌ Muitas falhas consecutivas na câmera {camera_id}, parando...")
                        break
                    
                    logger.warning(f"Falha ao capturar frame da câmera {camera_id} ({consecutive_failures}/{max_failures})")
                    
                    # Para arquivos de vídeo, tentar reiniciar do início
                    if isinstance(camera_url, str) and (camera_url.endswith('.mp4') or camera_url.endswith('.avi')):
                        logger.info(f"Reiniciando arquivo de vídeo {camera_id}")
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    
                    await asyncio.sleep(2)
                    continue
                
                # Reset contador de falhas em caso de sucesso
                consecutive_failures = 0
                frame_count += 1
                
                # Processar apenas a cada 5 frames para economizar recursos
                if frame_count % 5 == 0:
                    await self._send_frame_for_recognition(camera_id, frame)
                
                # Pequena pausa para não sobrecarregar
                await asyncio.sleep(0.2)
                
        except Exception as e:
            logger.error(f"Erro no processamento da câmera {camera_id}: {e}")
        finally:
            if cap:
                cap.release()
            camera_info['active'] = False
            logger.info(f"Câmera {camera_id} finalizada")
    
    async def _send_frame_for_recognition(self, camera_id: str, frame):
        """Enviar frame para o Recognition Worker"""
        try:
            if not self.socket_client:
                return
            
            # Comprimir frame para reduzir tamanho
            _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            frame_base64 = base64.b64encode(buffer).decode('utf-8')
            
            # Criar dados para envio
            data = {
                'camera_id': camera_id,
                'frame_id': f"{camera_id}_{int(time.time() * 1000)}",
                'timestamp': datetime.now().isoformat(),
                'frame_base64': frame_base64,
                'frame_shape': frame.shape,
                'processing_time_ms': 0
            }
            
            # Enviar frame para processamento
            await self.socket_client.emit('process_frame', data)
            logger.debug(f"Frame da câmera {camera_id} enviado para reconhecimento")
            
        except Exception as e:
            logger.error(f"Erro ao enviar frame para reconhecimento: {e}")
    
    async def run(self):
        """Executar o worker"""
        try:
            logger.info("📹 Simple Camera Worker em execução")
            
            # Iniciar processamento de câmeras
            await self.start_camera_processing()
            
        except KeyboardInterrupt:
            logger.info("Interrompido pelo usuário")
        except Exception as e:
            logger.error(f"Erro no loop principal: {e}")
        finally:
            await self.cleanup()
    
    async def cleanup(self):
        """Limpar recursos"""
        try:
            logger.info("Limpando recursos...")
            
            self.running = False
            
            # Desconectar Socket.IO
            if self.socket_client:
                await self.socket_client.disconnect()
            
            logger.info("✅ Recursos limpos")
            
        except Exception as e:
            logger.error(f"Erro ao limpar recursos: {e}")


class SimpleGStreamerWorkerManager:
    """Gerenciador simplificado compatível com o main.py"""
    
    def __init__(self):
        self.worker = None
        self.initialized = False
    
    async def initialize(self):
        """Inicializar o worker"""
        try:
            self.worker = SimpleCameraWorker()
            success = await self.worker.initialize()
            self.initialized = success
            return success
        except Exception as e:
            logger.error(f"Erro ao inicializar Simple GStreamer Worker Manager: {e}")
            return False
    
    async def run(self):
        """Executar o worker"""
        if not self.initialized or not self.worker:
            logger.error("Worker não está inicializado")
            return
            
        await self.worker.run()
    
    async def cleanup(self):
        """Limpar recursos"""
        if self.worker:
            await self.worker.cleanup()


# Compatibilidade com o main.py
GStreamerWorkerManager = SimpleGStreamerWorkerManager