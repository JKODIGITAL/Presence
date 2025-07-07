"""
Utilitários para detecção e configuração de GPU
"""

import os
import sys
from typing import Dict, Optional, Tuple
from loguru import logger


def detect_gpu_availability() -> Dict[str, any]:
    """
    Detectar disponibilidade real de GPU e bibliotecas CUDA
    
    Returns:
        Dict com informações de GPU disponibilidade
    """
    gpu_info = {
        'gpu_available': False,
        'cuda_available': False,
        'torch_cuda': False,
        'faiss_gpu': False,
        'onnx_cuda': False,
        'device_name': None,
        'cuda_version': None,
        'errors': []
    }
    
    try:
        # Teste PyTorch CUDA
        import torch
        gpu_info['torch_cuda'] = torch.cuda.is_available()
        if torch.cuda.is_available():
            gpu_info['device_name'] = torch.cuda.get_device_name(0)
            gpu_info['cuda_version'] = torch.version.cuda
            gpu_info['cuda_available'] = True
            logger.info(f"[OK] PyTorch CUDA: {gpu_info['device_name']}")
        else:
            gpu_info['errors'].append("PyTorch CUDA não disponível")
            logger.warning("[ERROR] PyTorch CUDA não disponível")
    except ImportError as e:
        gpu_info['errors'].append(f"PyTorch não encontrado: {e}")
        logger.error(f"[ERROR] PyTorch não encontrado: {e}")
    except Exception as e:
        gpu_info['errors'].append(f"Erro PyTorch: {e}")
        logger.error(f"[ERROR] Erro PyTorch: {e}")
    
    try:
        # Teste FAISS GPU
        import faiss
        gpu_info['faiss_gpu'] = hasattr(faiss, 'StandardGpuResources')
        if gpu_info['faiss_gpu']:
            # Testar inicialização real
            res = faiss.StandardGpuResources()
            logger.info("[OK] FAISS GPU resources disponíveis")
        else:
            gpu_info['errors'].append("FAISS GPU não disponível")
            logger.warning("[ERROR] FAISS GPU não disponível")
    except ImportError as e:
        gpu_info['errors'].append(f"FAISS não encontrado: {e}")
        logger.error(f"[ERROR] FAISS não encontrado: {e}")
    except Exception as e:
        gpu_info['errors'].append(f"Erro FAISS: {e}")
        logger.error(f"[ERROR] Erro FAISS: {e}")
    
    try:
        # Teste ONNX Runtime CUDA
        import onnxruntime as ort
        providers = ort.get_available_providers()
        gpu_info['onnx_cuda'] = 'CUDAExecutionProvider' in providers
        if gpu_info['onnx_cuda']:
            logger.info("[OK] ONNX Runtime CUDA disponível")
        else:
            gpu_info['errors'].append("ONNX Runtime CUDA não disponível")
            logger.warning("[ERROR] ONNX Runtime CUDA não disponível")
    except ImportError as e:
        gpu_info['errors'].append(f"ONNX Runtime não encontrado: {e}")
        logger.error(f"[ERROR] ONNX Runtime não encontrado: {e}")
    except Exception as e:
        gpu_info['errors'].append(f"Erro ONNX Runtime: {e}")
        logger.error(f"[ERROR] Erro ONNX Runtime: {e}")
    
    # GPU disponível se todas as bibliotecas estão funcionando
    gpu_info['gpu_available'] = (
        gpu_info['torch_cuda'] and 
        gpu_info['faiss_gpu'] and 
        gpu_info['onnx_cuda']
    )
    
    if gpu_info['gpu_available']:
        logger.info("[SUCCESS] GPU 100% disponível para reconhecimento facial")
    else:
        logger.warning(f"[WARNING] GPU não totalmente disponível. Erros: {gpu_info['errors']}")
    
    return gpu_info


