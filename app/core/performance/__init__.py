"""
Módulo de Performance - Arquitetura de alta performance para processamento de múltiplas câmeras
"""

from .camera_worker import CameraWorker
from .manager import PerformanceManager
from .recognition_engine import GPURecognitionEngine
from .pipeline_factory import GStreamerPipelineFactory

__all__ = [
    'CameraWorker',
    'PerformanceManager', 
    'GPURecognitionEngine',
    'GStreamerPipelineFactory'
]