"""
Configuração simplificada para Camera Worker MSYS2
SEM dependências do Pydantic - compatível com MSYS2
"""

import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any, Union


class SimpleSettings:
    """Configurações simplificadas sem Pydantic para Camera Worker MSYS2"""
    
    def __init__(self):
        # Configurações gerais
        self.APP_NAME = "Presence Camera Worker"
        self.APP_VERSION = "1.0.0"
        self.DEBUG = os.environ.get('DEBUG', 'false').lower() == 'true'
        
        # Diretórios de dados
        self.BASE_DIR = Path(__file__).parent.parent.parent
        self.DATA_DIR = self.BASE_DIR / "data"
        self.MODELS_DIR = self.BASE_DIR / "models"
        self.EMBEDDINGS_DIR = self.BASE_DIR / "data" / "embeddings"
        self.FRAMES_DIR = self.BASE_DIR / "data" / "frames"
        self.UPLOADS_DIR = self.BASE_DIR / "data" / "uploads"
        self.UNKNOWN_FACES_DIR = self.BASE_DIR / "data" / "unknown_faces"
        self.LOGS_PATH = self.BASE_DIR / "logs"
        
        # Configurações de API - URLs para comunicação
        self.API_HOST = os.environ.get('API_HOST', "127.0.0.1")
        self.API_PORT = int(os.environ.get('API_PORT', 17234))
        self.API_BASE_URL = os.environ.get('API_BASE_URL', "http://127.0.0.1:17234")
        self.API_URL = os.environ.get('API_URL', "http://127.0.0.1:17234")
        self.RECOGNITION_WORKER_URL = os.environ.get('RECOGNITION_WORKER_URL', "http://127.0.0.1:17235")
        
        # Configurações de câmera
        self.CAMERA_FPS_LIMIT = int(os.environ.get('CAMERA_FPS_LIMIT', 10))
        self.CAMERA_RECONNECT_INTERVAL = int(os.environ.get('CAMERA_RECONNECT_INTERVAL', 30))
        self.CAMERA_FRAME_WIDTH = int(os.environ.get('CAMERA_FRAME_WIDTH', 640))
        self.CAMERA_FRAME_HEIGHT = int(os.environ.get('CAMERA_FRAME_HEIGHT', 480))
        self.DEFAULT_FPS_LIMIT = int(os.environ.get('DEFAULT_FPS_LIMIT', 5))
        self.CAMERA_TIMEOUT = int(os.environ.get('CAMERA_TIMEOUT', 60))
        self.MAX_CAMERAS = int(os.environ.get('MAX_CAMERAS', 10))
        
        # Configurações do GStreamer
        self.GSTREAMER_ENABLED = os.environ.get('GSTREAMER_ENABLED', 'true').lower() == 'true'
        self.GSTREAMER_DEBUG_LEVEL = int(os.environ.get('GSTREAMER_DEBUG_LEVEL', 0))
        
        # GPU - Camera Worker não precisa de GPU diretamente, mas pode passar informação
        self.USE_GPU = os.environ.get('USE_GPU', 'true').lower() in ('true', '1', 'yes')
        self.GPU_DEVICE_ID = int(os.environ.get('GPU_DEVICE_ID', 0))
        self.CUDA_VISIBLE_DEVICES = os.environ.get('CUDA_VISIBLE_DEVICES', "0")
        
        # Performance
        self.MAX_WORKERS = int(os.environ.get('MAX_WORKERS', 4))
        self.BATCH_SIZE = int(os.environ.get('BATCH_SIZE', 32))
        self.USE_PERFORMANCE_WORKER = os.environ.get('USE_PERFORMANCE_WORKER', 'true').lower() == 'true'
        
        # Logging
        self.LOG_LEVEL = os.environ.get('LOG_LEVEL', "INFO")
        self.LOG_FORMAT = "{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{function}:{line} | {message}"
        
        # Configurações adicionais compatíveis
        self.ENVIRONMENT = os.environ.get('ENVIRONMENT', 'production')
        self.FACE_RECOGNITION_THRESHOLD = float(os.environ.get('FACE_RECOGNITION_THRESHOLD', 0.6))
        self.CONFIDENCE_THRESHOLD = float(os.environ.get('CONFIDENCE_THRESHOLD', 0.6))
        
        # Paths compatibility
        self.MODELS_PATH = str(self.MODELS_DIR)
        self.EMBEDDINGS_PATH = str(self.EMBEDDINGS_DIR)
        self.IMAGES_PATH = str(self.DATA_DIR / "images")
        # Fix: self.LOGS_PATH já é Path, não string
        self.LOGS_PATH_STR = str(self.LOGS_PATH)
        
        # Criar diretórios necessários
        self._create_directories()
    
    def _create_directories(self):
        """Criar diretórios necessários se não existirem"""
        directories = [
            self.DATA_DIR,
            self.MODELS_DIR,
            self.EMBEDDINGS_DIR,
            self.FRAMES_DIR,
            self.UPLOADS_DIR,
            self.UNKNOWN_FACES_DIR,
            self.LOGS_PATH
        ]
        
        for dir_path in directories:
            try:
                # Garantir que é um objeto Path
                if isinstance(dir_path, str):
                    dir_path = Path(dir_path)
                dir_path.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                print(f"[SimpleConfig] Aviso: Não foi possível criar diretório {dir_path}: {e}")
    
    def get_absolute_path(self, path: str) -> Path:
        """Obter caminho absoluto para um diretório ou arquivo"""
        if os.path.isabs(path):
            return Path(path)
        
        # Obter diretório raiz do projeto
        root_dir = Path(__file__).parent.parent.parent
        return root_dir / path


