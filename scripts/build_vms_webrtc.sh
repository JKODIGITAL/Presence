#!/bin/bash

# Script para construir e executar VMS WebRTC
echo "🚀 Construindo VMS WebRTC Server..."

# Navegar para o diretório do projeto
cd "$(dirname "$0")/.."

# Construir a imagem VMS WebRTC
echo "📦 Construindo imagem Docker..."
docker build -t presence-vms-webrtc -f docker/Dockerfile.webrtc-cuda .

if [ $? -eq 0 ]; then
    echo "✅ Imagem construída com sucesso!"
    
    # Verificar se já existe um container rodando
    if [ "$(docker ps -q -f name=presence-vms-webrtc)" ]; then
        echo "⏹️ Parando container existente..."
        docker stop presence-vms-webrtc
        docker rm presence-vms-webrtc
    fi
    
    # Executar o container
    echo "🔄 Iniciando VMS WebRTC Server..."
    docker run -d \
        --name presence-vms-webrtc \
        --network host \
        --gpus all \
        -v "$(pwd)":/root/presence \
        -v "$(pwd)/data":/root/presence/data \
        -v "$(pwd)/logs":/root/presence/logs \
        -e PYTHONPATH=/root/presence \
        -e INSIGHTFACE_HOME=/root/presence/data/models \
        -e USE_GPU=true \
        -e CUDA_VISIBLE_DEVICES=0 \
        -e DEVELOPMENT=true \
        -e ENVIRONMENT=development \
        -e DOCKER_ENV=true \
        -e RECOGNITION_WORKER_URL=http://172.21.15.83:9001 \
        -e API_BASE_URL=http://localhost:9000 \
        -e VMS_WEBRTC_PORT=8765 \
        -e GST_DEBUG=3 \
        presence-vms-webrtc
    
    if [ $? -eq 0 ]; then
        echo "✅ VMS WebRTC Server iniciado com sucesso!"
        echo "🌐 Acesse: http://localhost:8765/demo"
        echo "📊 Logs: docker logs -f presence-vms-webrtc"
    else
        echo "❌ Erro ao iniciar VMS WebRTC Server"
        exit 1
    fi
else
    echo "❌ Erro ao construir imagem"
    exit 1
fi