#!/usr/bin/env python3
"""
Script para verificar disponibilidade de CUDA e GPU no sistema
"""

import sys
import os

def check_nvidia_driver():
    """Verificar driver NVIDIA"""
    print("🔍 Verificando driver NVIDIA...")
    try:
        result = os.system("nvidia-smi > /dev/null 2>&1")
        if result == 0:
            print("✅ Driver NVIDIA detectado")
            os.system("nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader,nounits")
            return True
        else:
            print("❌ Driver NVIDIA não detectado")
            return False
    except Exception as e:
        print(f"❌ Erro ao verificar driver: {e}")
        return False

def check_cuda():
    """Verificar CUDA"""
    print("\n🔍 Verificando CUDA...")
    try:
        import torch
        print(f"PyTorch version: {torch.__version__}")
        
        if torch.cuda.is_available():
            print("✅ CUDA disponível no PyTorch")
            print(f"CUDA version: {torch.version.cuda}")
            print(f"Devices disponíveis: {torch.cuda.device_count()}")
            
            for i in range(torch.cuda.device_count()):
                props = torch.cuda.get_device_properties(i)
                print(f"  GPU {i}: {props.name}")
                print(f"    Memory: {props.total_memory / 1024**3:.1f} GB")
                print(f"    Compute capability: {props.major}.{props.minor}")
            return True
        else:
            print("❌ CUDA não disponível no PyTorch")
            return False
    except ImportError:
        print("❌ PyTorch não instalado")
        return False
    except Exception as e:
        print(f"❌ Erro ao verificar CUDA: {e}")
        return False

def check_onnxruntime_gpu():
    """Verificar ONNX Runtime GPU"""
    print("\n🔍 Verificando ONNX Runtime GPU...")
    try:
        import onnxruntime as ort
        print(f"ONNX Runtime version: {ort.__version__}")
        
        providers = ort.get_available_providers()
        print(f"Providers disponíveis: {providers}")
        
        if 'CUDAExecutionProvider' in providers:
            print("✅ ONNX Runtime GPU (CUDA) disponível")
            return True
        else:
            print("❌ ONNX Runtime GPU não disponível")
            return False
    except ImportError:
        print("❌ ONNX Runtime não instalado")
        return False
    except Exception as e:
        print(f"❌ Erro ao verificar ONNX Runtime: {e}")
        return False

def check_faiss_gpu():
    """Verificar FAISS GPU"""
    print("\n🔍 Verificando FAISS GPU...")
    try:
        import faiss
        print(f"FAISS version: {faiss.__version__ if hasattr(faiss, '__version__') else 'Unknown'}")
        
        gpu_count = faiss.get_num_gpus()
        print(f"GPUs detectadas pelo FAISS: {gpu_count}")
        
        if gpu_count > 0:
            print("✅ FAISS GPU disponível")
            
            # Teste rápido de performance
            print("\n🚀 Teste de performance FAISS GPU...")
            import numpy as np
            
            # Criar dados de teste
            d = 512  # Dimensão (InsightFace)
            nb = 10000  # Base vectors
            nq = 100   # Query vectors
            
            np.random.seed(1234)
            xb = np.random.random((nb, d)).astype('float32')
            xq = np.random.random((nq, d)).astype('float32')
            
            # Index CPU
            import time
            cpu_index = faiss.IndexFlatL2(d)
            start_time = time.time()
            cpu_index.add(xb)
            cpu_add_time = time.time() - start_time
            
            start_time = time.time()
            D, I = cpu_index.search(xq, 5)
            cpu_search_time = time.time() - start_time
            
            # Index GPU
            try:
                res = faiss.StandardGpuResources()
                gpu_index = faiss.index_cpu_to_gpu(res, 0, cpu_index)
                
                start_time = time.time()
                D_gpu, I_gpu = gpu_index.search(xq, 5)
                gpu_search_time = time.time() - start_time
                
                print(f"  CPU add time: {cpu_add_time:.4f}s")
                print(f"  CPU search time: {cpu_search_time:.4f}s")
                print(f"  GPU search time: {gpu_search_time:.4f}s")
                print(f"  Speedup: {cpu_search_time/gpu_search_time:.1f}x")
                
            except Exception as e:
                print(f"  ❌ Erro no teste GPU: {e}")
            
            return True
        else:
            print("❌ FAISS GPU não disponível")
            return False
    except ImportError:
        print("❌ FAISS não instalado")
        return False
    except Exception as e:
        print(f"❌ Erro ao verificar FAISS: {e}")
        return False

