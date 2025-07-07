"""
Database connection for Camera Worker (sem FastAPI)
"""

import sqlite3
from contextlib import contextmanager
import os

# Caminho do banco - usar o mesmo que a API
# Detectar se estamos no Windows/MSYS2
if os.name == 'nt' or 'MSYSTEM' in os.environ:
    # No Windows/MSYS2, usar caminho absoluto
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    DB_PATH = os.path.join(base_dir, 'app', 'data', 'db', 'presence.db')
else:
    # No Linux/WSL, usar caminho relativo
    DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'db', 'presence.db')

print(f"[Camera Worker] Sistema: {os.name}, MSYSTEM: {os.environ.get('MSYSTEM', 'N/A')}")
print(f"[Camera Worker] Usando banco de dados: {DB_PATH}")
print(f"[Camera Worker] Banco existe: {os.path.exists(DB_PATH)}")

@contextmanager
def get_db_sync():
    """Get database connection without FastAPI dependency"""
    # Debug: verificar caminho absoluto
    abs_path = os.path.abspath(DB_PATH)
    if not os.path.exists(abs_path):
        print(f"[Camera Worker] ❌ ERRO: Banco não encontrado em: {abs_path}")
        raise FileNotFoundError(f"Banco de dados não encontrado: {abs_path}")
    
    conn = sqlite3.connect(abs_path)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.cursor()
        yield cursor
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

# Classe Camera simples para compatibilidade
class Camera:
    def __init__(self, row):
        self.id = row['id']
        self.name = row['name']
        self.url = row['url']
        self.type = row['type'] if 'type' in row.keys() else 'rtsp'
        self.status = row['status'] if 'status' in row.keys() else 'active'
        self.fps_limit = row['fps_limit'] if 'fps_limit' in row.keys() else 10
        self.config = row['config'] if 'config' in row.keys() else None

# Mock do models para compatibilidade
class models:
    Camera = Camera