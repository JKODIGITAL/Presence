"""Enhanced Camera Model with Performance Metrics and Validation Support

This migration adds comprehensive camera tracking capabilities including:
- Performance metrics (latency, FPS, quality)
- Authentication credentials
- Capabilities detection
- Connection testing results
- Related tables for performance logs and capabilities
"""

from sqlalchemy import text
from alembic import op


def upgrade():
    """Upgrade database with enhanced camera model and related tables"""
    
    # First, let's create the new enhanced camera table
    op.execute(text("""
        CREATE TABLE cameras_new (
            -- Identificação
            id VARCHAR PRIMARY KEY,
            name VARCHAR NOT NULL,
            
            -- Conectividade
            url VARCHAR NOT NULL,
            type VARCHAR DEFAULT 'ip',
            ip_address VARCHAR,
            port INTEGER DEFAULT 554,
            username VARCHAR,
            password VARCHAR,
            stream_path VARCHAR DEFAULT '/Streaming/channels/101',
            
            -- Status e Qualidade
            status VARCHAR DEFAULT 'inactive',
            connection_quality REAL DEFAULT 0.0,
            last_connection_test DATETIME,
            connection_test_result TEXT,
            
            -- Configurações de Vídeo
            fps INTEGER DEFAULT 30,
            resolution_width INTEGER DEFAULT 1280,
            resolution_height INTEGER DEFAULT 720,
            fps_limit INTEGER DEFAULT 5,
            codec VARCHAR,
            
            -- Métricas de Performance (últimas medições)
            actual_fps REAL,
            latency_ms INTEGER,
            packet_loss_percent REAL DEFAULT 0.0,
            bandwidth_mbps REAL,
            
            -- Localização e Metadados
            location VARCHAR,
            description TEXT,
            manufacturer VARCHAR,
            model VARCHAR,
            firmware_version VARCHAR,
            
            -- Capacidades
            has_ptz BOOLEAN DEFAULT FALSE,
            has_audio BOOLEAN DEFAULT FALSE,
            has_recording BOOLEAN DEFAULT FALSE,
            supports_onvif BOOLEAN DEFAULT FALSE,
            
            -- Configurações Avançadas
            config TEXT,  -- JSON
            rtsp_transport VARCHAR DEFAULT 'tcp',
            connection_timeout INTEGER DEFAULT 10,
            reconnect_attempts INTEGER DEFAULT 3,
            
            -- Controle de Atividade
            is_enabled BOOLEAN DEFAULT TRUE,
            auto_reconnect BOOLEAN DEFAULT TRUE,
            last_frame_at DATETIME,
            last_error TEXT,
            error_count INTEGER DEFAULT 0,
            
            -- Timestamps
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """))
    
    # Copy existing camera data if table exists
    op.execute(text("""
        INSERT INTO cameras_new (
            id, name, url, type, fps, resolution_width, resolution_height, 
            fps_limit, location, description, status, last_frame_at, 
            created_at, updated_at
        )
        SELECT 
            id, name, url, type, fps, resolution_width, resolution_height,
            fps_limit, location, description, status, last_frame_at,
            created_at, updated_at
        FROM cameras
        WHERE EXISTS (SELECT 1 FROM sqlite_master WHERE type='table' AND name='cameras')
    """))
    
    # Drop old table if it exists
    op.execute(text("""
        DROP TABLE IF EXISTS cameras
    """))
    
    # Rename new table
    op.execute(text("ALTER TABLE cameras_new RENAME TO cameras"))
    
    # Create indexes for cameras table
    op.execute(text("CREATE INDEX ix_cameras_id ON cameras (id)"))
    op.execute(text("CREATE INDEX ix_cameras_name ON cameras (name)"))
    op.execute(text("CREATE INDEX ix_cameras_status ON cameras (status)"))
    op.execute(text("CREATE INDEX ix_cameras_type ON cameras (type)"))
    
    # Create camera performance logs table
    op.execute(text("""
        CREATE TABLE camera_performance_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            camera_id VARCHAR NOT NULL,
            
            -- Métricas de Performance
            fps_measured REAL,
            latency_ms INTEGER,
            packet_loss_percent REAL DEFAULT 0.0,
            bandwidth_mbps REAL,
            connection_quality REAL,
            
            -- Informações de Rede
            jitter_ms REAL,
            throughput_mbps REAL,
            connection_time_ms INTEGER,
            
            -- Status da Conexão
            connection_success BOOLEAN DEFAULT FALSE,
            error_message TEXT,
            error_type VARCHAR,
            
            -- Informações do Teste
            test_duration_seconds INTEGER DEFAULT 30,
            frames_received INTEGER DEFAULT 0,
            frames_expected INTEGER DEFAULT 0,
            
            -- Timestamp
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            
            FOREIGN KEY (camera_id) REFERENCES cameras (id) ON DELETE CASCADE
        )
    """))
    
    # Create indexes for performance logs
    op.execute(text("CREATE INDEX ix_camera_performance_logs_id ON camera_performance_logs (id)"))
    op.execute(text("CREATE INDEX ix_camera_performance_logs_camera_id ON camera_performance_logs (camera_id)"))
    op.execute(text("CREATE INDEX ix_camera_performance_logs_timestamp ON camera_performance_logs (timestamp)"))
    
    # Create camera capabilities table
    op.execute(text("""
        CREATE TABLE camera_capabilities (
            camera_id VARCHAR PRIMARY KEY,
            
            -- Resoluções Suportadas (JSON)
            supported_resolutions TEXT,  -- JSON array
            supported_codecs TEXT,       -- JSON array
            supported_framerates TEXT,   -- JSON array
            
            -- Capacidades de Hardware
            has_ptz BOOLEAN DEFAULT FALSE,
            has_zoom BOOLEAN DEFAULT FALSE,
            has_focus BOOLEAN DEFAULT FALSE,
            has_iris BOOLEAN DEFAULT FALSE,
            has_audio BOOLEAN DEFAULT FALSE,
            has_motion_detection BOOLEAN DEFAULT FALSE,
            has_night_vision BOOLEAN DEFAULT FALSE,
            has_recording BOOLEAN DEFAULT FALSE,
            
            -- Protocolos Suportados
            supports_onvif BOOLEAN DEFAULT FALSE,
            supports_rtmp BOOLEAN DEFAULT FALSE,
            supports_hls BOOLEAN DEFAULT FALSE,
            supports_webrtc BOOLEAN DEFAULT FALSE,
            
            -- Informações do Dispositivo
            manufacturer VARCHAR,
            model VARCHAR,
            firmware_version VARCHAR,
            hardware_version VARCHAR,
            serial_number VARCHAR,
            mac_address VARCHAR,
            
            -- Limites e Configurações
            max_bitrate_kbps INTEGER,
            min_bitrate_kbps INTEGER,
            max_fps INTEGER,
            min_fps INTEGER,
            
            -- Configurações Avançadas (JSON)
            advanced_settings TEXT,
            
            -- Timestamp da última detecção
            last_capability_check DATETIME DEFAULT CURRENT_TIMESTAMP,
            capability_check_success BOOLEAN DEFAULT FALSE,
            
            FOREIGN KEY (camera_id) REFERENCES cameras (id) ON DELETE CASCADE
        )
    """))
    
    # Create camera connection tests table
    op.execute(text("""
        CREATE TABLE camera_connection_tests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            camera_id VARCHAR NOT NULL,
            
            -- Resultado do Teste
            test_type VARCHAR NOT NULL,  -- basic, full, performance, stress
            success BOOLEAN DEFAULT FALSE,
            
            -- Detalhes do Teste
            connection_time_ms INTEGER,
            first_frame_time_ms INTEGER,
            test_duration_seconds INTEGER DEFAULT 10,
            
            -- Resultados Específicos
            authentication_success BOOLEAN,
            stream_available BOOLEAN,
            codec_supported BOOLEAN,
            resolution_confirmed BOOLEAN,
            
            -- Métricas Coletadas
            measured_fps REAL,
            measured_resolution_width INTEGER,
            measured_resolution_height INTEGER,
            measured_bitrate_kbps INTEGER,
            
            -- Diagnóstico de Erros
            error_message TEXT,
            error_type VARCHAR,  -- timeout, auth_failed, network_error, codec_error
            suggested_fix TEXT,
            
            -- Configurações Testadas
            tested_url VARCHAR NOT NULL,
            tested_settings TEXT,  -- JSON
            
            -- Timestamp
            test_started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            test_completed_at DATETIME,
            
            FOREIGN KEY (camera_id) REFERENCES cameras (id) ON DELETE CASCADE
        )
    """))
    
    # Create indexes for connection tests
    op.execute(text("CREATE INDEX ix_camera_connection_tests_id ON camera_connection_tests (id)"))
    op.execute(text("CREATE INDEX ix_camera_connection_tests_camera_id ON camera_connection_tests (camera_id)"))
    op.execute(text("CREATE INDEX ix_camera_connection_tests_test_started_at ON camera_connection_tests (test_started_at)"))


