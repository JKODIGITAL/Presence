"""
Configurações do sistema
"""

import os
import sys
from typing import Dict, List, Optional, Any, Union
from pathlib import Path

# Configuração compatível com pydantic v1 e v2
try:
    # Tentar v2 primeiro
    from pydantic_settings import BaseSettings
    from pydantic import Field, validator
    PYDANTIC_V2 = True
except ImportError:
    try:
        # Fallback para v1
        from pydantic import BaseSettings, Field, validator
        PYDANTIC_V2 = False
    except ImportError as e:
        # Se nem v1 nem v2 estão disponíveis
        raise ImportError(f"Pydantic não está disponível: {e}")


class Settings(BaseSettings):
    """Configurações do sistema"""
    
    # Configurações gerais
    APP_NAME: str = "Presence"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    
    # Diretórios de dados
    BASE_DIR: Path = Path(__file__).parent.parent.parent
    DATA_DIR: Path = BASE_DIR / "data"
    MODELS_DIR: Path = BASE_DIR / "models"
    EMBEDDINGS_DIR: Path = BASE_DIR / "data" / "embeddings"
    FRAMES_DIR: Path = BASE_DIR / "data" / "frames"
    UPLOADS_DIR: Path = BASE_DIR / "data" / "uploads"
    UNKNOWN_FACES_DIR: Path = BASE_DIR / "data" / "unknown_faces"
    
    # Configurações de banco de dados
    DATABASE_URL: str = "sqlite:///../data/db/presence.db"
    
    # Configurações de API
    API_HOST: str = os.environ.get('API_HOST', "127.0.0.1")  # Use 127.0.0.1 para LAN, 0.0.0.0 apenas se necessário
    API_PORT: int = int(os.environ.get('API_PORT', 17234))
    API_BASE_URL: str = os.environ.get('API_BASE_URL', "http://127.0.0.1:17234")
    API_URL: str = os.environ.get('API_URL', "http://127.0.0.1:17234")  # Compatibilidade com código legado
    RECOGNITION_WORKER_URL: str = os.environ.get('RECOGNITION_WORKER_URL', "http://127.0.0.1:17235")
    
    # Segurança
    SECRET_KEY: str = "your-secret-key-here-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # Configurações de reconhecimento facial
    FACE_RECOGNITION_MODEL: str = "models/face_recognition.onnx"
    FACE_DETECTION_MODEL: str = "models/face_detection.onnx"
    FACE_RECOGNITION_THRESHOLD: float = 0.6
    FACE_DETECTION_THRESHOLD: float = 0.5
    MAX_FACES_PER_IMAGE: int = 10
    EMBEDDING_SIZE: int = 512
    MIN_FACE_SIZE: int = 40
    MAX_FACE_SIZE: int = 640
    UNKNOWN_SIMILARITY_THRESHOLD: float = 0.5
    UNKNOWN_GRACE_PERIOD_SECONDS: int = 30  # 30 segundos de carência para evitar spam de desconhecidos
    CONFIDENCE_THRESHOLD: float = 0.6
    
    # Configurações de câmera
    CAMERA_FPS_LIMIT: int = 10
    CAMERA_RECONNECT_INTERVAL: int = 30
    CAMERA_FRAME_WIDTH: int = 640
    CAMERA_FRAME_HEIGHT: int = 480
    DEFAULT_FPS_LIMIT: int = 5
    CAMERA_TIMEOUT: int = 60  # Aumentar timeout para 60 segundos
    MAX_CAMERAS: int = 10
    
    # Configurações do GStreamer
    GSTREAMER_ENABLED: bool = True
    GSTREAMER_DEBUG_LEVEL: int = 0
    
    # Caminhos para recursos
    MODELS_PATH: str = "./models"
    EMBEDDINGS_PATH: str = "./data/embeddings"
    IMAGES_PATH: str = "./data/images"
    LOGS_PATH: str = "./logs"
    
    # GPU
    USE_GPU: bool = os.environ.get('USE_GPU', 'true').lower() in ('true', '1', 'yes')
    GPU_DEVICE_ID: int = 0
    CUDA_VISIBLE_DEVICES: str = "0"
    
    # FAISS
    FAISS_INDEX_PATH: str = "data/models/face_index.faiss"
    FAISS_DIMENSION: int = 512
    
    # Retenção de dados
    UNKNOWN_RETENTION_DAYS: int = 30
    LOG_RETENTION_DAYS: int = 90
    
    # Upload
    MAX_UPLOAD_SIZE: int = 10 * 1024 * 1024  # 10MB
    ALLOWED_IMAGE_EXTENSIONS: List[str] = [".jpg", ".jpeg", ".png", ".bmp"]
    
    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{function}:{line} | {message}"
    
    # Performance
    MAX_WORKERS: int = 4
    BATCH_SIZE: int = 32
    
    @validator("API_BASE_URL", pre=True)
    def set_api_base_url(cls, v: str, values: Dict[str, Any]) -> str:
        """Configurar URL base da API com base no ambiente"""
        if os.environ.get("API_BASE_URL"):
            return os.environ.get("API_BASE_URL")
        
        # Para uso em LAN, sempre usar 127.0.0.1
        return "http://127.0.0.1:17234"
    
    @validator("DATABASE_URL", pre=True)
    def set_database_url(cls, v: str) -> str:
        """Configurar URL do banco de dados com base no ambiente"""
        env_db_url = os.environ.get("DATABASE_URL")
        if env_db_url:
            print(f"[Config] Usando DATABASE_URL do ambiente: {env_db_url}")
            return env_db_url
        print(f"[Config] Usando DATABASE_URL padrão: {v}")
        return v
    
    @validator("USE_GPU", pre=True)
    def set_use_gpu(cls, v: Any) -> bool:
        """Configurar uso de GPU com base no ambiente"""
        if isinstance(v, str):
            return v.lower() in ("true", "1", "yes")
        return bool(v)
    
    @validator("ALLOWED_IMAGE_EXTENSIONS", pre=True)
    def validate_image_extensions(cls, v: Any) -> List[str]:
        """Validar extensões de imagem permitidas"""
        if isinstance(v, str):
            return [ext.strip() for ext in v.split(",")]
        return v
    
    def get_absolute_path(self, path: str) -> Path:
        """Obter caminho absoluto para um diretório ou arquivo"""
        if os.path.isabs(path):
            return Path(path)
        
        # Obter diretório raiz do projeto
        root_dir = Path(__file__).parent.parent.parent
        return root_dir / path
    
    class Config:
        """Configurações do Pydantic"""
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        if PYDANTIC_V2:
            extra = "allow"  # v2
        else:
            extra = "allow"  # v1 também suporta


