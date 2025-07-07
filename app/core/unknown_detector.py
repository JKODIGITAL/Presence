"""
Sistema de detecção automática de pessoas desconhecidas
"""

import cv2
import numpy as np
from typing import Dict, List, Optional, Tuple, Any
import uuid
import time
import base64
import json
from datetime import datetime, timedelta
from dataclasses import dataclass
from pathlib import Path
import asyncio
from collections import defaultdict
import math

from loguru import logger
from app.core.unknown_detection_config import unknown_detection_manager
from app.database.models import UnknownPerson
from app.database.database import get_db_sync


@dataclass
class FaceTrack:
    """Rastreamento de uma face ao longo do tempo"""
    track_id: str
    first_seen: float
    last_seen: float
    frame_count: int
    best_frame: Optional[np.ndarray] = None
    best_embedding: Optional[np.ndarray] = None
    best_confidence: float = 0.0
    best_bbox: Optional[Tuple[int, int, int, int]] = None
    average_size: float = 0.0
    is_processed: bool = False


@dataclass
class UnknownCandidate:
    """Candidato a pessoa desconhecida"""
    unknown_id: str
    image_data: str  # Base64
    embedding: np.ndarray
    bbox: Tuple[int, int, int, int]
    confidence: float
    detected_at: datetime
    camera_id: str
    quality_score: float
    frame_count: int = 1
    presence_duration: float = 0.0


class FaceQualityValidator:
    """Validador de qualidade facial"""
    
    def __init__(self):
        self.config = unknown_detection_manager.config.face_quality
    
    def validate_face_size(self, bbox: Tuple[int, int, int, int], frame_shape: Tuple[int, int]) -> bool:
        """Validar tamanho da face"""
        x1, y1, x2, y2 = bbox
        face_width = x2 - x1
        face_height = y2 - y1
        
        frame_height, frame_width = frame_shape[:2]
        face_area = face_width * face_height
        frame_area = frame_width * frame_height
        face_area_ratio = face_area / frame_area
        
        # Verificar tamanho mínimo em pixels
        if face_width < self.config.min_face_width or face_height < self.config.min_face_height:
            return False
        
        # Verificar proporção mínima da imagem
        if face_area_ratio < self.config.min_face_area_ratio:
            return False
        
        return True
    
    def validate_brightness(self, face_crop: np.ndarray) -> bool:
        """Validar iluminação da face"""
        try:
            # Converter para grayscale se necessário
            if len(face_crop.shape) == 3:
                gray = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)
            else:
                gray = face_crop
            
            mean_brightness = np.mean(gray)
            
            return self.config.min_brightness <= mean_brightness <= self.config.max_brightness
        except Exception:
            return False
    
    def validate_sharpness(self, face_crop: np.ndarray) -> bool:
        """Validar nitidez da face usando variância do Laplaciano"""
        try:
            # Converter para grayscale se necessário
            if len(face_crop.shape) == 3:
                gray = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)
            else:
                gray = face_crop
            
            # Calcular variância do Laplaciano
            laplacian = cv2.Laplacian(gray, cv2.CV_64F)
            sharpness = laplacian.var()
            
            return sharpness >= self.config.min_sharpness
        except Exception:
            return False
    
    def calculate_quality_score(self, face_crop: np.ndarray, bbox: Tuple[int, int, int, int], 
                              frame_shape: Tuple[int, int], confidence: float) -> float:
        """Calcular pontuação de qualidade (0-1)"""
        try:
            scores = []
            
            # 1. Confiança da detecção (peso: 30%)
            scores.append(min(confidence / self.config.min_detection_confidence, 1.0) * 0.3)
            
            # 2. Tamanho da face (peso: 25%)
            x1, y1, x2, y2 = bbox
            face_width = x2 - x1
            face_height = y2 - y1
            face_area = face_width * face_height
            frame_area = frame_shape[0] * frame_shape[1]
            size_ratio = min(face_area / (frame_area * self.config.min_face_area_ratio), 1.0)
            scores.append(size_ratio * 0.25)
            
            # 3. Nitidez (peso: 25%)
            if len(face_crop.shape) == 3:
                gray = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)
            else:
                gray = face_crop
            laplacian = cv2.Laplacian(gray, cv2.CV_64F)
            sharpness = laplacian.var()
            sharpness_score = min(sharpness / self.config.min_sharpness, 1.0)
            scores.append(sharpness_score * 0.25)
            
            # 4. Iluminação (peso: 20%)
            mean_brightness = np.mean(gray)
            optimal_brightness = (self.config.min_brightness + self.config.max_brightness) / 2
            brightness_diff = abs(mean_brightness - optimal_brightness)
            max_diff = (self.config.max_brightness - self.config.min_brightness) / 2
            brightness_score = max(0, 1 - (brightness_diff / max_diff))
            scores.append(brightness_score * 0.2)
            
            return sum(scores)
            
        except Exception as e:
            logger.error(f"Erro ao calcular qualidade: {e}")
            return 0.0
    
    def is_face_valid(self, face_crop: np.ndarray, bbox: Tuple[int, int, int, int], 
                     frame_shape: Tuple[int, int], confidence: float) -> bool:
        """Verificar se a face atende aos critérios de qualidade"""
        
        # 1. Verificar confiança mínima
        if confidence < self.config.min_detection_confidence:
            return False
        
        # 2. Verificar tamanho
        if not self.validate_face_size(bbox, frame_shape):
            return False
        
        # 3. Verificar iluminação
        if not self.validate_brightness(face_crop):
            return False
        
        # 4. Verificar nitidez
        if not self.validate_sharpness(face_crop):
            return False
        
        return True


