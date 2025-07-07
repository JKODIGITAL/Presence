#!/usr/bin/env python3
"""
Diagnóstico completo do sistema de reconhecimento facial
Testa cada componente de forma individual para identificar problemas
"""

import sys
import os
import cv2
import numpy as np
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def test_faiss_gpu():
    """Testa se FAISS GPU está funcionando"""
    print("🧪 Testando FAISS GPU...")
    try:
        import faiss
        print(f"✅ FAISS versão: {faiss.__version__}")
        
        # Testa GPU resources
        res = faiss.StandardGpuResources()
        print("✅ FAISS GPU resources inicializadas")
        
        # Testa índice simples
        d = 512  # dimensão dos embeddings
        index = faiss.IndexFlatL2(d)
        gpu_index = faiss.index_cpu_to_gpu(res, 0, index)
        
        # Testa inserção e busca
        np.random.seed(42)
        xb = np.random.random((100, d)).astype('float32')
        gpu_index.add(xb)
        
        xq = np.random.random((1, d)).astype('float32')
        D, I = gpu_index.search(xq, 1)
        
        print(f"✅ FAISS GPU search funcionando - distância: {D[0][0]:.4f}")
        return True
        
    except Exception as e:
        print(f"❌ FAISS GPU erro: {e}")
        return False

def test_gpu_availability():
    """Testa disponibilidade da GPU"""
    print("\n🧪 Testando GPU...")
    try:
        import torch
        if torch.cuda.is_available():
            print(f"✅ GPU disponível: {torch.cuda.get_device_name(0)}")
            print(f"✅ CUDA versão: {torch.version.cuda}")
            print(f"✅ VRAM disponível: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")
            return True
        else:
            print("❌ GPU não disponível")
            return False
    except Exception as e:
        print(f"❌ Erro ao verificar GPU: {e}")
        return False

def test_onnx_runtime():
    """Testa ONNX Runtime com CUDA"""
    print("\n🧪 Testando ONNX Runtime...")
    try:
        import onnxruntime as ort
        print(f"✅ ONNX Runtime versão: {ort.__version__}")
        
        providers = ort.get_available_providers()
        print(f"✅ Providers disponíveis: {providers}")
        
        if 'CUDAExecutionProvider' in providers:
            print("✅ CUDA Provider disponível")
            return True
        else:
            print("❌ CUDA Provider não disponível")
            return False
            
    except Exception as e:
        print(f"❌ ONNX Runtime erro: {e}")
        return False

def test_insightface():
    """Testa InsightFace modelo"""
    print("\n🧪 Testando InsightFace...")
    try:
        from insightface.app import FaceAnalysis
        
        app = FaceAnalysis(name="antelopev2", providers=["CUDAExecutionProvider", "CPUExecutionProvider"])
        app.prepare(ctx_id=0)
        print("✅ InsightFace modelo carregado")
        
        # Cria imagem de teste
        test_img = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        faces = app.get(test_img)
        print(f"✅ InsightFace processou imagem - {len(faces)} faces detectadas")
        
        return True
        
    except Exception as e:
        print(f"❌ InsightFace erro: {e}")
        return False

def test_recognition_engine():
    """Testa RecognitionEngine completa"""
    print("\n🧪 Testando RecognitionEngine...")
    try:
        from app.core.recognition_engine import RecognitionEngine
        
        # Diretórios necessários
        data_dir = project_root / "data"
        embeddings_dir = data_dir / "embeddings"
        images_dir = data_dir / "images"
        
        # Cria diretórios se não existirem
        embeddings_dir.mkdir(parents=True, exist_ok=True)
        images_dir.mkdir(parents=True, exist_ok=True)
        
        engine = RecognitionEngine(
            embeddings_dir=str(embeddings_dir),
            images_dir=str(images_dir)
        )
        
        print("✅ RecognitionEngine inicializada")
        
        # Testa com imagem vazia
        test_img = np.zeros((112, 112, 3), dtype=np.uint8)
        result = engine.recognize(test_img)
        print(f"✅ RecognitionEngine.recognize() retornou: {result}")
        
        return True
        
    except Exception as e:
        print(f"❌ RecognitionEngine erro: {e}")
        return False

