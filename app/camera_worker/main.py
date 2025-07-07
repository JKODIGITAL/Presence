"""
Camera Worker - Processar múltiplas câmeras usando GStreamer
"""

import asyncio
import aiohttp
import cv2
import numpy as np
import os
import sys
import platform
from typing import Dict, List, Optional
from datetime import datetime
import json
from loguru import logger
import multiprocessing as mp
from concurrent.futures import ThreadPoolExecutor
import threading
import time

# Usar configuração simplificada para ambiente MSYS2 (sem Pydantic)
try:
    # Tentar configuração normal primeiro (para ambiente Conda)
    from app.core.config import settings
    config_source = "app.core.config"
except ImportError as e:
    # Fallback para configuração simplificada (ambiente MSYS2)
    import os
    current_dir = os.path.dirname(os.path.abspath(__file__))
    if "camera_worker" in current_dir:
        # Estamos no camera_worker, usar configuração local
        from app.camera_worker.simple_config import settings
        config_source = "app.camera_worker.simple_config"
    else:
        raise e

print(f"[CameraWorker] Configuração carregada de: {config_source}")
print(f"[CameraWorker] Python: {sys.executable}")
print(f"[CameraWorker] Plataforma: {platform.system()}")
print(f"[CameraWorker] API URL: {settings.API_BASE_URL}")


async def check_gstreamer_availability():
    """Verificar disponibilidade do GStreamer"""
    try:
        from app.camera_worker.gstreamer_camera import gstreamer_service, GSTREAMER_AVAILABLE
        
        if GSTREAMER_AVAILABLE and gstreamer_service.is_initialized():
            version = gstreamer_service.get_version()
            logger.info(f"✅ GStreamer disponível e inicializado: {version}")
            
            # Verificar plugins críticos
            critical_plugins = ['rtspsrc', 'v4l2src', 'videoconvert', 'appsink']
            missing_plugins = []
            
            for plugin in critical_plugins:
                if not gstreamer_service.check_plugin(plugin):
                    missing_plugins.append(plugin)
            
            if missing_plugins:
                logger.warning(f"⚠️ Plugins críticos faltando: {', '.join(missing_plugins)}")
                logger.warning("O sistema pode funcionar com limitações")
            else:
                logger.info("✅ Todos os plugins críticos estão disponíveis")
                
            return True
        else:
            logger.error("❌ GStreamer não está disponível ou inicializado")
            
            if platform.system() == 'Windows':
                logger.error("Para instalar o GStreamer no Windows:")
                logger.error("1. Baixe em: https://gstreamer.freedesktop.org/download/")
                logger.error("2. Escolha a versão MSVC 64-bit (ou 32-bit se necessário)")
                logger.error("3. Selecione 'Complete' na instalação")
                logger.error("4. Marque a opção para adicionar ao PATH do sistema")
            else:
                logger.error("Para instalar o GStreamer no Linux:")
                logger.error("sudo apt-get install gstreamer1.0-tools gstreamer1.0-plugins-base gstreamer1.0-plugins-good")
                logger.error("sudo apt-get install gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-libav")
                logger.error("sudo apt-get install python3-gi python3-gi-cairo python3-gst-1.0")
            
            return False
    except Exception as e:
        logger.error(f"❌ Erro ao verificar GStreamer: {e}")
        return False


class GStreamerWorkerManager:
    """Gerenciador do GStreamer Worker"""
    
    def __init__(self):
        self.worker = None
        self.initialized = False
    
    async def initialize(self):
        """Inicializar o worker"""
        try:
            # Importar aqui para evitar importação circular
            from app.camera_worker.gstreamer_worker import GStreamerWorker
            
            self.worker = GStreamerWorker()
            success = await self.worker.initialize()
            self.initialized = success
            return success
        except Exception as e:
            logger.error(f"Erro ao inicializar GStreamer Worker Manager: {e}")
            logger.exception("Detalhes do erro:")
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


