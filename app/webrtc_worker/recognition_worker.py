"""
Recognition Worker para WebRTC com InsightFace AntelopeV2 + FAISS + ONNXRuntime GPU
Processamento de reconhecimento facial em tempo real com multiprocessing
"""

import os
import sys
import time
import json
import numpy as np
import cv2
import base64
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from multiprocessing import Queue, Process, Event
from loguru import logger
import threading
import asyncio
import socketio

# Configurar ambiente antes das importações CUDA
os.environ.pop('CUDA_VISIBLE_DEVICES', None)
os.environ.pop('DISABLE_GPU', None)

# InsightFace e FAISS imports
try:
    import insightface
    from insightface.app import FaceAnalysis
    INSIGHTFACE_AVAILABLE = True
    logger.info("InsightFace disponível")
except ImportError as e:
    logger.error(f"InsightFace não disponível: {e}")
    INSIGHTFACE_AVAILABLE = False

try:
    import faiss
    FAISS_AVAILABLE = True
    logger.info("FAISS disponível")
except ImportError as e:
    logger.error(f"FAISS não disponível: {e}")
    FAISS_AVAILABLE = False

try:
    import onnxruntime as ort
    # Verificar se GPU está disponível
    gpu_available = 'CUDAExecutionProvider' in ort.get_available_providers()
    logger.info(f"ONNXRuntime GPU disponível: {gpu_available}")
    ONNX_GPU_AVAILABLE = gpu_available
except ImportError as e:
    logger.error(f"ONNXRuntime não disponível: {e}")
    ONNX_GPU_AVAILABLE = False


