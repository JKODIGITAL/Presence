#!/usr/bin/env python3
"""
Script de Migração para GStreamer - Facilitar a transição do OpenCV para GStreamer
"""

import sys
import os
import asyncio
import shutil
import subprocess
from pathlib import Path
from typing import List, Dict, Any

# Adicionar o diretório raiz ao path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loguru import logger

def check_current_installation():
    """Verificar instalação atual"""
    print("🔍 Verificando instalação atual...")
    
    # Verificar se o OpenCV está sendo usado
    opencv_files = []
    for root, dirs, files in os.walk("app"):
        for file in files:
            if file.endswith('.py'):
                filepath = os.path.join(root, file)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()
                        if 'cv2.VideoCapture' in content:
                            opencv_files.append(filepath)
                except Exception:
                    pass
    
    if opencv_files:
        print(f"⚠️  Encontrados {len(opencv_files)} arquivos usando cv2.VideoCapture:")
        for file in opencv_files:
            print(f"   - {file}")
    else:
        print("✅ Nenhum arquivo usando cv2.VideoCapture encontrado")
    
    return opencv_files

def check_gstreamer_installation():
    """Verificar se o GStreamer está instalado"""
    print("\n🔧 Verificando instalação do GStreamer...")
    
    try:
        import gi
        gi.require_version('Gst', '1.0')
        from gi.repository import Gst
        
        Gst.init(None)
        version = Gst.version_string()
        print(f"✅ GStreamer instalado: {version}")
        return True
        
    except ImportError:
        print("❌ GStreamer não encontrado")
        return False
    except Exception as e:
        print(f"❌ Erro ao inicializar GStreamer: {e}")
        return False

def backup_current_files():
    """Fazer backup dos arquivos atuais"""
    print("\n💾 Fazendo backup dos arquivos atuais...")
    
    backup_dir = Path("backup_opencv_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    backup_dir.mkdir(exist_ok=True)
    
    files_to_backup = [
        "app/camera_worker/main.py",
        "app/api/endpoints/cameras.py",
        "app/api/endpoints/people.py",
        "app/api/services/camera_service.py",
        "scripts/check-webcam.py",
        "requirements.txt",
        "docker/Dockerfile.api"
    ]
    
    for file_path in files_to_backup:
        if os.path.exists(file_path):
            backup_path = backup_dir / file_path
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file_path, backup_path)
            print(f"   ✅ Backup: {file_path}")
    
    print(f"✅ Backup criado em: {backup_dir}")
    return backup_dir

def test_gstreamer_components():
    """Testar componentes GStreamer"""
    print("\n🧪 Testando componentes GStreamer...")
    
    try:
        # Testar serviço GStreamer
        from app.api.services.gstreamer_service import gstreamer_service
        print("✅ Serviço GStreamer carregado")
        
        # Testar criação de pipelines
        webcam_pipeline = gstreamer_service._build_pipeline("0", "webcam")
        rtsp_pipeline = gstreamer_service._build_pipeline("rtsp://test", "ip")
        print("✅ Pipelines GStreamer criados")
        
        # Testar worker GStreamer
        from app.camera_worker.gstreamer_worker import GStreamerCameraManager
        print("✅ Worker GStreamer carregado")
        
        return True
        
    except Exception as e:
        print(f"❌ Erro ao testar componentes GStreamer: {e}")
        return False

