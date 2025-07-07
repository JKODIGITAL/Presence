#!/bin/bash
# Script para iniciar o Camera Worker com Hot Reload

set -e

# Configurar variáveis de ambiente
export PYTHONPATH=/root/presence
export INSIGHTFACE_HOME=/root/presence/data/models
# API_BASE_URL é configurado via docker-compose (não sobrescrever)
export ENVIRONMENT=development

echo "🔥 Iniciando Camera Worker com Hot Reload..."

# Verificar se a aplicação existe
if [ ! -f "/root/presence/app/camera_worker/main.py" ]; then
    echo "❌ Erro: app/camera_worker/main.py não encontrado. Verifique se o volume está montado corretamente."
    exit 1
fi

# Aguardar a API estar disponível com timeout
echo "⏳ Aguardando API estar disponível..."
timeout=60
elapsed=0
until curl -s ${API_BASE_URL:-http://localhost:9000}/health > /dev/null 2>&1; do
    if [ $elapsed -ge $timeout ]; then
        echo "❌ Timeout aguardando API. Continuando mesmo assim..."
        break
    fi
    echo "API ainda não disponível, aguardando... ($elapsed/$timeout)s"
    sleep 5
    elapsed=$((elapsed + 5))
done

if curl -s ${API_BASE_URL:-http://localhost:9000}/health > /dev/null 2>&1; then
    echo "✅ API disponível!"
else
    echo "⚠️ API não disponível, mas continuando..."
fi

# Aguardar um pouco para garantir que dependências estão carregadas
sleep 3

echo "🚀 Iniciando Camera Worker..."

# Executar o worker diretamente
exec conda run --no-capture-output -n presence python -m app.camera_worker.main 