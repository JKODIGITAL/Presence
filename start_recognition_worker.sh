#!/bin/bash
# Script para iniciar Recognition Worker

echo "🚀 Iniciando Recognition Worker..."

# Verificar se estamos no diretório correto
if [ ! -d "app" ]; then
    echo "❌ Erro: Diretório 'app' não encontrado. Execute este script do diretório raiz do projeto."
    exit 1
fi

# Verificar se Recognition Worker já está rodando
if curl -s http://localhost:17235/health > /dev/null 2>&1; then
    echo "✅ Recognition Worker já está rodando"
    exit 0
fi

# Mudar para diretório app
cd app

# Verificar se o arquivo main.py existe
if [ ! -f "recognition_worker/main.py" ]; then
    echo "❌ Erro: recognition_worker/main.py não encontrado"
    exit 1
fi

echo "📂 Executando Recognition Worker..."

# Iniciar Recognition Worker
python3 recognition_worker/main.py &

# Armazenar PID
echo $! > ../recognition_worker.pid

# Aguardar inicialização
echo "⏳ Aguardando inicialização..."
sleep 5

# Verificar se está rodando
if curl -s http://localhost:17235/health > /dev/null 2>&1; then
    echo "✅ Recognition Worker iniciado com sucesso!"
    echo "📍 Endpoint: http://localhost:17235"
    echo "🔢 PID: $(cat ../recognition_worker.pid)"
else
    echo "❌ Falha ao iniciar Recognition Worker"
    exit 1
fi