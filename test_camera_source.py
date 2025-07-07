#!/usr/bin/env python3
"""
Teste para verificar se o pipeline está funcionando com uma fonte de teste
"""

import subprocess
import sys

def test_pipeline():
    """Testar pipeline com videotestsrc"""
    
    # Pipeline de teste simples
    pipeline = """
    gst-launch-1.0 -v videotestsrc pattern=ball ! 
    video/x-raw,width=640,height=480,framerate=1/1 ! 
    videoconvert ! 
    autovideosink
    """
    
    print("🧪 Testando pipeline GStreamer com fonte de teste...")
    print(f"Pipeline: {pipeline}")
    
    try:
        # Executar pipeline
        result = subprocess.run(pipeline, shell=True, capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0:
            print("✅ Pipeline de teste funcionou!")
        else:
            print(f"❌ Pipeline falhou: {result.stderr}")
            
    except subprocess.TimeoutExpired:
        print("✅ Pipeline rodou por 10 segundos (sucesso)")
    except Exception as e:
        print(f"❌ Erro: {e}")

def suggest_test_camera():
    """Sugerir como adicionar uma câmera de teste"""
    
    print("\n📷 Para adicionar uma câmera de teste no banco de dados:")
    print("""
    INSERT INTO cameras (
        id, 
        name, 
        url, 
        type, 
        status, 
        fps_limit
    ) VALUES (
        'test-camera-1',
        'Câmera de Teste',
        'test',
        'test',
        'active',
        5
    );
    """)
    
    print("\n🎯 Ou via API:")
    print("""
    curl -X POST http://127.0.0.1:17234/api/v1/cameras/ \\
    -H "Content-Type: application/json" \\
    -d '{
        "name": "Câmera de Teste",
        "url": "test",
        "type": "test",
        "fps_limit": 5
    }'
    """)

if __name__ == "__main__":
    test_pipeline()
    suggest_test_camera()