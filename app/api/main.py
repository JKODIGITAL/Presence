"""
Presence API - Sistema de Reconhecimento Facial
Main FastAPI Application
"""

import os
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from loguru import logger
import uvicorn
import asyncio
import time
import traceback

# PYTHONPATH is set in Docker container, no manual path manipulation needed

from app.database import models, database
from app.api.endpoints import people, cameras, recognition, unknown, system, websocket, webrtc_proxy, unknown_config
from app.api.middleware.rate_limiter import rate_limit_middleware
from app.core.config import settings
from app.core.recognition_engine import RecognitionEngine
from app.api.services.config_sync_service import config_sync_service

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerenciamento do ciclo de vida da aplicação"""
    logger.info("[ROCKET] Iniciando Presence API...")
    
    # Inicializar banco de dados
    await database.init_database()
    logger.info("[OK] Banco de dados inicializado")
    
    # NOVO: API não precisa mais do Recognition Engine (processo externo)
    # Apenas marcar que estamos em modo distribuído
    app.state.recognition_engine = None
    logger.info("[OK] API em modo distribuído - Recognition Engine é processo externo")
    
    # NOTA: Recognition Engine e Camera Worker rodam em processos separados
    # API agora funciona apenas como interface REST
    logger.info("📷 API funcionando em modo distribuído (Camera Worker e Recognition Worker externos)")
    
    # Iniciar sincronização de configurações
    await config_sync_service.start_sync()
    logger.info("Sincronização de configurações iniciada")
    
    logger.info("[SUCCESS] Presence API inicializado com sucesso!")
    
    yield
    
    # Cleanup
    logger.info("[PROCESSING] Finalizando Presence API...")
    
    # Cleanup Recognition Engine se existir
    if hasattr(app.state, 'recognition_engine') and app.state.recognition_engine:
        try:
            await app.state.recognition_engine.cleanup()
        except Exception as e:
            logger.error(f"Erro na limpeza do Recognition Engine: {e}")
    
    await database.close_database()
    logger.info("[OK] Presence API finalizado")


# Criar aplicação FastAPI
app = FastAPI(
    title="Presence API",
    description="Sistema Profissional de Reconhecimento Facial",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Permitir todas as origens por padrão
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Adicionar middleware de compressão
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Adicionar rate limiting
app.middleware("http")(rate_limit_middleware)

# Middleware para registro de requisições e performance (otimizado)
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Registrar requisições e tempos de resposta com filtros"""
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    
    # Log apenas requisições lentas (>1s) ou com erro
    if process_time > 1.0 or response.status_code >= 400:
        logger.warning(f"Slow/Error request {request.method} {request.url.path} "
                      f"completed in {process_time:.4f}s (status: {response.status_code})")
    
    return response

# Middleware para tratamento de exceções
@app.middleware("http")
async def handle_exceptions(request: Request, call_next):
    """Tratar exceções globalmente"""
    try:
        return await call_next(request)
    except Exception as e:
        logger.error(f"Erro na requisição {request.method} {request.url.path}: {str(e)}")
        logger.error(traceback.format_exc())
        return JSONResponse(
            status_code=500,
            content={"detail": str(e)}
        )

# Servir arquivos estáticos
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

# Servir arquivos de uploads (imagens de pessoas)
uploads_dir = os.path.join("..", "data", "uploads")
if os.path.exists(uploads_dir):
    app.mount("/data/uploads", StaticFiles(directory=uploads_dir), name="uploads")

# Incluir routers
app.include_router(people.router, prefix="/api/v1/people", tags=["People"])
app.include_router(cameras.router, prefix="/api/v1/cameras", tags=["Cameras"])
app.include_router(recognition.router, prefix="/api/v1/recognition", tags=["Recognition"])
app.include_router(unknown.router, prefix="/api/v1/unknown", tags=["Unknown"])
app.include_router(unknown_config.router, prefix="/api/v1/unknown-detection", tags=["Unknown Detection Config"])
app.include_router(system.router, prefix="/api/v1/system", tags=["System"])
app.include_router(webrtc_proxy.router, prefix="/api/v1/webrtc", tags=["WebRTC"])
app.include_router(websocket.router, tags=["WebSocket"])
# Routers comentados - módulos não existem
# app.include_router(streams.router, prefix="/api/v1/streams", tags=["Streams"])
# app.include_router(unknown_people.router, prefix="/api/v1/unknown", tags=["Unknown People"])
# app.include_router(stats.router, prefix="/api/v1/stats", tags=["Stats"])
# app.include_router(admin.router, prefix="/api/v1/admin", tags=["Admin"])