def update_docker_compose():
    """Atualizar docker-compose para usar GStreamer"""
    print("\n🐳 Atualizando configuração Docker...")
    
    docker_compose_file = "docker-compose.yml"
    if os.path.exists(docker_compose_file):
        try:
            with open(docker_compose_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Verificar se já tem configurações GStreamer
            if 'GST_DEBUG' not in content:
                # Adicionar variáveis de ambiente GStreamer
                content = content.replace(
                    'environment:',
                    '''environment:
      - GST_DEBUG=2
      - GST_DEBUG_DUMP_DOT_DIR=/tmp/gstreamer-debug'''
                )
                
                with open(docker_compose_file, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                print("✅ Docker Compose atualizado com variáveis GStreamer")
            else:
                print("✅ Docker Compose já configurado para GStreamer")
                
        except Exception as e:
            print(f"⚠️  Erro ao atualizar Docker Compose: {e}")
    else:
        print("⚠️  Arquivo docker-compose.yml não encontrado")

def create_migration_script():
    """Criar script de migração personalizado"""
    print("\n📝 Criando script de migração...")
    
    migration_script = """#!/bin/bash
# Script de Migração para GStreamer
# Execute este script para migrar do OpenCV para GStreamer

echo "🚀 Iniciando migração para GStreamer..."

# 1. Parar serviços atuais
echo "⏹️  Parando serviços atuais..."
docker-compose down

# 2. Reconstruir imagens com GStreamer
echo "🔨 Reconstruindo imagens com GStreamer..."
docker-compose build --no-cache

# 3. Iniciar serviços
echo "▶️  Iniciando serviços..."
docker-compose up -d

# 4. Aguardar inicialização
echo "⏳ Aguardando inicialização..."
sleep 30

# 5. Testar GStreamer
echo "🧪 Testando GStreamer..."
python scripts/test_gstreamer.py

echo "✅ Migração concluída!"
echo "💡 Verifique os logs: docker-compose logs -f"
"""
    
    with open("migrate_gstreamer.sh", 'w') as f:
        f.write(migration_script)
    
    os.chmod("migrate_gstreamer.sh", 0o755)
    print("✅ Script de migração criado: migrate_gstreamer.sh")

def create_rollback_script(backup_dir):
    """Criar script de rollback"""
    print("\n🔄 Criando script de rollback...")
    
    rollback_script = f"""#!/bin/bash
# Script de Rollback - Voltar para OpenCV
# Execute este script se precisar reverter a migração

echo "🔄 Iniciando rollback para OpenCV..."

# 1. Parar serviços
echo "⏹️  Parando serviços..."
docker-compose down

# 2. Restaurar arquivos do backup
echo "📁 Restaurando arquivos do backup..."
cp -r {backup_dir}/* .

# 3. Reconstruir imagens
echo "🔨 Reconstruindo imagens..."
docker-compose build --no-cache

# 4. Iniciar serviços
echo "▶️  Iniciando serviços..."
docker-compose up -d

echo "✅ Rollback concluído!"
"""
    
    with open("rollback_opencv.sh", 'w') as f:
        f.write(rollback_script)
    
    os.chmod("rollback_opencv.sh", 0o755)
    print("✅ Script de rollback criado: rollback_opencv.sh")

def print_migration_guide():
    """Imprimir guia de migração"""
    print("\n📋 Guia de Migração para GStreamer")
    print("=" * 50)
    print("1. ✅ Backup dos arquivos criado")
    print("2. ✅ Componentes GStreamer testados")
    print("3. ✅ Docker atualizado")
    print("4. ✅ Scripts de migração criados")
    print("\n🔄 Para completar a migração:")
    print("   chmod +x migrate_gstreamer.sh")
    print("   ./migrate_gstreamer.sh")
    print("\n🔄 Para reverter (se necessário):")
    print("   chmod +x rollback_opencv.sh")
    print("   ./rollback_opencv.sh")
    print("\n📊 Benefícios da migração:")
    print("   - Maior estabilidade em streams RTSP")
    print("   - Reconexão automática em falhas")
    print("   - Melhor performance e menor latência")
    print("   - Suporte a múltiplos codecs")
    print("\n⚠️  Considerações:")
    print("   - Teste todas as câmeras após a migração")
    print("   - Monitore os logs para problemas")
    print("   - Configure pipelines específicos se necessário")

async def main():
    """Função principal"""
    print("🚀 Migração para GStreamer - Sistema de Câmeras")
    print("=" * 60)
    
    # Verificar instalação atual
    opencv_files = check_current_installation()
    
    # Verificar GStreamer
    if not check_gstreamer_installation():
        print("\n❌ GStreamer não está instalado!")
        print("💡 Instale o GStreamer primeiro:")
        print("   sudo apt-get install gstreamer1.0-tools gstreamer1.0-plugins-base gstreamer1.0-plugins-good")
        print("   pip install PyGObject")
        return
    
    # Fazer backup
    backup_dir = backup_current_files()
    
    # Testar componentes
    if not test_gstreamer_components():
        print("\n❌ Componentes GStreamer com problemas!")
        print("💡 Verifique a implementação dos componentes GStreamer")
        return
    
    # Atualizar Docker
    update_docker_compose()
    
    # Criar scripts
    create_migration_script()
    create_rollback_script(backup_dir)
    
    # Imprimir guia
    print_migration_guide()
    
    print("\n✅ Preparação da migração concluída!")
    print("🎯 Execute ./migrate_gstreamer.sh para completar a migração")

if __name__ == "__main__":
    try:
        from datetime import datetime
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⏹️  Migração interrompida pelo usuário")
    except Exception as e:
        print(f"\n❌ Erro na migração: {e}")
        logger.error(f"Erro na migração: {e}") 