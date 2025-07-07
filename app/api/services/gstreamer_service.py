"""
GStreamer Service Stub - MODO DISTRIBUÍDO
Esta versão é um stub - toda funcionalidade de câmera agora é externa (MSYS2)
A API não mais depende de GStreamer internamente.
"""

import asyncio
from typing import Dict, Any, Optional, List
from loguru import logger

# GStreamer functionality is now external - no internal dependencies
GSTREAMER_AVAILABLE = False


class GStreamerService:
    """Stub para serviço GStreamer - funcionalidade movida para worker externo"""
    
    def __init__(self):
        """Inicializar stub do serviço"""
        self.is_initialized = False
        self.cameras = {}
        self.status = {
            'available': False,
            'initialized': False,
            'cameras': {},
            'version': "external",
            'mode': 'distributed'
        }
        
        logger.info("[PROCESSING] GStreamer Service em modo distribuído - funcionalidade externa")
    
    def _initialize(self):
        """Stub - inicialização não necessária"""
        self.is_initialized = True
        logger.info("[OK] GStreamer Service stub inicializado")
    
    def get_status(self) -> Dict[str, Any]:
        """Retornar status do serviço stub"""
        return {
            **self.status,
            'message': 'Camera functionality handled by external MSYS2 worker',
            'worker_url': 'External MSYS2 process'
        }
    
    def start_stream(self, camera_url: str, **kwargs) -> Dict[str, Any]:
        """Stub - streaming é tratado pelo worker externo"""
        logger.warning("[PROCESSING] Stream request - handled by external camera worker")
        return {
            'success': False,
            'message': 'Streaming handled by external camera worker (MSYS2)',
            'camera_url': camera_url
        }
    
    def stop_stream(self, camera_url: str) -> Dict[str, Any]:
        """Stub - parar stream"""
        logger.warning("[PROCESSING] Stop stream request - handled by external camera worker")
        return {
            'success': False,
            'message': 'Stream control handled by external camera worker (MSYS2)',
            'camera_url': camera_url
        }
    
    def capture_snapshot(self, camera_url: str, **kwargs) -> Dict[str, Any]:
        """Stub - captura de snapshot"""
        logger.warning("[PROCESSING] Snapshot request - handled by external camera worker")
        return {
            'success': False,
            'message': 'Snapshot capture handled by external camera worker (MSYS2)',
            'camera_url': camera_url
        }
    
    def get_frame(self, camera_url: str, **kwargs) -> Optional[Any]:
        """Stub - captura de frame"""
        logger.warning("[PROCESSING] Frame request - handled by external camera worker")
        return None
    
    def test_connection(self, camera_url: str, **kwargs) -> Dict[str, Any]:
        """Stub - teste de conexão"""
        logger.warning("[PROCESSING] Connection test - handled by external camera worker")
        return {
            'success': False,
            'message': 'Connection testing handled by external camera worker (MSYS2)',
            'camera_url': camera_url
        }
    
    def list_cameras(self) -> List[Dict[str, Any]]:
        """Stub - listar câmeras"""
        return []
    
    def cleanup(self):
        """Stub - limpeza não necessária"""
        logger.info("[PROCESSING] GStreamer Service stub cleanup")


# Instância global do serviço stub
gstreamer_api_service = GStreamerService()

# Compatibilidade com código legado
gstreamer_service = gstreamer_api_service