class FaceRecognitionEngine:
    """Engine de reconhecimento facial com InsightFace + FAISS"""
    
    def __init__(self):
        self.app = None
        self.faiss_index = None
        self.known_faces = {}  # person_id -> {"name": str, "embedding": np.array}
        self.is_initialized = False
        self.embedding_dim = 512
        
        # Configurações de performance
        self.confidence_threshold = 0.3
        self.face_similarity_threshold = 0.6  # Distância FAISS (menor = mais similar)
        
        # Estatísticas
        self.stats = {
            'faces_processed': 0,
            'faces_recognized': 0,
            'faces_unknown': 0,
            'avg_processing_time_ms': 0.0,
            'start_time': time.time()
        }
        
        logger.info("FaceRecognitionEngine inicializado")
    
    def initialize(self) -> bool:
        """Inicializar engine de reconhecimento"""
        try:
            if not INSIGHTFACE_AVAILABLE or not FAISS_AVAILABLE:
                logger.error("Dependências não disponíveis para reconhecimento facial")
                return False
            
            logger.info("🚀 Inicializando InsightFace AntelopeV2...")
            
            # Configurar providers ONNX
            providers = ['CPUExecutionProvider']
            if ONNX_GPU_AVAILABLE:
                providers.insert(0, 'CUDAExecutionProvider')
                logger.info("Usando CUDA para InsightFace")
            else:
                logger.warning("CUDA não disponível, usando CPU")
            
            # Inicializar InsightFace
            self.app = FaceAnalysis(
                name='antelopev2',
                providers=providers,
                allowed_modules=['detection', 'recognition']
            )
            
            # Preparar modelo
            ctx_id = 0 if ONNX_GPU_AVAILABLE else -1
            self.app.prepare(ctx_id=ctx_id, det_size=(640, 640))
            
            logger.info("✅ InsightFace inicializado com sucesso")
            
            # Inicializar índice FAISS
            logger.info("🔍 Inicializando índice FAISS...")
            
            if ONNX_GPU_AVAILABLE and hasattr(faiss, 'StandardGpuResources'):
                try:
                    # Tentar usar FAISS GPU
                    res = faiss.StandardGpuResources()
                    config = faiss.GpuIndexFlatConfig()
                    config.device = 0
                    
                    # Criar índice GPU
                    cpu_index = faiss.IndexFlatL2(self.embedding_dim)
                    self.faiss_index = faiss.index_cpu_to_gpu(res, 0, cpu_index, config)
                    logger.info("✅ FAISS GPU inicializado")
                    
                except Exception as gpu_error:
                    logger.warning(f"FAISS GPU falhou, usando CPU: {gpu_error}")
                    self.faiss_index = faiss.IndexFlatL2(self.embedding_dim)
            else:
                # Usar FAISS CPU
                self.faiss_index = faiss.IndexFlatL2(self.embedding_dim)
                logger.info("✅ FAISS CPU inicializado")
            
            self.is_initialized = True
            logger.info("🎉 FaceRecognitionEngine inicializado completamente")
            return True
            
        except Exception as e:
            logger.error(f"❌ Erro ao inicializar FaceRecognitionEngine: {e}")
            return False
    
    def add_known_face(self, person_id: str, person_name: str, embedding: np.ndarray) -> bool:
        """Adicionar face conhecida ao índice"""
        try:
            if not self.is_initialized:
                logger.warning("Engine não inicializado")
                return False
            
            # Normalizar embedding
            embedding = embedding.astype(np.float32)
            if embedding.shape[0] != self.embedding_dim:
                logger.error(f"Embedding deve ter dimensão {self.embedding_dim}, recebido: {embedding.shape}")
                return False
            
            # Adicionar ao índice FAISS
            self.faiss_index.add(embedding.reshape(1, -1))
            
            # Salvar metadados
            face_id = len(self.known_faces)
            self.known_faces[face_id] = {
                'person_id': person_id,
                'name': person_name,
                'embedding': embedding
            }
            
            logger.info(f"✅ Face adicionada: {person_name} (ID: {person_id})")
            return True
            
        except Exception as e:
            logger.error(f"❌ Erro ao adicionar face conhecida: {e}")
            return False
    
    def load_known_faces_from_database(self):
        """Carregar faces conhecidas do banco de dados"""
        try:
            # Implementar carregamento do banco de dados
            # Por enquanto, simular carregamento
            logger.info("🔄 Carregando faces conhecidas do banco de dados...")
            
            # TODO: Integrar com PersonService para carregar pessoas reais
            # from app.api.services.person_service import PersonService
            # from app.database.database import get_db
            
            logger.info("✅ Faces conhecidas carregadas")
            
        except Exception as e:
            logger.error(f"❌ Erro ao carregar faces conhecidas: {e}")
    
    def recognize_faces(self, frame: np.ndarray) -> List[Dict[str, Any]]:
        """Reconhecer faces no frame"""
        start_time = time.time()
        
        try:
            if not self.is_initialized:
                return []
            
            # Detectar faces usando InsightFace
            faces = self.app.get(frame)
            
            if not faces:
                return []
            
            results = []
            
            for face in faces:
                # Extrair informações da face
                bbox = face.bbox.astype(int)
                embedding = face.embedding.astype(np.float32)
                
                # Buscar face similar no índice FAISS
                person_id = None
                person_name = "Desconhecido"
                confidence = 0.0
                is_unknown = True
                
                if self.faiss_index.ntotal > 0:
                    # Buscar no índice
                    distances, indices = self.faiss_index.search(embedding.reshape(1, -1), k=1)
                    
                    if len(distances) > 0 and len(indices) > 0:
                        distance = float(distances[0][0])
                        face_idx = int(indices[0][0])
                        
                        # Verificar se a distância está dentro do threshold
                        if distance < self.face_similarity_threshold and face_idx in self.known_faces:
                            known_face = self.known_faces[face_idx]
                            person_id = known_face['person_id']
                            person_name = known_face['name']
                            confidence = max(0.0, 1.0 - (distance / self.face_similarity_threshold))
                            is_unknown = False
                
                # Criar resultado
                result = {
                    'person_id': person_id,
                    'person_name': person_name,
                    'confidence': confidence,
                    'bbox': [int(bbox[0]), int(bbox[1]), int(bbox[2] - bbox[0]), int(bbox[3] - bbox[1])],  # x, y, w, h
                    'is_unknown': is_unknown,
                    'embedding': embedding,
                    'face_quality': float(face.det_score) if hasattr(face, 'det_score') else 1.0
                }
                
                results.append(result)
            
            # Atualizar estatísticas
            processing_time = (time.time() - start_time) * 1000
            self.stats['faces_processed'] += len(results)
            self.stats['faces_recognized'] += len([r for r in results if not r['is_unknown']])
            self.stats['faces_unknown'] += len([r for r in results if r['is_unknown']])
            
            # Calcular tempo médio de processamento
            total_time = self.stats['avg_processing_time_ms'] * (self.stats['faces_processed'] - len(results))
            self.stats['avg_processing_time_ms'] = (total_time + processing_time) / self.stats['faces_processed']
            
            return results
            
        except Exception as e:
            logger.error(f"❌ Erro ao reconhecer faces: {e}")
            return []
    
    def get_stats(self) -> Dict[str, Any]:
        """Obter estatísticas do engine"""
        uptime = time.time() - self.stats['start_time']
        
        return {
            **self.stats,
            'uptime_seconds': uptime,
            'known_faces_count': len(self.known_faces),
            'faiss_index_size': self.faiss_index.ntotal if self.faiss_index else 0,
            'is_initialized': self.is_initialized,
            'insightface_available': INSIGHTFACE_AVAILABLE,
            'faiss_available': FAISS_AVAILABLE,
            'onnx_gpu_available': ONNX_GPU_AVAILABLE
        }


