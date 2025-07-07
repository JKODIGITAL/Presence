#!/bin/bash
# Script para iniciar a API com Hot Reload

set -e

# Configurar variáveis de ambiente
export PYTHONPATH=/root/presence
export INSIGHTFACE_HOME=/root/presence/data/models
export ENVIRONMENT=development

echo "🔥 Iniciando API com Hot Reload..."

# Verificar se a aplicação existe
if [ ! -f "/root/presence/app/api/main.py" ]; then
    echo "❌ Erro: app/api/main.py não encontrado. Verifique se o volume está montado corretamente."
    exit 1
fi

# Aguardar um pouco para garantir que dependências estão carregadas
sleep 2

echo "🚀 Iniciando API com Uvicorn Hot Reload..."

# Usar o conda para executar com hot reload nativo do uvicorn
exec conda run --no-capture-output -n presence uvicorn app.api.main:app \
    --host 0.0.0.0 \
    --port 9000 \
    --reload \
    --reload-dir /root/presence/app \
    --reload-exclude "*.pyc" \
    --reload-exclude "__pycache__" \
    --reload-exclude "*.log" \
    --log-level info \
    --access-log 