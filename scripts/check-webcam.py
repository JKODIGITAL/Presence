#!/usr/bin/env python3
"""
Script para verificar disponibilidade de webcam
Útil para diagnóstico em ambientes Docker/WSL2
"""

import cv2
import sys
import os
from pathlib import Path

def check_video_devices():
    """Verificar dispositivos de vídeo disponíveis"""
    print("🔍 Verificando dispositivos de vídeo...")
    
    # Verificar dispositivos /dev/video*
    video_devices = []
    for i in range(10):
        device_path = f"/dev/video{i}"
        if os.path.exists(device_path):
            video_devices.append(device_path)
    
    if video_devices:
        print(f"✅ Dispositivos de vídeo encontrados: {video_devices}")
    else:
        print("❌ Nenhum dispositivo de vídeo encontrado em /dev/video*")
    
    return video_devices

def test_opencv_camera(camera_index):
    """Testar abertura de câmera com OpenCV"""
    print(f"🎥 Testando câmera {camera_index}...")
    
    try:
        cap = cv2.VideoCapture(camera_index)
        
        if not cap.isOpened():
            print(f"❌ Não foi possível abrir a câmera {camera_index}")
            return False
        
        # Tentar capturar um frame
        ret, frame = cap.read()
        if ret:
            height, width = frame.shape[:2]
            print(f"✅ Câmera {camera_index} funcionando - Resolução: {width}x{height}")
            cap.release()
            return True
        else:
            print(f"❌ Não foi possível capturar frame da câmera {camera_index}")
            cap.release()
            return False
            
    except Exception as e:
        print(f"❌ Erro ao testar câmera {camera_index}: {e}")
        return False

def check_opencv_backends():
    """Verificar backends disponíveis no OpenCV"""
    print("📚 Backends disponíveis no OpenCV:")
    
    backends = [
        (cv2.CAP_V4L2, "V4L2"),
        (cv2.CAP_GSTREAMER, "GStreamer"),
        (cv2.CAP_FFMPEG, "FFMPEG"),
        (cv2.CAP_DSHOW, "DirectShow"),
    ]
    
    for backend_id, backend_name in backends:
        try:
            cap = cv2.VideoCapture(0, backend_id)
            if cap.isOpened():
                print(f"✅ {backend_name} - Disponível")
                cap.release()
            else:
                print(f"❌ {backend_name} - Não disponível")
        except:
            print(f"❌ {backend_name} - Erro")

def check_docker_environment():
    """Verificar se está rodando em Docker"""
    print("🐳 Verificando ambiente Docker...")
    
    # Verificar se está em container
    if os.path.exists("/.dockerenv"):
        print("✅ Rodando em container Docker")
    else:
        print("❌ Não está rodando em container Docker")
    
    # Verificar permissões de dispositivos
    if os.path.exists("/dev"):
        dev_contents = os.listdir("/dev")
        video_devs = [d for d in dev_contents if d.startswith("video")]
        print(f"📁 Dispositivos de vídeo em /dev: {video_devs if video_devs else 'Nenhum'}")

def show_troubleshooting_tips():
    """Mostrar dicas de resolução de problemas"""
    print("\n🔧 DICAS DE RESOLUÇÃO DE PROBLEMAS:")
    print("="*50)
    
    print("\n📋 Para Windows + WSL2 + Docker:")
    print("1. Certifique-se que a webcam está conectada ao Windows")
    print("2. Verifique se o Docker Desktop está configurado para usar WSL2")
    print("3. Execute: lsusb (para ver dispositivos USB)")
    print("4. Execute: ls -la /dev/video* (para ver dispositivos de vídeo)")
    
    print("\n🐳 Para Docker:")
    print("1. Certifique-se que os dispositivos estão mapeados no docker-compose.yml:")
    print("   devices:")
    print("     - /dev/video0:/dev/video0")
    print("     - /dev/video1:/dev/video1")
    print("2. Use privileged: true no container")
    print("3. Volume: /dev:/dev")
    
    print("\n💻 Para testar manualmente:")
    print("1. docker exec -it presence-camera-worker bash")
    print("2. ls -la /dev/video*")
    print("3. python -c \"import cv2; cap=cv2.VideoCapture(0); print(cap.isOpened())\"")

def main():
    """Função principal"""
    print("🚀 DIAGNÓSTICO DE WEBCAM - Presence System")
    print("="*50)
    
    # Verificar ambiente
    check_docker_environment()
    print()
    
    # Verificar dispositivos
    video_devices = check_video_devices()
    print()
    
    # Verificar backends do OpenCV
    check_opencv_backends()
    print()
    
    # Testar câmeras
    working_cameras = []
    for i in range(5):  # Testar índices 0-4
        if test_opencv_camera(i):
            working_cameras.append(i)
    
    print(f"\n📊 RESUMO:")
    print("="*30)
    print(f"Dispositivos de vídeo encontrados: {len(video_devices)}")
    print(f"Câmeras funcionando: {working_cameras if working_cameras else 'Nenhuma'}")
    
    if not working_cameras:
        print("\n❌ PROBLEMA DETECTADO: Nenhuma câmera funcional encontrada")
        show_troubleshooting_tips()
    else:
        print(f"\n✅ SUCCESS: {len(working_cameras)} câmera(s) funcionando")

if __name__ == "__main__":
    main()