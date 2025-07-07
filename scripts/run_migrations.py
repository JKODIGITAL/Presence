"""Script to run database migrations"""

import os
import sys
from pathlib import Path

# Adicionar diretório raiz ao PYTHONPATH
root_dir = Path(__file__).parent.parent
sys.path.append(str(root_dir))

from alembic import command
from alembic.config import Config
from app.core.config import settings

def run_migrations():
    """Run database migrations"""
    try:
        # Garantir que o diretório de migrations existe
        migrations_dir = root_dir / "app" / "db" / "migrations"
        migrations_dir.mkdir(parents=True, exist_ok=True)
        
        # Criar config do Alembic
        alembic_cfg = Config()
        alembic_cfg.set_main_option("script_location", str(root_dir / "app" / "db"))
        alembic_cfg.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
        
        # Executar migração
        command.upgrade(alembic_cfg, "head")
        print("✅ Migrations completed successfully")
        
    except Exception as e:
        print(f"❌ Error running migrations: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_migrations() 