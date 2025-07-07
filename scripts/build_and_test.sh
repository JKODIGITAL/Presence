#!/bin/bash
# Script para Build e Teste Completo do Sistema Presence

set -e

# Cores para output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Função para log
log() {
    echo -e "${BLUE}[$(date +'%H:%M:%S')]${NC} $1"
}

success() {
    echo -e "${GREEN}[$(date +'%H:%M:%S')]${NC} ✅ $1"
}

warn() {
    echo -e "${YELLOW}[$(date +'%H:%M:%S')]${NC} ⚠️ $1"
}

error() {
    echo -e "${RED}[$(date +'%H:%M:%S')]${NC} ❌ $1"
}

# Verificar se Docker está rodando
check_docker() {
    log "Verificando Docker..."
    if ! docker info > /dev/null 2>&1; then
        error "Docker não está rodando. Inicie o Docker e tente novamente."
        exit 1
    fi
    success "Docker está rodando"
}

# Verificar se nvidia-docker está disponível (se aplicável)
check_nvidia_docker() {
    log "Verificando suporte a GPU..."
    if docker run --rm --gpus all nvidia/cuda:11.8-base-ubuntu22.04 nvidia-smi > /dev/null 2>&1; then
        success "Suporte a GPU funcionando"
        export GPU_SUPPORT=true
    else
        warn "Suporte a GPU não disponível - continuando sem GPU"
        export GPU_SUPPORT=false
    fi
}

# Build das imagens base
build_base_images() {
    log "Construindo imagens base..."
    
    # Common base
    log "Construindo presence-common-base..."
    docker build -f docker/Dockerfile.common-base -t presence-common-base:latest . || {
        error "Falha ao construir presence-common-base"
        exit 1
    }
    
    # API base
    log "Construindo presence-api-base..."
    docker build -f docker/Dockerfile.api-base -t presence-api-base:latest . || {
        error "Falha ao construir presence-api-base"
        exit 1
    }
    
    # Worker base
    log "Construindo presence-worker-base..."
    docker build -f docker/Dockerfile.worker-base -t presence-worker-base:latest . || {
        error "Falha ao construir presence-worker-base"
        exit 1
    }
    
    # Frontend base
    log "Construindo presence-frontend-base..."
    docker build -f docker/Dockerfile.frontend-base -t presence-frontend-base:latest . || {
        error "Falha ao construir presence-frontend-base"
        exit 1
    }
    
    success "Imagens base construídas com sucesso"
}

# Build das imagens de aplicação
build_app_images() {
    log "Construindo imagens de aplicação..."
    
    # Usar docker-compose para build
    docker-compose build || {
        error "Falha no build das imagens de aplicação"
        exit 1
    }
    
    success "Imagens de aplicação construídas com sucesso"
}

# Iniciar serviços
start_services() {
    log "Iniciando serviços..."
    
    # Parar serviços existentes primeiro
    docker-compose down --remove-orphans || true
    
    # Iniciar serviços
    docker-compose up -d || {
        error "Falha ao iniciar serviços"
        exit 1
    }
    
    success "Serviços iniciados"
}

# Aguardar serviços estarem prontos
wait_for_services() {
    log "Aguardando serviços ficarem prontos..."
    
    # Aguardar API
    log "Aguardando API (máximo 120s)..."
    timeout=120
    elapsed=0
    while [ $elapsed -lt $timeout ]; do
        if curl -s http://localhost:9000/health > /dev/null 2>&1; then
            success "API está pronta"
            break
        fi
        sleep 5
        elapsed=$((elapsed + 5))
        log "API ainda não pronta... ($elapsed/$timeout)s"
    done
    
    if [ $elapsed -ge $timeout ]; then
        error "Timeout aguardando API"
        return 1
    fi
    
    # Aguardar Frontend
    log "Aguardando Frontend (máximo 60s)..."
    timeout=60
    elapsed=0
    while [ $elapsed -lt $timeout ]; do
        if curl -s http://localhost:3000 > /dev/null 2>&1; then
            success "Frontend está pronto"
            break
        fi
        sleep 5
        elapsed=$((elapsed + 5))
        log "Frontend ainda não pronto... ($elapsed/$timeout)s"
    done
    
    if [ $elapsed -ge $timeout ]; then
        warn "Timeout aguardando Frontend - mas continuando"
    fi
    
    success "Serviços prontos para teste"
}

# Executar testes
run_tests() {
    log "Executando testes do sistema..."
    
    # Instalar dependências de teste se necessário
    pip install aiohttp loguru > /dev/null 2>&1 || {
        warn "Não foi possível instalar dependências de teste"
    }
    
    # Executar script de teste
    if python scripts/test_system_complete.py; then
        success "Todos os testes passaram!"
        return 0
    else
        error "Alguns testes falharam"
        return 1
    fi
}

# Mostrar logs dos serviços
show_logs() {
    log "Mostrando logs dos serviços..."
    echo ""
    echo "=== API LOGS ==="
    docker-compose logs --tail=20 presence-api
    echo ""
    echo "=== WORKER LOGS ==="
    docker-compose logs --tail=20 presence-camera-worker
    echo ""
    echo "=== FRONTEND LOGS ==="
    docker-compose logs --tail=20 presence-frontend
}

# Mostrar status dos serviços
show_status() {
    log "Status dos serviços:"
    docker-compose ps
    echo ""
    log "URLs dos serviços:"
    echo "  - API: http://localhost:9000"
    echo "  - API Health: http://localhost:9000/health"
    echo "  - API Docs: http://localhost:9000/docs"
    echo "  - Frontend: http://localhost:3000"
    echo ""
}

# Função principal
main() {
    echo ""
    echo "🚀 BUILD E TESTE COMPLETO DO SISTEMA PRESENCE"
    echo "=============================================="
    echo ""
    
    # Verificações iniciais
    check_docker
    check_nvidia_docker
    
    # Build das imagens
    log "Fase 1: Build das imagens"
    build_base_images
    build_app_images
    
    # Iniciar e testar
    log "Fase 2: Inicialização e teste"
    start_services
    wait_for_services
    
    # Executar testes
    log "Fase 3: Execução de testes"
    if run_tests; then
        success "🎉 SISTEMA COMPLETAMENTE FUNCIONAL!"
        show_status
    else
        error "❌ Sistema com problemas. Verificando logs..."
        show_logs
        exit 1
    fi
    
    # Informações finais
    echo ""
    echo "================================================"
    success "Build e teste concluídos com sucesso!"
    echo "================================================"
    echo ""
    log "Para visualizar logs em tempo real:"
    echo "  docker-compose logs -f"
    echo ""
    log "Para parar os serviços:"
    echo "  docker-compose down"
    echo ""
    log "Para reiniciar um serviço específico:"
    echo "  docker-compose restart presence-api"
    echo "  docker-compose restart presence-camera-worker"
    echo "  docker-compose restart presence-frontend"
    echo ""
}

# Executar função principal
main "$@"