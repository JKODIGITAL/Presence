#!/bin/bash

# Script inteligente para build Docker com detecção de GPU
# Verifica se NVIDIA GPU está disponível e usa a configuração apropriada

echo "🚀 Build Inteligente do Sistema Presence"
echo "==========================================="

# Verificar se NVIDIA Docker está disponível
GPU_AVAILABLE=false
if command -v nvidia-smi &> /dev/null; then
    if nvidia-smi &> /dev/null; then
        echo "✅ NVIDIA GPU detectada:"
        nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
        GPU_AVAILABLE=true
    else
        echo "⚠️ nvidia-smi encontrado mas GPU não acessível"
    fi
else
    echo "⚠️ NVIDIA GPU não detectada (nvidia-smi não encontrado)"
fi

# Verificar se Docker Compose está disponível
if ! command -v docker &> /dev/null; then
    echo "❌ Docker não encontrado. Instale o Docker primeiro."
    exit 1
fi

if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo "❌ Docker Compose não encontrado."
    exit 1
fi

# Determinar comando do Docker Compose
if docker compose version &> /dev/null; then
    DOCKER_COMPOSE="docker compose"
else
    DOCKER_COMPOSE="docker-compose"
fi

echo ""
echo "🔧 Configuração de Build:"
echo "   GPU Disponível: $GPU_AVAILABLE"
echo "   Docker Compose: $DOCKER_COMPOSE"

# Escolher configuração
if [ "$GPU_AVAILABLE" = true ]; then
    echo ""
    echo "🎯 Modo GPU detectado - usando configuração otimizada"
    echo "   - WebRTC Server com CUDA"
    echo "   - Recognition Worker com GPU"
    echo "   - Camera Worker com hardware acceleration"
    
    read -p "Deseja usar GPU? (Y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Nn]$ ]]; then
        echo "👤 Usuário escolheu modo CPU"
        GPU_MODE=false
    else
        echo "🚀 Usando modo GPU"
        GPU_MODE=true
    fi
else
    echo ""
    echo "💻 Modo CPU detectado - usando configuração compatível"
    echo "   - WebRTC Server com fallback CPU"
    echo "   - Recognition Worker CPU-only"
    echo "   - Sem hardware acceleration"
    GPU_MODE=false
fi

echo ""
echo "📦 Iniciando build..."

# Build baseado na configuração
if [ "$GPU_MODE" = true ]; then
    echo "🏗️ Building com suporte GPU..."
    $DOCKER_COMPOSE -f docker-compose.yml -f docker-compose.gpu.yml build --no-cache
    
    if [ $? -eq 0 ]; then
        echo ""
        echo "✅ Build GPU concluído com sucesso!"
        echo ""
        echo "🚀 Para iniciar com GPU:"
        echo "   $DOCKER_COMPOSE -f docker-compose.yml -f docker-compose.gpu.yml up"
    else
        echo ""
        echo "❌ Build GPU falhou. Tentando fallback CPU..."
        echo ""
        $DOCKER_COMPOSE build --no-cache
    fi
else
    echo "🏗️ Building modo CPU..."
    $DOCKER_COMPOSE build --no-cache
    
    if [ $? -eq 0 ]; then
        echo ""
        echo "✅ Build CPU concluído com sucesso!"
        echo ""
        echo "🚀 Para iniciar:"
        echo "   $DOCKER_COMPOSE up"
    else
        echo ""
        echo "❌ Build falhou. Verifique os logs acima."
        exit 1
    fi
fi

echo ""
echo "📋 Próximos passos:"
echo "   1. docker compose up presence-api presence-recognition-worker"
echo "   2. docker compose up presence-webrtc-server"
echo "   3. docker compose up presence-frontend"
echo ""
echo "🌐 URLs:"
echo "   - API: http://localhost:9000"
echo "   - Frontend: http://localhost:3000"
echo "   - WebRTC: http://localhost:8080"
echo "   - Recognition Worker: http://localhost:9001"
echo ""
echo "📊 Monitoramento:"
if [ "$GPU_MODE" = true ]; then
    echo "   - GPU: watch -n1 nvidia-smi"
fi
echo "   - Logs: docker compose logs -f"
echo "   - Sistema: htop"