def downgrade():
    """Downgrade database to previous camera model"""
    
    # Create simplified camera table (original schema)
    op.execute(text("""
        CREATE TABLE cameras_old (
            id VARCHAR PRIMARY KEY,
            name VARCHAR NOT NULL,
            url VARCHAR NOT NULL,
            type VARCHAR DEFAULT 'ip',
            fps INTEGER DEFAULT 30,
            resolution_width INTEGER DEFAULT 1280,
            resolution_height INTEGER DEFAULT 720,
            fps_limit INTEGER DEFAULT 5,
            location VARCHAR,
            description TEXT,
            status VARCHAR DEFAULT 'inactive',
            last_frame_at DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """))
    
    # Copy essential data back
    op.execute(text("""
        INSERT INTO cameras_old (
            id, name, url, type, fps, resolution_width, resolution_height,
            fps_limit, location, description, status, last_frame_at,
            created_at, updated_at
        )
        SELECT 
            id, name, url, type, fps, resolution_width, resolution_height,
            fps_limit, location, description, status, last_frame_at,
            created_at, updated_at
        FROM cameras
    """))
    
    # Drop enhanced tables
    op.execute(text("DROP TABLE IF EXISTS camera_connection_tests"))
    op.execute(text("DROP TABLE IF EXISTS camera_capabilities"))
    op.execute(text("DROP TABLE IF EXISTS camera_performance_logs"))
    op.execute(text("DROP TABLE IF EXISTS cameras"))
    
    # Rename old table back
    op.execute(text("ALTER TABLE cameras_old RENAME TO cameras"))
    
    # Recreate basic indexes
    op.execute(text("CREATE INDEX ix_cameras_id ON cameras (id)"))