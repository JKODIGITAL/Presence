#!/usr/bin/env python3
"""
Script para migrar banco de dados adicionando campo detection_enabled
"""

import sys
import os

# Adicionar o diretório raiz ao path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database.database import get_db_sync
from app.database.migrations.add_detection_enabled import upgrade_database
from loguru import logger

def main():
    """Executar migração do banco de dados"""
    try:
        logger.info("🚀 Iniciando migração para adicionar campo detection_enabled...")
        
        # Obter sessão do banco
        db_gen = get_db_sync()
        db = next(db_gen)
        
        # Executar migração
        upgrade_database(db)
        
        logger.info("✅ Migração concluída com sucesso!")
        
    except Exception as e:
        logger.error(f"❌ Erro na migração: {e}")
        sys.exit(1)
    
    finally:
        try:
            db.close()
        except:
            pass

if __name__ == "__main__":
    main()