# Instância global das configurações
settings = Settings()

# Criar diretórios necessários se não existirem
for dir_path in [
    settings.DATA_DIR,
    settings.MODELS_DIR,
    settings.EMBEDDINGS_DIR,
    settings.FRAMES_DIR,
    settings.UPLOADS_DIR,
    settings.UNKNOWN_FACES_DIR
]:
    dir_path.mkdir(parents=True, exist_ok=True)


# Configurações específicas por ambiente
class DevelopmentSettings(Settings):
    """Configurações para desenvolvimento"""
    DEBUG: bool = True
    LOG_LEVEL: str = "DEBUG"


class ProductionSettings(Settings):
    """Configurações para produção"""
    DEBUG: bool = False
    LOG_LEVEL: str = "WARNING"


def get_settings() -> Settings:
    """Factory para obter configurações baseadas no ambiente"""
    env = os.getenv("ENVIRONMENT", "development").lower()
    
    if env == "development":
        return DevelopmentSettings()
    elif env == "production":
        return ProductionSettings()
    else:
        return Settings()


# Configurações de modelos InsightFace
INSIGHTFACE_MODELS = {
    "antelopev2": {
        "name": "antelopev2",
        "providers": ["CUDAExecutionProvider", "CPUExecutionProvider"] if settings.USE_GPU else ["CPUExecutionProvider"],
        "embedding_size": 512
    },
    "detection": {
        "retinaface": {
            "name": "retinaface_r50_v1",
            "providers": ["CUDAExecutionProvider", "CPUExecutionProvider"] if settings.USE_GPU else ["CPUExecutionProvider"]
        }
    },
    "recognition": {
        "antelopev2": {
            "name": "antelopev2", 
            "providers": ["CUDAExecutionProvider", "CPUExecutionProvider"] if settings.USE_GPU else ["CPUExecutionProvider"]
        }
    }
}

# Configurações de câmera
CAMERA_SETTINGS = {
    "default": {
        "fps": 30,
        "resolution": (1280, 720),
        "format": "MJPG"
    },
    "detection": {
        "min_face_size": 40,
        "max_face_size": settings.MAX_FACE_SIZE,
        "detection_threshold": 0.6
    }
}

# Configurações do banco de dados
DATABASE_SETTINGS = {
    "sqlite": {
        "echo": settings.DEBUG,
        "pool_pre_ping": True,
    }
}