class RecognitionWorkerProcess:
    """Processo worker para reconhecimento facial"""
    
    def __init__(self, frame_queue: Queue):
        self.frame_queue = frame_queue
        self.recognition_engine = FaceRecognitionEngine()
        self.is_running = False
        
        # Socket.IO client para comunicação
        self.sio = socketio.AsyncClient()
        self.webrtc_server_url = os.environ.get('WEBRTC_SERVER_URL', 'http://presence-webrtc-server:8080')
        
        logger.info("RecognitionWorkerProcess inicializado")
    
    async def initialize(self):
        """Inicializar worker"""
        try:
            # Inicializar engine de reconhecimento
            if not self.recognition_engine.initialize():
                logger.error("Falha ao inicializar engine de reconhecimento")
                return False
            
            # Carregar faces conhecidas
            self.recognition_engine.load_known_faces_from_database()
            
            # Conectar ao servidor WebRTC via Socket.IO
            await self.connect_to_webrtc_server()
            
            logger.info("✅ RecognitionWorkerProcess inicializado")
            return True
            
        except Exception as e:
            logger.error(f"❌ Erro ao inicializar worker: {e}")
            return False
    
    async def connect_to_webrtc_server(self):
        """Conectar ao servidor WebRTC"""
        try:
            await self.sio.connect(self.webrtc_server_url)
            logger.info(f"✅ Conectado ao servidor WebRTC: {self.webrtc_server_url}")
        except Exception as e:
            logger.warning(f"⚠️ Não foi possível conectar ao servidor WebRTC: {e}")
    
    async def process_frames(self):
        """Processar frames da fila"""
        self.is_running = True
        
        while self.is_running:
            try:
                # Tentar obter frame da fila (com timeout)
                try:
                    frame_data = self.frame_queue.get(timeout=1.0)
                except:
                    continue
                
                if frame_data is None:
                    break
                
                # Extrair dados do frame
                camera_id = frame_data.get('camera_id')
                timestamp = frame_data.get('timestamp')
                frame = frame_data.get('frame')
                frame_id = frame_data.get('frame_id')
                
                if frame is None:
                    continue
                
                # Processar reconhecimento facial
                start_time = time.time()
                recognition_results = self.recognition_engine.recognize_faces(frame)
                processing_time = (time.time() - start_time) * 1000
                
                # Preparar resultado
                result_data = {
                    'camera_id': camera_id,
                    'timestamp': timestamp,
                    'frame_id': frame_id,
                    'processing_time_ms': processing_time,
                    'faces_detected': len(recognition_results),
                    'recognitions': []
                }
                
                # Processar cada face detectada
                for recognition in recognition_results:
                    # Converter numpy arrays para listas para JSON
                    face_result = {
                        'person_id': recognition['person_id'],
                        'person_name': recognition['person_name'],
                        'confidence': recognition['confidence'],
                        'bbox': recognition['bbox'],
                        'is_unknown': recognition['is_unknown'],
                        'face_quality': recognition['face_quality']
                    }
                    result_data['recognitions'].append(face_result)
                
                # Enviar resultado via Socket.IO
                if self.sio.connected:
                    await self.sio.emit('recognition_result', result_data)
                
                # Log do processamento
                if recognition_results:
                    names = [r['person_name'] for r in recognition_results if not r['is_unknown']]
                    if names:
                        logger.info(f"🎯 Reconhecido: {', '.join(names)} (Câmera: {camera_id}, Tempo: {processing_time:.1f}ms)")
                    else:
                        logger.info(f"❓ {len(recognition_results)} face(s) desconhecida(s) (Câmera: {camera_id}, Tempo: {processing_time:.1f}ms)")
                
            except Exception as e:
                logger.error(f"❌ Erro ao processar frame: {e}")
                continue
        
        logger.info("Process frames loop finalizado")
    
    async def run(self):
        """Executar worker"""
        try:
            if not await self.initialize():
                logger.error("Falha na inicialização do worker")
                return
            
            logger.info("🚀 Iniciando processamento de frames...")
            await self.process_frames()
            
        except Exception as e:
            logger.error(f"❌ Erro no worker: {e}")
        finally:
            await self.cleanup()
    
    async def cleanup(self):
        """Limpeza do worker"""
        self.is_running = False
        
        if self.sio.connected:
            await self.sio.disconnect()
        
        logger.info("🧹 Cleanup do recognition worker concluído")


def start_recognition_worker(frame_queue: Queue):
    """Função para iniciar worker em processo separado"""
    import asyncio
    
    # Configurar logging para o processo
    logger.remove()
    logger.add(
        sys.stdout,
        format="<green>{time:HH:mm:ss}</green> | <cyan>RECOGNITION</cyan> | <level>{level}</level> | {message}",
        level="INFO"
    )
    
    # Configurar loop de eventos
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    # Criar e executar worker
    worker = RecognitionWorkerProcess(frame_queue)
    
    try:
        asyncio.run(worker.run())
    except KeyboardInterrupt:
        logger.info("Worker interrompido pelo usuário")
    except Exception as e:
        logger.error(f"Erro no worker: {e}")


if __name__ == "__main__":
    # Teste standalone do recognition worker
    from multiprocessing import Queue
    
    # Criar fila de teste
    test_queue = Queue()
    
    # Adicionar frame de teste (opcional)
    # test_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    # test_queue.put({
    #     'camera_id': 'test',
    #     'timestamp': time.time(),
    #     'frame': test_frame,
    #     'frame_id': 1
    # })
    
    # Executar worker
    start_recognition_worker(test_queue)