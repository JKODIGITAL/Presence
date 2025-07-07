#!/bin/bash

# Build incremental - apenas o que foi modificado
echo "🚀 Build Incremental - Presence System"
echo "====================================="

# Verificar se Docker está disponível
if ! command -v docker &> /dev/null; then
    echo "❌ Docker não encontrado. Use o Docker Desktop no Windows."
    echo "💡 Execute este script no terminal do Windows ou configure WSL integration"
    exit 1
fi

# Função para verificar se imagem existe
image_exists() {
    docker images --format "table {{.Repository}}:{{.Tag}}" | grep -q "$1"
}

# Função para verificar última modificação dos Dockerfiles
dockerfile_newer_than_image() {
    local dockerfile=$1
    local image=$2
    
    if ! image_exists "$image"; then
        return 0  # Imagem não existe, precisa buildar
    fi
    
    if [ ! -f "$dockerfile" ]; then
        return 1  # Dockerfile não existe, não precisa buildar
    fi
    
    # Verificar se Dockerfile foi modificado depois da imagem
    local dockerfile_time=$(stat -c %Y "$dockerfile" 2>/dev/null || echo 0)
    local image_time=$(docker inspect "$image" --format='{{.Created}}' 2>/dev/null | xargs -I {} date -d {} +%s 2>/dev/null || echo 0)
    
    [ "$dockerfile_time" -gt "$image_time" ]
}

echo "🔍 Verificando quais imagens precisam ser reconstruídas..."

BUILD_LIST=()

# Verificar cada componente
echo ""
echo "📋 Status das imagens:"

# Base Images
if dockerfile_newer_than_image "docker/Dockerfile.common-base" "presence-common-base:latest"; then
    echo "🔄 presence-common-base: PRECISA REBUILD"
    BUILD_LIST+=("presence-common-base")
else
    echo "✅ presence-common-base: OK"
fi

if dockerfile_newer_than_image "docker/Dockerfile.worker-base" "presence-worker-base:latest"; then
    echo "🔄 presence-worker-base: PRECISA REBUILD" 
    BUILD_LIST+=("presence-worker-base")
else
    echo "✅ presence-worker-base: OK"
fi

if dockerfile_newer_than_image "docker/Dockerfile.api-base" "presence-api-base:latest"; then
    echo "🔄 presence-api-base: PRECISA REBUILD"
    BUILD_LIST+=("presence-api-base") 
else
    echo "✅ presence-api-base: OK"
fi

if dockerfile_newer_than_image "docker/Dockerfile.frontend-base" "presence-frontend-base:latest"; then
    echo "🔄 presence-frontend-base: PRECISA REBUILD"
    BUILD_LIST+=("presence-frontend-base")
else
    echo "✅ presence-frontend-base: OK"
fi

# Service Images
if dockerfile_newer_than_image "docker/Dockerfile.api" "presence_presence-api:latest"; then
    echo "🔄 presence-api: PRECISA REBUILD"
    BUILD_LIST+=("presence-api")
else
    echo "✅ presence-api: OK"
fi

if dockerfile_newer_than_image "docker/Dockerfile.recognition-worker" "presence_presence-recognition-worker:latest"; then
    echo "🔄 presence-recognition-worker: PRECISA REBUILD"
    BUILD_LIST+=("presence-recognition-worker")
else
    echo "✅ presence-recognition-worker: OK"
fi

if dockerfile_newer_than_image "docker/Dockerfile.worker" "presence_presence-camera-worker:latest"; then
    echo "🔄 presence-camera-worker: PRECISA REBUILD"
    BUILD_LIST+=("presence-camera-worker")
else
    echo "✅ presence-camera-worker: OK"
fi

if dockerfile_newer_than_image "docker/Dockerfile.webrtc" "presence_presence-webrtc-server:latest"; then
    echo "🔄 presence-webrtc-server: PRECISA REBUILD"
    BUILD_LIST+=("presence-webrtc-server")
else
    echo "✅ presence-webrtc-server: OK"
fi

if dockerfile_newer_than_image "docker/Dockerfile.frontend" "presence_presence-frontend:latest"; then
    echo "🔄 presence-frontend: PRECISA REBUILD"
    BUILD_LIST+=("presence-frontend")
else
    echo "✅ presence-frontend: OK"
fi

echo ""

# Verificar se há algo para buildar
if [ ${#BUILD_LIST[@]} -eq 0 ]; then
    echo "✅ Todas as imagens estão atualizadas!"
    echo ""
    echo "🚀 Para iniciar o sistema:"
    echo "   docker compose up -d"
    exit 0
fi

echo "🔧 Imagens que serão reconstruídas: ${BUILD_LIST[*]}"
echo ""

# Confirmar com usuário
read -p "Deseja prosseguir com o build incremental? (Y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Nn]$ ]]; then
    echo "❌ Build cancelado pelo usuário"
    exit 1
fi

echo ""
echo "🏗️ Iniciando build incremental..."

# Determinar comando do Docker Compose
if docker compose version &> /dev/null; then
    DOCKER_COMPOSE="docker compose"
else
    DOCKER_COMPOSE="docker-compose"
fi

# Build incremental na ordem correta de dependências
for service in "${BUILD_LIST[@]}"; do
    echo ""
    echo "🔨 Building $service..."
    
    case $service in
        "presence-common-base"|"presence-worker-base"|"presence-api-base"|"presence-frontend-base")
            # Base images
            $DOCKER_COMPOSE build --no-cache "$service"
            ;;
        *)
            # Service images
            $DOCKER_COMPOSE build "$service"
            ;;
    esac
    
    if [ $? -eq 0 ]; then
        echo "✅ $service concluído"
    else
        echo "❌ Falha no build de $service"
        exit 1
    fi
done

echo ""
echo "🎉 Build incremental concluído com sucesso!"
echo ""
echo "📊 Resumo:"
echo "   - Imagens reconstruídas: ${#BUILD_LIST[@]}"
echo "   - Serviços: ${BUILD_LIST[*]}"
echo ""
echo "🚀 Para iniciar o sistema:"
echo "   $DOCKER_COMPOSE up -d"
echo ""
echo "🌐 URLs após inicialização:"
echo "   - API: http://localhost:9000"
echo "   - Frontend: http://localhost:3000" 
echo "   - WebRTC: http://localhost:8080"
echo "   - Recognition Worker: http://localhost:9001"