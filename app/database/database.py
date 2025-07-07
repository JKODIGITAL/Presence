"""
Database connection and session management
"""

import sqlite3
import os
import contextlib
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from loguru import logger

from app.core.config import settings

# SQLAlchemy setup com pool otimizado
if "sqlite" in settings.DATABASE_URL:
    # Configuração específica para SQLite
    engine = create_engine(
        settings.DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
        pool_pre_ping=True
    )
else:
    # Configuração para outros bancos (PostgreSQL, etc.)
    engine = create_engine(
        settings.DATABASE_URL,
        echo=False,
        pool_pre_ping=True,
        pool_recycle=300,
        pool_size=5,
        max_overflow=10
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


async def init_database():
    """Inicializar banco de dados"""
    try:
        # Garantir que o diretório existe
        db_dir = os.path.dirname(settings.DATABASE_URL.replace("sqlite:///", ""))
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        
        # Criar tabelas
        from app.database import models
        Base.metadata.create_all(bind=engine)
        
        logger.info("[OK] Banco de dados inicializado")
        return True
    except Exception as e:
        logger.error(f"[ERROR] Erro ao inicializar banco: {e}")
        return False


async def close_database():
    """Fechar conexões do banco"""
    try:
        engine.dispose()
        logger.info("[OK] Conexões do banco fechadas")
    except Exception as e:
        logger.error(f"[ERROR] Erro ao fechar banco: {e}")


async def check_health():
    """Verificar saúde do banco de dados"""
    try:
        from sqlalchemy import text
        db = SessionLocal()
        result = db.execute(text("SELECT 1"))
        db.close()
        return True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return False


@contextlib.asynccontextmanager
async def get_db():
    """Dependency para obter sessão do banco como contexto assíncrono"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextlib.contextmanager
def get_db_sync():
    """Obter sessão do banco de forma síncrona"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_db_dependency():
    """Dependency para FastAPI que retorna sessão síncrona"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()