"""
Config Sync Service - Serviço para sincronizar configurações entre API e Worker
"""

import asyncio
import json
import time
from datetime import datetime
from typing import Dict, List, Optional, Any
from loguru import logger

from app.database.database import get_db
from app.database.models import Camera


class ConfigSyncService:
    """Serviço para sincronizar configurações entre API e Worker"""
    
    def __init__(self):
        self.last_sync = None
        self.sync_interval = 30  # Sincronizar a cada 30 segundos
        self.is_running = False
        self.lock = asyncio.Lock()
        
        # Cache de configurações
        self.camera_configs: Dict[str, Dict[str, Any]] = {}
        self.last_config_hash = None
    
    async def start_sync(self):
        """Iniciar sincronização automática"""
        if self.is_running:
            return
        
        self.is_running = True
        logger.info("Iniciando sincronização automática de configurações")
        
        # Executar loop de sincronização
        asyncio.create_task(self._sync_loop())
    
    async def stop_sync(self):
        """Parar sincronização automática"""
        self.is_running = False
        logger.info("Sincronização automática parada")
    
    async def _sync_loop(self):
        """Loop de sincronização automática"""
        while self.is_running:
            try:
                await self.sync_camera_configs()
                await asyncio.sleep(self.sync_interval)
            except Exception as e:
                logger.error(f"Erro no loop de sincronização: {e}")
                await asyncio.sleep(10)  # Aguardar antes de tentar novamente
    
    async def sync_camera_configs(self) -> bool:
        """Sincronizar configurações de câmeras"""
        try:
            async with self.lock:
                # Obter configurações atuais do banco
                current_configs = await self._get_camera_configs_from_db()
                
                # Calcular hash das configurações
                config_hash = self._calculate_config_hash(current_configs)
                
                # Verificar se houve mudanças
                if config_hash == self.last_config_hash:
                    return True  # Nenhuma mudança
                
                logger.info("Detectadas mudanças nas configurações de câmeras")
                
                # Aplicar mudanças no worker
                success = await self._apply_config_changes(current_configs)
                
                if success:
                    self.last_config_hash = config_hash
                    self.camera_configs = current_configs
                    self.last_sync = datetime.now()
                    logger.info("Configurações sincronizadas com sucesso")
                    return True
                else:
                    logger.error("Falha ao sincronizar configurações")
                    return False
                    
        except Exception as e:
            logger.error(f"Erro ao sincronizar configurações: {e}")
            return False
    
    async def _get_camera_configs_from_db(self) -> Dict[str, Dict[str, Any]]:
        """Obter configurações de câmeras do banco de dados"""
        try:
            from app.database.database import get_db
            from app.database.models import Camera
            
            # Usar async with corretamente
            async with get_db() as db:
                # Buscar todas as câmeras usando ORM
                cameras = db.query(Camera).all()
                
                configs = {}
                for camera in cameras:
                    configs[camera.id] = {
                        'id': camera.id,
                        'name': camera.name,
                        'url': camera.url,
                        'type': camera.type,
                        'status': camera.status,
                        'fps_limit': camera.fps_limit if camera.fps_limit else 10,
                        'enabled': camera.status == 'active',
                        'created_at': camera.created_at.isoformat() if camera.created_at and hasattr(camera.created_at, 'isoformat') else str(camera.created_at) if camera.created_at else None,
                        'updated_at': camera.updated_at.isoformat() if camera.updated_at and hasattr(camera.updated_at, 'isoformat') else str(camera.updated_at) if camera.updated_at else None
                    }
                
                logger.info(f"[DEBUG] Câmeras carregadas do banco: {len(configs)}")
                for cam_id, cam_config in configs.items():
                    logger.info(f"[DEBUG] Câmera: {cam_id} -> {cam_config['name']} ({cam_config['status']})")
                
                return configs
                
        except Exception as e:
            logger.error(f"Erro ao obter configurações do banco: {e}")
            import traceback
            logger.error(f"Traceback completo: {traceback.format_exc()}")
            return {}
    
    def _calculate_config_hash(self, configs: Dict[str, Dict[str, Any]]) -> str:
        """Calcular hash das configurações para detectar mudanças"""
        import hashlib
        
        # Criar string ordenada das configurações
        config_str = json.dumps(configs, sort_keys=True, default=str)
        
        # Calcular hash
        return hashlib.md5(config_str.encode()).hexdigest()
    
    async def _apply_config_changes(self, new_configs: Dict[str, Dict[str, Any]]) -> bool:
        """Aplicar mudanças de configuração - MODO DISTRIBUÍDO"""
        try:
            # Camera worker agora é externo - sem aplicação direta de mudanças
            logger.info("[PROCESSING] Config changes detected - external camera worker will sync independently")
            
            # Em modo distribuído, apenas logamos as mudanças
            # O worker externo (MSYS2) deve implementar sua própria sincronização
            current_cameras = set()  # Não temos acesso direto ao worker externo
            new_cameras = set(new_configs.keys())
            
            # Câmeras para adicionar (log apenas)
            cameras_to_add = new_cameras - current_cameras
            
            # Câmeras para remover (log apenas)  
            cameras_to_remove = current_cameras - new_cameras
            
            # Log das mudanças para o worker externo
            cameras_to_update = current_cameras & new_cameras
            
            logger.info(f"Mudanças detectadas: +{len(cameras_to_add)} -{len(cameras_to_remove)} ~{len(cameras_to_update)}")
            
            # Log de mudanças para o worker externo (MSYS2)
            if cameras_to_remove:
                logger.info(f"📝 Câmeras para remover (worker externo): {list(cameras_to_remove)}")
            
            if cameras_to_add:
                logger.info(f"📝 Novas câmeras para adicionar (worker externo): {list(cameras_to_add)}")
                for camera_id in cameras_to_add:
                    config = new_configs[camera_id]
                    logger.info(f"📝 Config da nova câmera {camera_id}: {config.get('name', 'N/A')}")
            
            # Em modo distribuído, não aplicamos mudanças diretamente
            # O worker externo deve consultar a API para obter configurações atualizadas
            
            return True  # Sempre retorna sucesso em modo distribuído
            
        except Exception as e:
            logger.error(f"Erro ao aplicar mudanças de configuração: {e}")
            return False
    
    def _has_significant_changes(self, old_config: Dict[str, Any], new_config: Dict[str, Any]) -> bool:
        """Verificar se houve mudanças significativas na configuração"""
        significant_fields = ['url', 'type', 'fps_limit', 'enabled']
        
        for field in significant_fields:
            if old_config.get(field) != new_config.get(field):
                return True
        
        return False
    
    async def force_sync(self) -> bool:
        """Forçar sincronização imediata - MODO DISTRIBUÍDO"""
        logger.info("[PROCESSING] Forçando sincronização de configurações (modo distribuído)")
        # Em modo distribuído, apenas triggamos a sincronização local
        return await self.sync_camera_configs()
    
    async def get_sync_status(self) -> Dict[str, Any]:
        """Obter status da sincronização - MODO DISTRIBUÍDO"""
        return {
            'is_running': self.is_running,
            'last_sync': self.last_sync.isoformat() if self.last_sync else None,
            'sync_interval': self.sync_interval,
            'mode': 'distributed',
            'total_cameras': len(self.camera_configs),
            'active_cameras': len([c for c in self.camera_configs.values() if c.get('enabled', False)]),
            'config_hash': self.last_config_hash
        }
    
    async def update_camera_config(self, camera_id: str, config: Dict[str, Any]) -> bool:
        """Atualizar configuração de câmera específica"""
        try:
            # Atualizar no banco
            from app.database.database import get_db
            async with get_db() as db:
                from sqlalchemy import text
                db.execute(
                    text("""
                    UPDATE cameras 
                    SET name = :name, url = :url, type = :type, status = :status, 
                    fps_limit = :fps_limit, updated_at = :updated_at
                    WHERE id = :id
                    """),
                    {
                        "name": config['name'],
                        "url": config['url'],
                        "type": config['type'],
                        "status": 'active' if config.get('enabled', False) else 'inactive',
                        "fps_limit": config.get('fps_limit', 10),
                        "updated_at": datetime.now(),
                        "id": camera_id
                    }
                )
                db.commit()
            
            # Forçar sincronização
            return await self.force_sync()
            
        except Exception as e:
            logger.error(f"Erro ao atualizar configuração da câmera {camera_id}: {e}")
            return False
    
    async def add_camera_config(self, config: Dict[str, Any]) -> bool:
        """Adicionar nova configuração de câmera"""
        try:
            camera_id = config['id']
            
            # Inserir no banco
            from app.database.database import get_db
            async with get_db() as db:
                from sqlalchemy import text
                db.execute(
                    text("""
                    INSERT INTO cameras (id, name, url, type, status, fps_limit, created_at, updated_at)
                    VALUES (:id, :name, :url, :type, :status, :fps_limit, :created_at, :updated_at)
                    """),
                    {
                        "id": camera_id,
                        "name": config['name'],
                        "url": config['url'],
                        "type": config['type'],
                        "status": 'active' if config.get('enabled', False) else 'inactive',
                        "fps_limit": config.get('fps_limit', 10),
                        "created_at": datetime.now(),
                        "updated_at": datetime.now()
                    }
                )
                db.commit()
            
            # Forçar sincronização
            return await self.force_sync()
            
        except Exception as e:
            logger.error(f"Erro ao adicionar configuração de câmera: {e}")
            return False
    
    async def remove_camera_config(self, camera_id: str) -> bool:
        """Remover configuração de câmera"""
        try:
            # Remover do banco
            from app.database.database import get_db
            async with get_db() as db:
                from sqlalchemy import text
                db.execute(text("DELETE FROM cameras WHERE id = :id"), {"id": camera_id})
                db.commit()
            
            # Forçar sincronização
            return await self.force_sync()
            
        except Exception as e:
            logger.error(f"Erro ao remover configuração da câmera {camera_id}: {e}")
            return False


# Instância global do serviço de sincronização
config_sync_service = ConfigSyncService() 