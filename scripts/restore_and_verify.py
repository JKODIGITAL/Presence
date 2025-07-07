#!/usr/bin/env python3
"""
Script para verificar e restaurar possíveis problemas no projeto
"""

import os
import sys
from pathlib import Path

def check_file_integrity():
    """Verificar integridade dos arquivos principais"""
    print("🔍 Verificando integridade dos arquivos...")
    
    # Arquivos críticos que devem existir
    critical_files = [
        "app/api/main.py",
        "app/camera_worker/main.py", 
        "app/camera_worker/gstreamer_worker.py",
        "app/camera_worker/performance_worker.py",
        "app/core/performance/camera_worker.py",
        "app/core/performance/recognition_engine.py",
        "app/core/performance/manager.py",
        "app/core/performance/pipeline_factory.py",
        "docker-compose.yml",
        "CLAUDE.md",
    ]
    
    missing_files = []
    corrupted_files = []
    
    for file_path in critical_files:
        full_path = Path(file_path)
        
        if not full_path.exists():
            missing_files.append(file_path)
            print(f"❌ Arquivo ausente: {file_path}")
            continue
            
        # Verificar se arquivo tem conteúdo
        try:
            content = full_path.read_text()
            if len(content.strip()) == 0:
                corrupted_files.append(file_path)
                print(f"⚠️ Arquivo vazio: {file_path}")
            elif len(content) < 100:  # Muito pequeno
                corrupted_files.append(file_path)
                print(f"⚠️ Arquivo suspeito (muito pequeno): {file_path}")
            else:
                print(f"✅ Arquivo OK: {file_path}")
        except Exception as e:
            corrupted_files.append(file_path)
            print(f"❌ Erro ao ler arquivo {file_path}: {e}")
    
    return missing_files, corrupted_files

def check_import_issues():
    """Verificar problemas de importação"""
    print("\n🐍 Verificando problemas de importação...")
    
    import_tests = [
        ("from app.core.config import settings", "Settings"),
        ("from app.core.performance.manager import PerformanceManager", "PerformanceManager"),
        ("from app.camera_worker.performance_worker import PerformanceWorkerMain", "PerformanceWorkerMain"),
        ("from app.api.main import app", "FastAPI App"),
    ]
    
    issues = []
    
    for import_code, description in import_tests:
        try:
            exec(import_code)
            print(f"✅ Import OK: {description}")
        except Exception as e:
            issues.append((description, str(e)))
            print(f"❌ Import ERROR: {description} - {e}")
    
    return issues

def check_docker_config():
    """Verificar configuração Docker"""
    print("\n🐳 Verificando configuração Docker...")
    
    compose_file = Path("docker-compose.yml")
    
    if not compose_file.exists():
        print("❌ docker-compose.yml não encontrado")
        return False
    
    try:
        content = compose_file.read_text()
        
        # Verificar elementos críticos
        checks = [
            ("USE_PERFORMANCE_WORKER=true", "Performance worker habilitado"),
            ("USE_GPU=true", "GPU habilitada"),
            ("presence-camera-worker", "Camera worker service"),
            ("presence-recognition-worker", "Recognition worker service"),
            ("presence-api", "API service"),
        ]
        
        for check, description in checks:
            if check in content:
                print(f"✅ {description}")
            else:
                print(f"⚠️ Pode estar faltando: {description}")
        
        return True
        
    except Exception as e:
        print(f"❌ Erro ao verificar docker-compose.yml: {e}")
        return False

def check_performance_pipeline():
    """Verificar se o pipeline de performance está configurado"""
    print("\n⚡ Verificando pipeline de performance...")
    
    # Verificar se todos os módulos de performance existem
    performance_modules = [
        "app/core/performance/__init__.py",
        "app/core/performance/camera_worker.py",
        "app/core/performance/recognition_engine.py", 
        "app/core/performance/manager.py",
        "app/core/performance/pipeline_factory.py",
    ]
    
    missing = []
    for module in performance_modules:
        if not Path(module).exists():
            missing.append(module)
            print(f"❌ Módulo ausente: {module}")
        else:
            print(f"✅ Módulo OK: {module}")
    
    return len(missing) == 0

def suggest_fixes(missing_files, corrupted_files, import_issues):
    """Sugerir correções"""
    print("\n🔧 SUGESTÕES DE CORREÇÃO:")
    print("=" * 50)
    
    if missing_files:
        print("\n📄 Arquivos ausentes:")
        for file in missing_files:
            print(f"  - {file}")
        print("  Solução: Re-executar git checkout ou restaurar backup")
    
    if corrupted_files:
        print("\n⚠️ Arquivos corrompidos:")
        for file in corrupted_files:
            print(f"  - {file}")
        print("  Solução: Restaurar do git ou backup")
    
    if import_issues:
        print("\n🐍 Problemas de importação:")
        for desc, error in import_issues:
            print(f"  - {desc}: {error}")
        print("  Solução: Verificar PYTHONPATH e dependências")
    
    print("\n🚀 Para restaurar completamente:")
    print("1. git status  # Ver arquivos modificados")
    print("2. git checkout -- <arquivo>  # Restaurar arquivo específico")
    print("3. git reset --hard HEAD  # Restaurar tudo (CUIDADO!)")
    print("4. ./scripts/build_and_verify.sh  # Verificar sistema")

def main():
    """Função principal"""
    print("🔍 VERIFICAÇÃO E DIAGNÓSTICO DO SISTEMA")
    print("=" * 60)
    
    # Verificar integridade dos arquivos
    missing_files, corrupted_files = check_file_integrity()
    
    # Verificar importações
    import_issues = check_import_issues()
    
    # Verificar Docker
    docker_ok = check_docker_config()
    
    # Verificar pipeline de performance
    performance_ok = check_performance_pipeline()
    
    # Resumo
    print("\n" + "=" * 60)
    print("📋 RESUMO DO DIAGNÓSTICO")
    print("=" * 60)
    
    total_issues = len(missing_files) + len(corrupted_files) + len(import_issues)
    
    if total_issues == 0 and docker_ok and performance_ok:
        print("\n🎉 SISTEMA OK!")
        print("✅ Todos os arquivos estão íntegros")
        print("✅ Importações funcionando")
        print("✅ Docker configurado")
        print("✅ Pipeline de performance OK")
        print("\n🚀 Sistema pronto para uso!")
    else:
        print(f"\n⚠️ {total_issues} problemas encontrados")
        print(f"   Arquivos ausentes: {len(missing_files)}")
        print(f"   Arquivos corrompidos: {len(corrupted_files)}")
        print(f"   Problemas de import: {len(import_issues)}")
        print(f"   Docker OK: {docker_ok}")
        print(f"   Performance Pipeline OK: {performance_ok}")
        
        suggest_fixes(missing_files, corrupted_files, import_issues)
    
    return total_issues == 0 and docker_ok and performance_ok

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)