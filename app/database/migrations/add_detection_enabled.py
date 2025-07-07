"""
Migração para adicionar campo detection_enabled na tabela people
"""

from sqlalchemy import text

def upgrade_database(db_session):
    """Adicionar campo detection_enabled à tabela people"""
    try:
        # Verificar se a coluna já existe
        result = db_session.execute(text("PRAGMA table_info(people)"))
        columns = [column[1] for column in result.fetchall()]
        
        if 'detection_enabled' not in columns:
            # Adicionar coluna detection_enabled
            db_session.execute(text("ALTER TABLE people ADD COLUMN detection_enabled BOOLEAN DEFAULT 1"))
            
            # Atualizar pessoas existentes para ter detection_enabled = True
            db_session.execute(text("UPDATE people SET detection_enabled = 1 WHERE detection_enabled IS NULL"))
            
            db_session.commit()
            print("[OK] Campo detection_enabled adicionado com sucesso à tabela people")
        else:
            print("[WARNING] Campo detection_enabled já existe na tabela people")
            
    except Exception as e:
        db_session.rollback()
        print(f"[ERROR] Erro ao adicionar campo detection_enabled: {e}")
        raise

def downgrade_database(db_session):
    """Remover campo detection_enabled da tabela people"""
    try:
        # SQLite não suporta DROP COLUMN diretamente
        # Esta operação seria mais complexa e não é recomendada
        print("[WARNING] Downgrade não suportado para SQLite - campo detection_enabled mantido")
        
    except Exception as e:
        print(f"[ERROR] Erro no downgrade: {e}")
        raise