class UnknownDetector:
    """Detector automático de pessoas desconhecidas"""
    
    def __init__(self):
        self.config = unknown_detection_manager.config
        self.quality_validator = FaceQualityValidator()
        
        # Tracking de faces por câmera
        self.face_tracks: Dict[str, Dict[str, FaceTrack]] = defaultdict(dict)
        
        # Cooldown para evitar duplicatas
        self.detection_cooldown: Dict[str, float] = {}
        
        # Contador de sessão
        self.session_unknown_count = 0
        
        # Última limpeza
        self.last_cleanup = time.time()
        
        logger.info("UnknownDetector inicializado")
    
    def _calculate_face_distance(self, embedding1: np.ndarray, embedding2: np.ndarray) -> float:
        """Calcular distância entre embeddings de faces"""
        try:
            # Normalizar embeddings
            embedding1_norm = embedding1 / np.linalg.norm(embedding1)
            embedding2_norm = embedding2 / np.linalg.norm(embedding2)
            
            # Calcular similaridade coseno
            cosine_sim = np.dot(embedding1_norm, embedding2_norm)
            
            # Converter para distância (0 = idêntico, 1 = completamente diferente)
            distance = 1 - cosine_sim
            return float(distance)
        except Exception:
            return 1.0  # Máxima distância em caso de erro
    
    def _find_matching_track(self, embedding: np.ndarray, bbox: Tuple[int, int, int, int], 
                           camera_id: str) -> Optional[str]:
        """Encontrar track existente que corresponde à face"""
        if camera_id not in self.face_tracks:
            return None
        
        current_time = time.time()
        center_x = (bbox[0] + bbox[2]) / 2
        center_y = (bbox[1] + bbox[3]) / 2
        
        best_match = None
        min_distance = float('inf')
        
        for track_id, track in self.face_tracks[camera_id].items():
            # Verificar se o track não expirou
            if current_time - track.last_seen > self.config.temporal.face_tracking_timeout:
                continue
            
            # Comparar embeddings se disponível
            if track.best_embedding is not None:
                distance = self._calculate_face_distance(embedding, track.best_embedding)
                if distance < 0.3 and distance < min_distance:  # Threshold para mesmo rosto
                    min_distance = distance
                    best_match = track_id
        
        return best_match
    
    def _crop_face(self, frame: np.ndarray, bbox: Tuple[int, int, int, int]) -> np.ndarray:
        """Extrair crop da face com margem"""
        try:
            x1, y1, x2, y2 = bbox
            h, w = frame.shape[:2]
            
            # Adicionar margem de 20%
            margin_x = int((x2 - x1) * 0.2)
            margin_y = int((y2 - y1) * 0.2)
            
            # Ajustar coordenadas com margem
            x1 = max(0, x1 - margin_x)
            y1 = max(0, y1 - margin_y)
            x2 = min(w, x2 + margin_x)
            y2 = min(h, y2 + margin_y)
            
            return frame[y1:y2, x1:x2]
        except Exception:
            return frame[bbox[1]:bbox[3], bbox[0]:bbox[2]]
    
    def _frame_to_base64(self, frame: np.ndarray) -> str:
        """Converter frame para base64"""
        try:
            _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            return base64.b64encode(buffer).decode('utf-8')
        except Exception as e:
            logger.error(f"Erro ao converter frame para base64: {e}")
            return ""
    
    async def _check_unknown_recurrence(self, candidate: UnknownCandidate, session) -> Dict[str, Any]:
        """Verificar se uma pessoa desconhecida já foi vista antes (recorrência)"""
        try:
            # Buscar todos os desconhecidos existentes
            existing_unknowns = session.query(UnknownPerson).filter(
                UnknownPerson.status.in_(["pending", "identified"])  # Não incluir ignorados
            ).all()
            
            best_match_id = None
            best_distance = float('inf')
            last_seen = None
            
            # Comparar embedding com todos os desconhecidos existentes
            for existing_unknown in existing_unknowns:
                if existing_unknown.embedding_data:
                    try:
                        existing_embedding = np.frombuffer(existing_unknown.embedding_data, dtype=np.float32)
                        distance = self._calculate_face_distance(candidate.embedding, existing_embedding)
                        
                        # Threshold para considerar recorrência (mais permissivo que duplicata)
                        recurrence_threshold = 0.3
                        
                        if distance < recurrence_threshold and distance < best_distance:
                            best_distance = distance
                            best_match_id = existing_unknown.id
                            last_seen = existing_unknown.detected_at
                            
                    except Exception as e:
                        logger.warning(f"Erro ao comparar embedding: {e}")
                        continue
            
            # Considerar recorrente se encontrou match com boa similaridade
            is_recurrent = best_match_id is not None and best_distance < 0.3
            
            return {
                'is_recurrent': is_recurrent,
                'existing_id': best_match_id,
                'similarity_distance': best_distance,
                'last_seen': last_seen.isoformat() if last_seen else None,
                'confidence': 1.0 - best_distance if is_recurrent else 0.0
            }
            
        except Exception as e:
            logger.error(f"Erro ao verificar recorrência: {e}")
            return {
                'is_recurrent': False,
                'existing_id': None,
                'similarity_distance': float('inf'),
                'last_seen': None,
                'confidence': 0.0
            }
    
    async def _save_unknown_to_database(self, candidate: UnknownCandidate) -> bool:
        """Salvar pessoa desconhecida no banco de dados"""
        try:
            session = next(get_db_sync())
            
            # Verificar recorrência - buscar em todos os desconhecidos existentes
            recurrence_result = await self._check_unknown_recurrence(candidate, session)
            
            if recurrence_result['is_recurrent']:
                # Pessoa desconhecida já foi vista antes
                existing_id = recurrence_result['existing_id']
                logger.info(f"[PROCESSING] Desconhecido recorrente detectado: {existing_id} (última vez: {recurrence_result['last_seen']})")
                
                # Atualizar informações do desconhecido existente
                existing_unknown = session.query(UnknownPerson).filter(
                    UnknownPerson.id == existing_id
                ).first()
                
                if existing_unknown:
                    # Incrementar contadores de recorrência
                    existing_unknown.frame_count += candidate.frame_count
                    existing_unknown.presence_duration += candidate.presence_duration
                    existing_unknown.detected_at = datetime.now()  # Atualizar última detecção
                    
                    # Adicionar informações de recorrência
                    additional_data = json.loads(existing_unknown.additional_data or '{}')
                    recurrence_count = additional_data.get('recurrence_count', 0) + 1
                    additional_data.update({
                        'recurrence_count': recurrence_count,
                        'last_camera_id': candidate.camera_id,
                        'total_sightings': recurrence_count + 1
                    })
                    existing_unknown.additional_data = json.dumps(additional_data)
                    
                    session.commit()
                    session.close()
                    
                    logger.info(f"[OK] Desconhecido recorrente atualizado: {existing_id} (total: {recurrence_count + 1} avistamentos)")
                    return True
            
            # Verificar duplicatas recentes (última hora) para evitar spam
            recent_threshold = datetime.now() - timedelta(hours=1)
            recent_similar = session.query(UnknownPerson).filter(
                UnknownPerson.camera_id == candidate.camera_id,
                UnknownPerson.detected_at >= recent_threshold
            ).all()
            
            # Comparar embeddings para evitar duplicatas recentes
            for recent_unknown in recent_similar:
                if recent_unknown.embedding_data:
                    try:
                        recent_embedding = np.frombuffer(recent_unknown.embedding_data, dtype=np.float32)
                        distance = self._calculate_face_distance(candidate.embedding, recent_embedding)
                        if distance < 0.15:  # Muito similar recentemente, ignorar
                            logger.debug(f"Desconhecido muito similar detectado recentemente: {recent_unknown.id}")
                            session.close()
                            return False
                    except Exception:
                        continue
            
            # Criar nova entrada
            unknown_person = UnknownPerson(
                id=candidate.unknown_id,
                image_data=candidate.image_data,
                embedding_data=candidate.embedding.tobytes(),
                bbox_data=json.dumps(candidate.bbox),
                confidence=candidate.confidence,
                quality_score=candidate.quality_score,
                camera_id=candidate.camera_id,
                detected_at=candidate.detected_at,
                status='pending',
                frame_count=candidate.frame_count,
                presence_duration=candidate.presence_duration
            )
            
            session.add(unknown_person)
            session.commit()
            session.close()
            
            logger.info(f"[OK] Desconhecido salvo: {candidate.unknown_id} da câmera {candidate.camera_id}")
            return True
            
        except Exception as e:
            logger.error(f"[ERROR] Erro ao salvar desconhecido no banco: {e}")
            if 'session' in locals():
                session.rollback()
                session.close()
            return False
    
    async def process_frame(self, frame: np.ndarray, detection_results: List[Dict], 
                          camera_id: str) -> List[UnknownCandidate]:
        """Processar frame para detectar pessoas desconhecidas"""
        
        if not self.config.enabled:
            return []
        
        current_time = time.time()
        unknown_candidates = []
        
        # Limpeza periódica (a cada hora)
        if current_time - self.last_cleanup > 3600:
            await self._cleanup_old_tracks(camera_id)
            self.last_cleanup = current_time
        
        # Verificar limite de sessão
        if self.session_unknown_count >= self.config.max_unknowns_per_session:
            return []
        
        for detection in detection_results:
            try:
                # Extrair dados da detecção
                if 'person_name' in detection and detection['person_name'] != 'Desconhecido':
                    continue  # Pessoa conhecida, pular
                
                bbox = detection.get('bbox', [])
                confidence = detection.get('confidence', 0.0)
                embedding = detection.get('embedding')
                
                if len(bbox) != 4 or embedding is None:
                    continue
                
                bbox = tuple(map(int, bbox))
                
                # Validar qualidade da face
                face_crop = self._crop_face(frame, bbox)
                if not self.quality_validator.is_face_valid(face_crop, bbox, frame.shape, confidence):
                    continue
                
                # Calcular pontuação de qualidade
                quality_score = self.quality_validator.calculate_quality_score(
                    face_crop, bbox, frame.shape, confidence
                )
                
                # Encontrar ou criar track
                track_id = self._find_matching_track(embedding, bbox, camera_id)
                if track_id is None:
                    track_id = str(uuid.uuid4())
                    self.face_tracks[camera_id][track_id] = FaceTrack(
                        track_id=track_id,
                        first_seen=current_time,
                        last_seen=current_time,
                        frame_count=1,
                        best_frame=face_crop.copy(),
                        best_embedding=embedding.copy(),
                        best_confidence=confidence,
                        best_bbox=bbox,
                        average_size=((bbox[2] - bbox[0]) * (bbox[3] - bbox[1]))
                    )
                else:
                    # Atualizar track existente
                    track = self.face_tracks[camera_id][track_id]
                    track.last_seen = current_time
                    track.frame_count += 1
                    
                    # Atualizar melhor frame se a qualidade for maior
                    if quality_score > track.best_confidence:
                        track.best_frame = face_crop.copy()
                        track.best_embedding = embedding.copy()
                        track.best_confidence = quality_score
                        track.best_bbox = bbox
                
                # Verificar se track atende aos critérios temporais
                track = self.face_tracks[camera_id][track_id]
                presence_duration = track.last_seen - track.first_seen
                
                if (track.frame_count >= self.config.temporal.min_frame_count and
                    presence_duration >= self.config.temporal.min_presence_duration and
                    not track.is_processed):
                    
                    # Verificar cooldown
                    cooldown_key = f"{camera_id}_{track_id}"
                    last_detection = self.detection_cooldown.get(cooldown_key, 0)
                    if current_time - last_detection < self.config.temporal.cooldown_period:
                        continue
                    
                    # Criar candidato a desconhecido
                    unknown_id = f"unknown_{uuid.uuid4().hex[:8]}"
                    image_data = self._frame_to_base64(track.best_frame)
                    
                    candidate = UnknownCandidate(
                        unknown_id=unknown_id,
                        image_data=image_data,
                        embedding=track.best_embedding,
                        bbox=track.best_bbox,
                        confidence=track.best_confidence,
                        detected_at=datetime.now(),
                        camera_id=camera_id,
                        quality_score=quality_score,
                        frame_count=track.frame_count,
                        presence_duration=presence_duration
                    )
                    
                    # Salvar no banco de dados
                    if await self._save_unknown_to_database(candidate):
                        unknown_candidates.append(candidate)
                        track.is_processed = True
                        self.detection_cooldown[cooldown_key] = current_time
                        self.session_unknown_count += 1
                        
                        logger.info(f"[SEARCH] Novo desconhecido detectado: {unknown_id} na câmera {camera_id}")
                
            except Exception as e:
                logger.error(f"Erro ao processar detecção: {e}")
                continue
        
        return unknown_candidates
    
    async def _cleanup_old_tracks(self, camera_id: str):
        """Limpar tracks antigos"""
        current_time = time.time()
        timeout = self.config.temporal.face_tracking_timeout
        
        if camera_id in self.face_tracks:
            expired_tracks = [
                track_id for track_id, track in self.face_tracks[camera_id].items()
                if current_time - track.last_seen > timeout
            ]
            
            for track_id in expired_tracks:
                del self.face_tracks[camera_id][track_id]
            
            if expired_tracks:
                logger.info(f"Limpeza: {len(expired_tracks)} tracks expirados removidos da câmera {camera_id}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Obter estatísticas do detector"""
        active_tracks = sum(len(tracks) for tracks in self.face_tracks.values())
        
        return {
            'enabled': self.config.enabled,
            'active_tracks': active_tracks,
            'session_unknown_count': self.session_unknown_count,
            'cameras_with_tracks': len(self.face_tracks),
            'config': unknown_detection_manager.get_config_dict()
        }


# Instância global do detector
unknown_detector = UnknownDetector()