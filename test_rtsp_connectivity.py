#!/usr/bin/env python3
"""
Teste rápido de conectividade RTSP
"""

import subprocess
import urllib.parse
import socket
import time

def test_rtsp_url(url):
    """Testa conectividade básica com URL RTSP"""
    print(f"🔍 Testando URL RTSP: {url}")
    
    # Parse da URL
    try:
        parsed = urllib.parse.urlparse(url)
        host = parsed.hostname
        port = parsed.port or 554
        
        print(f"📡 Host: {host}")
        print(f"🔌 Porta: {port}")
        
        # Teste de conectividade TCP
        print(f"🔌 Testando conectividade TCP para {host}:{port}...")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        
        result = sock.connect_ex((host, port))
        sock.close()
        
        if result == 0:
            print(f"✅ Conectividade TCP OK")
            return True
        else:
            print(f"❌ Falha na conectividade TCP (código: {result})")
            return False
            
    except Exception as e:
        print(f"❌ Erro ao testar conectividade: {e}")
        return False

def test_with_gstreamer():
    """Teste básico com GStreamer"""
    print("\n🎥 Testando com GStreamer...")
    
    # URLs para testar
    rtsp_url = "rtsp://admin:Extreme%40123@192.168.0.153:554/Streaming/channels/101"
    video_file = "videoplayback.mp4"
    
    # Teste RTSP
    print("\n=== TESTE RTSP ===")
    if test_rtsp_url(rtsp_url):
        print("✅ RTSP parece acessível")
        
        # Teste rápido com gst-launch (se disponível)
        try:
            cmd = [
                "gst-launch-1.0",
                "rtspsrc", f"location={rtsp_url}",
                "latency=200", "timeout=5",
                "!", "fakesink"
            ]
            print(f"🧪 Testando: {' '.join(cmd)}")
            result = subprocess.run(cmd, timeout=10, capture_output=True, text=True)
            
            if result.returncode == 0:
                print("✅ GStreamer conseguiu conectar no RTSP")
            else:
                print(f"❌ GStreamer falhou: {result.stderr}")
                
        except subprocess.TimeoutExpired:
            print("⚠️ GStreamer timeout (pode ser normal se stream estiver funcionando)")
        except FileNotFoundError:
            print("⚠️ gst-launch-1.0 não encontrado")
        except Exception as e:
            print(f"❌ Erro no teste GStreamer: {e}")
    else:
        print("❌ RTSP não está acessível")
    
    # Teste arquivo de vídeo
    print("\n=== TESTE ARQUIVO DE VÍDEO ===")
    import os
    
    if os.path.exists(video_file):
        print(f"✅ Arquivo encontrado: {video_file}")
        
        # Informações do arquivo
        stat = os.stat(video_file)
        print(f"📊 Tamanho: {stat.st_size / (1024*1024):.1f} MB")
        print(f"📅 Modificado: {time.ctime(stat.st_mtime)}")
        
        # Teste GStreamer com arquivo
        try:
            cmd = [
                "gst-launch-1.0",
                "filesrc", f"location={video_file}",
                "!", "decodebin",
                "!", "fakesink"
            ]
            print(f"🧪 Testando: {' '.join(cmd)}")
            result = subprocess.run(cmd, timeout=10, capture_output=True, text=True)
            
            if result.returncode == 0:
                print("✅ GStreamer conseguiu processar o arquivo")
            else:
                print(f"❌ GStreamer falhou: {result.stderr}")
                
        except subprocess.TimeoutExpired:
            print("⚠️ GStreamer timeout (pode ser normal se arquivo estiver sendo processado)")
        except FileNotFoundError:
            print("⚠️ gst-launch-1.0 não encontrado")
        except Exception as e:
            print(f"❌ Erro no teste GStreamer: {e}")
    else:
        print(f"❌ Arquivo não encontrado: {video_file}")
        
        # Listar arquivos MP4 no diretório
        try:
            files = os.listdir(".")
            mp4_files = [f for f in files if f.endswith('.mp4')]
            if mp4_files:
                print(f"📁 Arquivos MP4 encontrados: {mp4_files}")
            else:
                print("📁 Nenhum arquivo MP4 encontrado no diretório atual")
        except Exception as e:
            print(f"❌ Erro ao listar arquivos: {e}")

if __name__ == "__main__":
    print("=== TESTE DE CONECTIVIDADE RTSP E ARQUIVO ===")
    test_with_gstreamer()
    print("\n=== TESTE CONCLUÍDO ===")