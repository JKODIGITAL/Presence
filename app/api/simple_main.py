"""
Versão simplificada da API para resolução de problemas
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
import uvicorn
import sqlite3
import os
from datetime import datetime
from typing import List, Dict, Any, Optional
from fastapi.responses import JSONResponse

# Criar a aplicação
app = FastAPI(
    title="Presence API Simplificada",
    version="1.0.0",
    description="API de acesso ao banco de dados de câmeras"
)

# Adicionar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Adicionar compressão gzip
app.add_middleware(GZipMiddleware, minimum_size=1000)


# Função auxiliar para conectar ao banco SQLite
def get_db_connection():
    """Obter conexão com o banco SQLite"""
    db_path = os.path.join("data", "db", "presence.db")
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Banco de dados não encontrado: {db_path}")
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


@app.get("/")
async def root():
    """Endpoint raiz"""
    return {"status": "ok", "message": "API simplificada funcionando"}


@app.get("/health")
async def health():
    """Verificar saúde da API"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        conn.close()
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        return {"status": "unhealthy", "database": "disconnected", "error": str(e)}


@app.get("/api/cameras")
async def get_cameras(
    skip: int = 0,
    limit: int = 50,
    status: Optional[str] = None
):
    """Listar câmeras com SQL direto"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Construir query SQL básica
        sql = "SELECT id, name, url, type, status, fps, resolution_width, resolution_height, fps_limit, location, description, created_at, updated_at FROM cameras"
        
        # Adicionar filtro se fornecido
        params = []
        if status:
            sql += " WHERE status = ?"
            params.append(status)
        
        # Adicionar paginação
        sql += " LIMIT ? OFFSET ?"
        params.extend([limit, skip])
        
        # Executar consulta
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        
        # Contar totais
        cursor.execute("SELECT COUNT(*) FROM cameras")
        total_count = cursor.fetchone()[0]
        
        # Contar por status
        cursor.execute("SELECT COUNT(*) FROM cameras WHERE status = 'active'")
        active_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM cameras WHERE status = 'inactive'")
        inactive_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM cameras WHERE status = 'error'")
        error_count = cursor.fetchone()[0]
        
        # Converter para lista de dicionários
        cameras = []
        for row in rows:
            camera = dict(row)
            cameras.append(camera)
        
        conn.close()
        
        return {
            "cameras": cameras,
            "total": total_count,
            "active": active_count,
            "inactive": inactive_count,
            "error": error_count
        }
    except Exception as e:
        print(f"Erro ao buscar câmeras: {e}")
        # Retornar resposta vazia em caso de erro
        return {
            "cameras": [],
            "total": 0,
            "active": 0,
            "inactive": 0,
            "error": 0
        }


@app.get("/api/v1/cameras")
async def get_cameras_v1(
    skip: int = 0,
    limit: int = 50,
    status: Optional[str] = None
):
    """Alias para API v1"""
    return await get_cameras(skip, limit, status)


@app.get("/api/system/status")
async def get_system_status():
    """Status do sistema"""
    return {
        "status": "online",
        "version": "1.0.0",
        "uptime": "0h:0m:0s",
        "database": "connected",
        "processing_status": "idle"
    }


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Manipulador global de exceções"""
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc)},
    )


if __name__ == "__main__":
    uvicorn.run("app.api.simple_main:app", host="0.0.0.0", port=17234, reload=True)