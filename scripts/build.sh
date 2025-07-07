#!/bin/bash
# Script para construir as imagens base do Presence

set -e

echo "🚀 Iniciando build das imagens base do Presence..."

# Verificar se o Docker está instalado
if ! command -v docker &> /dev/null; then
    echo "❌ Docker não está instalado. Por favor, instale o Docker primeiro."
    exit 1
fi

# Construir imagem base da API
echo "🔨 Construindo imagem base da API..."
docker build -t presence-api-base:latest -f docker/Dockerfile.api-base .

# Construir imagem base do Camera Worker
echo "🔨 Construindo imagem base do Camera Worker..."
docker build -t presence-worker-base:latest -f docker/Dockerfile.worker-base .

# Construir imagem base do Frontend
echo "🔨 Construindo imagem base do Frontend..."
docker build -t presence-frontend-base:latest -f docker/Dockerfile.frontend-base ./frontend

echo "✅ Todas as imagens base foram construídas com sucesso!"
echo ""
echo "Para construir as imagens finais, execute:"
echo "docker-compose build"
echo ""
echo "Para iniciar os serviços, execute:"
echo "docker-compose up -d" 