# Instância global das configurações simplificadas
settings = SimpleSettings()

# Configurações específicas por ambiente
class DevelopmentSettings(SimpleSettings):
    """Configurações para desenvolvimento"""
    def __init__(self):
        super().__init__()
        self.DEBUG = True
        self.LOG_LEVEL = "DEBUG"


class ProductionSettings(SimpleSettings):
    """Configurações para produção"""
    def __init__(self):
        super().__init__()
        self.DEBUG = False
        self.LOG_LEVEL = "WARNING"


def get_settings() -> SimpleSettings:
    """Factory para obter configurações baseadas no ambiente"""
    env = os.getenv("ENVIRONMENT", "development").lower()
    
    if env == "development":
        return DevelopmentSettings()
    elif env == "production":
        return ProductionSettings()
    else:
        return SimpleSettings()


# Configurações de câmera para MSYS2/GStreamer
CAMERA_SETTINGS = {
    "default": {
        "fps": 30,
        "resolution": (1280, 720),
        "format": "MJPG"
    },
    "detection": {
        "min_face_size": 40,
        "max_face_size": 640,
        "detection_threshold": 0.6
    }
}

# Configurações específicas do GStreamer
GSTREAMER_SETTINGS = {
    "plugins_required": [
        "rtspsrc",      # Para câmeras RTSP
        "v4l2src",      # Para câmeras USB no Linux
        "videoconvert", # Conversão de formato
        "appsink",      # Sink para aplicação
        "videoscale",   # Redimensionamento
        "queue",        # Buffer
    ],
    "plugins_optional": [
        "nvh264dec",    # Decodificação H264 por hardware
        "nvh264enc",    # Codificação H264 por hardware
        "vp8enc",       # Codificação VP8
        "rtpvp8pay",    # RTP payload para VP8
    ],
    "debug_level": settings.GSTREAMER_DEBUG_LEVEL
}

print(f"[SimpleConfig] Camera Worker configurado para ambiente MSYS2")
print(f"[SimpleConfig] API URL: {settings.API_BASE_URL}")
print(f"[SimpleConfig] Recognition Worker URL: {settings.RECOGNITION_WORKER_URL}")
print(f"[SimpleConfig] GStreamer habilitado: {settings.GSTREAMER_ENABLED}")
print(f"[SimpleConfig] Performance Worker: {settings.USE_PERFORMANCE_WORKER}")