#!/bin/bash
"""
Script para build e verificação completa do sistema de performance
"""

set -e  # Parar em caso de erro

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Função para log
log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Verificar se estamos no diretório correto
if [[ ! -f "docker-compose.yml" ]]; then
    error "docker-compose.yml não encontrado. Execute este script no diretório raiz do projeto."
    exit 1
fi

log "🚀 Iniciando build e verificação completa do sistema de performance"

# 1. Verificar dependências do sistema
log "📋 Verificando dependências do sistema..."

# Verificar Docker
if ! command -v docker &> /dev/null; then
    error "Docker não está instalado"
    exit 1
fi

# Verificar Docker Compose
if ! command -v docker-compose &> /dev/null; then
    error "Docker Compose não está instalado"
    exit 1
fi

# Verificar NVIDIA drivers
if ! command -v nvidia-smi &> /dev/null; then
    warning "nvidia-smi não encontrado. GPU pode não estar disponível."
else
    success "NVIDIA drivers detectados"
    nvidia-smi --query-gpu=name,driver_version --format=csv,noheader
fi

# 2. Parar containers existentes
log "🛑 Parando containers existentes..."
docker-compose down --remove-orphans || true

# 3. Limpar imagens antigas (opcional)
if [[ "$1" == "--clean" ]]; then
    log "🧹 Limpando imagens antigas..."
    docker system prune -f
    docker-compose down --rmi all --volumes --remove-orphans || true
fi

# 4. Build das imagens base
log "🏗️ Construindo imagens base..."

# Build common base
log "📦 Construindo presence-common-base..."
docker build -f docker/Dockerfile.common-base -t presence-common-base:latest .

# Build API base
log "📦 Construindo presence-api-base..."
docker build -f docker/Dockerfile.api-base -t presence-api-base:latest .

# Build Worker base  
log "📦 Construindo presence-worker-base..."
docker build -f docker/Dockerfile.worker-base -t presence-worker-base:latest .

# Build Frontend base
log "📦 Construindo presence-frontend-base..."
docker build -f docker/Dockerfile.frontend-base -t presence-frontend-base:latest .

# 5. Build das imagens de aplicação
log "🏗️ Construindo imagens de aplicação..."
docker-compose build

# 6. Verificar se as imagens foram criadas
log "🔍 Verificando imagens criadas..."
docker images | grep presence

# 7. Testar configuração do performance pipeline
log "🔬 Verificando configuração do performance pipeline..."
python3 scripts/verify_docker_performance.py

# 8. Iniciar containers
log "🚀 Iniciando containers..."
docker-compose up -d

# 9. Aguardar containers inicializarem
log "⏳ Aguardando containers inicializarem..."
sleep 30

# 10. Verificar saúde dos containers
log "🏥 Verificando saúde dos containers..."
docker-compose ps

# 11. Verificar logs para erros
log "📋 Verificando logs dos containers..."

# API logs
echo "=== LOGS DA API ==="
docker-compose logs --tail=20 presence-api

# Camera Worker logs
echo "=== LOGS DO CAMERA WORKER ==="
docker-compose logs --tail=20 presence-camera-worker

# Recognition Worker logs  
echo "=== LOGS DO RECOGNITION WORKER ==="
docker-compose logs --tail=20 presence-recognition-worker

# 12. Testar endpoints da API
log "🌐 Testando endpoints da API..."

# Aguardar API estar pronta
for i in {1..30}; do
    if curl -f http://localhost:9000/health &> /dev/null; then
        success "API está respondendo"
        break
    fi
    if [[ $i -eq 30 ]]; then
        error "API não está respondendo após 30 tentativas"
        exit 1
    fi
    sleep 2
done

# Testar endpoint de saúde
api_health=$(curl -s http://localhost:9000/health)
echo "API Health: $api_health"

# Testar endpoint de câmeras
cameras_response=$(curl -s http://localhost:9000/api/v1/cameras)
echo "Cameras endpoint: ${cameras_response:0:100}..."

# 13. Verificar se o performance worker está ativo
log "📈 Verificando se o performance worker está ativo..."

# Procurar por logs do performance worker
if docker-compose logs presence-camera-worker | grep -q "Performance Worker"; then
    success "Performance Worker está ativo!"
    echo "Pipeline em uso:"
    echo "📸 RTSP Cameras (via GStreamer)"
    echo " └▶ 🧵 1 processo/câmera (multiprocessing)"
    echo "      └▶ 🎥 GStreamer com appsink → NumPy"
    echo "           └▶ 🧠 InsightFace (GPU) → FAISS (GPU)"
    echo "                └▶ 🧑 Nome identificado"
    echo "                     └▶ 📦 Fila de comunicação para main process"
    echo "                          └▶ 🖥️ Visualização opcional"
elif docker-compose logs presence-camera-worker | grep -q "GStreamer Worker"; then
    warning "Usando GStreamer Worker tradicional (fallback)"
    echo "Para ativar o performance worker:"
    echo "1. Certifique-se de que USE_PERFORMANCE_WORKER=true"
    echo "2. Verifique se NVIDIA GPU está disponível"
    echo "3. Execute: python scripts/verify_performance_pipeline.py"
else
    error "Não foi possível determinar qual worker está ativo"
fi

# 14. Resumo final
log "📊 Resumo final do build"
echo "================================"
echo "✅ Build concluído com sucesso"
echo "✅ Containers estão rodando"
echo "✅ API está respondendo"

# URLs de acesso
echo ""
echo "🌐 URLs de acesso:"
echo "  API: http://localhost:9000"
echo "  Frontend: http://localhost:3000"
echo "  API Health: http://localhost:9000/health"
echo "  Recognition Worker: http://localhost:9001/health"

echo ""
echo "📚 Comandos úteis:"
echo "  Ver logs: docker-compose logs -f [service]"
echo "  Parar: docker-compose down"
echo "  Restart: docker-compose restart [service]"
echo "  Testar pipeline: python scripts/verify_performance_pipeline.py"

echo ""
success "🎉 Sistema está pronto para uso!"