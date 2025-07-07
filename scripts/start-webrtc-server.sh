#!/bin/bash

# Script para inicializar WebRTC Server
# WebRTC + GStreamer CUDA + InsightFace + FAISS

echo "🚀 Iniciando WebRTC Server para Recognition System..."

# Verificar se está no diretório correto
if [ ! -f "app/webrtc_worker/webrtc_server.py" ]; then
    echo "❌ Erro: Execute este script do diretório raiz do projeto"
    exit 1
fi

# Configurar variáveis de ambiente
export PYTHONPATH="$(pwd)"
export INSIGHTFACE_HOME="$(pwd)/data/models"
export CUDA_VISIBLE_DEVICES=0
export USE_GPU=true
export DEVELOPMENT=true

# Verificar dependências CUDA
echo "🔍 Verificando CUDA..."
if command -v nvidia-smi &> /dev/null; then
    nvidia-smi --query-gpu=name,memory.total,memory.free --format=csv,noheader,nounits
    echo "✅ CUDA disponível"
else
    echo "⚠️ CUDA não encontrado - usando CPU"
    export USE_GPU=false
fi

# Verificar GStreamer
echo "🔍 Verificando GStreamer..."
if command -v gst-inspect-1.0 &> /dev/null; then
    GST_VERSION=$(gst-inspect-1.0 --version | head -n1)
    echo "✅ $GST_VERSION"
    
    # Verificar plugins essenciais
    if gst-inspect-1.0 nvh264dec &> /dev/null; then
        echo "✅ NVDEC disponível"
    else
        echo "⚠️ NVDEC não encontrado - usando software decode"
    fi
    
    if gst-inspect-1.0 rtspsrc &> /dev/null; then
        echo "✅ RTSP suportado"
    else
        echo "❌ Plugin RTSP não encontrado"
    fi
else
    echo "❌ GStreamer não encontrado"
    echo "Instale com: sudo apt-get install gstreamer1.0-* python3-gi"
    exit 1
fi

# Verificar Python dependencies
echo "🔍 Verificando dependências Python..."
python3 -c "
import sys
missing = []

try:
    import aiortc
    print(f'✅ aiortc {aiortc.__version__}')
except ImportError:
    missing.append('aiortc')

try:
    import aiohttp
    print(f'✅ aiohttp {aiohttp.__version__}')
except ImportError:
    missing.append('aiohttp')

try:
    import cv2
    print(f'✅ opencv {cv2.__version__}')
except ImportError:
    missing.append('opencv-python')

try:
    import numpy as np
    print(f'✅ numpy {np.__version__}')
except ImportError:
    missing.append('numpy')

try:
    import gi
    gi.require_version('Gst', '1.0')
    from gi.repository import Gst
    print(f'✅ GStreamer Python bindings')
except ImportError:
    missing.append('python3-gi gir1.2-gstreamer-1.0')

try:
    import insightface
    print(f'✅ insightface {insightface.__version__}')
except ImportError:
    missing.append('insightface')

try:
    import faiss
    print(f'✅ faiss')
except ImportError:
    missing.append('faiss-cpu ou faiss-gpu')

if missing:
    print(f'❌ Dependências faltantes: {missing}')
    sys.exit(1)
else:
    print('✅ Todas as dependências disponíveis')
"

if [ $? -ne 0 ]; then
    echo "❌ Instale as dependências faltantes"
    echo "pip install -r requirements.txt"
    exit 1
fi

# Criar diretórios necessários
echo "📁 Criando diretórios..."
mkdir -p data/models
mkdir -p data/embeddings  
mkdir -p data/images
mkdir -p data/frames
mkdir -p logs

echo "✅ Diretórios criados"

# Verificar se Recognition Worker está rodando
echo "🔍 Verificando Recognition Worker..."
RECOGNITION_URL=${RECOGNITION_WORKER_URL:-"http://localhost:9001"}
if curl -f -s $RECOGNITION_URL/health &> /dev/null; then
    echo "✅ Recognition Worker está rodando em $RECOGNITION_URL"
else
    echo "⚠️ Recognition Worker não encontrado em $RECOGNITION_URL"
    echo "   WebRTC Server funcionará com funcionalidade limitada"
fi

# Verificar se API está rodando
echo "🔍 Verificando API..."
API_URL=${API_BASE_URL:-"http://localhost:9000"}
if curl -f -s $API_URL/health &> /dev/null; then
    echo "✅ API está rodando em $API_URL"
else
    echo "⚠️ API não encontrada em $API_URL"
    echo "   Algumas funcionalidades podem não funcionar"
fi

# Configurações finais
echo "⚙️ Configurações:"
echo "   - Porta WebRTC: 8080"
echo "   - CUDA: $USE_GPU"
echo "   - Modo: DEVELOPMENT"
echo "   - Python Path: $PYTHONPATH"
echo "   - InsightFace Home: $INSIGHTFACE_HOME"

# Iniciar servidor
echo ""
echo "🎬 Iniciando WebRTC Server..."
echo "   URL: http://localhost:8080"
echo "   Health Check: http://localhost:8080/health"
echo "   Status: http://localhost:8080/status"
echo ""
echo "📊 Para monitorar:"
echo "   - Logs: tail -f logs/webrtc.log"
echo "   - GPU: watch -n1 nvidia-smi"
echo "   - Sistema: htop"
echo ""
echo "🛑 Para parar: Ctrl+C"
echo ""

# Executar servidor
cd "$(dirname "$0")/.." && python3 -m app.webrtc_worker.webrtc_server