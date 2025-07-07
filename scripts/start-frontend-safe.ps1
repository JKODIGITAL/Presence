#!/usr/bin/env pwsh
# Script para iniciar frontend de forma segura
# Uso: .\scripts\start-frontend-safe.ps1

Write-Host "🌐 Iniciando Frontend (modo seguro)..." -ForegroundColor Cyan

# Ir para diretório do frontend
Set-Location "frontend"

Write-Host "📁 Diretório atual: $(Get-Location)" -ForegroundColor Yellow

# Verificar se node_modules existe
if (-not (Test-Path "node_modules")) {
    Write-Host "📦 Instalando dependências..." -ForegroundColor Yellow
    npm install
    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ Falha ao instalar dependências" -ForegroundColor Red
        exit 1
    }
}

# Verificar se o Vite está disponível
if (Test-Path "node_modules\.bin\vite.cmd") {
    Write-Host "✅ Vite encontrado em node_modules\.bin\" -ForegroundColor Green
    Write-Host "🚀 Iniciando servidor de desenvolvimento..." -ForegroundColor Green
    
    # Usar script dev:safe que usa caminho completo do vite
    npm run dev:safe
} elseif (Test-Path "node_modules\vite\bin\vite.js") {
    Write-Host "✅ Vite encontrado em node_modules\vite\bin\" -ForegroundColor Green
    Write-Host "🚀 Iniciando servidor de desenvolvimento..." -ForegroundColor Green
    
    # Usar node diretamente
    node node_modules/vite/bin/vite.js --host 0.0.0.0 --port 3000
} else {
    Write-Host "❌ Vite não encontrado. Reinstalando dependências..." -ForegroundColor Red
    
    # Limpar e reinstalar
    if (Test-Path "node_modules") {
        Remove-Item -Recurse -Force "node_modules"
    }
    if (Test-Path "package-lock.json") {
        Remove-Item "package-lock.json"
    }
    
    Write-Host "📦 Reinstalando dependências..." -ForegroundColor Yellow
    npm install
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "🚀 Tentando iniciar novamente..." -ForegroundColor Green
        npm run dev:safe
    } else {
        Write-Host "❌ Falha ao reinstalar dependências" -ForegroundColor Red
        exit 1
    }
}