@app.get("/")
async def root():
    """Endpoint raiz da API"""
    return {
        "message": "Presence API - Sistema de Reconhecimento Facial",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs"
    }

@app.get("/health")
async def health_check():
    """Health check endpoint otimizado"""
    # Health check ultra-rápido - apenas verificar se API está viva
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "api": "running"
    }

@app.get("/health/detailed")
async def detailed_health_check():
    """Health check detalhado (mais lento)"""
    try:
        # Verificar status do banco de dados
        db_status = await database.check_health()
        
        # Recognition Engine agora é externo - não verificar aqui
        engine_status = True  # Assume que Recognition Worker está rodando externamente
        
        # Camera Worker agora é externo (MSYS2)
        worker_status = True  # Assume que está funcionando externamente
        
        # Verificar status da sincronização
        sync_status = await config_sync_service.get_sync_status()
        
        # Determinar status geral
        if db_status and engine_status and worker_status and sync_status:
            status = "healthy"
        elif db_status and engine_status and worker_status:
            status = "degraded"  # API funciona mas sem reconhecimento
        else:
            status = "unhealthy"
        
        return {
            "status": status,
            "database": "ok" if db_status else "error",
            "recognition_worker": "external" if engine_status else "error",
            "camera_worker": "external" if worker_status else "error",
            "sync": sync_status,
            "timestamp": models.get_current_timestamp()
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "database": "error",
            "recognition_worker": "error",
            "camera_worker": "error",
            "sync": "error",
            "error": str(e),
            "timestamp": models.get_current_timestamp()
        }

@app.get("/api/v1/info")
async def get_api_info():
    """Informações da API"""
    return {
        "name": "Presence API",
        "version": "1.0.0",
        "description": "Sistema Profissional de Reconhecimento Facial",
        "features": [
            "Reconhecimento facial em tempo real",
            "Gestão de pessoas e câmeras",
            "Logs de reconhecimento",
            "Relatórios e estatísticas",
            "API RESTful completa"
        ],
        "endpoints": {
            "people": "/api/v1/people",
            "cameras": "/api/v1/cameras", 
            "recognition": "/api/v1/recognition",
            "unknown": "/api/v1/unknown",
            "system": "/api/v1/system"
        }
    }

@app.get("/api/status")
async def get_system_status():
    """Obter status completo do sistema"""
    try:
        # Status do worker (agora externo)
        worker_stats = {"status": "external_msys2", "active": True}
        
        # Status da sincronização
        sync_status = await config_sync_service.get_sync_status()
        
        return {
            "api_status": "running",
            "worker": worker_stats,
            "sync": sync_status,
            "timestamp": asyncio.get_event_loop().time()
        }
        
    except Exception as e:
        logger.error(f"Erro ao obter status do sistema: {e}")
        raise HTTPException(status_code=500, detail="Erro ao obter status do sistema")

# Para compatibilidade com código legado - rotas sem versão
app.include_router(cameras.router, prefix="/api/cameras", tags=["cameras-legacy"])
app.include_router(people.router, prefix="/api/people", tags=["people-legacy"])
app.include_router(recognition.router, prefix="/api/recognition", tags=["recognition-legacy"])
app.include_router(system.router, prefix="/api/system", tags=["system-legacy"])

if __name__ == "__main__":
    # Configurar logging
    logger.add(
        "logs/api.log",
        rotation="10 MB",
        retention="7 days",
        level="INFO",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{function}:{line} | {message}"
    )
    
    # Executar servidor
    port = int(os.environ.get('API_PORT', 17234))
    host = os.environ.get('API_HOST', "127.0.0.1")
    uvicorn.run(
        "app.api.main:app",
        host=host,
        port=port,
        reload=settings.DEBUG,
        log_level="info"
    )