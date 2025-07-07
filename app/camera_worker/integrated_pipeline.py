#!/usr/bin/env python3
"""
Pipeline Integrado: RTSP → NVDEC → Recognition Worker → OpenCV Overlay → NVENC → Janus/WebRTC
Conecta todo o pipeline de alta performance com reconhecimento facial
"""

import asyncio
import logging
import os
import sys
from typing import Dict, List, Optional
from dataclasses import dataclass
import aiohttp

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

# Importação compatível dos módulos de pipeline
try:
    from app.core.gstreamer_pipeline import HighPerformancePipeline, PipelineConfig
    PIPELINE_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Pipeline de alta performance não disponível: {e}")
    logger.info("Integrated Pipeline será desabilitado")
    PIPELINE_AVAILABLE = False
    
    # Classe dummy para compatibilidade
    class HighPerformancePipeline:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("Pipeline de alta performance não disponível no ambiente MSYS2")
    
    class PipelineConfig:
        def __init__(self, *args, **kwargs):
            pass

from loguru import logger

@dataclass
class CameraConfig:
    """Configuração de uma câmera"""
    camera_id: str
    name: str
    rtsp_url: str
    enabled: bool = True
    recognition_enabled: bool = True

class IntegratedPipelineManager:
    """Gerenciador do pipeline integrado para múltiplas câmeras"""
    
    def __init__(self):
        self.pipelines: Dict[str, HighPerformancePipeline] = {}
        self.camera_configs: Dict[str, CameraConfig] = {}
        self.is_running = False
        
        # URLs dos serviços
        self.api_base_url = os.environ.get('API_BASE_URL', 'http://127.0.0.1:17234')
        self.recognition_worker_url = os.environ.get('RECOGNITION_WORKER_URL', 'http://127.0.0.1:17235')
        self.webrtc_server_url = self.api_base_url.replace('17234', '17236')
        
        # Configurações do pipeline
        self.use_gpu = os.environ.get('USE_GPU', 'true').lower() == 'true'
        self.use_janus = os.environ.get('USE_JANUS', 'true').lower() == 'true'
        
        logger.info(f"Pipeline Manager inicializado:")
        logger.info(f"  - API: {self.api_base_url}")
        logger.info(f"  - Recognition: {self.recognition_worker_url}")
        logger.info(f"  - WebRTC: {self.webrtc_server_url}")
        logger.info(f"  - GPU: {self.use_gpu}")
        logger.info(f"  - Janus: {self.use_janus}")

    async def load_cameras_from_api(self):
        """Carrega câmeras cadastradas na API"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.api_base_url}/api/v1/cameras/active") as resp:
                    if resp.status == 200:
                        cameras_data = await resp.json()
                        logger.info(f"Carregadas {len(cameras_data)} câmeras da API")
                        
                        for camera in cameras_data:
                            camera_id = camera.get('id') or camera.get('camera_id')
                            if not camera_id:
                                continue
                                
                            # Construir URL RTSP
                            rtsp_url = camera.get('rtsp_url')
                            if not rtsp_url:
                                # Construir URL se não estiver pronta
                                ip = camera.get('ip_address')
                                port = camera.get('port', 554)
                                username = camera.get('username', '')
                                password = camera.get('password', '')
                                
                                if ip:
                                    if username and password:
                                        rtsp_url = f"rtsp://{username}:{password}@{ip}:{port}/stream1"
                                    else:
                                        rtsp_url = f"rtsp://{ip}:{port}/stream1"
                            
                            if rtsp_url:
                                config = CameraConfig(
                                    camera_id=camera_id,
                                    name=camera.get('name', f'Camera {camera_id}'),
                                    rtsp_url=rtsp_url,
                                    enabled=True,
                                    recognition_enabled=True
                                )
                                self.camera_configs[camera_id] = config
                                logger.info(f"Câmera configurada: {config.name} ({config.rtsp_url})")
                    else:
                        logger.error(f"Erro ao buscar câmeras: HTTP {resp.status}")
                        
        except Exception as e:
            logger.error(f"Erro ao carregar câmeras: {e}")
    
    async def create_pipeline_for_camera(self, camera_config: CameraConfig) -> bool:
        """Cria pipeline para uma câmera específica"""
        try:
            pipeline_config = PipelineConfig(
                rtsp_url=camera_config.rtsp_url,
                camera_id=camera_config.camera_id,
                output_width=1280,
                output_height=720,
                fps=25,  # 25 FPS para melhor performance
                use_hardware_decode=self.use_gpu,
                use_hardware_encode=self.use_gpu,
                use_janus=self.use_janus,
                recognition_worker_url=self.recognition_worker_url,
                api_base_url=self.api_base_url,
                enable_recognition=camera_config.recognition_enabled
            )
            
            pipeline = HighPerformancePipeline(pipeline_config)
            
            # Iniciar pipeline
            logger.info(f"Iniciando pipeline para {camera_config.name}...")
            success = await pipeline.start()
            
            if success:
                self.pipelines[camera_config.camera_id] = pipeline
                logger.info(f"✅ Pipeline criado para {camera_config.name}")
                return True
            else:
                logger.error(f"❌ Falha ao criar pipeline para {camera_config.name}")
                return False
                
        except Exception as e:
            logger.error(f"Erro ao criar pipeline para {camera_config.name}: {e}")
            return False
    
    async def start_all_pipelines(self):
        """Inicia pipelines para todas as câmeras"""
        if not self.camera_configs:
            logger.warning("Nenhuma câmera configurada")
            return
        
        self.is_running = True
        success_count = 0
        
        for camera_id, config in self.camera_configs.items():
            if config.enabled:
                try:
                    success = await self.create_pipeline_for_camera(config)
                    if success:
                        success_count += 1
                        # Aguardar um pouco entre inicializações
                        await asyncio.sleep(2)
                except Exception as e:
                    logger.error(f"Erro ao iniciar pipeline {camera_id}: {e}")
        
        logger.info(f"Pipeline Manager: {success_count}/{len(self.camera_configs)} câmeras iniciadas")
        
        if success_count > 0:
            logger.info("🎥 Sistema de pipeline integrado ativo:")
            logger.info("   RTSP → NVDEC → Recognition Worker → OpenCV → NVENC → Janus/WebRTC")
        
        return success_count > 0

    def stop_all_pipelines(self):
        """Para todos os pipelines"""
        self.is_running = False
        
        for camera_id, pipeline in self.pipelines.items():
            try:
                pipeline.stop()
                logger.info(f"Pipeline parado: {camera_id}")
            except Exception as e:
                logger.error(f"Erro ao parar pipeline {camera_id}: {e}")
        
        self.pipelines.clear()
        logger.info("Todos os pipelines foram parados")

    async def run(self):
        """Executa o gerenciador de pipeline"""
        try:
            # Carregar câmeras
            await self.load_cameras_from_api()
            
            # Iniciar pipelines
            success = await self.start_all_pipelines()
            
            if not success:
                logger.error("Nenhum pipeline foi iniciado com sucesso")
                return
            
            # Manter rodando
            logger.info("Pipeline Manager rodando... (Ctrl+C para parar)")
            try:
                while self.is_running:
                    await asyncio.sleep(1)
                    
                    # Health check dos pipelines
                    active_count = len([p for p in self.pipelines.values() if p.is_running])
                    if active_count == 0 and self.is_running:
                        logger.warning("Todos os pipelines foram interrompidos")
                        break
                        
            except KeyboardInterrupt:
                logger.info("Interrompido pelo usuário")
            
        except Exception as e:
            logger.error(f"Erro no Pipeline Manager: {e}")
        finally:
            self.stop_all_pipelines()

    def get_status(self) -> Dict:
        """Retorna status do sistema"""
        return {
            "is_running": self.is_running,
            "total_cameras": len(self.camera_configs),
            "active_pipelines": len(self.pipelines),
            "camera_status": {
                camera_id: {
                    "name": config.name,
                    "enabled": config.enabled,
                    "pipeline_active": camera_id in self.pipelines,
                    "pipeline_running": self.pipelines[camera_id].is_running if camera_id in self.pipelines else False
                }
                for camera_id, config in self.camera_configs.items()
            }
        }

async def main():
    """Função principal"""
    logging.basicConfig(level=logging.INFO)
    
    print("=" * 60)
    print("  PIPELINE INTEGRADO - SISTEMA COMPLETO")
    print("=" * 60)
    print()
    print("Arquitetura:")
    print("  RTSP → GStreamer NVDEC → Recognition Worker → OpenCV Overlay → NVENC → Janus → Frontend")
    print()
    
    manager = IntegratedPipelineManager()
    await manager.run()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Sistema finalizado pelo usuário")
    except Exception as e:
        logger.error(f"Erro fatal: {e}")
        sys.exit(1)