import numpy as np
import cv2
import insightface
from insightface.app import FaceAnalysis
import faiss
from typing import List, Tuple, Optional
import pickle
import os
from loguru import logger
from app.core.config import settings

class FaceRecognitionService:
    def __init__(self):
        self.app = None
        self.index = None
        self.id_map = {}
        self.embedding_size = settings.FAISS_DIMENSION
        
    async def initialize(self):
        """Inicializa o modelo de reconhecimento facial"""
        # TODO: Integrar com Recognition Worker via Socket.IO
        # Por enquanto, desabilitado para evitar conflitos de GPU com Recognition Worker
        logger.warning("FaceRecognitionService desabilitado - usando Recognition Worker dedicado")
        return False
        
        try:
            # Código desabilitado temporariamente
            if False:
                logger.info("Inicializando InsightFace...")
                self.app = FaceAnalysis(
                    name='antelopev2',
                    providers=['CUDAExecutionProvider', 'CPUExecutionProvider']
                )
                self.app.prepare(ctx_id=0, det_size=(640, 640))
            
            # Inicializar ou carregar índice FAISS
            self._initialize_faiss_index()
            
            logger.info("InsightFace inicializado com sucesso")
        except Exception as e:
            logger.error(f"Erro ao inicializar InsightFace: {e}")
            raise
    
    def _initialize_faiss_index(self):
        """Inicializa ou carrega o índice FAISS"""
        index_path = settings.FAISS_INDEX_PATH
        id_map_path = str(settings.DATA_DIR / "embeddings" / "id_map.pkl")
        
        if os.path.exists(index_path) and os.path.exists(id_map_path):
            logger.info("Carregando índice FAISS existente...")
            self.index = faiss.read_index(index_path)
            with open(id_map_path, 'rb') as f:
                self.id_map = pickle.load(f)
        else:
            logger.info("Criando novo índice FAISS...")
            self.index = faiss.IndexFlatL2(self.embedding_size)
            self.id_map = {}
    
    def extract_embedding(self, image: np.ndarray) -> Optional[np.ndarray]:
        """Extrai embedding facial de uma imagem"""
        try:
            faces = self.app.get(image)
            if len(faces) == 0:
                return None
            
            # Pegar a face com maior área (mais próxima)
            largest_face = max(faces, key=lambda x: (x.bbox[2] - x.bbox[0]) * (x.bbox[3] - x.bbox[1]))
            return largest_face.embedding
            
        except Exception as e:
            logger.error(f"Erro ao extrair embedding: {e}")
            return None
    
    def add_face(self, person_id: int, embedding: np.ndarray):
        """Adiciona uma face ao índice"""
        try:
            # Normalizar embedding
            embedding = embedding / np.linalg.norm(embedding)
            
            # Adicionar ao índice FAISS
            idx = self.index.ntotal
            self.index.add(embedding.reshape(1, -1))
            self.id_map[idx] = person_id
            
            # Salvar índice atualizado
            self._save_index()
            
            logger.info(f"Face adicionada para pessoa ID: {person_id}")
            
        except Exception as e:
            logger.error(f"Erro ao adicionar face: {e}")
            raise
    
    def search_face(self, embedding: np.ndarray, k: int = 1) -> Tuple[Optional[int], float]:
        """Busca uma face no índice"""
        try:
            if self.index.ntotal == 0:
                return None, 0.0
            
            # Normalizar embedding
            embedding = embedding / np.linalg.norm(embedding)
            
            # Buscar no índice
            distances, indices = self.index.search(embedding.reshape(1, -1), k)
            
            if len(indices[0]) > 0:
                distance = distances[0][0]
                similarity = 1 - (distance / 2)  # Converter distância L2 em similaridade
                
                if similarity >= settings.CONFIDENCE_THRESHOLD:
                    idx = indices[0][0]
                    person_id = self.id_map.get(idx)
                    return person_id, similarity
            
            return None, 0.0
            
        except Exception as e:
            logger.error(f"Erro ao buscar face: {e}")
            return None, 0.0
    
    def _save_index(self):
        """Salva o índice FAISS e mapeamento de IDs"""
        try:
            os.makedirs(settings.DATA_DIR / "embeddings", exist_ok=True)
            
            index_path = settings.FAISS_INDEX_PATH
            id_map_path = str(settings.DATA_DIR / "embeddings" / "id_map.pkl")
            
            faiss.write_index(self.index, index_path)
            with open(id_map_path, 'wb') as f:
                pickle.dump(self.id_map, f)
                
        except Exception as e:
            logger.error(f"Erro ao salvar índice: {e}")
            raise

# Instância global do serviço
face_service = FaceRecognitionService()
