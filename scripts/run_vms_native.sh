#!/bin/bash

# Script para executar VMS WebRTC nativamente (sem Docker)
echo "🚀 Iniciando VMS WebRTC Server (modo nativo)..."

# Navegar para o diretório do projeto
cd "$(dirname "$0")/.."

# Verificar se o ambiente Python está configurado
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 não encontrado"
    exit 1
fi

# Verificar se GStreamer está instalado
if ! command -v gst-inspect-1.0 &> /dev/null; then
    echo "❌ GStreamer não encontrado. Execute:"
    echo "sudo apt-get install gstreamer1.0-tools gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-nice"
    exit 1
fi

# Verificar se WebRTC plugin está disponível
if ! gst-inspect-1.0 webrtcbin &> /dev/null; then
    echo "⚠️ Plugin webrtcbin não encontrado. Tentando instalar..."
    sudo apt-get update
    sudo apt-get install -y gstreamer1.0-nice gstreamer1.0-plugins-bad
fi

# Instalar dependências Python se necessário
echo "📦 Verificando dependências Python..."
pip3 install --quiet fastapi uvicorn websockets python-socketio aiofiles PyGObject opencv-python-headless numpy

# Configurar variáveis de ambiente
export PYTHONPATH=/mnt/d/Projetopresence/presence
export RECOGNITION_WORKER_URL=http://172.21.15.83:9001
export API_BASE_URL=http://localhost:9000
export VMS_WEBRTC_PORT=8765
export GST_DEBUG=3

# Criar diretórios de log se não existirem
mkdir -p logs

echo "✅ Iniciando VMS WebRTC Server na porta 8765..."
echo "🌐 Demo: http://localhost:8765/demo"
echo "🔄 Use Ctrl+C para parar"

# Executar o servidor
python3 -m app.webrtc_worker.main_vms