def test_with_real_image():
    """Testa com imagem real se disponível"""
    print("\n🧪 Testando com imagem real...")
    
    # Procura por imagem de teste
    test_paths = [
        project_root / "data" / "test_images" / "test_face.jpg",
        project_root / "test_face.jpg",
        project_root / "app" / "test_face.jpg"
    ]
    
    test_img_path = None
    for path in test_paths:
        if path.exists():
            test_img_path = path
            break
    
    if not test_img_path:
        print("⚠️  Nenhuma imagem de teste encontrada")
        print("   Crie uma imagem test_face.jpg na pasta data/test_images/")
        return False
    
    try:
        from app.core.recognition_engine import RecognitionEngine
        from insightface.app import FaceAnalysis
        
        # Carrega imagem
        img = cv2.imread(str(test_img_path))
        if img is None:
            print(f"❌ Não foi possível carregar imagem: {test_img_path}")
            return False
        
        print(f"✅ Imagem carregada: {img.shape}")
        
        # Detecta faces
        app = FaceAnalysis(name="antelopev2", providers=["CUDAExecutionProvider", "CPUExecutionProvider"])
        app.prepare(ctx_id=0)
        
        faces = app.get(img)
        print(f"✅ Faces detectadas: {len(faces)}")
        
        if len(faces) == 0:
            print("⚠️  Nenhuma face detectada na imagem")
            return False
        
        # Testa embedding
        face = faces[0]
        embedding = face.embedding
        print(f"✅ Embedding gerado: shape={embedding.shape}, primeiros valores={embedding[:5]}")
        
        # Testa se embedding não está zerado
        if np.all(embedding == 0):
            print("❌ Embedding está zerado!")
            return False
        
        # Testa RecognitionEngine
        data_dir = project_root / "data"
        embeddings_dir = data_dir / "embeddings"
        images_dir = data_dir / "images"
        
        embeddings_dir.mkdir(parents=True, exist_ok=True)
        images_dir.mkdir(parents=True, exist_ok=True)
        
        engine = RecognitionEngine(
            embeddings_dir=str(embeddings_dir),
            images_dir=str(images_dir)
        )
        
        # Extrai face para teste
        bbox = face.bbox.astype(int)
        face_img = img[bbox[1]:bbox[3], bbox[0]:bbox[2]]
        
        if face_img.size == 0:
            print("❌ Face cropada está vazia")
            return False
        
        print(f"✅ Face cropada: {face_img.shape}")
        
        # Testa reconhecimento
        result = engine.recognize(face_img)
        print(f"✅ Resultado reconhecimento: {result}")
        
        return True
        
    except Exception as e:
        print(f"❌ Teste com imagem real erro: {e}")
        return False

def main():
    """Executa todos os testes"""
    print("🔍 DIAGNÓSTICO DO SISTEMA DE RECONHECIMENTO FACIAL")
    print("=" * 50)
    
    tests = [
        ("GPU", test_gpu_availability),
        ("ONNX Runtime", test_onnx_runtime),
        ("FAISS GPU", test_faiss_gpu),
        ("InsightFace", test_insightface),
        ("RecognitionEngine", test_recognition_engine),
        ("Imagem Real", test_with_real_image)
    ]
    
    results = {}
    for name, test_func in tests:
        results[name] = test_func()
    
    print("\n" + "=" * 50)
    print("📊 RESUMO DOS TESTES:")
    
    for name, passed in results.items():
        status = "✅ PASSOU" if passed else "❌ FALHOU"
        print(f"{name:<20} {status}")
    
    failed_tests = [name for name, passed in results.items() if not passed]
    
    if failed_tests:
        print(f"\n⚠️  TESTES FALHARAM: {', '.join(failed_tests)}")
        print("\n🔧 PRÓXIMOS PASSOS:")
        if "GPU" in failed_tests:
            print("• Instalar NVIDIA drivers e CUDA 11.8")
        if "ONNX Runtime" in failed_tests:
            print("• pip install onnxruntime-gpu")
        if "FAISS GPU" in failed_tests:
            print("• conda install pytorch::faiss-gpu")
        if "InsightFace" in failed_tests:
            print("• pip install insightface")
        if "RecognitionEngine" in failed_tests:
            print("• Verificar logs detalhados do sistema")
    else:
        print("\n🎉 TODOS OS TESTES PASSARAM!")
        print("   O sistema de reconhecimento facial está funcionando.")

if __name__ == "__main__":
    main()