def get_optimal_providers() -> Tuple[list, str]:
    """
    Obter providers ONNX otimizados baseados na disponibilidade de GPU
    
    Returns:
        Tuple de (providers_list, device_description)
    """
    # Verificar especificamente ONNX Runtime CUDA
    try:
        import onnxruntime as ort
        available_providers = ort.get_available_providers()
        logger.info(f"ONNX Runtime providers disponíveis: {available_providers}")
        
        # Para Recognition Worker, tentar CUDA mas aceitar fallback gracioso para CPU
        cuda_works = False
        if 'CUDAExecutionProvider' in available_providers:
            try:
                # Teste simples: verificar se CUDA Provider está listado
                # O erro DLL será detectado durante execução real pelo InsightFace
                logger.info("[SEARCH] CUDAExecutionProvider listado, tentará usar durante execução")
                
                # Verificar PyTorch CUDA para garantir que GPU está disponível
                try:
                    import torch
                    if torch.cuda.is_available():
                        cuda_works = True
                        logger.info("[OK] PyTorch CUDA confirma GPU disponível, tentando ONNX CUDA")
                    else:
                        logger.warning("[WARNING] PyTorch CUDA não disponível, forçando CPU")
                        cuda_works = False
                except ImportError:
                    logger.warning("[WARNING] PyTorch não disponível, assumindo CUDA funcionará")
                    # Se PyTorch não está disponível, assumir que CUDA pode funcionar
                    cuda_works = True
                    
            except Exception as cuda_test_error:
                logger.warning(f"[WARNING] Erro na verificação CUDA: {cuda_test_error}")
                cuda_works = False
        
        if cuda_works:
            providers = ['CUDAExecutionProvider', 'CPUExecutionProvider']
            device_desc = "GPU: CUDA disponível"
        else:
            providers = ['CPUExecutionProvider']
            device_desc = "CPU only (CUDA não funcional)"
            logger.warning("[WARNING] Usando CPU devido a problemas com CUDA")
    
    except Exception as e:
        logger.error(f"[ERROR] Erro ao verificar ONNX Runtime: {e}")
        providers = ['CPUExecutionProvider']
        device_desc = "CPU only (erro ONNX)"
    
    logger.info(f"Providers ONNX finais: {providers} ({device_desc})")
    return providers, device_desc


def setup_cuda_environment():
    """
    Configurar ambiente CUDA otimizado
    """
    # Configurações de ambiente CUDA
    os.environ['CUDA_LAUNCH_BLOCKING'] = '0'  # Async CUDA operations
    os.environ['CUDA_CACHE_DISABLE'] = '0'    # Enable CUDA caching
    
    # Configurações ONNX Runtime
    os.environ['OMP_NUM_THREADS'] = '1'       # Evitar conflitos threading
    os.environ['ORT_TENSORRT_ENGINE_CACHE_ENABLE'] = '1'  # TensorRT cache
    
    # Verificar CUDA_VISIBLE_DEVICES
    cuda_devices = os.environ.get('CUDA_VISIBLE_DEVICES', '0')
    logger.info(f"CUDA_VISIBLE_DEVICES: {cuda_devices}")
    
    # Log das configurações
    gpu_info = detect_gpu_availability()
    if gpu_info['gpu_available']:
        logger.info(f"[ROCKET] Ambiente CUDA configurado para {gpu_info['device_name']}")
    else:
        logger.warning("[WARNING] Ambiente CUDA não disponível, usando CPU")
    
    return gpu_info


def check_missing_gpu_dependencies() -> list:
    """
    Verificar dependências GPU faltantes
    
    Returns:
        Lista de dependências faltantes
    """
    missing = []
    
    try:
        import torch
        if not torch.cuda.is_available():
            missing.append("PyTorch CUDA support")
    except ImportError:
        missing.append("PyTorch")
    
    try:
        import faiss
        if not hasattr(faiss, 'StandardGpuResources'):
            missing.append("FAISS GPU support")
    except ImportError:
        missing.append("FAISS")
    
    try:
        import onnxruntime as ort
        if 'CUDAExecutionProvider' not in ort.get_available_providers():
            missing.append("ONNX Runtime GPU support")
    except ImportError:
        missing.append("ONNX Runtime")
    
    # Verificar bibliotecas específicas que podem estar faltando
    try:
        import numpy
    except ImportError:
        missing.append("NumPy")
    
    try:
        import cv2
    except ImportError:
        missing.append("OpenCV")
    
    try:
        import insightface
    except ImportError:
        missing.append("InsightFace")
    
    return missing


if __name__ == "__main__":
    """Teste das funções de GPU"""
    print("=== Teste de Detecção GPU ===")
    gpu_info = detect_gpu_availability()
    print(f"GPU Available: {gpu_info['gpu_available']}")
    print(f"Device: {gpu_info['device_name']}")
    print(f"CUDA Version: {gpu_info['cuda_version']}")
    print(f"Errors: {gpu_info['errors']}")
    
    print("\n=== Dependências Faltantes ===")
    missing = check_missing_gpu_dependencies()
    if missing:
        print(f"Faltando: {missing}")
    else:
        print("Todas as dependências GPU estão disponíveis!")
    
    print("\n=== Providers ONNX ===")
    providers, desc = get_optimal_providers()
    print(f"Providers: {providers}")
    print(f"Description: {desc}")