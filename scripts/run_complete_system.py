#!/usr/bin/env python3
"""
Script para executar o sistema completo integrado
- API Principal (FastAPI) na porta 9000
- Servidor WebRTC GStreamer na porta 8080  
- Camera Worker para reconhecimento
- Frontend Tauri (se necessário)
"""

import asyncio
import subprocess
import sys
import time
import os
import signal
from pathlib import Path
from typing import List, Optional

# Adicionar app ao path
sys.path.append(str(Path(__file__).parent.parent))

class SystemManager:
    """Gerenciador do sistema completo"""
    
    def __init__(self):
        self.processes: List[subprocess.Popen] = []
        self.running = True
        
    def signal_handler(self, signum, frame):
        """Handler para sinais de parada"""
        print(f"\n🛑 Recebido sinal {signum}, parando sistema...")
        self.stop_all()
        sys.exit(0)
    
    def start_process(self, name: str, cmd: List[str], cwd: Optional[str] = None) -> subprocess.Popen:
        """Iniciar um processo"""
        print(f"🚀 Iniciando {name}...")
        try:
            process = subprocess.Popen(
                cmd,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1
            )
            self.processes.append(process)
            print(f"✅ {name} iniciado (PID: {process.pid})")
            return process
            
        except Exception as e:
            print(f"❌ Erro ao iniciar {name}: {e}")
            raise
    
    def check_dependencies(self):
        """Verificar dependências do sistema"""
        print("🔍 Verificando dependências...")
        
        # Verificar Python 3
        if sys.version_info < (3, 8):
            raise Exception("Python 3.8+ é necessário")
        print("✅ Python 3.8+ encontrado")
        
        # Verificar se está no diretório correto
        if not os.path.exists("app/api/main.py"):
            raise Exception("Execute este script a partir do diretório raiz do projeto")
        print("✅ Diretório do projeto correto")
        
        # Verificar dependências Python básicas
        try:
            import fastapi
            import uvicorn
            import aiohttp
            print("✅ Dependências Python básicas encontradas")
        except ImportError as e:
            print(f"❌ Dependência faltando: {e}")
            print("Execute: pip install -r requirements.txt")
            raise
        
        # Verificar GStreamer (opcional)
        try:
            import gi
            gi.require_version('Gst', '1.0')
            from gi.repository import Gst
            print("✅ GStreamer Python bindings encontrados")
        except ImportError:
            print("⚠️ GStreamer não disponível - WebRTC funcionará em modo básico")
    
    def start_api_server(self):
        """Iniciar servidor da API"""
        cmd = [
            sys.executable, "-m", "uvicorn",
            "app.api.main:app",
            "--host", "0.0.0.0",
            "--port", "17234",
            "--reload"
        ]
        return self.start_process("API Server", cmd)
    
    def start_webrtc_server(self):
        """Iniciar servidor WebRTC"""
        cmd = [
            sys.executable,
            "app/webrtc_worker/gstreamer_webrtc_server.py"
        ]
        return self.start_process("WebRTC Server", cmd)
    
    def start_camera_worker(self):
        """Iniciar Camera Worker"""
        cmd = [
            sys.executable,
            "app/camera_worker/main.py"
        ]
        return self.start_process("Camera Worker", cmd)
    
    def start_recognition_worker(self):
        """Iniciar Recognition Worker"""
        cmd = [
            sys.executable,
            "app/recognition_worker/main.py"
        ]
        return self.start_process("Recognition Worker", cmd)
    
    def start_frontend(self):
        """Iniciar Frontend Tauri (opcional)"""
        if os.path.exists("frontend/package.json"):
            print("🎨 Frontend Tauri encontrado")
            try:
                cmd = ["npm", "run", "tauri", "dev"]
                return self.start_process("Frontend Tauri", cmd, cwd="frontend")
            except Exception as e:
                print(f"⚠️ Não foi possível iniciar o frontend: {e}")
                print("Execute manualmente: cd frontend && npm run tauri dev")
                return None
        else:
            print("⚠️ Frontend não encontrado - pule esta etapa se não necessário")
            return None
    
    def monitor_processes(self):
        """Monitorar processos em execução"""
        print("\n📊 Monitorando processos...")
        print("Pressione Ctrl+C para parar o sistema\n")
        
        process_names = [
            "API Server",
            "WebRTC Server", 
            "Camera Worker",
            "Recognition Worker",
            "Frontend Tauri"
        ]
        
        while self.running:
            alive_count = 0
            for i, process in enumerate(self.processes):
                if process and process.poll() is None:
                    alive_count += 1
                elif process:
                    process_name = process_names[i] if i < len(process_names) else f"Process {i}"
                    print(f"❌ {process_name} parou inesperadamente (código: {process.returncode})")
                    
            print(f"\r🟢 {alive_count}/{len([p for p in self.processes if p])} processos ativos", end="", flush=True)
            time.sleep(2)
    
    def stop_all(self):
        """Parar todos os processos"""
        self.running = False
        print("\n🛑 Parando todos os processos...")
        
        for process in self.processes:
            if process and process.poll() is None:
                try:
                    process.terminate()
                    process.wait(timeout=5)
                    print(f"✅ Processo {process.pid} parado")
                except subprocess.TimeoutExpired:
                    print(f"⚠️ Forçando parada do processo {process.pid}")
                    process.kill()
                except Exception as e:
                    print(f"❌ Erro ao parar processo {process.pid}: {e}")
    
    def show_access_info(self):
        """Mostrar informações de acesso"""
        print("\n" + "="*60)
        print("🎉 SISTEMA PRESENCE INICIADO COM SUCESSO!")
        print("="*60)
        print("📱 ACESSO AO SISTEMA:")
        print("   • API Principal: http://localhost:17234")
        print("   • Documentação API: http://localhost:17234/docs")
        print("   • WebRTC Server: http://localhost:17236")
        print("   • Health Check: http://localhost:17234/health")
        print("\n🔧 ENDPOINTS IMPORTANTES:")
        print("   • Câmeras: http://localhost:17234/api/v1/cameras")
        print("   • Pessoas: http://localhost:17234/api/v1/people")
        print("   • WebRTC Proxy: http://localhost:17234/api/v1/webrtc")
        print("   • Monitor Tempo Real: Frontend Tauri")
        print("\n💡 PRÓXIMOS PASSOS:")
        print("   1. Acesse http://localhost:17234/docs para ver a API")
        print("   2. Configure câmeras através da API")
        print("   3. Use o Frontend para monitoramento em tempo real")
        print("   4. Teste WebRTC em http://localhost:17236/test_client.html")
        print("="*60)
    
    async def run(self):
        """Executar sistema completo"""
        # Configurar handlers de sinal
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
        try:
            print("🎬 INICIANDO SISTEMA PRESENCE")
            print("="*40)
            
            # Verificar dependências
            self.check_dependencies()
            print()
            
            # Aguardar um pouco entre cada serviço
            wait_time = 3
            
            # 1. Iniciar API Server primeiro
            api_process = self.start_api_server()
            print(f"⏳ Aguardando {wait_time}s para API estabilizar...")
            time.sleep(wait_time)
            
            # 2. Iniciar WebRTC Server
            webrtc_process = self.start_webrtc_server()
            print(f"⏳ Aguardando {wait_time}s para WebRTC estabilizar...")
            time.sleep(wait_time)
            
            # 3. Iniciar Camera Worker
            camera_process = self.start_camera_worker()
            print(f"⏳ Aguardando {wait_time}s para Camera Worker estabilizar...")
            time.sleep(wait_time)
            
            # 4. Iniciar Recognition Worker
            recognition_process = self.start_recognition_worker()
            print(f"⏳ Aguardando {wait_time}s para Recognition Worker estabilizar...")
            time.sleep(wait_time)
            
            # 5. Iniciar Frontend (opcional)
            frontend_process = self.start_frontend()
            if frontend_process:
                print(f"⏳ Aguardando {wait_time}s para Frontend estabilizar...")
                time.sleep(wait_time)
            
            # Mostrar informações de acesso
            self.show_access_info()
            
            # Monitorar processos
            self.monitor_processes()
            
        except KeyboardInterrupt:
            print("\n🛑 Interrompido pelo usuário")
        except Exception as e:
            print(f"\n❌ Erro ao iniciar sistema: {e}")
        finally:
            self.stop_all()

def main():
    """Função principal"""
    manager = SystemManager()
    asyncio.run(manager.run())

if __name__ == "__main__":
    main()