async def main():
    """Função principal - Usar Performance Worker"""
    logger.add(
        "logs/performance_camera_worker.log",
        rotation="1 day",
        retention="30 days",
        level="INFO",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{function}:{line} | {message}"
    )
    
    logger.info("🚀 Iniciando Performance Camera Worker...")
    
    # Verificar se deve usar performance worker ou fallback
    use_performance = os.environ.get('USE_PERFORMANCE_WORKER', 'true').lower() == 'true'
    
    if use_performance:
        logger.info("📈 Usando sistema de alta performance (multiprocessing)")
        
        # Verificar disponibilidade do GStreamer
        gstreamer_ok = await check_gstreamer_availability()
        if not gstreamer_ok:
            logger.error("❌ GStreamer não disponível - Performance Worker requer GStreamer")
            use_performance = False
    
    if use_performance:
        try:
            # Usar Performance Worker
            from app.camera_worker.performance_worker import PerformanceWorkerMain, PERFORMANCE_AVAILABLE
            
            # Verificar se os módulos estão disponíveis
            if not PERFORMANCE_AVAILABLE:
                logger.warning("⚠️ Módulos de performance não disponíveis no ambiente MSYS2")
                logger.info("🔄 Fallback para GStreamer Worker tradicional")
                use_performance = False
            else:
                worker = PerformanceWorkerMain()
                
                # Inicializar
                if not await worker.initialize():
                    logger.error("❌ Falha ao inicializar Performance Worker")
                    logger.info("🔄 Fallback para GStreamer Worker tradicional")
                    use_performance = False
                else:
                    logger.info("✅ Performance Worker inicializado com sucesso")
                    
                    # Executar
                    await worker.run()
                    return  # Sucesso, sair da função
            
        except ImportError as e:
            logger.error(f"❌ Performance Worker não disponível: {e}")
            logger.info("🔄 Fallback para GStreamer Worker tradicional")
            use_performance = False
        except Exception as e:
            logger.error(f"❌ Erro no Performance Worker: {e}")
            logger.exception("Detalhes do erro:")
            logger.info("🔄 Fallback para GStreamer Worker tradicional")
            use_performance = False
    
    if not use_performance:
        # Aguardar API estar disponível
        await wait_for_api()
        
        try:
            # Tentar worker GStreamer tradicional primeiro
            try:
                from app.camera_worker.gstreamer_worker import GStreamerWorkerManager
                worker_manager = GStreamerWorkerManager()
                logger.info("🎥 Usando GStreamer Worker tradicional")
            except ImportError as e:
                logger.warning(f"GStreamer Worker tradicional não disponível: {e}")
                logger.info("🔄 Fallback para Simple GStreamer Worker (OpenCV)")
                from app.camera_worker.simple_gstreamer_worker import SimpleGStreamerWorkerManager
                worker_manager = SimpleGStreamerWorkerManager()
            
            success = await worker_manager.initialize()
            
            if not success:
                logger.error("❌ Falha ao inicializar Worker Manager")
                # Último fallback - tentar worker ainda mais simples
                logger.info("🔄 Último fallback - Simple Camera Worker")
                from app.camera_worker.simple_gstreamer_worker import SimpleCameraWorker
                simple_worker = SimpleCameraWorker()
                if await simple_worker.initialize():
                    logger.info("✅ Simple Camera Worker inicializado")
                    await simple_worker.run()
                    return
                else:
                    logger.error("❌ Todos os workers falharam")
                    return
            
            # Mostrar mensagem APÓS a detecção das capacidades reais
            logger.info("✅ Worker inicializado com capacidades detectadas automaticamente")
            
            # Executar worker
            await worker_manager.run()
            
        except KeyboardInterrupt:
            logger.info("Interrompido pelo usuário")
        except Exception as e:
            logger.error(f"Erro no GStreamer Camera Worker: {e}")
            logger.exception("Detalhes do erro:")
        finally:
            try:
                # Limpar recursos
                if 'worker_manager' in locals():
                    await worker_manager.cleanup()
            except Exception as e:
                logger.error(f"Erro ao limpar recursos: {e}")
            logger.info("GStreamer Camera Worker finalizado")


async def wait_for_api():
    """Aguardar API estar disponível"""
    max_retries = 30
    retry_count = 0
    
    logger.info(f"Tentando conectar à API em {settings.API_BASE_URL}")
    
    while retry_count < max_retries:
        try:
            async with aiohttp.ClientSession() as session:
                # Aumentando o timeout para 10 segundos e adicionando cabeçalhos
                headers = {"Accept": "application/json", "User-Agent": "CameraWorker/1.0"}
                async with session.get(
                    f"{settings.API_BASE_URL}/health", 
                    timeout=10,
                    headers=headers
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"✅ API disponível: {data.get('status', 'status desconhecido')}")
                        return
                    else:
                        logger.warning(f"API respondeu com status {response.status}")
        except aiohttp.ClientConnectorError as e:
            logger.warning(f"Erro de conexão: {e}")
        except aiohttp.ClientTimeout:
            logger.warning("Timeout ao conectar à API")
        except Exception as e:
            logger.warning(f"Erro ao verificar API: {e}")
        
        retry_count += 1
        logger.info(f"Aguardando API... ({retry_count}/{max_retries})")
        await asyncio.sleep(2)
    
    logger.error("❌ API não disponível após várias tentativas")
    raise Exception("API não disponível")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrompido pelo usuário")
    except Exception as e:
        logger.error(f"Erro fatal: {e}")
        sys.exit(1)