#!/bin/bash
# Script para construir as imagens Docker do projeto Presence

set -e

# Cores para saída
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Função para exibir mensagens
log() {
    echo -e "${BLUE}[$(date +'%H:%M:%S')]${NC} $1"
}

# Função para exibir mensagens de sucesso
success() {
    echo -e "${GREEN}[$(date +'%H:%M:%S')]${NC} ✅ $1"
}

# Função para exibir avisos
warn() {
    echo -e "${YELLOW}[$(date +'%H:%M:%S')]${NC} ⚠️ $1"
}

# Função para exibir erros
error() {
    echo -e "${RED}[$(date +'%H:%M:%S')]${NC} ❌ $1"
}

# Verificar se o Docker está instalado
if ! command -v docker &> /dev/null; then
    error "Docker não está instalado. Por favor, instale o Docker primeiro."
    exit 1
fi

# Verificar se o Docker Compose está instalado
if ! command -v docker-compose &> /dev/null; then
    warn "Docker Compose não encontrado, tentando usar 'docker compose'..."
    if ! docker compose version &> /dev/null; then
        error "Docker Compose não está instalado. Por favor, instale o Docker Compose primeiro."
        exit 1
    fi
    DOCKER_COMPOSE="docker compose"
else
    DOCKER_COMPOSE="docker-compose"
fi

# Criar diretórios necessários para scripts
mkdir -p docker/scripts
chmod +x docker/scripts/*.sh 2>/dev/null || true

# Função para construir as imagens base
build_base_images() {
    log "Construindo imagem base comum..."
    docker build -t presence-common-base:latest -f docker/Dockerfile.common-base .
    success "Imagem base comum construída com sucesso!"

    log "Construindo imagem base da API..."
    docker build -t presence-api-base:latest -f docker/Dockerfile.api-base .
    success "Imagem base da API construída com sucesso!"

    log "Construindo imagem base do Camera Worker..."
    docker build -t presence-worker-base:latest -f docker/Dockerfile.worker-base .
    success "Imagem base do Camera Worker construída com sucesso!"

    log "Construindo imagem base do Frontend..."
    docker build -t presence-frontend-base:latest -f docker/Dockerfile.frontend-base ./frontend
    success "Imagem base do Frontend construída com sucesso!"
}

# Função para construir as imagens de aplicação
build_app_images() {
    log "Construindo imagens de aplicação com docker-compose..."
    $DOCKER_COMPOSE build
    success "Imagens de aplicação construídas com sucesso!"
}

# Menu principal
echo "==================================================="
echo "🐳 Construção de Imagens Docker do Projeto Presence"
echo "==================================================="
echo ""
echo "Escolha uma opção:"
echo "1) Construir apenas imagens base"
echo "2) Construir apenas imagens de aplicação"
echo "3) Construir todas as imagens (base + aplicação)"
echo "4) Iniciar serviços com Hot Reload"
echo "5) Parar todos os serviços"
echo "q) Sair"
echo ""

read -p "Opção: " option

case $option in
    1)
        build_base_images
        ;;
    2)
        build_app_images
        ;;
    3)
        build_base_images
        build_app_images
        ;;
    4)
        log "Iniciando serviços com Hot Reload..."
        $DOCKER_COMPOSE up -d
        success "Serviços iniciados com sucesso!"
        echo ""
        echo "📋 Serviços disponíveis:"
        echo "- API: http://localhost:9000"
        echo "- Frontend: http://localhost"
        ;;
    5)
        log "Parando todos os serviços..."
        $DOCKER_COMPOSE down
        success "Serviços parados com sucesso!"
        ;;
    q|Q)
        log "Saindo..."
        exit 0
        ;;
    *)
        error "Opção inválida!"
        exit 1
        ;;
esac

echo ""
success "Operação concluída com sucesso!" 