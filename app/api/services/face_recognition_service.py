"""
Serviço de Reconhecimento Facial para a API
"""

import os
import sys
import asyncio
from typing import Dict, Any, List, Optional
from loguru import logger
import numpy as np
import cv2
import time
from datetime import datetime

# Tentar importar o RecognitionEngine
try:
    from app.core.recognition_engine import RecognitionEngine
except ImportError as e:
    logger.error(f"Erro ao importar RecognitionEngine: {e}")
    RecognitionEngine = None


class FaceRecognitionService:
    """Serviço para reconhecimento facial na API"""
    
    def __init__(self):
        """Inicializar serviço de reconhecimento facial"""
        self.recognition_engine = None
        self.is_initialized = False
        self.status = {
            'available': RecognitionEngine is not None,
            'initialized': False,
            'model_loaded': False,
            'last_process_time': None,
            'total_faces_processed': 0
        }
        
    async def initialize(self):
        """Inicializar o serviço de reconhecimento facial"""
        # TODO: Integrar com Recognition Worker via Socket.IO
        # Por enquanto, desabilitado para evitar conflitos de GPU
        logger.warning("FaceRecognitionService desabilitado - usando Recognition Worker dedicado")
        self.is_initialized = False
        self.status['initialized'] = False
        self.status['model_loaded'] = False
        return False
    
    async def process_image(self, image: np.ndarray) -> Dict[str, Any]:
        """Processar imagem para reconhecimento facial"""
        if not self.is_initialized or not self.recognition_engine:
            return {
                'success': False,
                'error': 'Serviço não inicializado'
            }
            
        try:
            start_time = time.time()
            
            # Processar imagem
            result = await self.recognition_engine.process_frame(image)
            
            # Atualizar estatísticas
            process_time = time.time() - start_time
            self.status['last_process_time'] = process_time
            self.status['total_faces_processed'] += len(result.get('faces', []))
            
            return {
                'success': True,
                'result': result,
                'process_time': process_time
            }
            
        except Exception as e:
            logger.error(f"Erro ao processar imagem: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def identify_person(self, face_embedding: List[float]) -> Dict[str, Any]:
        """Identificar pessoa a partir de um embedding facial"""
        if not self.is_initialized or not self.recognition_engine:
            return {
                'success': False,
                'error': 'Serviço não inicializado'
            }
            
        try:
            # Converter para numpy array
            embedding = np.array(face_embedding, dtype=np.float32)
            
            # Identificar pessoa
            result = await self.recognition_engine.identify_person(embedding)
            
            return {
                'success': True,
                'result': result
            }
            
        except Exception as e:
            logger.error(f"Erro ao identificar pessoa: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_status(self) -> Dict[str, Any]:
        """Obter status do serviço de reconhecimento facial"""
        return self.status
    
    async def cleanup(self):
        """Limpar recursos do serviço"""
        if self.recognition_engine:
            await self.recognition_engine.cleanup()
            self.is_initialized = False
            self.status['initialized'] = False
            self.status['model_loaded'] = False
            logger.info("Serviço de reconhecimento facial finalizado")


# Instância global do serviço
face_recognition_service = FaceRecognitionService() 