"""Migration to allow NULL values in recognition_logs.person_id"""

from sqlalchemy import text
from alembic import op


def upgrade():
    """Upgrade database"""
    # SQLite não suporta ALTER COLUMN, então precisamos recriar a tabela
    op.execute(text("""
        CREATE TABLE recognition_logs_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            person_id VARCHAR,
            camera_id VARCHAR NOT NULL,
            confidence FLOAT NOT NULL,
            bounding_box TEXT,
            frame_path VARCHAR,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            is_unknown BOOLEAN DEFAULT FALSE
        )
    """))
    
    # Copiar dados da tabela antiga
    op.execute(text("""
        INSERT INTO recognition_logs_new 
        SELECT * FROM recognition_logs
    """))
    
    # Remover tabela antiga
    op.execute(text("DROP TABLE recognition_logs"))
    
    # Renomear nova tabela
    op.execute(text("ALTER TABLE recognition_logs_new RENAME TO recognition_logs"))
    
    # Recriar índices
    op.execute(text("CREATE INDEX ix_recognition_logs_id ON recognition_logs (id)"))


def downgrade():
    """Downgrade database"""
    # Reverter para NOT NULL
    op.execute(text("""
        CREATE TABLE recognition_logs_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            person_id VARCHAR NOT NULL,
            camera_id VARCHAR NOT NULL,
            confidence FLOAT NOT NULL,
            bounding_box TEXT,
            frame_path VARCHAR,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            is_unknown BOOLEAN DEFAULT FALSE
        )
    """))
    
    # Copiar dados, convertendo NULL para um valor padrão
    op.execute(text("""
        INSERT INTO recognition_logs_new 
        SELECT 
            id,
            COALESCE(person_id, 'unknown_' || CAST(strftime('%s', timestamp) as TEXT)) as person_id,
            camera_id,
            confidence,
            bounding_box,
            frame_path,
            timestamp,
            is_unknown
        FROM recognition_logs
    """))
    
    # Remover tabela antiga
    op.execute(text("DROP TABLE recognition_logs"))
    
    # Renomear nova tabela
    op.execute(text("ALTER TABLE recognition_logs_new RENAME TO recognition_logs"))
    
    # Recriar índices
    op.execute(text("CREATE INDEX ix_recognition_logs_id ON recognition_logs (id)")) 