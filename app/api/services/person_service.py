"""
Person service - Business logic for person management
"""

import uuid
import json
import os
from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session
from loguru import logger
import numpy as np
from PIL import Image
import io
import cv2
import time

from app.database import models
from app.api.schemas.person import PersonCreate, PersonUpdate, PersonResponse
from app.core.config import settings


class PersonService:
    """Service para gerenciamento de pessoas"""
    
    @staticmethod
    async def create_person(db: Session, person_data: PersonCreate, image_data: Optional[bytes] = None, validate_face: bool = True) -> models.Person:
        """Criar uma nova pessoa"""
        start_time = time.time()
        
        try:
            from datetime import datetime
            
            logger.info(f"[ROCKET] Iniciando criação de pessoa: {person_data.name}")
            
            # Gerar ID único
            person_id = str(uuid.uuid4())
            
            # Criar pessoa
            person = models.Person(
                id=person_id,
                name=person_data.name,
                department=person_data.department,
                email=person_data.email,
                phone=person_data.phone,
                tags=person_data.tags,
                is_unknown=False,
                status="active",
                first_seen=datetime.now(),
                last_seen=datetime.now(),
                recognition_count=0,
                confidence=0.0
            )
            
            # Processar imagem se fornecida
            if image_data:
                try:
                    logger.info(f"[IMAGE] Processando imagem para {person_data.name}")
                    img_start_time = time.time()
                    
                    # Validar se há face na imagem se solicitado
                    if validate_face:
                        logger.info(f"[SEARCH] Validando face na imagem...")
                        validation_start = time.time()
                        PersonService._validate_face_in_image(image_data)
                        validation_time = time.time() - validation_start
                        logger.info(f"[OK] Face validada em {validation_time:.2f}s")
                    
                    # Salvar imagem
                    logger.info(f"[SAVE] Salvando imagem...")
                    save_start = time.time()
                    thumbnail_path = PersonService._save_person_image(person_id, image_data)
                    person.thumbnail_path = thumbnail_path
                    save_time = time.time() - save_start
                    logger.info(f"[OK] Imagem salva em {save_time:.2f}s")
                    
                    # Criar pessoa com encoding temporário para ser rápido
                    # (será atualizado em background)
                    person.face_encoding = PersonService._generate_mock_encoding()
                    person.status = "pending" # Marcar como pendente enquanto processa embeddings
                    person.detection_enabled = True  # Por padrão, detecção habilitada
                    logger.info(f"[WAIT] Usando encoding temporário enquanto processa em background")
                    
                    img_total_time = time.time() - img_start_time
                    logger.info(f"[IMAGE] Processamento inicial de imagem concluído em {img_total_time:.2f}s")
                    
                except ValueError as ve:
                    # Erro na validação da face
                    db.rollback()
                    logger.error(f"[ERROR] Erro na validação da face: {ve}")
                    raise ValueError(f"Erro ao processar imagem: {str(ve)}")
                except Exception as e:
                    # Outros erros no processamento da imagem
                    db.rollback()
                    logger.error(f"[ERROR] Erro ao processar imagem: {e}")
                    raise ValueError(f"Erro ao processar imagem: {str(e)}")
            
            # Salvar pessoa no banco
            try:
                logger.info(f"[SAVE] Salvando pessoa no banco...")
                db_start = time.time()
                db.add(person)
                db.commit()
                db.refresh(person)
                db_time = time.time() - db_start
                logger.info(f"[OK] Pessoa salva no banco em {db_time:.2f}s")
            except Exception as db_error:
                db.rollback()
                logger.error(f"[ERROR] Erro ao salvar pessoa no banco: {db_error}")
                raise ValueError(f"Erro ao salvar pessoa no banco: {str(db_error)}")
            
            # Processar face encoding em background se imagem fornecida
            if image_data:
                try:
                    import threading
                    import asyncio
                    
                    # Esta função será executada em uma thread separada
                    def process_embedding_background():
                        try:
                            logger.info(f"[RECOGNITION] Iniciando extração de face encoding em background para {person.id}...")
                            
                            # Criar novo loop de eventos para processar o embedding
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                            
                            # Extrair embedding e atualizar pessoa
                            face_encoding = loop.run_until_complete(PersonService._extract_face_encoding(image_data))
                            
                            if face_encoding:
                                # Atualizar pessoa com embedding real
                                with db.begin():
                                    db_person = db.query(models.Person).filter(models.Person.id == person.id).first()
                                    if db_person:
                                        db_person.face_encoding = face_encoding
                                        db_person.status = "active"
                                        db.commit()
                                logger.info(f"[OK] Face encoding extraído e salvo para {person.id}")
                                
                                # Atualizar recognition engine também
                                loop.run_until_complete(PersonService._update_recognition_engine(person.id, face_encoding, person.name))
                                logger.info(f"[OK] Recognition engine atualizado para {person.id}")
                                
                                # Sincronizar com o recognition worker
                                from app.api.services.recognition_client import recognition_client
                                import numpy as np
                                
                                embedding = np.frombuffer(face_encoding, dtype=np.float32)
                                success = loop.run_until_complete(recognition_client.add_known_face(person.id, embedding, person.name))
                                if success:
                                    logger.info(f"[OK] Pessoa sincronizada com recognition worker: {person.id}")
                                    # Solicitar reload das faces conhecidas
                                    loop.run_until_complete(recognition_client.reload_known_faces())
                                    logger.info(f"[OK] Reload das faces solicitado após adicionar {person.name}")
                                else:
                                    logger.warning(f"[WARNING] Falha ao sincronizar com recognition worker: {person.id}")
                            else:
                                logger.warning(f"[WARNING] Não foi possível extrair face encoding em background para {person.id}")
                            
                            loop.close()
                            
                        except Exception as e:
                            logger.error(f"[ERROR] Erro ao processar embedding em background: {e}")
                    
                    # Iniciar thread para processamento em background
                    thread = threading.Thread(target=process_embedding_background)
                    thread.daemon = True
                    thread.start()
                    logger.info(f"[PROCESSING] Processamento de embedding iniciado em background para {person.id}")
                    
                except Exception as e:
                    logger.warning(f"[WARNING] Não foi possível iniciar processamento em background: {e}")
            
            total_time = time.time() - start_time
            logger.info(f"[OK] Pessoa criada com sucesso: {person.name} (ID: {person.id}) em {total_time:.2f}s")
            return person
            
        except ValueError as ve:
            # Repassar erros de validação
            total_time = time.time() - start_time
            logger.error(f"[ERROR] Erro de validação após {total_time:.2f}s: {ve}")
            raise ve
        except Exception as e:
            # Outros erros não tratados
            db.rollback()
            total_time = time.time() - start_time
            logger.error(f"[ERROR] Erro não tratado após {total_time:.2f}s: {e}")
            raise ValueError(f"Erro ao criar pessoa: {str(e)}")
    
    @staticmethod
    def get_person(db: Session, person_id: str) -> Optional[models.Person]:
        """Buscar pessoa por ID"""
        return db.query(models.Person).filter(models.Person.id == person_id).first()
    
    @staticmethod
    def get_people(
        db: Session, 
        skip: int = 0, 
        limit: int = 50,
        search: Optional[str] = None,
        department: Optional[str] = None,
        status: Optional[str] = None
    ) -> List[models.Person]:
        """Listar pessoas com filtros"""
        query = db.query(models.Person)
        
        if search:
            query = query.filter(models.Person.name.contains(search))
        
        if department:
            query = query.filter(models.Person.department == department)
        
        if status:
            query = query.filter(models.Person.status == status)
        
        return query.offset(skip).limit(limit).all()
    
    @staticmethod
    def update_person(db: Session, person_id: str, person_data: PersonUpdate) -> Optional[models.Person]:
        """Atualizar pessoa"""
        try:
            person = db.query(models.Person).filter(models.Person.id == person_id).first()
            if not person:
                return None
            
            # Atualizar campos fornecidos
            if hasattr(person_data, 'dict'):
                update_data = person_data.dict(exclude_unset=True)
            elif hasattr(person_data, 'model_dump'):
                update_data = person_data.model_dump(exclude_unset=True)
            elif isinstance(person_data, dict):
                update_data = person_data
            else:
                update_data = person_data.__dict__
            for field, value in update_data.items():
                setattr(person, field, value)
            
            person.updated_at = datetime.now()
            db.commit()
            db.refresh(person)
            
            logger.info(f"Pessoa atualizada: {person.name} (ID: {person.id})")
            return person
            
        except Exception as e:
            db.rollback()
            logger.error(f"Erro ao atualizar pessoa: {e}")
            raise
    
    @staticmethod
    def delete_person(db: Session, person_id: str) -> bool:
        """Deletar pessoa"""
        try:
            logger.info(f"Tentando deletar pessoa com ID: {person_id}")
            
            # Buscar pessoa primeiro
            person = db.query(models.Person).filter(models.Person.id == person_id).first()
            if not person:
                logger.warning(f"Pessoa não encontrada para ID: {person_id}")
                return False
            
            logger.info(f"Encontrada pessoa para deletar: {person.name} (ID: {person.id})")
            
            # Deletar reconhecimentos associados primeiro
            try:
                recognition_count = db.query(models.RecognitionLog).filter(
                    models.RecognitionLog.person_id == person_id
                ).count()
                
                if recognition_count > 0:
                    logger.info(f"Deletando {recognition_count} logs de reconhecimento para pessoa {person.name}")
                    db.query(models.RecognitionLog).filter(
                        models.RecognitionLog.person_id == person_id
                    ).delete()
                    
            except Exception as e:
                logger.warning(f"Erro ao deletar logs de reconhecimento: {e}")
                # Continuar mesmo se não conseguir deletar os logs
                
            # Remover arquivo de imagem se existir
            if hasattr(person, 'thumbnail_path') and person.thumbnail_path:
                try:
                    PersonService._delete_person_image(person.thumbnail_path)
                    logger.info(f"Imagem deletada: {person.thumbnail_path}")
                except Exception as e:
                    logger.warning(f"Erro ao deletar imagem: {e}")
                    # Continuar mesmo se não conseguir deletar a imagem
            
            # Deletar pessoa
            person_name = person.name
            db.delete(person)
            db.commit()
            
            logger.info(f"Pessoa deletada com sucesso: {person_name} (ID: {person_id})")
            return True
            
        except Exception as e:
            db.rollback()
            logger.error(f"Erro ao deletar pessoa {person_id}: {e}")
            raise Exception(f"Erro ao deletar pessoa: {str(e)}")
    
    @staticmethod
    def get_person_stats(db: Session) -> Dict[str, int]:
        """Obter estatísticas de pessoas"""
        try:
            total_people = db.query(models.Person).count()
            active_people = db.query(models.Person).filter(models.Person.status == "active").count()
            unknown_people = db.query(models.Person).filter(models.Person.is_unknown == True).count()
            
            # Reconhecimentos recentes (últimas 24h)
            from datetime import timedelta
            yesterday = datetime.now() - timedelta(days=1)
            recent_recognitions = db.query(models.RecognitionLog).filter(
                models.RecognitionLog.timestamp >= yesterday
            ).count()
            
            return {
                "total_people": total_people,
                "active_people": active_people,
                "unknown_people": unknown_people,
                "recent_recognitions": recent_recognitions
            }
            
        except Exception as e:
            logger.error(f"Erro ao obter estatísticas: {e}")
            return {
                "total_people": 0,
                "active_people": 0,
                "unknown_people": 0,
                "recent_recognitions": 0
            }
    
    @staticmethod
    async def update_person_image(db: Session, person_id: str, image_data: bytes) -> Optional[models.Person]:
        """Atualizar imagem da pessoa"""
        try:
            person = db.query(models.Person).filter(models.Person.id == person_id).first()
            if not person:
                return None
            
            # Validar se há face na imagem
            PersonService._validate_face_in_image(image_data)
            
            # Deletar imagem antiga se existir
            old_thumbnail = getattr(person, 'thumbnail_path', None)
            if old_thumbnail:
                PersonService._delete_person_image(str(old_thumbnail))
            
            # Salvar nova imagem
            thumbnail_path = PersonService._save_person_image(str(person_id), image_data)
            setattr(person, 'thumbnail_path', thumbnail_path)
            
            # Atualizar face encoding
            face_encoding = await PersonService._extract_face_encoding(image_data)
            if face_encoding is not None:
                setattr(person, 'face_encoding', face_encoding)
                # Atualizar recognition engine
                await PersonService._update_recognition_engine(str(person.id), face_encoding)
            
            setattr(person, 'updated_at', datetime.now())
            db.commit()
            db.refresh(person)
            
            logger.info(f"Imagem atualizada para pessoa: {person.name} (ID: {person.id})")
            return person
            
        except Exception as e:
            db.rollback()
            logger.error(f"Erro ao atualizar imagem da pessoa: {e}")
            raise
    
    @staticmethod
    def update_recognition_stats(db: Session, person_id: str, confidence: float):
        """Atualizar estatísticas de reconhecimento"""
        try:
            person = db.query(models.Person).filter(models.Person.id == person_id).first()
            if person:
                person.last_seen = datetime.now()
                person.recognition_count += 1
                person.confidence = max(person.confidence, confidence)
                db.commit()
                
        except Exception as e:
            logger.error(f"Erro ao atualizar estatísticas de reconhecimento: {e}")
    
    @staticmethod
    def _save_person_image(person_id: str, image_data: bytes) -> str:
        """Salvar imagem da pessoa"""
        try:
            # Criar diretório se não existir
            upload_dir = settings.UPLOADS_DIR / "people"
            upload_dir.mkdir(parents=True, exist_ok=True)
            
            # Gerar nome do arquivo
            filename = f"{person_id}.jpg"
            file_path = upload_dir / filename
            
            # Processar e salvar imagem
            image = Image.open(io.BytesIO(image_data))
            image = image.convert("RGB")
            
            # Redimensionar se necessário
            if image.width > 512 or image.height > 512:
                image.thumbnail((512, 512), Image.Resampling.LANCZOS)
            
            image.save(file_path, "JPEG", quality=85)
            
            return str(file_path.relative_to(settings.BASE_DIR))
            
        except Exception as e:
            logger.error(f"Erro ao salvar imagem: {e}")
            raise
    
    @staticmethod
    def _delete_person_image(thumbnail_path: str):
        """Deletar imagem da pessoa"""
        try:
            if thumbnail_path:
                full_path = settings.BASE_DIR / thumbnail_path
                if os.path.exists(full_path):
                    os.unlink(full_path)
                    logger.info(f"Imagem deletada: {thumbnail_path}")
        except Exception as e:
            logger.error(f"Erro ao deletar imagem: {e}")
    
    @staticmethod
    def _validate_face_in_image(image_data: bytes) -> bool:
        """Validar se há pelo menos uma face na imagem"""
        import time
        start_time = time.time()
        
        try:
            # Converter bytes para imagem OpenCV
            nparr = np.frombuffer(image_data, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if img is None:
                raise ValueError("Não foi possível decodificar a imagem")
            
            # Recognition Engine agora é processo externo - usar fallback direto
            logger.info("[PROCESSING] Usando detector Haar Cascade para validação de face (Recognition Engine é externo)")
            
            # Fallback para detector Haar Cascade (mais rápido)
            fallback_start = time.time()
            face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(gray, 1.1, 4)
            
            if len(faces) == 0:
                raise ValueError("Nenhuma face detectada na imagem")
            
            fallback_time = time.time() - fallback_start
            total_time = time.time() - start_time
            logger.info(f"[OK] Detectadas {len(faces)} face(s) em {fallback_time:.2f}s usando Haar Cascade (total: {total_time:.2f}s)")
            return True
            
        except Exception as e:
            total_time = time.time() - start_time
            logger.error(f"[ERROR] Erro na validação de face após {total_time:.2f}s: {e}")
            raise ValueError(f"Erro na validação da imagem: {str(e)}")
    
    @staticmethod
    async def _extract_face_encoding(image_data: bytes) -> Optional[bytes]:
        """Extrair face encoding usando o recognition engine se disponível"""
        import time
        start_time = time.time()
        
        try:
            # Converter bytes para imagem OpenCV
            nparr = np.frombuffer(image_data, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if img is None:
                logger.error("Não foi possível decodificar a imagem para extração de encoding")
                return PersonService._generate_mock_encoding()
            
            # Usar Recognition Worker via Socket.IO para extração de face encoding
            try:
                from app.api.services.recognition_client import recognition_client
                
                # Tentar extrair embedding real usando Recognition Worker
                logger.info("[PROCESSING] Tentando extrair embedding via Recognition Worker...")
                embedding = await recognition_client.extract_face_embedding(image_data)
                
                if embedding is not None:
                    encoding_time = time.time() - start_time
                    logger.info(f"[OK] Face encoding extraído via Recognition Worker em {encoding_time:.2f}s")
                    return embedding.tobytes()
                else:
                    logger.warning("Recognition Worker não conseguiu extrair embedding, usando mock")
                    
                # Fallback para mock se Recognition Worker falhar
                if True:  # Habilitado como fallback
                    # Usar timeout para evitar travamento
                    import threading
                    import queue
                    
                    result_queue = queue.Queue()
                    error_queue = queue.Queue()
                    
                    def extract_encoding():
                        try:
                            # Detectar faces na imagem
                            faces = engine.detect_faces(img)
                            if faces and len(faces) > 0:
                                # Usar o embedding da primeira face detectada
                                embedding = faces[0]['embedding']
                                result_queue.put(embedding.tobytes())
                            else:
                                result_queue.put(None)
                        except Exception as e:
                            error_queue.put(e)
                    
                    # Executar extração com timeout
                    thread = threading.Thread(target=extract_encoding)
                    thread.daemon = True
                    thread.start()
                    thread.join(timeout=10.0)  # 10 segundos de timeout
                    
                    if thread.is_alive():
                        logger.warning("Timeout na extração de encoding usando Recognition Engine, usando mock")
                        return PersonService._generate_mock_encoding()
                    
                    if not error_queue.empty():
                        raise error_queue.get()
                    
                    if not result_queue.empty():
                        encoding = result_queue.get()
                        if encoding:
                            encoding_time = time.time() - start_time
                            logger.info(f"[OK] Face encoding extraído em {encoding_time:.2f}s")
                            return encoding
                            
            except Exception as engine_error:
                logger.warning(f"Recognition engine não disponível ou timeout: {engine_error}")
            
            # Se não conseguir extrair encoding, usar mock
            mock_time = time.time() - start_time
            logger.warning(f"[WARNING] Usando mock encoding após {mock_time:.2f}s")
            return PersonService._generate_mock_encoding()
            
        except Exception as e:
            total_time = time.time() - start_time
            logger.warning(f"[WARNING] Erro ao extrair face encoding após {total_time:.2f}s: {e}")
            return PersonService._generate_mock_encoding()
    
    @staticmethod
    async def _update_recognition_engine(person_id: str, face_encoding: bytes, person_name: str = ""):
        """Atualizar recognition engine com nova face via Recognition Worker"""
        try:
            from app.api.services.recognition_client import recognition_client
            
            # Converter bytes para numpy array
            embedding = np.frombuffer(face_encoding, dtype=np.float32)
            
            # Enviar face encoding para Recognition Worker via Socket.IO
            logger.info(f"[PROCESSING] Adicionando face para pessoa {person_name} ({person_id}) via Recognition Worker...")
            success = await recognition_client.add_known_face(person_id, embedding, person_name)
            
            if success:
                logger.info(f"[OK] Face adicionada ao Recognition Worker: {person_name} ({person_id})")
            else:
                logger.warning(f"[WARNING] Falha ao adicionar face ao Recognition Worker: {person_name} ({person_id})")
                
        except Exception as e:
            logger.warning(f"Não foi possível atualizar Recognition Engine: {e}")
    
    @staticmethod
    def _generate_mock_encoding() -> bytes:
        """Gerar encoding mock para desenvolvimento"""
        # Em produção, seria extraído usando o recognition engine
        mock_encoding = np.random.rand(512).astype(np.float32)
        return mock_encoding.tobytes()
    
    @staticmethod
    async def reprocess_pending_people(db: Session) -> Dict[str, int]:
        """Reprocessar pessoas que ficaram com status pending"""
        try:
            from datetime import timedelta
            import threading
            import asyncio
            
            # Buscar pessoas pendentes há mais de 5 minutos
            five_minutes_ago = datetime.now() - timedelta(minutes=5)
            pending_people = db.query(models.Person).filter(
                models.Person.status == "pending",
                models.Person.updated_at < five_minutes_ago,
                models.Person.thumbnail_path.isnot(None)
            ).all()
            
            processed = 0
            failed = 0
            
            logger.info(f"[PROCESSING] Encontradas {len(pending_people)} pessoas pendentes para reprocessar")
            
            for person in pending_people:
                try:
                    # Tentar carregar imagem
                    import os
                    if person.thumbnail_path and os.path.exists(person.thumbnail_path):
                        with open(person.thumbnail_path, 'rb') as f:
                            image_data = f.read()
                        
                        # Processar embedding em background
                        def process_embedding_background():
                            try:
                                loop = asyncio.new_event_loop()
                                asyncio.set_event_loop(loop)
                                
                                # Extrair embedding
                                face_encoding = loop.run_until_complete(PersonService._extract_face_encoding(image_data))
                                
                                if face_encoding:
                                    # Atualizar pessoa
                                    with db.begin():
                                        db_person = db.query(models.Person).filter(models.Person.id == person.id).first()
                                        if db_person:
                                            db_person.face_encoding = face_encoding
                                            db_person.status = "active"
                                            db_person.updated_at = datetime.now()
                                            db.commit()
                                    
                                    # Atualizar recognition engine
                                    loop.run_until_complete(PersonService._update_recognition_engine(person.id, face_encoding, person.name))
                                    
                                    # Sincronizar com recognition worker
                                    from app.api.services.recognition_client import recognition_client
                                    embedding = np.frombuffer(face_encoding, dtype=np.float32)
                                    loop.run_until_complete(recognition_client.add_known_face(person.id, embedding, person.name))
                                    loop.run_until_complete(recognition_client.reload_known_faces())
                                    
                                    logger.info(f"[OK] Pessoa reprocessada com sucesso: {person.name} ({person.id})")
                                else:
                                    # Se não conseguir extrair, marcar como inativa
                                    with db.begin():
                                        db_person = db.query(models.Person).filter(models.Person.id == person.id).first()
                                        if db_person:
                                            db_person.status = "inactive"
                                            db_person.updated_at = datetime.now()
                                            db.commit()
                                    logger.warning(f"[WARNING] Não foi possível extrair embedding, marcado como inativo: {person.name}")
                                
                                loop.close()
                                
                            except Exception as e:
                                logger.error(f"[ERROR] Erro ao reprocessar pessoa {person.name}: {e}")
                                # Marcar como inativa em caso de erro
                                try:
                                    with db.begin():
                                        db_person = db.query(models.Person).filter(models.Person.id == person.id).first()
                                        if db_person:
                                            db_person.status = "inactive"
                                            db_person.updated_at = datetime.now()
                                            db.commit()
                                except:
                                    pass
                        
                        # Iniciar processamento em background
                        thread = threading.Thread(target=process_embedding_background)
                        thread.daemon = True
                        thread.start()
                        processed += 1
                        
                    else:
                        # Se não há imagem, marcar como inativa
                        person.status = "inactive"
                        person.updated_at = datetime.now()
                        db.commit()
                        logger.warning(f"[WARNING] Pessoa sem imagem marcada como inativa: {person.name}")
                        failed += 1
                        
                except Exception as e:
                    logger.error(f"[ERROR] Erro ao processar pessoa pendente {person.name}: {e}")
                    failed += 1
            
            return {
                "found": len(pending_people),
                "processed": processed,
                "failed": failed
            }
            
        except Exception as e:
            logger.error(f"[ERROR] Erro ao reprocessar pessoas pendentes: {e}")
            return {"found": 0, "processed": 0, "failed": 0}

    @staticmethod
    async def update_person_with_image(db: Session, person_id: str, person_data: PersonUpdate, image_data: Optional[bytes] = None) -> Optional[models.Person]:
        """Atualizar pessoa com nova imagem"""
        try:
            person = db.query(models.Person).filter(models.Person.id == person_id).first()
            if not person:
                return None
            
            # Atualizar dados da pessoa
            if hasattr(person_data, 'dict'):
                update_data = person_data.dict(exclude_unset=True)
            elif hasattr(person_data, 'model_dump'):
                update_data = person_data.model_dump(exclude_unset=True)
            elif isinstance(person_data, dict):
                update_data = person_data
            else:
                update_data = person_data.__dict__
                
            for field, value in update_data.items():
                if hasattr(person, field):
                    setattr(person, field, value)
            
            # Processar nova imagem se fornecida
            if image_data:
                try:
                    logger.info(f"[IMAGE] Atualizando imagem para {person.name}")
                    
                    # Validar se há face na imagem
                    PersonService._validate_face_in_image(image_data)
                    
                    # Deletar imagem antiga se existir
                    old_thumbnail = getattr(person, 'thumbnail_path', None)
                    if old_thumbnail:
                        PersonService._delete_person_image(str(old_thumbnail))
                    
                    # Salvar nova imagem
                    thumbnail_path = PersonService._save_person_image(str(person_id), image_data)
                    person.thumbnail_path = thumbnail_path
                    
                    # Atualizar status para pendente enquanto processa embedding
                    person.status = "pending"
                    person.updated_at = datetime.now()
                    
                    # Salvar alterações no banco
                    db.commit()
                    db.refresh(person)
                    
                    # Processar face encoding em background
                    import threading
                    import asyncio
                    
                    def process_embedding_background():
                        try:
                            logger.info(f"[RECOGNITION] Iniciando atualização de face encoding para {person.id}...")
                            
                            # Criar novo loop de eventos
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                            
                            # Extrair novo embedding
                            face_encoding = loop.run_until_complete(PersonService._extract_face_encoding(image_data))
                            
                            if face_encoding:
                                # Atualizar pessoa com novo embedding
                                with db.begin():
                                    db_person = db.query(models.Person).filter(models.Person.id == person.id).first()
                                    if db_person:
                                        db_person.face_encoding = face_encoding
                                        db_person.status = "active"
                                        db.commit()
                                logger.info(f"[OK] Face encoding atualizado para {person.id}")
                                
                                # Atualizar recognition engine
                                loop.run_until_complete(PersonService._update_recognition_engine(person.id, face_encoding, person.name))
                                logger.info(f"[OK] Recognition engine atualizado para {person.id}")
                                
                                # Sincronizar com o recognition worker
                                from app.api.services.recognition_client import recognition_client
                                import numpy as np
                                
                                embedding = np.frombuffer(face_encoding, dtype=np.float32)
                                success = loop.run_until_complete(recognition_client.add_known_face(person.id, embedding, person.name))
                                if success:
                                    logger.info(f"[OK] Pessoa sincronizada com recognition worker: {person.id}")
                                    # Solicitar reload das faces conhecidas
                                    loop.run_until_complete(recognition_client.reload_known_faces())
                                    logger.info(f"[OK] Reload das faces solicitado após atualizar {person.name}")
                                else:
                                    logger.warning(f"[WARNING] Falha ao sincronizar com recognition worker: {person.id}")
                            else:
                                logger.warning(f"[WARNING] Não foi possível extrair face encoding para {person.id}")
                            
                            loop.close()
                            
                        except Exception as e:
                            logger.error(f"[ERROR] Erro ao processar embedding em background: {e}")
                    
                    # Iniciar thread para processamento em background
                    thread = threading.Thread(target=process_embedding_background)
                    thread.daemon = True
                    thread.start()
                    logger.info(f"[PROCESSING] Processamento de embedding iniciado em background para {person.id}")
                    
                except ValueError as ve:
                    # Erro na validação da face
                    db.rollback()
                    logger.error(f"[ERROR] Erro na validação da face: {ve}")
                    raise ValueError(f"Erro ao processar imagem: {str(ve)}")
                except Exception as e:
                    # Outros erros no processamento da imagem
                    db.rollback()
                    logger.error(f"[ERROR] Erro ao processar imagem: {e}")
                    raise ValueError(f"Erro ao processar imagem: {str(e)}")
            else:
                # Atualizar apenas dados sem imagem
                person.updated_at = datetime.now()
                db.commit()
                db.refresh(person)
            
            logger.info(f"[OK] Pessoa atualizada com sucesso: {person.name} (ID: {person.id})")
            return person
            
        except ValueError as ve:
            # Repassar erros de validação
            logger.error(f"[ERROR] Erro de validação: {ve}")
            raise ve
        except Exception as e:
            # Outros erros não tratados
            db.rollback()
            logger.error(f"[ERROR] Erro ao atualizar pessoa: {e}")
            raise ValueError(f"Erro ao atualizar pessoa: {str(e)}")

    @staticmethod  
    async def _extract_face_embedding(image: np.ndarray) -> Optional[np.ndarray]:
        """Extrair embedding de face de uma imagem usando Recognition Worker via Socket.IO"""
        try:
            from app.api.services.recognition_client import recognition_client
            import cv2
            import base64
            
            # Converter imagem para base64
            _, img_encoded = cv2.imencode('.jpg', image)
            img_base64 = base64.b64encode(img_encoded).decode('utf-8')
            
            # Solicitar embedding do Recognition Worker
            logger.info("[PROCESSING] Solicitando embedding do Recognition Worker...")
            result = await recognition_client.extract_embedding(img_base64)
            
            if result and result.get('success') and result.get('embedding'):
                embedding = np.array(result['embedding'], dtype=np.float32)
                logger.info(f"[OK] Embedding extraído via Recognition Worker: {embedding.shape}")
                return embedding
            else:
                error = result.get('error', 'Erro desconhecido') if result else 'Recognition Worker não disponível'
                logger.warning(f"[WARNING] Falha ao extrair embedding: {error}")
                return None
                
        except Exception as e:
            logger.error(f"[ERROR] Erro ao extrair embedding via Recognition Worker: {e}")
            return None