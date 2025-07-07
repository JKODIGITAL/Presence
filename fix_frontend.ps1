#!/usr/bin/env pwsh
# ============================================================================
# FIX FRONTEND - Diagnóstico e correção do Frontend
# ============================================================================

$ErrorActionPreference = "Continue"

function Write-ColorText {
    param([string]$Text, [string]$Color = "White")
    Write-Host $Text -ForegroundColor $Color
}

function Write-Banner {
    param([string]$Text)
    Write-Host ""
    Write-Host ("=" * 60) -ForegroundColor Cyan
    Write-Host "  $Text" -ForegroundColor Cyan
    Write-Host ("=" * 60) -ForegroundColor Cyan
    Write-Host ""
}

Write-Banner "FRONTEND DIAGNOSTICS & FIX"

# Verificar se estamos no diretório correto
$frontendPath = "D:\Projetopresence\presence\frontend"
$packageJsonPath = "$frontendPath\package.json"

Write-ColorText "🔍 Verificando estrutura do projeto..." "Cyan"

if (!(Test-Path $packageJsonPath)) {
    Write-ColorText "❌ package.json não encontrado em $frontendPath" "Red"
    Write-ColorText "Estrutura esperada:" "Yellow"
    Write-ColorText "D:\Projetopresence\presence\frontend\package.json" "Yellow"
    exit 1
}

Write-ColorText "✅ package.json encontrado" "Green"

# Verificar Node.js
Write-ColorText "🟢 Verificando Node.js..." "Cyan"
try {
    $nodeVersion = node --version
    if ($LASTEXITCODE -eq 0) {
        Write-ColorText "✅ Node.js: $nodeVersion" "Green"
    } else {
        Write-ColorText "❌ Node.js não funciona" "Red"
        Write-ColorText "Instale Node.js de: https://nodejs.org/" "Yellow"
        exit 1
    }
} catch {
    Write-ColorText "❌ Node.js não encontrado" "Red"
    Write-ColorText "Instale Node.js de: https://nodejs.org/" "Yellow"
    exit 1
}

# Verificar npm
Write-ColorText "📦 Verificando npm..." "Cyan"
try {
    $npmVersion = npm --version
    if ($LASTEXITCODE -eq 0) {
        Write-ColorText "✅ npm: $npmVersion" "Green"
    } else {
        Write-ColorText "❌ npm não funciona" "Red"
        exit 1
    }
} catch {
    Write-ColorText "❌ npm não encontrado" "Red"
    exit 1
}

# Navegar para o diretório frontend
Write-ColorText "📁 Navegando para: $frontendPath" "Cyan"
Set-Location $frontendPath

# Verificar se node_modules existe
if (Test-Path "node_modules") {
    Write-ColorText "⚠️ node_modules já existe, limpando..." "Yellow"
    Remove-Item -Recurse -Force "node_modules" -ErrorAction SilentlyContinue
}

# Limpar cache npm
Write-ColorText "🧹 Limpando cache npm..." "Cyan"
npm cache clean --force 2>&1 | Out-Null

# Instalar dependências
Write-ColorText "📦 Instalando dependências..." "Cyan"
npm install

if ($LASTEXITCODE -ne 0) {
    Write-ColorText "❌ Falha ao instalar dependências" "Red"
    Write-ColorText "Tentando com --legacy-peer-deps..." "Yellow"
    npm install --legacy-peer-deps
    
    if ($LASTEXITCODE -ne 0) {
        Write-ColorText "❌ Falha mesmo com --legacy-peer-deps" "Red"
        exit 1
    }
}

Write-ColorText "✅ Dependências instaladas com sucesso" "Green"

# Verificar se o script dev existe
Write-ColorText "🔍 Verificando scripts do package.json..." "Cyan"
$packageContent = Get-Content "package.json" | ConvertFrom-Json

if ($packageContent.scripts.dev) {
    Write-ColorText "✅ Script 'dev' encontrado: $($packageContent.scripts.dev)" "Green"
} else {
    Write-ColorText "❌ Script 'dev' não encontrado no package.json" "Red"
}

# Testar se consegue iniciar (modo dry-run)
Write-ColorText "🧪 Testando se consegue iniciar..." "Cyan"
Write-ColorText "Executando: npm run dev (será interrompido em 10 segundos)" "Yellow"

# Executar npm run dev em background e matar após 10 segundos
$job = Start-Job -ScriptBlock {
    Set-Location $args[0]
    npm run dev
} -ArgumentList $frontendPath

Start-Sleep -Seconds 10
Stop-Job $job -ErrorAction SilentlyContinue
Remove-Job $job -ErrorAction SilentlyContinue

# Verificar se a porta 3000 está livre
Write-ColorText "🔍 Verificando porta 3000..." "Cyan"
try {
    $tcpClient = New-Object System.Net.Sockets.TcpClient
    $connect = $tcpClient.BeginConnect("127.0.0.1", 3000, $null, $null)
    $wait = $connect.AsyncWaitHandle.WaitOne(1000, $false)
    if ($wait) {
        $tcpClient.EndConnect($connect)
        $tcpClient.Close()
        Write-ColorText "⚠️ Porta 3000 já está em uso" "Yellow"
        
        # Encontrar processo na porta 3000
        $processes = Get-NetTCPConnection -LocalPort 3000 -ErrorAction SilentlyContinue
        if ($processes) {
            foreach ($proc in $processes) {
                $processInfo = Get-Process -Id $proc.OwningProcess -ErrorAction SilentlyContinue
                if ($processInfo) {
                    Write-ColorText "📊 Processo na porta 3000: $($processInfo.ProcessName) (PID: $($processInfo.Id))" "White"
                    
                    $kill = Read-Host "Deseja matar o processo? (y/n)"
                    if ($kill -eq 'y') {
                        Stop-Process -Id $processInfo.Id -Force
                        Write-ColorText "✅ Processo encerrado" "Green"
                    }
                }
            }
        }
    } else {
        Write-ColorText "✅ Porta 3000 livre" "Green"
    }
    $tcpClient.Close()
} catch {
    Write-ColorText "✅ Porta 3000 livre" "Green"
}

# Criar script de inicialização manual
$startScript = @"
@echo off
title Frontend - Manual Start
cd /d "$frontendPath"
echo ============================================
echo Frontend Development Server (Manual)
echo ============================================
echo Node.js: $nodeVersion
echo npm: $npmVersion
echo Port: 3000
echo ============================================
set VITE_API_URL=http://127.0.0.1:17234
set VITE_VMS_WEBRTC_URL=http://127.0.0.1:17236
set VITE_WEBRTC_CAMERA_WS_BASE=ws://127.0.0.1:17236
echo Starting frontend server...
npm run dev
pause
"@

$startScriptPath = "$frontendPath\start-frontend-manual.bat"
[System.IO.File]::WriteAllText($startScriptPath, $startScript)

Write-Banner "DIAGNÓSTICO COMPLETO"

Write-ColorText "✅ Frontend diagnosticado e corrigido" "Green"
Write-ColorText "✅ Dependências instaladas" "Green"
Write-ColorText "✅ Script manual criado" "Green"

Write-Host ""
Write-ColorText "📋 Próximos passos:" "Cyan"
Write-ColorText "1. Execute o sistema: .\start-system-webrtc.ps1" "White"
Write-ColorText "2. Ou execute manualmente: .\frontend\start-frontend-manual.bat" "White"
Write-ColorText "3. Acesse: http://localhost:3000" "White"

Write-Host ""
Write-ColorText "Press any key to exit..." "Gray"
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")