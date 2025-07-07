"""
GPU Recognition Engine - Engine otimizado para reconhecimento facial em GPU
- InsightFace com ONNX Runtime GPU
- FAISS GPU para busca vetorial ultra-rápida
- Cache inteligente de embeddings
"""

import os
import sys
import time
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
from loguru import logger
import threading
from pathlib import Path
import pickle
from datetime import datetime, timedelta

# Configurar ambiente CUDA
os.environ.pop('CUDA_VISIBLE_DEVICES', None)
os.environ.pop('DISABLE_GPU', None)


class GPURecognitionEngine:
    """
    Engine de reconhecimento facial otimizado para GPU
    - InsightFace com providers CUDA
    - FAISS GPU para busca vetorial
    - Cache de embeddings em memória
    """
    
    def __init__(self):
        self.face_analysis = None
        self.faiss_index = None
        self.person_embeddings = {}  # person_id -> embedding
        self.person_metadata = {}    # person_id -> metadata
        self.embedding_cache = {}    # cache de embeddings por face
        
        # Estado
        self.is_initialized = False
        self.gpu_available = False
        self.embedding_dimension = 512
        
        # Performance
        self.batch_size = 8
        self.max_faces_per_frame = 10
        self.confidence_threshold = 0.6
        self.similarity_threshold = 0.7
        
        # Cache settings
        self.cache_max_size = 10000
        self.cache_ttl_seconds = 300  # 5 minutos
        
        # Thread safety
        self.lock = threading.RLock()
        
        # Estatísticas
        self.stats = {
            'faces_detected': 0,
            'faces_recognized': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'gpu_inference_time_ms': 0,
            'faiss_search_time_ms': 0
        }
    
    def initialize(self) -> bool:
        """Inicializar engine com GPU"""
        try:
            logger.info("Inicializando GPU Recognition Engine...")
            
            # Verificar disponibilidade de GPU
            self.gpu_available = self._check_gpu_availability()
            
            # Inicializar InsightFace
            if not self._initialize_insightface():
                return False
            
            # Inicializar FAISS
            if not self._initialize_faiss():
                return False
            
            # Carregar embeddings conhecidos
            self._load_known_embeddings()
            
            self.is_initialized = True
            logger.info("[OK] GPU Recognition Engine inicializado com sucesso")
            return True
            
        except Exception as e:
            logger.error(f"[ERROR] Erro ao inicializar GPU Recognition Engine: {e}")
            return False
    
    def _check_gpu_availability(self) -> bool:
        """Verificar disponibilidade de GPU/CUDA"""
        try:
            # Verificar PyTorch CUDA
            try:
                import torch
                if torch.cuda.is_available():
                    device_name = torch.cuda.get_device_name(0)
                    logger.info(f"GPU disponível: {device_name}")
                    return True
                else:
                    logger.warning("CUDA não disponível via PyTorch")
            except ImportError:
                logger.debug("PyTorch não instalado")
            
            # Verificar ONNX Runtime GPU
            try:
                import onnxruntime as ort
                providers = ort.get_available_providers()
                if 'CUDAExecutionProvider' in providers:
                    logger.info("ONNX Runtime GPU disponível")
                    return True
                else:
                    logger.warning("ONNX Runtime GPU não disponível")
            except ImportError:
                logger.warning("ONNX Runtime não instalado")
            
            return False
            
        except Exception as e:
            logger.error(f"Erro ao verificar GPU: {e}")
            return False
    
    def _initialize_insightface(self) -> bool:
        """Inicializar InsightFace com GPU"""
        try:
            # Importar InsightFace (compatibilidade v0.7.3)
            try:
                from insightface import FaceAnalysis
            except ImportError:
                from insightface.app import FaceAnalysis
            
            # Configurar providers
            if self.gpu_available:
                providers = ['CUDAExecutionProvider', 'CPUExecutionProvider']
                logger.info("Usando CUDA para InsightFace")
            else:
                providers = ['CPUExecutionProvider']
                logger.warning("Usando CPU para InsightFace")
            
            # Inicializar FaceAnalysis
            self.face_analysis = FaceAnalysis(
                name='antelopev2',
                providers=providers
            )
            
            # Preparar modelo
            self.face_analysis.prepare(
                ctx_id=0 if self.gpu_available else -1,
                det_size=(640, 640)
            )
            
            logger.info("[OK] InsightFace inicializado")
            return True
            
        except Exception as e:
            logger.error(f"[ERROR] Erro ao inicializar InsightFace: {e}")
            return False
    
    def _initialize_faiss(self) -> bool:
        """Inicializar FAISS GPU"""
        try:
            import faiss
            
            # Criar índice FAISS
            if self.gpu_available:
                try:
                    # Tentar usar FAISS GPU
                    res = faiss.StandardGpuResources()
                    index_cpu = faiss.IndexFlatIP(self.embedding_dimension)  # Inner Product para cosine similarity
                    self.faiss_index = faiss.index_cpu_to_gpu(res, 0, index_cpu)
                    logger.info("[OK] FAISS GPU inicializado")
                except Exception as e:
                    logger.warning(f"FAISS GPU falhou, usando CPU: {e}")
                    self.faiss_index = faiss.IndexFlatIP(self.embedding_dimension)
            else:
                self.faiss_index = faiss.IndexFlatIP(self.embedding_dimension)
                logger.info("[OK] FAISS CPU inicializado")
            
            return True
            
        except Exception as e:
            logger.error(f"[ERROR] Erro ao inicializar FAISS: {e}")
            return False
    
    def _load_known_embeddings(self):
        """Carregar embeddings de pessoas conhecidas"""
        try:
            from app.core.config import settings
            from app.database.database import get_db_sync
            from app.database import models
            
            # Obter sessão do banco
            db = next(get_db_sync())
            
            # Carregar pessoas ativas
            people = db.query(models.Person).filter(
                models.Person.status == "active",
                models.Person.detection_enabled == True,
                models.Person.is_unknown == False
            ).all()
            
            logger.info(f"Carregando embeddings de {len(people)} pessoas...")
            
            embeddings_list = []
            person_ids = []
            
            for person in people:
                # Carregar embedding da pessoa
                embedding_path = settings.EMBEDDINGS_DIR / f"{person.id}.npy"
                
                if embedding_path.exists():
                    try:
                        embedding = np.load(embedding_path)
                        
                        # Normalizar embedding para cosine similarity
                        embedding = embedding / np.linalg.norm(embedding)
                        
                        embeddings_list.append(embedding)
                        person_ids.append(person.id)
                        
                        # Armazenar metadata
                        self.person_metadata[person.id] = {
                            'name': person.name,
                            'created_at': person.created_at,
                            'status': person.status,
                            'detection_enabled': person.detection_enabled
                        }
                        
                    except Exception as e:
                        logger.warning(f"Erro ao carregar embedding de {person.name}: {e}")
                else:
                    logger.debug(f"Embedding não encontrado para {person.name}")
            
            if embeddings_list:
                # Adicionar embeddings ao índice FAISS
                embeddings_array = np.vstack(embeddings_list).astype(np.float32)
                self.faiss_index.add(embeddings_array)
                
                # Manter mapeamento person_id -> índice
                for i, person_id in enumerate(person_ids):
                    self.person_embeddings[i] = person_id
                
                logger.info(f"[OK] {len(embeddings_list)} embeddings carregados no índice FAISS")
            else:
                logger.warning("Nenhum embedding encontrado")
            
            db.close()
            
        except Exception as e:
            logger.error(f"Erro ao carregar embeddings conhecidos: {e}")
    
    def process_frame(self, frame: np.ndarray) -> List[Dict[str, Any]]:
        """
        Processar frame e retornar reconhecimentos
        
        Args:
            frame: Frame BGR no formato NumPy
            
        Returns:
            Lista de dicionários com reconhecimentos
        """
        results = []
        
        try:
            if not self.is_initialized:
                return results
            
            start_time = time.time()
            
            # Detectar faces
            faces = self.face_analysis.get(frame)
            
            if not faces:
                return results
            
            detection_time = (time.time() - start_time) * 1000
            
            # Limitar número de faces
            faces = faces[:self.max_faces_per_frame]
            
            # Processar cada face
            for face in faces:
                try:
                    # Obter embedding
                    embedding = face.normed_embedding
                    if embedding is None:
                        continue
                    
                    # Obter bbox
                    bbox = face.bbox.astype(int)
                    confidence = face.det_score
                    
                    if confidence < self.confidence_threshold:
                        continue
                    
                    # Buscar pessoa correspondente
                    person_id, person_name, similarity = self._search_person(embedding)
                    
                    # Criar resultado
                    result = {
                        'person_id': person_id,
                        'person_name': person_name,
                        'confidence': float(confidence),
                        'similarity': float(similarity) if similarity is not None else 0.0,
                        'bbox': bbox.tolist(),
                        'embedding': embedding,
                        'is_unknown': person_id is None,
                        'detection_time_ms': detection_time
                    }
                    
                    results.append(result)
                    
                    # Atualizar estatísticas
                    self.stats['faces_detected'] += 1
                    if person_id:
                        self.stats['faces_recognized'] += 1
                
                except Exception as e:
                    logger.error(f"Erro ao processar face: {e}")
                    continue
            
            processing_time = (time.time() - start_time) * 1000
            self.stats['gpu_inference_time_ms'] = processing_time
            
        except Exception as e:
            logger.error(f"Erro ao processar frame: {e}")
        
        return results
    
    def _search_person(self, embedding: np.ndarray) -> Tuple[Optional[str], Optional[str], Optional[float]]:
        """
        Buscar pessoa correspondente ao embedding
        
        Returns:
            Tuple (person_id, person_name, similarity)
        """
        try:
            if self.faiss_index.ntotal == 0:
                return None, None, None
            
            start_time = time.time()
            
            # Normalizar embedding para cosine similarity
            embedding = embedding / np.linalg.norm(embedding)
            embedding = embedding.reshape(1, -1).astype(np.float32)
            
            # Buscar no índice FAISS
            similarities, indices = self.faiss_index.search(embedding, k=1)
            
            search_time = (time.time() - start_time) * 1000
            self.stats['faiss_search_time_ms'] = search_time
            
            if len(similarities[0]) > 0:
                similarity = similarities[0][0]
                index = indices[0][0]
                
                if similarity >= self.similarity_threshold:
                    person_id = self.person_embeddings.get(index)
                    if person_id:
                        metadata = self.person_metadata.get(person_id, {})
                        person_name = metadata.get('name', 'Desconhecido')
                        return person_id, person_name, similarity
            
            return None, None, None
            
        except Exception as e:
            logger.error(f"Erro na busca de pessoa: {e}")
            return None, None, None
    
    def add_person_embedding(self, person_id: str, person_name: str, embedding: np.ndarray):
        """Adicionar novo embedding de pessoa ao índice"""
        try:
            with self.lock:
                # Normalizar embedding
                embedding = embedding / np.linalg.norm(embedding)
                embedding = embedding.reshape(1, -1).astype(np.float32)
                
                # Adicionar ao índice FAISS
                self.faiss_index.add(embedding)
                
                # Atualizar mapeamentos
                index = self.faiss_index.ntotal - 1
                self.person_embeddings[index] = person_id
                self.person_metadata[person_id] = {
                    'name': person_name,
                    'created_at': datetime.now(),
                    'is_active': True
                }
                
                logger.info(f"Embedding adicionado para {person_name} (índice: {index})")
                
        except Exception as e:
            logger.error(f"Erro ao adicionar embedding: {e}")
    
    def remove_person_embedding(self, person_id: str):
        """Remover embedding de pessoa (rebuild do índice)"""
        try:
            with self.lock:
                # Para FAISS, precisamos rebuild o índice para remover
                self._rebuild_index_without_person(person_id)
                logger.info(f"Embedding removido para pessoa {person_id}")
                
        except Exception as e:
            logger.error(f"Erro ao remover embedding: {e}")
    
    def _rebuild_index_without_person(self, person_id_to_remove: str):
        """Rebuild do índice FAISS sem uma pessoa específica"""
        try:
            # Coletar embeddings sem a pessoa removida
            embeddings_list = []
            new_person_embeddings = {}
            new_person_metadata = {}
            
            for index, person_id in self.person_embeddings.items():
                if person_id != person_id_to_remove:
                    # Obter embedding do índice atual
                    embedding = self.faiss_index.reconstruct(index)
                    embeddings_list.append(embedding)
                    
                    new_index = len(embeddings_list) - 1
                    new_person_embeddings[new_index] = person_id
                    new_person_metadata[person_id] = self.person_metadata[person_id]
            
            # Recriar índice
            if embeddings_list:
                embeddings_array = np.vstack(embeddings_list)
                self.faiss_index.reset()
                self.faiss_index.add(embeddings_array)
            else:
                self.faiss_index.reset()
            
            # Atualizar mapeamentos
            self.person_embeddings = new_person_embeddings
            self.person_metadata = new_person_metadata
            
        except Exception as e:
            logger.error(f"Erro ao rebuild índice: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Obter estatísticas do engine"""
        return {
            'is_initialized': self.is_initialized,
            'gpu_available': self.gpu_available,
            'known_people_count': len(self.person_metadata),
            'faiss_index_size': self.faiss_index.ntotal if self.faiss_index else 0,
            'cache_size': len(self.embedding_cache),
            'stats': self.stats.copy()
        }
    
    def cleanup(self):
        """Limpeza de recursos"""
        try:
            self.is_initialized = False
            
            if self.faiss_index:
                self.faiss_index.reset()
                self.faiss_index = None
            
            self.face_analysis = None
            self.person_embeddings.clear()
            self.person_metadata.clear()
            self.embedding_cache.clear()
            
            logger.info("GPU Recognition Engine finalizado")
            
        except Exception as e:
            logger.error(f"Erro na limpeza do Recognition Engine: {e}")