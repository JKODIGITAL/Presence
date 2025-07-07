#!/usr/bin/env python3
"""
Script para verificar se o pipeline de alta performance está funcionando
"""

import sys
import os
from pathlib import Path

# Adicionar path do projeto
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def test_imports():
    """Testar todas as importações necessárias"""
    print("🔍 Verificando importações do pipeline de performance...")
    
    try:
        # Testar config
        from app.core.config import settings
        print("✅ Config importado")
        
        # Testar performance modules
        from app.core.performance.manager import PerformanceManager
        print("✅ PerformanceManager importado")
        
        from app.core.performance.camera_worker import CameraWorker, FrameData, RecognitionResult
        print("✅ CameraWorker importado")
        
        from app.core.performance.recognition_engine import GPURecognitionEngine
        print("✅ GPURecognitionEngine importado")
        
        from app.core.performance.pipeline_factory import GStreamerPipelineFactory
        print("✅ GStreamerPipelineFactory importado")
        
        # Testar worker principal
        from app.camera_worker.performance_worker import PerformanceWorkerMain
        print("✅ PerformanceWorkerMain importado")
        
        return True
        
    except ImportError as e:
        print(f"❌ Erro de importação: {e}")
        return False
    except Exception as e:
        print(f"❌ Erro geral: {e}")
        return False

def test_gstreamer():
    """Testar disponibilidade do GStreamer"""
    print("\n🎥 Verificando GStreamer...")
    
    try:
        import gi
        gi.require_version('Gst', '1.0')
        from gi.repository import Gst
        
        if not Gst.is_initialized():
            Gst.init(None)
        
        if Gst.is_initialized():
            version = Gst.version_string()
            print(f"✅ GStreamer disponível: {version}")
            
            # Verificar plugins críticos
            registry = Gst.Registry.get()
            plugins = ['rtspsrc', 'v4l2src', 'appsink', 'videoconvert']
            
            for plugin in plugins:
                element = registry.find_feature(plugin, Gst.ElementFactory.__gtype__)
                if element:
                    print(f"✅ Plugin {plugin} disponível")
                else:
                    print(f"❌ Plugin {plugin} não encontrado")
            
            # Verificar NVDEC
            nvh264dec = registry.find_feature("nvh264dec", Gst.ElementFactory.__gtype__)
            if nvh264dec:
                print("✅ NVDEC (nvh264dec) disponível - decodificação por hardware habilitada")
            else:
                print("⚠️ NVDEC não disponível - usando decodificação por software")
            
            return True
        else:
            print("❌ GStreamer não foi inicializado")
            return False
            
    except Exception as e:
        print(f"❌ Erro no GStreamer: {e}")
        return False

def test_gpu():
    """Testar disponibilidade de GPU"""
    print("\n🚀 Verificando GPU/CUDA...")
    
    try:
        # Testar PyTorch CUDA
        import torch
        if torch.cuda.is_available():
            device_name = torch.cuda.get_device_name(0)
            print(f"✅ PyTorch CUDA disponível: {device_name}")
        else:
            print("⚠️ PyTorch CUDA não disponível")
    except ImportError:
        print("⚠️ PyTorch não instalado")
    
    try:
        # Testar ONNX Runtime GPU
        import onnxruntime as ort
        providers = ort.get_available_providers()
        if 'CUDAExecutionProvider' in providers:
            print("✅ ONNX Runtime GPU disponível")
        else:
            print("⚠️ ONNX Runtime GPU não disponível")
    except ImportError:
        print("⚠️ ONNX Runtime não instalado")
    
    try:
        # Testar FAISS GPU
        import faiss
        print(f"✅ FAISS disponível: versão {faiss.__version__}")
        
        # Testar FAISS GPU
        try:
            res = faiss.StandardGpuResources()
            index = faiss.IndexFlatIP(512)
            gpu_index = faiss.index_cpu_to_gpu(res, 0, index)
            print("✅ FAISS GPU disponível")
        except Exception as e:
            print(f"⚠️ FAISS GPU não disponível: {e}")
    except ImportError:
        print("❌ FAISS não instalado")

