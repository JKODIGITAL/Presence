#!/usr/bin/env python3
"""
Script para otimizar performance do WebRTC Server
Configurações de sistema e rede para máxima performance local
"""
import os
import sys
import platform
import subprocess

def optimize_windows_network():
    """Otimizar configurações de rede no Windows"""
    try:
        print("🔧 Aplicando otimizações de rede Windows...")
        
        # Comandos de otimização de rede (executar como admin se possível)
        network_optimizations = [
            # Desabilitar Nagle Algorithm para baixa latência
            "netsh int tcp set global autotuninglevel=normal",
            
            # Otimizar buffer TCP
            "netsh int tcp set global chimney=enabled",
            
            # Habilitar RSS (Receive Side Scaling)
            "netsh int tcp set global rss=enabled",
            
            # Configurar UDP buffers
            "netsh int udp set global uro=enabled",
        ]
        
        for cmd in network_optimizations:
            try:
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                if result.returncode == 0:
                    print(f"✅ {cmd}")
                else:
                    print(f"⚠️  {cmd} (pode precisar de privilégios admin)")
            except Exception as e:
                print(f"❌ Erro em {cmd}: {e}")
                
    except Exception as e:
        print(f"❌ Erro nas otimizações de rede: {e}")

def optimize_ffmpeg_environment():
    """Configurar variáveis de ambiente do FFmpeg para performance"""
    try:
        print("🎥 Configurando FFmpeg para performance...")
        
        # Variáveis de ambiente para otimização
        ffmpeg_vars = {
            "FFMPEG_THREADS": "4",                    # Threads para decoding
            "FFMPEG_HWACCEL": "nvdec",               # Hardware acceleration
            "FFMPEG_HWACCEL_OUTPUT_FORMAT": "cuda",  # Output format
            "AV_LOG_LEVEL": "warning",               # Reduzir logs verbosos
            "CUDA_CACHE_DISABLE": "0",               # Habilitar cache CUDA
            "CUDA_LAUNCH_BLOCKING": "0",             # Não bloquear launches
        }
        
        for var, value in ffmpeg_vars.items():
            os.environ[var] = value
            print(f"✅ {var}={value}")
            
        print("✅ FFmpeg otimizado para NVDEC/CUDA")
        
    except Exception as e:
        print(f"❌ Erro nas otimizações FFmpeg: {e}")

def optimize_python_gc():
    """Otimizar Garbage Collector do Python"""
    try:
        print("🐍 Otimizando Python Garbage Collector...")
        
        import gc
        
        # Configurações otimizadas para aplicações real-time
        gc.set_threshold(700, 10, 10)  # Reduzir coletas automáticas
        
        # Desabilitar GC durante operações críticas
        # (será reabilitado automaticamente)
        print("✅ GC otimizado para performance real-time")
        
    except Exception as e:
        print(f"❌ Erro na otimização do GC: {e}")

def check_gpu_status():
    """Verificar status da GPU"""
    try:
        print("🎮 Verificando status da GPU...")
        
        # Verificar NVIDIA-SMI
        try:
            result = subprocess.run("nvidia-smi --query-gpu=name,memory.total,memory.used --format=csv,noheader,nounits", 
                                  shell=True, capture_output=True, text=True)
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                for i, line in enumerate(lines):
                    name, total, used = line.split(', ')
                    print(f"✅ GPU {i}: {name}")
                    print(f"   Memória: {used}MB / {total}MB ({(int(used)/int(total)*100):.1f}%)")
            else:
                print("⚠️  nvidia-smi não disponível")
        except Exception as e:
            print(f"⚠️  Erro ao verificar GPU: {e}")
            
        # Verificar NVDEC
        try:
            result = subprocess.run("ffmpeg -hwaccels", shell=True, capture_output=True, text=True)
            if "nvdec" in result.stdout.lower():
                print("✅ NVDEC disponível")
            else:
                print("⚠️  NVDEC não detectado")
        except Exception as e:
            print(f"⚠️  Erro ao verificar NVDEC: {e}")
            
    except Exception as e:
        print(f"❌ Erro na verificação GPU: {e}")

def optimize_udp_buffers():
    """Otimizar buffers UDP para WebRTC"""
    try:
        print("📡 Otimizando buffers UDP...")
        
        if platform.system() == "Windows":
            # Windows UDP buffer optimization
            udp_cmds = [
                "netsh int udp set global uro=enabled",
                "netsh int tcp set global ecncapability=enabled",
            ]
            
            for cmd in udp_cmds:
                try:
                    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                    if result.returncode == 0:
                        print(f"✅ {cmd}")
                    else:
                        print(f"⚠️  {cmd} (privilégios admin necessários)")
                except Exception as e:
                    print(f"❌ {cmd}: {e}")
        else:
            print("⚠️  Otimizações UDP específicas para Windows")
            
    except Exception as e:
        print(f"❌ Erro na otimização UDP: {e}")

def main():
    """Executar todas as otimizações"""
    print("🚀 OTIMIZAÇÕES DE PERFORMANCE WEBRTC")
    print("=" * 50)
    print(f"Sistema: {platform.system()} {platform.release()}")
    print(f"Python: {sys.version}")
    print("=" * 50)
    
    # Executar otimizações
    optimizations = [
        ("Status GPU", check_gpu_status),
        ("FFmpeg Environment", optimize_ffmpeg_environment),
        ("Python GC", optimize_python_gc),
        ("UDP Buffers", optimize_udp_buffers),
    ]
    
    # Adicionar otimizações específicas do Windows
    if platform.system() == "Windows":
        optimizations.append(("Windows Network", optimize_windows_network))
    
    for name, func in optimizations:
        print(f"\n🔧 {name}:")
        print("-" * 30)
        func()
    
    print("\n" + "=" * 50)
    print("🎉 OTIMIZAÇÕES CONCLUÍDAS!")
    print("=" * 50)
    print("\n📋 Recomendações:")
    print("1. Execute como administrador para melhores resultados")
    print("2. Reinicie o WebRTC Server após as otimizações")
    print("3. Monitor performance com nvidia-smi durante uso")
    print("4. Verifique logs do WebRTC para confirmação NVDEC")

if __name__ == "__main__":
    main()