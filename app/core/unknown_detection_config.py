"""
Configuração para detecção automática de pessoas desconhecidas
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional
import json
import os
from pathlib import Path
from loguru import logger


@dataclass
class FaceQualityRules:
    """Regras de qualidade facial para auto-cadastro"""
    
    # Tamanho mínimo da face em pixels (CONFIGURÁVEL)
    min_face_width: int = 100  # Aumentado para melhor qualidade
    min_face_height: int = 100
    
    # Tamanho mínimo da face em porcentagem da imagem (CONFIGURÁVEL)
    min_face_area_ratio: float = 0.03  # 3% da imagem
    
    # Qualidade da detecção (confidence score)
    min_detection_confidence: float = 0.85  # Aumentado para maior precisão
    
    # Threshold de similaridade para considerar desconhecido (CONFIGURÁVEL)
    max_similarity_threshold: float = 0.35  # Abaixo de 35% = desconhecido
    
    # Verificação de alinhamento facial
    max_face_angle: float = 25.0  # Mais restritivo
    
    # Verificação de iluminação
    min_brightness: float = 60.0  # Melhor iluminação
    max_brightness: float = 180.0
    
    # Nitidez da imagem (laplacian variance)
    min_sharpness: float = 120.0  # Mais nítido


@dataclass 
class TemporalRules:
    """Regras temporais para auto-cadastro"""
    
    # Tempo mínimo que a face deve permanecer visível (segundos) (CONFIGURÁVEL)
    min_presence_duration: float = 3.0  # Aumentado para 3 segundos
    
    # Número mínimo de frames com a mesma face (CONFIGURÁVEL)
    min_frame_count: int = 15  # Mais frames para maior confiança
    
    # Intervalo entre tentativas de cadastro da mesma face (segundos) (CONFIGURÁVEL)
    cooldown_period: float = 60.0  # 1 minuto de cooldown
    
    # Timeout para tracking de faces (segundos)
    face_tracking_timeout: float = 5.0
    
    # Número máximo de tentativas de detecção por face
    max_detection_attempts: int = 3


@dataclass
class UnknownDetectionConfig:
    """Configuração completa para detecção de desconhecidos"""
    
    # Habilitar sistema de auto-detecção
    enabled: bool = True
    
    # Regras de qualidade facial
    face_quality: FaceQualityRules = field(default_factory=FaceQualityRules)
    
    # Regras temporais
    temporal: TemporalRules = field(default_factory=TemporalRules)
    
    # Threshold de similaridade para considerar "desconhecido"
    unknown_threshold: float = 0.4  # Se similaridade < 0.4 = desconhecido
    
    # Diretório para salvar imagens de desconhecidos
    unknown_images_dir: str = "data/unknown_faces"
    
    # Limitar número de desconhecidos por sessão
    max_unknowns_per_session: int = 100
    
    # Auto-limpar desconhecidos antigos (dias)
    auto_cleanup_days: int = 30


class UnknownDetectionManager:
    """Gerenciador de configurações de detecção automática"""
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or "config/unknown_detection.json"
        self.config = self.load_config()
        
        # Criar diretório de imagens se não existir
        os.makedirs(self.config.unknown_images_dir, exist_ok=True)
    
    def load_config(self) -> UnknownDetectionConfig:
        """Carregar configuração do arquivo"""
        config_file = Path(self.config_path)
        
        if config_file.exists():
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)
                
                # Converter dict para dataclass
                face_quality = FaceQualityRules(**config_data.get('face_quality', {}))
                temporal = TemporalRules(**config_data.get('temporal', {}))
                
                config = UnknownDetectionConfig(
                    enabled=config_data.get('enabled', True),
                    face_quality=face_quality,
                    temporal=temporal,
                    unknown_threshold=config_data.get('unknown_threshold', 0.4),
                    unknown_images_dir=config_data.get('unknown_images_dir', 'data/unknown_faces'),
                    max_unknowns_per_session=config_data.get('max_unknowns_per_session', 100),
                    auto_cleanup_days=config_data.get('auto_cleanup_days', 30)
                )
                
                logger.info(f"Configuração de detecção carregada de {config_file}")
                return config
                
            except Exception as e:
                logger.error(f"Erro ao carregar configuração: {e}")
        
        # Retornar configuração padrão
        logger.info("Usando configuração padrão para detecção de desconhecidos")
        return UnknownDetectionConfig()
    
    def get_config(self) -> UnknownDetectionConfig:
        """Obter configuração atual"""
        return self.config
    
    def save_config(self, config: UnknownDetectionConfig = None):
        """Salvar configuração atual"""
        if config:
            self.config = config
        try:
            # Criar diretório se não existir
            config_dir = Path(self.config_path).parent
            os.makedirs(config_dir, exist_ok=True)
            
            # Converter dataclass para dict
            config_dict = {
                'enabled': self.config.enabled,
                'face_quality': {
                    'min_face_width': self.config.face_quality.min_face_width,
                    'min_face_height': self.config.face_quality.min_face_height,
                    'min_face_area_ratio': self.config.face_quality.min_face_area_ratio,
                    'min_detection_confidence': self.config.face_quality.min_detection_confidence,
                    'max_similarity_threshold': self.config.face_quality.max_similarity_threshold,
                    'max_face_angle': self.config.face_quality.max_face_angle,
                    'min_brightness': self.config.face_quality.min_brightness,
                    'max_brightness': self.config.face_quality.max_brightness,
                    'min_sharpness': self.config.face_quality.min_sharpness
                },
                'temporal': {
                    'min_presence_duration': self.config.temporal.min_presence_duration,
                    'min_frame_count': self.config.temporal.min_frame_count,
                    'cooldown_period': self.config.temporal.cooldown_period,
                    'face_tracking_timeout': self.config.temporal.face_tracking_timeout
                },
                'unknown_threshold': self.config.unknown_threshold,
                'unknown_images_dir': self.config.unknown_images_dir,
                'max_unknowns_per_session': self.config.max_unknowns_per_session,
                'auto_cleanup_days': self.config.auto_cleanup_days
            }
            
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(config_dict, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Configuração salva em {self.config_path}")
            
        except Exception as e:
            logger.error(f"Erro ao salvar configuração: {e}")
    
    def update_config(self, **kwargs):
        """Atualizar configuração dinamicamente"""
        for key, value in kwargs.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)
                logger.info(f"Configuração atualizada: {key} = {value}")
        
        self.save_config()
    
    def get_config_dict(self) -> Dict[str, Any]:
        """Obter configuração como dicionário para API"""
        return {
            'enabled': self.config.enabled,
            'face_quality': {
                'min_face_width': self.config.face_quality.min_face_width,
                'min_face_height': self.config.face_quality.min_face_height,
                'min_face_area_ratio': self.config.face_quality.min_face_area_ratio,
                'min_detection_confidence': self.config.face_quality.min_detection_confidence,
                'max_similarity_threshold': self.config.face_quality.max_similarity_threshold,
                'max_face_angle': self.config.face_quality.max_face_angle,
                'min_brightness': self.config.face_quality.min_brightness,
                'max_brightness': self.config.face_quality.max_brightness,
                'min_sharpness': self.config.face_quality.min_sharpness
            },
            'temporal': {
                'min_presence_duration': self.config.temporal.min_presence_duration,
                'min_frame_count': self.config.temporal.min_frame_count,
                'cooldown_period': self.config.temporal.cooldown_period,
                'face_tracking_timeout': self.config.temporal.face_tracking_timeout
            },
            'unknown_threshold': self.config.unknown_threshold,
            'unknown_images_dir': self.config.unknown_images_dir,
            'max_unknowns_per_session': self.config.max_unknowns_per_session,
            'auto_cleanup_days': self.config.auto_cleanup_days
        }
    
    def reset_to_defaults(self) -> bool:
        """Resetar configuração para valores padrão"""
        try:
            self.config = UnknownDetectionConfig()
            self.save_config()
            logger.info("Configuração resetada para valores padrão")
            return True
        except Exception as e:
            logger.error(f"Erro ao resetar configuração: {e}")
            return False


# Instância global do gerenciador
unknown_detection_manager = UnknownDetectionManager()