def test_insightface():
    """Testar InsightFace"""
    print("\n🧠 Verificando InsightFace...")
    
    try:
        # Testar importação
        try:
            from insightface import FaceAnalysis
        except ImportError:
            from insightface.app import FaceAnalysis
        
        print("✅ InsightFace importado")
        
        # Verificar se pode inicializar
        providers = ['CPUExecutionProvider']  # Usar CPU para teste
        app = FaceAnalysis(name='antelopev2', providers=providers)
        print("✅ FaceAnalysis criado")
        
        return True
        
    except Exception as e:
        print(f"❌ Erro no InsightFace: {e}")
        return False

def test_pipeline_creation():
    """Testar criação de pipeline"""
    print("\n🔧 Testando criação de pipeline...")
    
    try:
        from app.core.performance.pipeline_factory import GStreamerPipelineFactory
        
        # Testar pipeline para webcam
        webcam_config = {
            'url': '0',
            'type': 'webcam',
            'fps_limit': 10
        }
        
        pipeline = GStreamerPipelineFactory.auto_create_pipeline(webcam_config, 'recognition')
        print("✅ Pipeline para webcam criado")
        print(f"   Pipeline: {pipeline[:100]}...")
        
        # Testar pipeline RTSP
        rtsp_config = {
            'url': 'rtsp://test:test@192.168.1.100/stream1',
            'type': 'rtsp',
            'fps_limit': 10
        }
        
        pipeline = GStreamerPipelineFactory.auto_create_pipeline(rtsp_config, 'recognition')
        print("✅ Pipeline RTSP criado")
        print(f"   Pipeline: {pipeline[:100]}...")
        
        return True
        
    except Exception as e:
        print(f"❌ Erro na criação de pipeline: {e}")
        return False

def test_performance_manager():
    """Testar Performance Manager"""
    print("\n📊 Testando Performance Manager...")
    
    try:
        from app.core.performance.manager import PerformanceManager
        
        manager = PerformanceManager()
        print("✅ PerformanceManager criado")
        
        # Testar start/stop
        if manager.start():
            print("✅ PerformanceManager iniciado")
            manager.stop()
            print("✅ PerformanceManager parado")
            return True
        else:
            print("❌ Falha ao iniciar PerformanceManager")
            return False
            
    except Exception as e:
        print(f"❌ Erro no PerformanceManager: {e}")
        return False

def main():
    """Função principal"""
    print("🔍 VERIFICAÇÃO DO PIPELINE DE ALTA PERFORMANCE")
    print("=" * 60)
    
    results = []
    
    # Executar todos os testes
    results.append(("Importações", test_imports()))
    results.append(("GStreamer", test_gstreamer()))
    results.append(("GPU/CUDA", test_gpu()))
    results.append(("InsightFace", test_insightface()))
    results.append(("Pipeline Creation", test_pipeline_creation()))
    results.append(("Performance Manager", test_performance_manager()))
    
    # Resumo
    print("\n" + "=" * 60)
    print("📋 RESUMO DOS TESTES")
    print("=" * 60)
    
    passed = 0
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASSOU" if result else "❌ FALHOU"
        print(f"{test_name:20} {status}")
        if result:
            passed += 1
    
    print(f"\nResultado: {passed}/{total} testes passaram")
    
    if passed == total:
        print("\n🎉 TODOS OS TESTES PASSARAM!")
        print("🚀 O pipeline de alta performance está pronto para uso!")
        print("\nPara ativar, certifique-se de que:")
        print("- USE_PERFORMANCE_WORKER=true")
        print("- USE_GPU=true")
        print("- GStreamer está instalado")
        print("- GPU NVIDIA com drivers CUDA")
    else:
        print(f"\n⚠️ {total - passed} testes falharam")
        print("Verifique os erros acima e instale as dependências necessárias")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)