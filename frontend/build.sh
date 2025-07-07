#!/bin/bash

# Script de build robusto para o frontend
set -e

echo "🚀 Iniciando build do frontend..."

# Limpar cache e dependências se necessário
if [ "$1" = "--clean" ]; then
    echo "🧹 Limpando cache e dependências..."
    rm -rf node_modules package-lock.json
    npm cache clean --force
fi

# Verificar se node_modules existe
if [ ! -d "node_modules" ]; then
    echo "📦 Instalando dependências..."
    rm -f package-lock.json
    npm install --include=optional
fi

# Verificar se TypeScript está disponível
if ! command -v npx &> /dev/null; then
    echo "❌ npx não encontrado"
    exit 1
fi

echo "🔍 Verificando TypeScript..."
npx tsc --version

echo "🏗️  Compilando TypeScript..."
npx tsc --noEmit

echo "📦 Construindo com Vite..."
# Garantir que todas as dependências estão instaladas
npm install --include=optional --silent
npx vite build

echo "✅ Build concluído com sucesso!"

# Verificar se dist foi criado
if [ -d "dist" ]; then
    echo "📁 Diretório dist criado com sucesso:"
    ls -la dist/
else
    echo "❌ Erro: Diretório dist não foi criado"
    exit 1
fi