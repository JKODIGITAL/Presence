#!/usr/bin/env python3
"""
Recognition Worker Main - Ponto de entrada para o worker de reconhecimento
"""

import asyncio
import sys
import os
import platform
from loguru import logger

# Configurar PATH para CUDA no Windows
if platform.system() == "Windows":
    cuda_bin_path = r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v11.8\bin"
    if os.path.exists(cuda_bin_path) and cuda_bin_path not in os.environ["PATH"]:
        os.environ["PATH"] = cuda_bin_path + ";" + os.environ["PATH"]
        print(f"[CONFIG] CUDA PATH adicionado: {cuda_bin_path}")

# Adicionar path do projeto
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from app.recognition_worker.recognition_worker import RecognitionWorker


async def main():
    """Função principal"""
    # Configurar logging
    logger.remove()
    # Console com logs essenciais apenas
    logger.add(
        sys.stdout,
        format="<green>{time:HH:mm:ss}</green> | <cyan>RECOGNITION</cyan> | <white>{message}</white>",
        level="INFO",
        filter=lambda record: any(keyword in record["message"] for keyword in [
            "Reconhecido:", "detectadas", "Worker inicializado", "ERROR"
        ]) and not any(skip in record["message"] for skip in [
            "getaddrinfo failed", "DNS/hostname"
        ])
    )
    
    # Adicionar arquivo de log
    logger.add(
        "logs/recognition_worker.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
        level="DEBUG",
        rotation="10 MB",
        retention="30 days"
    )
    
    logger.info("[ROCKET] Iniciando Recognition Worker...")
    
    worker = RecognitionWorker(port=int(os.environ.get('RECOGNITION_PORT', 17235)))
    
    try:
        # Inicializar worker
        success = await worker.initialize()
        if not success:
            logger.error("[ERROR] Falha ao inicializar Recognition Worker")
            return 1
        
        logger.info("[OK] Recognition Worker inicializado, aguardando conexões...")
        
        # Executar
        await worker.run()
        
    except KeyboardInterrupt:
        logger.info("⏹️ Recognition Worker interrompido pelo usuário")
    except Exception as e:
        logger.error(f"[ERROR] Erro no Recognition Worker: {e}")
        logger.exception("Detalhes do erro:")
        return 1
    finally:
        await worker.cleanup()
        logger.info("[PROCESSING] Recognition Worker finalizado")
    
    return 0


if __name__ == "__main__":
    # Verificar se está rodando no ambiente correto
    if os.getcwd().endswith('presence'):
        os.chdir(os.path.dirname(os.path.dirname(__file__)))
    
    exit_code = asyncio.run(main())
    sys.exit(exit_code)