def check_gstreamer_nvdec():
    """Verificar GStreamer NVDEC"""
    print("\n🔍 Verificando GStreamer NVDEC...")
    try:
        import gi
        gi.require_version('Gst', '1.0')
        from gi.repository import Gst
        
        Gst.init(None)
        
        # Verificar plugins de hardware decoding
        registry = Gst.Registry.get()
        
        nvdec_plugins = [
            'nvh264dec',     # NVIDIA desktop/server
            'nvv4l2decoder', # NVIDIA Jetson  
            'vaapih264dec',  # Intel/AMD
            'v4l2h264dec'    # Generic hardware
        ]
        
        available_decoders = []
        for plugin in nvdec_plugins:
            element = registry.find_feature(plugin, Gst.ElementFactory.__gtype__)
            if element:
                available_decoders.append(plugin)
        
        if available_decoders:
            print(f"✅ Hardware decoders disponíveis: {available_decoders}")
            return True
        else:
            print("❌ Nenhum hardware decoder encontrado")
            return False
            
    except ImportError:
        print("❌ GStreamer (PyGObject) não instalado")
        return False
    except Exception as e:
        print(f"❌ Erro ao verificar GStreamer: {e}")
        return False

def check_insightface():
    """Verificar InsightFace"""
    print("\n🔍 Verificando InsightFace...")
    try:
        import insightface
        print(f"InsightFace version: {insightface.__version__ if hasattr(insightface, '__version__') else 'Unknown'}")
        
        # Verificar se consegue criar FaceAnalysis
        try:
            from insightface.app import FaceAnalysis
            providers = ['CUDAExecutionProvider', 'CPUExecutionProvider']
            app = FaceAnalysis(name='antelopev2', providers=providers)
            print("✅ InsightFace FaceAnalysis criado com sucesso")
            return True
        except Exception as e:
            print(f"❌ Erro ao criar FaceAnalysis: {e}")
            return False
            
    except ImportError:
        print("❌ InsightFace não instalado")
        return False
    except Exception as e:
        print(f"❌ Erro ao verificar InsightFace: {e}")
        return False

def main():
    """Função principal"""
    print("🚀 VERIFICAÇÃO DE DEPENDÊNCIAS GPU - SISTEMA DE RECONHECIMENTO FACIAL")
    print("=" * 80)
    
    results = {
        'nvidia_driver': check_nvidia_driver(),
        'cuda': check_cuda(),
        'onnxruntime_gpu': check_onnxruntime_gpu(),
        'faiss_gpu': check_faiss_gpu(),
        'gstreamer_nvdec': check_gstreamer_nvdec(),
        'insightface': check_insightface()
    }
    
    print("\n" + "=" * 80)
    print("📊 RESUMO DOS RESULTADOS:")
    
    total_checks = len(results)
    passed_checks = sum(results.values())
    
    for component, status in results.items():
        icon = "✅" if status else "❌"
        print(f"  {icon} {component.replace('_', ' ').title()}")
    
    print(f"\n🎯 Score: {passed_checks}/{total_checks} ({passed_checks/total_checks*100:.1f}%)")
    
    if passed_checks >= 4:
        print("🚀 Sistema pronto para HIGH-PERFORMANCE face recognition!")
    elif passed_checks >= 2:
        print("⚠️ Sistema parcialmente funcional - algumas otimizações indisponíveis")
    else:
        print("❌ Sistema não está configurado para GPU - funcionará apenas com CPU")
    
    return passed_checks >= 2

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)