"""
Exemplos de uso do sistema melhorado de mídia
Demonstra como usar RTSP, MP4, webcam e imagens
"""

import asyncio
import requests
import json
from typing import Dict, Any

# URL base do WebRTC Server
WEBRTC_SERVER_URL = "http://127.0.0.1:17236"

async def check_server_status():
    """Verificar se o servidor está rodando"""
    try:
        response = requests.get(f"{WEBRTC_SERVER_URL}/health")
        if response.status_code == 200:
            print("✅ WebRTC Server está rodando")
            return True
        else:
            print(f"❌ Servidor retornou status {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Erro ao conectar ao servidor: {e}")
        return False

def list_supported_formats():
    """Listar formatos suportados"""
    try:
        response = requests.get(f"{WEBRTC_SERVER_URL}/enhanced/media-types")
        if response.status_code == 200:
            formats = response.json()
            print("\n📋 Formatos de mídia suportados:")
            for category, types in formats.items():
                print(f"  {category}: {', '.join(types)}")
        else:
            print(f"❌ Erro ao obter formatos: {response.status_code}")
    except Exception as e:
        print(f"❌ Erro: {e}")

def add_rtsp_camera(camera_id: str, rtsp_url: str, camera_name: str = None):
    """Adicionar câmera RTSP (modo original)"""
    try:
        data = {
            "source": rtsp_url,
            "name": camera_name or f"RTSP Camera {camera_id}",
            "enable_recognition": True,
            "enable_hwaccel": True,
            "target_fps": 30
        }
        
        response = requests.post(
            f"{WEBRTC_SERVER_URL}/enhanced/cameras/{camera_id}",
            json=data
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ RTSP Camera adicionada: {camera_id}")
            print(f"   Media type: {result.get('media_type')}")
            return True
        else:
            print(f"❌ Erro ao adicionar RTSP camera: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Erro: {e}")
        return False

def add_mp4_camera(camera_id: str, mp4_path: str, camera_name: str = None):
    """Adicionar arquivo MP4"""
    try:
        data = {
            "source": mp4_path,
            "name": camera_name or f"MP4 Video {camera_id}",
            "enable_recognition": True,
            "enable_hwaccel": True,
            "target_fps": 30
        }
        
        response = requests.post(
            f"{WEBRTC_SERVER_URL}/enhanced/cameras/{camera_id}",
            json=data
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ MP4 Video adicionado: {camera_id}")
            print(f"   Media type: {result.get('media_type')}")
            print(f"   File: {mp4_path}")
            return True
        else:
            print(f"❌ Erro ao adicionar MP4: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Erro: {e}")
        return False

def add_webcam_camera(camera_id: str, webcam_id: int = 0, camera_name: str = None):
    """Adicionar webcam"""
    try:
        data = {
            "source": str(webcam_id),  # Webcam ID como string
            "name": camera_name or f"Webcam {webcam_id}",
            "enable_recognition": True,
            "enable_hwaccel": False,  # Webcam geralmente não precisa de NVDEC
            "target_fps": 30
        }
        
        response = requests.post(
            f"{WEBRTC_SERVER_URL}/enhanced/cameras/{camera_id}",
            json=data
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Webcam adicionada: {camera_id}")
            print(f"   Media type: {result.get('media_type')}")
            print(f"   Device ID: {webcam_id}")
            return True
        else:
            print(f"❌ Erro ao adicionar webcam: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Erro: {e}")
        return False

def add_image_camera(camera_id: str, image_path: str, camera_name: str = None):
    """Adicionar imagem estática"""
    try:
        data = {
            "source": image_path,
            "name": camera_name or f"Static Image {camera_id}",
            "enable_recognition": True,
            "enable_hwaccel": False,  # Imagem não precisa de hardware decode
            "target_fps": 1  # 1 FPS para imagem estática
        }
        
        response = requests.post(
            f"{WEBRTC_SERVER_URL}/enhanced/cameras/{camera_id}",
            json=data
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Imagem adicionada: {camera_id}")
            print(f"   Media type: {result.get('media_type')}")
            print(f"   File: {image_path}")
            return True
        else:
            print(f"❌ Erro ao adicionar imagem: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Erro: {e}")
        return False

def get_camera_info(camera_id: str):
    """Obter informações detalhadas de uma câmera"""
    try:
        response = requests.get(f"{WEBRTC_SERVER_URL}/enhanced/cameras/{camera_id}/info")
        
        if response.status_code == 200:
            info = response.json()
            print(f"\n📋 Informações da câmera {camera_id}:")
            print(f"   Config: {json.dumps(info.get('config', {}), indent=2)}")
            print(f"   Stats: {json.dumps(info.get('stats', {}), indent=2)}")
            return info
        else:
            print(f"❌ Erro ao obter info: {response.status_code}")
            return None
            
    except Exception as e:
        print(f"❌ Erro: {e}")
        return None

def enable_recording(camera_id: str, output_path: str):
    """Habilitar gravação para uma câmera"""
    try:
        data = {"output_path": output_path}
        response = requests.post(
            f"{WEBRTC_SERVER_URL}/enhanced/cameras/{camera_id}/recording/enable",
            json=data
        )
        
        if response.status_code == 200:
            print(f"✅ Gravação habilitada para {camera_id}: {output_path}")
            return True
        else:
            print(f"❌ Erro ao habilitar gravação: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Erro: {e}")
        return False

def disable_recording(camera_id: str):
    """Desabilitar gravação para uma câmera"""
    try:
        response = requests.post(f"{WEBRTC_SERVER_URL}/enhanced/cameras/{camera_id}/recording/disable")
        
        if response.status_code == 200:
            print(f"✅ Gravação desabilitada para {camera_id}")
            return True
        else:
            print(f"❌ Erro ao desabilitar gravação: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Erro: {e}")
        return False

def get_enhanced_stats():
    """Obter estatísticas do sistema melhorado"""
    try:
        response = requests.get(f"{WEBRTC_SERVER_URL}/enhanced/stats")
        
        if response.status_code == 200:
            stats = response.json()
            print(f"\n📊 Estatísticas do sistema melhorado:")
            print(f"   Tracks ativos: {stats.get('active_tracks', 0)}")
            
            for camera_id, track_stats in stats.get('tracks', {}).items():
                print(f"\n   📷 {camera_id}:")
                print(f"      FPS médio: {track_stats.get('avg_fps', 0):.1f}")
                print(f"      Frames gerados: {track_stats.get('frames_generated', 0)}")
                print(f"      Reconhecimento: {track_stats.get('enable_recognition', False)}")
                
            return stats
        else:
            print(f"❌ Erro ao obter stats: {response.status_code}")
            return None
            
    except Exception as e:
        print(f"❌ Erro: {e}")
        return None

def remove_camera(camera_id: str):
    """Remover uma câmera"""
    try:
        response = requests.delete(f"{WEBRTC_SERVER_URL}/enhanced/cameras/{camera_id}")
        
        if response.status_code == 200:
            print(f"✅ Câmera {camera_id} removida")
            return True
        else:
            print(f"❌ Erro ao remover câmera: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Erro: {e}")
        return False

async def main():
    """Função principal com exemplos"""
    print("🎬 Demonstração do Sistema de Mídia Melhorado")
    print("=" * 50)
    
    # Verificar servidor
    if not await check_server_status():
        print("❌ Servidor WebRTC não está disponível")
        return
    
    # Listar formatos suportados
    list_supported_formats()
    
    print("\n🚀 Exemplos de uso:")
    print("-" * 30)
    
    # Exemplo 1: Adicionar câmera RTSP
    print("\n1. Adicionando câmera RTSP...")
    add_rtsp_camera(
        camera_id="rtsp_cam1",
        rtsp_url="rtsp://wowzaec2demo.streamlock.net/vod/mp4:BigBuckBunny_115k.mp4",
        camera_name="Demo RTSP Stream"
    )
    
    # Exemplo 2: Adicionar arquivo MP4 (se existir)
    print("\n2. Tentando adicionar arquivo MP4...")
    # Substituir pelo caminho real de um arquivo MP4
    mp4_examples = [
        "C:/Users/Public/Videos/sample.mp4",
        "D:/videos/teste.mp4",
        "/home/user/videos/sample.mp4"
    ]
    
    for mp4_path in mp4_examples:
        if add_mp4_camera("mp4_cam1", mp4_path, "MP4 Test Video"):
            break
    else:
        print("   ⚠️ Nenhum arquivo MP4 de exemplo encontrado")
    
    # Exemplo 3: Adicionar webcam
    print("\n3. Tentando adicionar webcam...")
    add_webcam_camera("webcam1", 0, "Webcam Principal")
    
    # Exemplo 4: Adicionar imagem (se existir)
    print("\n4. Tentando adicionar imagem...")
    image_examples = [
        "C:/Users/Public/Pictures/sample.jpg",
        "D:/images/test.png",
        "/home/user/images/sample.jpg"
    ]
    
    for img_path in image_examples:
        if add_image_camera("img1", img_path, "Test Image"):
            break
    else:
        print("   ⚠️ Nenhuma imagem de exemplo encontrada")
    
    # Aguardar um momento para as câmeras inicializarem
    print("\n⏳ Aguardando inicialização...")
    await asyncio.sleep(3)
    
    # Mostrar estatísticas
    print("\n📊 Verificando estatísticas...")
    get_enhanced_stats()
    
    # Exemplo de gravação
    print("\n📹 Exemplo de gravação...")
    enable_recording("rtsp_cam1", "output/rtsp_recording.mp4")
    
    # Aguardar alguns segundos
    print("   ⏳ Gravando por 10 segundos...")
    await asyncio.sleep(10)
    
    # Parar gravação
    disable_recording("rtsp_cam1")
    
    print("\n✨ Demonstração concluída!")
    print("\n💡 Para usar o sistema:")
    print("   1. Inicie o WebRTC Server: python webrtc_worker/vms_webrtc_server_native.py")
    print("   2. Use os endpoints /enhanced/ para adicionar diferentes tipos de mídia")
    print("   3. Conecte o frontend em http://127.0.0.1:17236")

if __name__ == "__main__":
    asyncio.run(main())