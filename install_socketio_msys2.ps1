#!/usr/bin/env pwsh
# ============================================================================
# INSTALL SOCKET.IO IN MSYS2 - Instalação rápida do Socket.IO no MSYS2
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

Write-Banner "INSTALAÇÃO SOCKET.IO NO MSYS2"

# Verificar se MSYS2 existe
$msysPath = "C:\msys64\mingw64\bin\python.exe"
if (!(Test-Path $msysPath)) {
    Write-ColorText "❌ MSYS2 Python não encontrado" "Red"
    exit 1
}

Write-ColorText "✅ MSYS2 Python encontrado" "Green"

# Instalar Socket.IO
Write-ColorText "📦 Instalando python-socketio..." "Cyan"
$installCmd = 'C:\msys64\usr\bin\bash.exe -lc "cd /mingw64; python -m pip install python-socketio[client] aiohttp"'

try {
    Invoke-Expression $installCmd
    if ($LASTEXITCODE -eq 0) {
        Write-ColorText "✅ Socket.IO instalado com sucesso" "Green"
    } else {
        Write-ColorText "⚠️ Possível erro na instalação" "Yellow"
    }
} catch {
    Write-ColorText "❌ Erro ao instalar Socket.IO" "Red"
}

# Testar instalação
Write-ColorText "🧪 Testando instalação..." "Cyan"
$testCmd = 'C:\msys64\usr\bin\bash.exe -lc "cd /mingw64; python -c \"import socketio; print(\'Socket.IO OK:\', socketio.__version__)\""'

try {
    $result = Invoke-Expression $testCmd
    if ($result -match "Socket.IO OK:") {
        Write-ColorText "✅ Socket.IO funcionando corretamente" "Green"
        Write-ColorText "Versão: $result" "White"
    } else {
        Write-ColorText "❌ Socket.IO não está funcionando" "Red"
    }
} catch {
    Write-ColorText "❌ Erro ao testar Socket.IO" "Red"
}

Write-Host ""
Write-ColorText "Agora execute: .\start-system-webrtc.ps1" "Cyan"
Write-Host ""
Write-ColorText "Pressione qualquer tecla para sair..." "Gray"
$null = $Host.UI.RawUI.ReadKey('NoEcho,IncludeKeyDown')
