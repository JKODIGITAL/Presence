"""
Recognition Engine - Core face recognition functionality
"""

import numpy as np
import cv2
from typing import List, Dict, Optional, Tuple
import asyncio
from loguru import logger
import uuid
from datetime import datetime, timedelta
from collections import defaultdict
import threading
import os

from app.core.config import settings
from app.core.utils import safe_float_conversion, safe_int_conversion

# Lock global para evitar inicializações CUDA simultâneas
_cuda_init_lock = threading.Lock()

# Importar FAISS com tratamento de erro
try:
    import faiss
    FAISS_AVAILABLE = True
    logger.info("FAISS importado com sucesso")
except ImportError:
    FAISS_AVAILABLE = False
    logger.warning("FAISS não disponível - usando busca linear")


class RecognitionEngine:
    """Engine principal de reconhecimento facial - Singleton Pattern"""
    
    _instance = None
    _initialized = False
    _initialization_lock = asyncio.Lock()
    
    def __new__(cls):
        # Se estamos no Recognition Worker, sempre recriar para garantir GPU
        if os.environ.get('RECOGNITION_WORKER', '').lower() == 'true':
            cls._instance = None  # Forçar recriação
            
        if cls._instance is None:
            cls._instance = super(RecognitionEngine, cls).__new__(cls)
            cls._instance.face_analysis = None
            cls._instance.face_embeddings = {}  # Cache de embeddings conhecidos
            cls._instance.is_initialized = False
            # Forçar GPU no Recognition Worker
            if os.environ.get('RECOGNITION_WORKER', '').lower() == 'true':
                cls._instance.use_gpu = True
                print(f"[CONFIG] Recognition Engine: Forçando GPU para Recognition Worker")
            else:
                cls._instance.use_gpu = settings.USE_GPU
                print(f"[CONFIG] Recognition Engine: Usando settings.USE_GPU = {settings.USE_GPU}")
            cls._instance._initialization_error = None
            
            # FAISS GPU Index para high-performance face search
            cls._instance.faiss_index = None
            cls._instance.faiss_gpu_resource = None
            cls._instance.person_ids = []  # Lista ordenada de person_ids para mapear indices FAISS
            cls._instance.use_faiss = FAISS_AVAILABLE and settings.USE_GPU
            
            # Sistema de tempo de carência para desconhecidos
            cls._instance.unknown_grace_buffer = {}  # {embedding_hash: {'first_seen': datetime, 'embedding': np.array, 'count': int}}
            cls._instance.unknown_grace_period = settings.UNKNOWN_GRACE_PERIOD_SECONDS
            cls._instance.unknown_similarity_threshold = settings.UNKNOWN_SIMILARITY_THRESHOLD
            
            # Limpeza periódica do buffer
            asyncio.create_task(cls._instance._cleanup_grace_buffer())
        return cls._instance
    
    def __init__(self):
        # Singleton já inicializado no __new__
        pass
    
    async def initialize(self):
        """Inicializar o engine de reconhecimento (thread-safe)"""
        if self._initialized:
            return
        
        async with self._initialization_lock:
            if self._initialized:  # Double-check locking
                return
            
            try:
                logger.info("Inicializando Recognition Engine...")
                
                # Verificar se está rodando no processo de reconhecimento separado
                if os.environ.get('RECOGNITION_WORKER', '').lower() == 'true':
                    # Processo separado - usar GPU
                    with _cuda_init_lock:
                        # Manter CUDA_VISIBLE_DEVICES configurado, apenas remover DISABLE_GPU
                        os.environ.pop('DISABLE_GPU', None)
                        
                        # Garantir que CUDA_VISIBLE_DEVICES esteja configurado
                        if 'CUDA_VISIBLE_DEVICES' not in os.environ:
                            os.environ['CUDA_VISIBLE_DEVICES'] = '0'
                        
                        # No Recognition Worker, sempre tentar usar GPU primeiro
                        from app.core.gpu_utils import get_optimal_providers
                        providers, provider_info = get_optimal_providers()
                        
                        logger.info(f"[CONFIG] Recognition Worker GPU Config:")
                        logger.info(f"   - self.use_gpu: {self.use_gpu}")
                        logger.info(f"   - settings.USE_GPU: {settings.USE_GPU}")
                        logger.info(f"   - CUDA_VISIBLE_DEVICES: {os.environ.get('CUDA_VISIBLE_DEVICES', 'NOT_SET')}")
                        logger.info(f"[ROCKET] Recognition Worker - {provider_info}")
                        logger.info(f"[ROCKET] Recognition Worker - usando providers: {providers}")
                else:
                    # Processo principal (camera worker) - forçar CPU apenas
                    with _cuda_init_lock:
                        os.environ['CUDA_VISIBLE_DEVICES'] = ''
                        os.environ['DISABLE_GPU'] = '1'
                        
                        providers = ['CPUExecutionProvider']
                        logger.info("📷 Camera Worker - forçando CPU para evitar conflitos")
                
                logger.info("[PROCESSING] Recognition Engine inicializando com processo isolado")
                
                # Verificar e forçar download correto do modelo antelopev2
                await self._ensure_antelopev2_model()
                
                # Importar InsightFace (compatibilidade v0.7.3)
                try:
                    from insightface import FaceAnalysis
                except ImportError:
                    # Para InsightFace 0.7.3 e anteriores
                    from insightface.app import FaceAnalysis
                
                # Inicializar FaceAnalysis com antelopev2
                logger.info("Inicializando InsightFace com modelo antelopev2...")
                self.face_analysis = FaceAnalysis(name='antelopev2', providers=providers)
                
                # Preparar modelo
                logger.info("Preparando modelo...")
                self.face_analysis.prepare(ctx_id=0, det_size=(640, 640))
                
                logger.info(f"[OK] InsightFace inicializado com antelopev2 e providers: {providers}")
                
                # Inicializar FAISS GPU se disponível
                if self.use_faiss:
                    await self._initialize_faiss_gpu()
                
                # Carregar embeddings conhecidos
                await self.load_known_faces()
                
                self.is_initialized = True
                self._initialized = True
                self._initialization_error = None
                logger.info("[OK] Recognition Engine inicializado com sucesso")
                
            except Exception as e:
                self._initialization_error = str(e)
                logger.error(f"[ERROR] Erro ao inicializar Recognition Engine: {e}")
                # Não fazer raise para evitar falha completa da aplicação
                # A aplicação pode continuar funcionando com funcionalidades limitadas
    
    async def ensure_initialized(self):
        """Garantir que o engine está inicializado"""
        if not self._initialized:
            await self.initialize()
        
        if not self.is_initialized:
            raise Exception(f"Recognition Engine não pôde ser inicializado: {self._initialization_error}")
    
    async def _ensure_antelopev2_model(self):
        """Garantir que o modelo antelopev2 está baixado e extraído corretamente"""
        import os
        import shutil
        import zipfile
        import urllib.request
        import tempfile
        
        model_path = os.path.expanduser('~/.insightface/models/antelopev2')
        expected_files = ['1k3d68.onnx', '2d106det.onnx', 'genderage.onnx', 'glintr100.onnx', 'scrfd_10g_bnkps.onnx']
        
        # Verificar se o modelo está completo
        if os.path.exists(model_path):
            missing_files = [f for f in expected_files if not os.path.exists(os.path.join(model_path, f))]
            if not missing_files:
                logger.info("Modelo antelopev2 já existe e está completo")
                return
            else:
                logger.warning(f"Modelo antelopev2 incompleto. Arquivos faltando: {missing_files}")
                shutil.rmtree(model_path, ignore_errors=True)
        
        # Criar diretório de modelos se não existir
        models_dir = os.path.expanduser('~/.insightface/models')
        os.makedirs(models_dir, exist_ok=True)
        
        # URL oficial do modelo antelopev2
        url = 'https://github.com/deepinsight/insightface/releases/download/v0.7/antelopev2.zip'
        
        try:
            logger.info(f"Baixando antelopev2 de: {url}")
            
            # Baixar o arquivo zip
            with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp_file:
                urllib.request.urlretrieve(url, tmp_file.name)
                zip_path = tmp_file.name
            
            logger.info(f"Download concluído: {zip_path}")
            
        except Exception as e:
            raise Exception(f"Falha ao baixar modelo antelopev2: {e}")
        
        try:
            # Extrair o arquivo zip
            logger.info(f"Extraindo modelo antelopev2...")
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(models_dir)
            
            # Verificar se a extração foi bem-sucedida
            if os.path.exists(model_path):
                missing_files = [f for f in expected_files if not os.path.exists(os.path.join(model_path, f))]
                if missing_files:
                    raise Exception(f"Extração incompleta. Arquivos faltando: {missing_files}")
                
                logger.info("[OK] Modelo antelopev2 baixado e extraído com sucesso")
            else:
                raise Exception("Diretório do modelo não foi criado após extração")
                
        finally:
            # Limpar arquivo temporário
            if zip_path and os.path.exists(zip_path):
                os.unlink(zip_path)
    
    async def _initialize_faiss_gpu(self):
        """Inicializar FAISS GPU para busca vetorial ultra-rápida"""
        try:
            if not FAISS_AVAILABLE:
                logger.warning("FAISS não disponível - pulando inicialização GPU")
                return
            
            logger.info("[ROCKET] Inicializando FAISS GPU para high-performance face search...")
            
            # Verificar se GPU está disponível para FAISS
            if faiss.get_num_gpus() > 0:
                # Criar resource GPU
                self.faiss_gpu_resource = faiss.StandardGpuResources()
                
                # Criar index FAISS para embeddings de 512 dimensões (InsightFace)
                cpu_index = faiss.IndexFlatL2(512)  # L2 distance para similaridade
                
                # Mover index para GPU
                self.faiss_index = faiss.index_cpu_to_gpu(
                    self.faiss_gpu_resource, 
                    0,  # GPU device 0
                    cpu_index
                )
                
                logger.info("[OK] FAISS GPU inicializado com sucesso")
            else:
                # Fallback para CPU se GPU não disponível
                self.faiss_index = faiss.IndexFlatL2(512)
                logger.warning("[PROCESSING] GPU não disponível para FAISS, usando CPU")
                
            self.person_ids = []  # Resetar lista de IDs
            
        except Exception as e:
            logger.error(f"[ERROR] Erro ao inicializar FAISS GPU: {e}")
            self.use_faiss = False
            self.faiss_index = None
    
    def _rebuild_faiss_index(self):
        """Reconstruir index FAISS com embeddings atuais"""
        try:
            if not self.use_faiss or not self.faiss_index:
                return
            
            # Limpar index atual
            self.faiss_index.reset()
            self.person_ids = []
            
            if not self.face_embeddings:
                logger.debug("Nenhum embedding para adicionar ao FAISS")
                return
            
            # Preparar embeddings para FAISS
            embeddings_array = []
            person_ids_list = []
            
            for person_id, embedding in self.face_embeddings.items():
                embeddings_array.append(embedding)
                person_ids_list.append(person_id)
            
            if embeddings_array:
                # Converter para numpy array
                embeddings_matrix = np.array(embeddings_array, dtype=np.float32)
                
                # Adicionar ao index FAISS
                self.faiss_index.add(embeddings_matrix)
                self.person_ids = person_ids_list
                
                logger.info(f"[TARGET] FAISS index reconstruído com {len(embeddings_array)} faces")
            
        except Exception as e:
            logger.error(f"[ERROR] Erro ao reconstruir FAISS index: {e}")
    
    def _faiss_search(self, query_embedding: np.ndarray, k: int = 1) -> Tuple[List[float], List[str]]:
        """Buscar faces similares usando FAISS GPU"""
        try:
            if not self.use_faiss or not self.faiss_index or len(self.person_ids) == 0:
                return [], []
            
            # Preparar query
            query = query_embedding.reshape(1, -1).astype(np.float32)
            
            # Buscar no FAISS
            distances, indices = self.faiss_index.search(query, min(k, len(self.person_ids)))
            
            # Converter resultados
            result_distances = []
            result_person_ids = []
            
            for i, (distance, index) in enumerate(zip(distances[0], indices[0])):
                if index >= 0 and index < len(self.person_ids):
                    result_distances.append(float(distance))
                    result_person_ids.append(self.person_ids[index])
            
            return result_distances, result_person_ids
            
        except Exception as e:
            logger.error(f"[ERROR] Erro na busca FAISS: {e}")
            return [], []
    
    async def load_known_faces(self):
        """Carregar faces conhecidas do banco de dados"""
        try:
            # Modo compatibilidade - pular carregamento apenas se não for recognition worker
            if self.face_analysis is None and os.environ.get('RECOGNITION_WORKER', '').lower() != 'true':
                logger.debug("Recognition engine em modo compatibilidade - pulando carregamento de faces")
                self.face_embeddings = {}
                return
                
            from app.database.database import get_db_sync
            from app.database import models
            
            # Carregar faces conhecidas do banco de dados
            session = next(get_db_sync())
            people = session.query(models.Person).filter(
                models.Person.face_encoding.isnot(None),
                models.Person.status == "active",
                models.Person.detection_enabled == True,  # Apenas pessoas com detecção habilitada
                models.Person.is_unknown == False  # Apenas pessoas conhecidas
            ).all()
            
            self.face_embeddings = {}
            loaded_count = 0
            
            for person in people:
                face_encoding = getattr(person, 'face_encoding', None)
                if face_encoding:
                    try:
                        # Converter bytes de volta para numpy array
                        embedding = np.frombuffer(face_encoding, dtype=np.float32)
                        
                        # Verificar se o embedding tem o tamanho correto
                        if embedding.shape[0] == 512:  # InsightFace antelopev2 usa 512 dimensões
                            self.face_embeddings[person.id] = embedding
                            loaded_count += 1
                            logger.debug(f"Carregado embedding para {person.name} (ID: {person.id})")
                        else:
                            logger.warning(f"Embedding inválido para {person.name}: dimensão {embedding.shape[0]} (esperado 512)")
                    except Exception as e:
                        logger.error(f"Erro ao carregar embedding para {person.name}: {e}")
            
            logger.info(f"[OK] Carregados {loaded_count} embeddings de faces conhecidas")
            
            # Log das pessoas carregadas
            for person_id in self.face_embeddings.keys():
                person = session.query(models.Person).filter(models.Person.id == person_id).first()
                if person:
                    logger.info(f"  - {person.name} (ID: {person_id})")
            
            # Fechar session
            session.close()
            
            # Reconstruir FAISS index com novos embeddings
            if self.use_faiss:
                self._rebuild_faiss_index()
            
        except Exception as e:
            logger.error(f"[ERROR] Erro ao carregar faces conhecidas: {e}")
            self.face_embeddings = {}
            # Tentar fechar session em caso de erro
            try:
                if 'session' in locals():
                    session.close()
            except:
                pass
    
    def reload_known_faces(self):
        """Recarregar faces conhecidas (método síncrono para uso em callbacks)"""
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Se o loop estiver rodando, criar task
                asyncio.create_task(self.load_known_faces())
            else:
                # Se não estiver rodando, executar diretamente
                loop.run_until_complete(self.load_known_faces())
        except Exception as e:
            logger.error(f"Erro ao recarregar faces conhecidas: {e}")
    
    def detect_faces(self, image: np.ndarray) -> List[Dict]:
        """Detectar faces em uma imagem"""
        try:
            if self.face_analysis is None and os.environ.get('RECOGNITION_WORKER', '').lower() != 'true':
                # Modo compatibilidade - retornar lista vazia
                logger.debug(f"Recognition engine em modo compatibilidade - sem detecção")
                return []
            
            if self.face_analysis is None:
                logger.error(f"face_analysis é None no Recognition Worker")
                return []
            
            # Usar InsightFace para detecção real
            faces = self.face_analysis.get(image)
            logger.debug(f"InsightFace detectou {len(faces)} faces")
            
            results = []
            for face in faces:
                # Calcular tamanho da face (largura x altura)
                bbox = face.bbox.astype(int)
                face_width = bbox[2] - bbox[0]
                face_height = bbox[3] - bbox[1]
                face_size = min(face_width, face_height)  # Usar o menor lado
                
                # Filtrar por tamanho mínimo
                if face_size < settings.MIN_FACE_SIZE:
                    logger.debug(f"Face ignorada por ser muito pequena: {face_size}px")
                    continue
                
                results.append({
                    'bbox': [safe_int_conversion(x) for x in bbox.tolist()],  # Convert to native Python ints
                    'landmarks': [[safe_int_conversion(x) for x in point] for point in face.kps.astype(int).tolist()],
                    'embedding': face.embedding,
                    'confidence': safe_float_conversion(face.det_score),
                    'face_size': safe_int_conversion(face_size)  # Convert numpy int to Python int
                })
                logger.debug(f"Face aceita: bbox={bbox.tolist()}, size={face_size}, conf={face.det_score:.3f}")
            
            if len(results) > 0:
                logger.info(f"👥 Detectadas {len(results)} faces válidas de {len(faces)} encontradas")
            return results
            
        except Exception as e:
            logger.error(f"[ERROR] [DETECT] Erro na detecção de faces: {e}")
            import traceback
            logger.error(f"[ERROR] [DETECT] Traceback: {traceback.format_exc()}")
            return []
    
    def _mock_face_detection(self, image: np.ndarray) -> List[Dict]:
        """Implementação mock para desenvolvimento"""
        # Simular detecção de face (para desenvolvimento sem GPU)
        height, width = image.shape[:2]
        
        # Simular uma face detectada no centro da imagem
        mock_face = {
            'bbox': [width//4, height//4, width//2, height//2],
            'landmarks': [[width//2, height//3], [width//2, height//2]],  # Olhos simplificados
            'embedding': np.random.rand(512).astype(np.float32),  # Embedding aleatório
            'confidence': 0.9
        }
        
        return [mock_face]
    
    def recognize_faces(self, faces: List[Dict]) -> List[Dict]:
        """Reconhecer faces detectadas"""
        if not faces:
            return []
            
        logger.debug(f"Reconhecendo {len(faces)} faces")
        results = []
        
        for i, face in enumerate(faces):
            embedding = face['embedding']
            person_id, confidence = self._find_best_match(embedding)
            
            # Get person name for WebRTC overlay
            person_name = self._get_person_name(person_id)
            
            # Log apenas reconhecimentos positivos
            if person_id and not person_id.startswith('unknown_'):
                logger.info(f"👤 Reconhecido: {person_name} (conf: {confidence:.2f})")
            
            result_item = {
                'bbox': [safe_int_conversion(x) for x in face['bbox']] if isinstance(face['bbox'], (list, tuple)) else face['bbox'],
                'landmarks': face['landmarks'],
                'person_id': person_id,
                'person_name': person_name,  # Add person_name for WebRTC overlay
                'confidence': safe_float_conversion(confidence),
                'is_unknown': person_id.startswith('unknown_') if person_id else True,
                'face_size': safe_int_conversion(face.get('face_size', 0)),
                'detection_confidence': safe_float_conversion(face.get('confidence', 0.0))
            }
            
            results.append(result_item)
        
        return results
    
    def _find_best_match(self, embedding: np.ndarray) -> Tuple[Optional[str], float]:
        """Encontrar a melhor correspondência para um embedding usando FAISS GPU"""
        if not self.face_embeddings:
            logger.debug("Nenhuma face conhecida carregada, usando sistema de carência")
            return self._handle_unknown_with_grace_period(embedding)
        
        # Usar FAISS GPU se disponível
        if self.use_faiss and self.faiss_index and len(self.person_ids) > 0:
            return self._find_best_match_faiss(embedding)
        else:
            return self._find_best_match_linear(embedding)
    
    def _find_best_match_faiss(self, embedding: np.ndarray) -> Tuple[Optional[str], float]:
        """Busca ultra-rápida usando FAISS GPU"""
        try:
            # Buscar usando FAISS
            distances, person_ids = self._faiss_search(embedding, k=1)
            
            if not distances or not person_ids:
                logger.debug("FAISS não retornou resultados")
                return self._handle_unknown_with_grace_period(embedding)
            
            # FAISS retorna distância L2, converter para similaridade cosine
            distance = distances[0]
            person_id = person_ids[0]
            
            # Converter L2 distance para cosine similarity aproximada
            # Para embeddings normalizados: cosine_sim ≈ 1 - (l2_dist²/4)
            cosine_similarity = 1.0 - (distance / 4.0)
            
            logger.debug(f"[TARGET] FAISS GPU: {person_id}, L2={distance:.3f}, cos_sim={cosine_similarity:.3f}")
            
            if cosine_similarity > settings.CONFIDENCE_THRESHOLD:
                return person_id, cosine_similarity
            else:
                logger.debug(f"FAISS result below threshold {settings.CONFIDENCE_THRESHOLD}")
                return self._handle_unknown_with_grace_period(embedding)
                
        except Exception as e:
            logger.error(f"[ERROR] Erro na busca FAISS, fallback para busca linear: {e}")
            return self._find_best_match_linear(embedding)
    
    def _find_best_match_linear(self, embedding: np.ndarray) -> Tuple[Optional[str], float]:
        """Busca linear tradicional (fallback)"""
        best_match_id = None
        best_confidence = 0.0
        
        for person_id, known_embedding in self.face_embeddings.items():
            # Calcular similaridade (cosine similarity)
            similarity = np.dot(embedding, known_embedding) / (
                np.linalg.norm(embedding) * np.linalg.norm(known_embedding)
            )
            
            logger.debug(f"Comparando com {person_id}: similaridade = {similarity:.3f}")
            
            if similarity > best_confidence and similarity > settings.CONFIDENCE_THRESHOLD:
                best_confidence = similarity
                best_match_id = person_id
        
        if best_match_id is None:
            logger.debug(f"Nenhuma correspondência encontrada acima do limiar {settings.CONFIDENCE_THRESHOLD}")
            return self._handle_unknown_with_grace_period(embedding)
        
        logger.debug(f"Melhor correspondência: {best_match_id} com confiança {best_confidence:.3f}")
        return best_match_id, best_confidence

    def _handle_unknown_with_grace_period(self, embedding: np.ndarray) -> Tuple[Optional[str], float]:
        """Gerenciar desconhecidos com tempo de carência"""
        current_time = datetime.now()
        embedding_hash = self._get_embedding_hash(embedding)
        
        # Verificar se já está no buffer de carência
        if embedding_hash in self.unknown_grace_buffer:
            buffer_info = self.unknown_grace_buffer[embedding_hash]
            buffer_info['count'] += 1
            
            # Verificar se já passou do tempo de carência
            if current_time - buffer_info['first_seen'] >= timedelta(seconds=self.unknown_grace_period):
                # Tempo de carência expirado, criar desconhecido
                del self.unknown_grace_buffer[embedding_hash]
                return self._create_or_find_unknown(embedding)
            else:
                # Ainda no período de carência, retornar None
                return None, 0.0
        else:
            # Primeira vez vendo esta face, adicionar ao buffer
            self.unknown_grace_buffer[embedding_hash] = {
                'first_seen': current_time,
                'embedding': embedding.copy(),
                'count': 1
            }
            return None, 0.0

    def _get_embedding_hash(self, embedding: np.ndarray) -> str:
        """Gerar hash único para o embedding (simplificado)"""
        # Usar os primeiros 10 valores para gerar um hash simples
        return str(hash(tuple(embedding[:10])))
    
    def _create_or_find_unknown(self, embedding: np.ndarray) -> Tuple[str, float]:
        """Criar ou encontrar pessoa desconhecida existente baseada no embedding"""
        try:
            from app.database.database import get_db_sync
            from app.database import models
            import os
            from PIL import Image
            import io
            
            db = next(get_db_sync())
            
            # Primeiro, verificar se já existe uma pessoa desconhecida similar
            unknown_people = db.query(models.Person).filter(
                models.Person.is_unknown == True,
                models.Person.face_encoding.isnot(None)
            ).all()
            
            # Verificar similaridade com desconhecidos existentes usando limiar específico
            for unknown_person in unknown_people:
                face_encoding = getattr(unknown_person, 'face_encoding', None)
                if face_encoding:
                    unknown_embedding = np.frombuffer(face_encoding, dtype=np.float32)
                    similarity = np.dot(embedding, unknown_embedding) / (
                        np.linalg.norm(embedding) * np.linalg.norm(unknown_embedding)
                    )
                    
                    # Usar limiar específico para desconhecidos
                    if similarity > self.unknown_similarity_threshold:
                        # Atualizar última visualização
                        setattr(unknown_person, 'last_seen', datetime.now())
                        setattr(unknown_person, 'recognition_count', unknown_person.recognition_count + 1)
                        db.commit()
                        
                        # Adicionar ao cache se não estiver
                        if unknown_person.id not in self.face_embeddings:
                            self.face_embeddings[unknown_person.id] = unknown_embedding
                        
                        return str(unknown_person.id), similarity
            
            # Criar nova pessoa desconhecida
            unknown_id = f"unknown_{uuid.uuid4().hex[:8]}"
            
            new_unknown = models.Person(
                id=unknown_id,
                name=f"Desconhecido {unknown_id[-8:]}",
                is_unknown=True,
                face_encoding=embedding.tobytes(),
                first_seen=datetime.now(),
                last_seen=datetime.now(),
                recognition_count=1,
                confidence=0.0,
                status="active"
            )
            
            db.add(new_unknown)
            db.commit()
            
            # Adicionar ao cache
            self.face_embeddings[unknown_id] = embedding
            
            logger.info(f"Nova pessoa desconhecida criada: {unknown_id}")
            return unknown_id, 0.0
            
        except Exception as e:
            logger.error(f"Erro ao criar/encontrar pessoa desconhecida: {e}")
            # Fallback para ID único sem persistência
            unknown_id = f"unknown_{uuid.uuid4().hex[:8]}"
            return unknown_id, 0.0
    
    async def process_frame(
        self, 
        image: np.ndarray, 
        camera_id: str,
        timestamp: datetime = None
    ) -> Dict:
        """Processar um frame completo"""
        if timestamp is None:
            timestamp = datetime.now()
        
        try:
            # Detectar faces
            faces = self.detect_faces(image)
            
            # Reconhecer faces  
            recognitions = self.recognize_faces(faces)
            
            # Processar detecção automática de desconhecidos
            try:
                from app.core.unknown_detector import unknown_detector
                unknown_candidates = await unknown_detector.process_frame(
                    image, recognitions, camera_id
                )
                if unknown_candidates:
                    logger.info(f"[SEARCH] {len(unknown_candidates)} novos desconhecidos detectados automaticamente")
            except Exception as e:
                logger.warning(f"Erro na detecção automática de desconhecidos: {e}")
            
            # Salvar imagens de faces desconhecidas (método legado)
            for i, recognition in enumerate(recognitions):
                if recognition.get('is_unknown', False) and recognition.get('person_id'):
                    await self._save_unknown_face_image(
                        image, 
                        faces[i], 
                        recognition['person_id'],
                        camera_id,
                        timestamp
                    )
            
            result = {
                'camera_id': camera_id,
                'timestamp': timestamp.isoformat(),
                'faces_detected': len(faces),
                'faces': recognitions,  # WebRTC overlay expects 'faces' field
                'recognitions': recognitions,  # Keep for backward compatibility
                'processed': True
            }
            
            return result
            
        except Exception as e:
            logger.error(f"Erro ao processar frame: {e}")
            return {
                'camera_id': camera_id,
                'timestamp': timestamp.isoformat(),
                'faces_detected': 0,
                'recognitions': [],
                'processed': False,
                'error': str(e)
            }
    
    async def _save_unknown_face_image(
        self, 
        image: np.ndarray, 
        face_data: Dict, 
        person_id: str,
        camera_id: str,
        timestamp: datetime
    ):
        """Salvar imagem da face de pessoa desconhecida"""
        try:
            import os
            from PIL import Image
            
            # Criar diretório para armazenar imagens de desconhecidos
            unknown_images_dir = os.path.join(settings.DATA_DIR, "unknown_faces")
            os.makedirs(unknown_images_dir, exist_ok=True)
            
            # Extrair região da face
            bbox = face_data['bbox']
            x, y, w, h = bbox
            
            # Adicionar margem à bounding box
            margin = 20
            x = max(0, x - margin)
            y = max(0, y - margin)
            x2 = min(image.shape[1], x + w + 2*margin)
            y2 = min(image.shape[0], y + h + 2*margin)
            
            # Extrair face da imagem
            face_crop = image[y:y2, x:x2]
            
            # Converter BGR para RGB
            face_crop_rgb = cv2.cvtColor(face_crop, cv2.COLOR_BGR2RGB)
            
            # Criar nome do arquivo
            timestamp_str = timestamp.strftime("%Y%m%d_%H%M%S")
            filename = f"{person_id}_{camera_id}_{timestamp_str}.jpg"
            filepath = os.path.join(unknown_images_dir, filename)
            
            # Salvar imagem
            pil_image = Image.fromarray(face_crop_rgb)
            pil_image.save(filepath, "JPEG", quality=90)
            
            # Atualizar thumbnail_path no banco de dados se for a primeira imagem
            try:
                from app.database.database import get_db_sync
                from app.database import models
                
                db = next(get_db_sync())
                person = db.query(models.Person).filter(models.Person.id == person_id).first()
                
                if person and not person.thumbnail_path:
                    person.thumbnail_path = filepath
                    db.commit()
                    
                logger.debug(f"Imagem de desconhecido salva: {filepath}")
                
            except Exception as e:
                logger.error(f"Erro ao atualizar thumbnail_path: {e}")
                
        except Exception as e:
            logger.error(f"Erro ao salvar imagem de desconhecido: {e}")
    
    def add_known_face(self, person_id: str, embedding: np.ndarray):
        """Adicionar face conhecida ao cache"""
        try:
            # Verificar se o embedding tem o tamanho correto
            if embedding.shape[0] != 512:
                logger.warning(f"Embedding inválido para {person_id}: dimensão {embedding.shape[0]} (esperado 512)")
                return False
            
            self.face_embeddings[person_id] = embedding
            logger.info(f"[OK] Face conhecida adicionada ao cache: {person_id}")
            return True
            
        except Exception as e:
            logger.error(f"[ERROR] Erro ao adicionar face conhecida {person_id}: {e}")
            return False
    
    def remove_known_face(self, person_id: str):
        """Remover face conhecida do cache"""
        try:
            if person_id in self.face_embeddings:
                del self.face_embeddings[person_id]
                logger.info(f"[OK] Face conhecida removida do cache: {person_id}")
                return True
            return False
            
        except Exception as e:
            logger.error(f"[ERROR] Erro ao remover face conhecida {person_id}: {e}")
            return False
    
    def get_known_faces_count(self) -> int:
        """Obter número de faces conhecidas no cache"""
        return len(self.face_embeddings)
    
    def get_known_faces_ids(self) -> List[str]:
        """Obter IDs das faces conhecidas no cache"""
        return list(self.face_embeddings.keys())
    
    def is_healthy(self) -> bool:
        """Verificar se o engine está saudável"""
        try:
            return (
                self.is_initialized and 
                self.face_analysis is not None and
                self._initialization_error is None
            )
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False
    
    async def cleanup(self):
        """Limpeza de recursos"""
        try:
            self.face_embeddings.clear()
            self.is_initialized = False
            logger.info("Recognition Engine finalizado")
        except Exception as e:
            logger.error(f"Erro na limpeza do Recognition Engine: {e}")
    
    def get_stats(self) -> Dict:
        """Obter estatísticas do engine"""
        return {
            'is_initialized': self.is_initialized,
            'known_faces': len(self.face_embeddings),
            'use_gpu': self.use_gpu,
            'confidence_threshold': settings.CONFIDENCE_THRESHOLD
        }
    
    def _get_person_name(self, person_id: str) -> str:
        """Get person name from person_id for WebRTC overlay"""
        if not person_id:
            return "Desconhecido"
        
        if person_id.startswith('unknown_'):
            return "Desconhecido"
        
        # Try to get name from known faces mapping (if available)
        if hasattr(self, 'person_names') and person_id in self.person_names:
            return self.person_names[person_id]
        
        # Try to query database synchronously for name
        try:
            from app.database.database import get_db_sync
            from app.database import models
            
            db_gen = get_db_sync()
            db = next(db_gen)
            
            person = db.query(models.Person).filter(models.Person.id == person_id).first()
            if person and person.name:
                # Cache the name for future use
                if not hasattr(self, 'person_names'):
                    self.person_names = {}
                self.person_names[person_id] = person.name
                db.close()
                return person.name
            
            db.close()
            
        except Exception as e:
            logger.warning(f"Could not get person name for {person_id}: {e}")
        
        # Fallback to person_id if name not found
        return person_id

    async def _cleanup_grace_buffer(self):
        """Limpeza periódica do buffer de desconhecidos"""
        while True:
            await asyncio.sleep(self.unknown_grace_period)
            current_time = datetime.now()
            to_remove = []
            for embedding_hash, info in self.unknown_grace_buffer.items():
                if current_time - info['first_seen'] > timedelta(seconds=self.unknown_grace_period):
                    to_remove.append(embedding_hash)
            
            for embedding_hash in to_remove:
                del self.unknown_grace_buffer[embedding_hash]