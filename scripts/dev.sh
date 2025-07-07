#!/bin/bash

# Script de desenvolvimento para Presence
# Uso: ./scripts/dev.sh [comando]

set -e

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Função para imprimir mensagens coloridas
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Função para mostrar ajuda
show_help() {
    echo "Script de desenvolvimento para Presence"
    echo ""
    echo "Uso: ./scripts/dev.sh [comando]"
    echo ""
    echo "Comandos disponíveis:"
    echo "  start     - Inicia todos os serviços em modo desenvolvimento"
    echo "  stop      - Para todos os serviços"
    echo "  restart   - Reinicia todos os serviços"
    echo "  rebuild   - Reconstrói as imagens Docker"
    echo "  logs      - Mostra logs de todos os serviços"
    echo "  api-logs  - Mostra logs apenas da API"
    echo "  worker-logs - Mostra logs apenas do worker"
    echo "  frontend-logs - Mostra logs apenas do frontend"
    echo "  shell     - Abre shell no container da API"
    echo "  frontend-shell - Abre shell no container do frontend"
    echo "  clean     - Remove containers e volumes não utilizados"
    echo "  help      - Mostra esta ajuda"
    echo ""
    echo "Exemplos:"
    echo "  ./scripts/dev.sh start"
    echo "  ./scripts/dev.sh logs"
    echo "  ./scripts/dev.sh shell"
}

# Função para verificar se Docker está rodando
check_docker() {
    if ! docker info > /dev/null 2>&1; then
        print_error "Docker não está rodando. Inicie o Docker primeiro."
        exit 1
    fi
}

# Função para iniciar serviços
start_services() {
    print_status "Iniciando serviços em modo desenvolvimento..."
    docker-compose -f docker-compose.dev.yml up -d
    print_success "Serviços iniciados!"
    print_status "API: http://localhost:9000"
    print_status "Frontend: http://localhost:3000"
    print_status "Use './scripts/dev.sh logs' para ver os logs"
}

# Função para parar serviços
stop_services() {
    print_status "Parando serviços..."
    docker-compose -f docker-compose.dev.yml down
    print_success "Serviços parados!"
}

# Função para reiniciar serviços
restart_services() {
    print_status "Reiniciando serviços..."
    docker-compose -f docker-compose.dev.yml restart
    print_success "Serviços reiniciados!"
}

# Função para reconstruir imagens
rebuild_services() {
    print_status "Reconstruindo imagens Docker..."
    docker-compose -f docker-compose.dev.yml build --no-cache
    print_success "Imagens reconstruídas!"
    print_status "Use './scripts/dev.sh start' para iniciar os serviços"
}

# Função para mostrar logs
show_logs() {
    print_status "Mostrando logs de todos os serviços..."
    docker-compose -f docker-compose.dev.yml logs -f
}

# Função para mostrar logs da API
show_api_logs() {
    print_status "Mostrando logs da API..."
    docker-compose -f docker-compose.dev.yml logs -f presence-api
}

# Função para mostrar logs do worker
show_worker_logs() {
    print_status "Mostrando logs do worker..."
    docker-compose -f docker-compose.dev.yml logs -f presence-camera-worker
}

# Função para mostrar logs do frontend
show_frontend_logs() {
    print_status "Mostrando logs do frontend..."
    docker-compose -f docker-compose.dev.yml logs -f presence-frontend
}

# Função para abrir shell na API
open_api_shell() {
    print_status "Abrindo shell no container da API..."
    docker-compose -f docker-compose.dev.yml exec presence-api bash
}

# Função para abrir shell no frontend
open_frontend_shell() {
    print_status "Abrindo shell no container do frontend..."
    docker-compose -f docker-compose.dev.yml exec presence-frontend bash
}

# Função para limpar containers não utilizados
clean_docker() {
    print_status "Limpando containers e volumes não utilizados..."
    docker system prune -f
    docker volume prune -f
    print_success "Limpeza concluída!"
}

# Verificar se Docker está rodando
check_docker

# Processar comando
case "${1:-help}" in
    start)
        start_services
        ;;
    stop)
        stop_services
        ;;
    restart)
        restart_services
        ;;
    rebuild)
        rebuild_services
        ;;
    logs)
        show_logs
        ;;
    api-logs)
        show_api_logs
        ;;
    worker-logs)
        show_worker_logs
        ;;
    frontend-logs)
        show_frontend_logs
        ;;
    shell)
        open_api_shell
        ;;
    frontend-shell)
        open_frontend_shell
        ;;
    clean)
        clean_docker
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        print_error "Comando desconhecido: $1"
        echo ""
        show_help
        exit 1
        ;;
esac 