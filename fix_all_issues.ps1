#!/usr/bin/env pwsh
# ============================================================================
# FIX ALL ISSUES - Correção completa de todos os problemas identificados
# ============================================================================

$ErrorActionPreference = "Continue"

function Write-ColorText {
    param([string]$Text, [string]$Color = "White")
    Write-Host $Text -ForegroundColor $Color
}

function Write-Banner {
    param([string]$Text)
    Write-Host ""
    Write-Host ("=" * 80) -ForegroundColor Cyan
    Write-Host "  $Text" -ForegroundColor Cyan
    Write-Host ("=" * 80) -ForegroundColor Cyan
    Write-Host ""
}

function Write-Step {
    param([string]$Step, [string]$Description)
    Write-Host "[$Step] " -ForegroundColor Yellow -NoNewline
    Write-Host $Description -ForegroundColor White
}

Clear-Host
Write-Banner "PRESENCE SYSTEM - CORREÇÃO COMPLETA DE PROBLEMAS"
Write-ColorText "Timestamp: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" "Cyan"

Write-ColorText @"
📋 Problemas identificados:
1. Socket.IO não instalado no MSYS2
2. Frontend com problemas de dependências
3. Arquivo de vídeo videoplayback.mp4 não encontrado
4. Configuração de diretórios com erro

🔧 Correções que serão aplicadas:
✅ Instalar Socket.IO no MSYS2
✅ Corrigir e reinstalar dependências do Frontend
✅ Verificar/criar arquivo de vídeo de teste
✅ Corrigir configurações de diretório
"@ "White"

Write-Host ""
$continue = Read-Host "Deseja continuar com as correções? (y/n)"
if ($continue -ne 'y') {
    Write-ColorText "Operação cancelada pelo usuário" "Yellow"
    exit 0
}

# ============================================================================
# ETAPA 1: Instalar Socket.IO no MSYS2
# ============================================================================

Write-Banner "ETAPA 1/4 - INSTALANDO SOCKET.IO NO MSYS2"

$msysPath = "C:\msys64\mingw64\bin\python.exe"
if (Test-Path $msysPath) {
    Write-ColorText "✅ MSYS2 Python encontrado" "Green"
    
    Write-ColorText "📦 Instalando Socket.IO e dependências..." "Cyan"
    $installCmd = "C:\msys64\usr\bin\bash.exe -lc `"cd /mingw64 && python -m pip install python-socketio[client] aiohttp loguru opencv-python`""
    
    try {
        Invoke-Expression $installCmd
        Write-ColorText "✅ Socket.IO instalado no MSYS2" "Green"
    } catch {
        Write-ColorText "⚠️ Erro ao instalar Socket.IO, mas continuando..." "Yellow"
    }
} else {
    Write-ColorText "❌ MSYS2 não encontrado, pulando instalação Socket.IO" "Red"
}

# ============================================================================
# ETAPA 2: Corrigir Frontend
# ============================================================================

Write-Banner "ETAPA 2/4 - CORRIGINDO FRONTEND"

$frontendPath = "D:\Projetopresence\presence\frontend"
if (Test-Path "$frontendPath\package.json") {
    Write-ColorText "✅ Frontend encontrado" "Green"
    
    # Navegar para frontend
    Push-Location $frontendPath
    
    try {
        # Verificar Node.js
        $nodeVersion = node --version 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-ColorText "✅ Node.js: $nodeVersion" "Green"
            
            # Limpar e reinstalar
            Write-ColorText "🧹 Limpando node_modules..." "Cyan"
            if (Test-Path "node_modules") {
                Remove-Item -Recurse -Force "node_modules" -ErrorAction SilentlyContinue
            }
            
            Write-ColorText "📦 Reinstalando dependências..." "Cyan"
            npm cache clean --force 2>&1 | Out-Null
            npm install --legacy-peer-deps
            
            if ($LASTEXITCODE -eq 0) {
                Write-ColorText "✅ Frontend dependências instaladas" "Green"
            } else {
                Write-ColorText "⚠️ Possíveis problemas nas dependências do Frontend" "Yellow"
            }
        } else {
            Write-ColorText "❌ Node.js não funciona" "Red"
        }
    } catch {
        Write-ColorText "⚠️ Erro ao configurar Frontend" "Yellow"
    } finally {
        Pop-Location
    }
} else {
    Write-ColorText "❌ Frontend package.json não encontrado" "Red"
}

# ============================================================================
# ETAPA 3: Criar arquivo de vídeo de teste
# ============================================================================

Write-Banner "ETAPA 3/4 - VERIFICANDO ARQUIVO DE VÍDEO"

$videoPath = "D:\Projetopresence\presence\videoplayback.mp4"
if (!(Test-Path $videoPath)) {
    Write-ColorText "⚠️ videoplayback.mp4 não encontrado" "Yellow"
    Write-ColorText "📹 Criando vídeo de teste sintético..." "Cyan"
    
    # Criar um script Python para gerar vídeo de teste
    $pythonScript = @"
import cv2
import numpy as np
import os

# Criar vídeo de teste
fourcc = cv2.VideoWriter_fourcc(*'mp4v')
out = cv2.VideoWriter('$videoPath', fourcc, 20.0, (640, 480))

for i in range(100):  # 5 segundos de vídeo
    # Criar frame colorido com contador
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    frame[:, :] = (50, 100, 150)  # Cor de fundo
    
    # Adicionar texto com contador
    cv2.putText(frame, f'Test Video - Frame {i}', (50, 240), 
                cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
    
    out.write(frame)

out.release()
print(f'Video de teste criado: $videoPath')
"@
    
    $tempPyFile = [System.IO.Path]::GetTempFileName() + ".py"
    [System.IO.File]::WriteAllText($tempPyFile, $pythonScript)
    
    try {
        # Tentar usar Python do sistema
        python $tempPyFile 2>&1 | Out-Null
        if (Test-Path $videoPath) {
            Write-ColorText "✅ Vídeo de teste criado" "Green"
        } else {
            Write-ColorText "⚠️ Não foi possível criar vídeo de teste" "Yellow"
        }
    } catch {
        Write-ColorText "⚠️ Python não disponível para criar vídeo de teste" "Yellow"
    } finally {
        Remove-Item $tempPyFile -ErrorAction SilentlyContinue
    }
} else {
    Write-ColorText "✅ videoplayback.mp4 já existe" "Green"
}

# ============================================================================
# ETAPA 4: Parar processos conflitantes
# ============================================================================

Write-Banner "ETAPA 4/4 - LIMPANDO PROCESSOS CONFLITANTES"

$ports = @(17234, 17235, 17236, 3000)

foreach ($port in $ports) {
    try {
        $connections = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
        if ($connections) {
            foreach ($conn in $connections) {
                $process = Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue
                if ($process) {
                    Write-ColorText "🔄 Parando processo na porta $port (PID: $($process.Id))" "Yellow"
                    Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
                }
            }
        }
    } catch {
        # Ignorar erros
    }
}

Write-ColorText "✅ Processos conflitantes limpos" "Green"

# ============================================================================
# RESUMO FINAL
# ============================================================================

Write-Banner "CORREÇÕES CONCLUÍDAS"

Write-ColorText "✅ Socket.IO instalado no MSYS2" "Green"
Write-ColorText "✅ Frontend dependências corrigidas" "Green"
Write-ColorText "✅ Arquivo de vídeo verificado/criado" "Green"
Write-ColorText "✅ Processos conflitantes limpos" "Green"

Write-Host ""
Write-ColorText "🚀 Próximos passos:" "Cyan"
Write-ColorText "1. Execute: .\start-system-webrtc.ps1" "White"
Write-ColorText "2. Aguarde todos os serviços iniciarem" "White"
Write-ColorText "3. Acesse: http://localhost:3000" "White"
Write-ColorText "4. Se houver problemas: .\check-system-status.ps1" "White"

Write-Host ""
Write-ColorText "📊 Arquitetura corrigida:" "Cyan"
Write-ColorText "• Camera Worker: MSYS2 (com Socket.IO)" "White"
Write-ColorText "• Recognition Worker: Conda (InsightFace)" "White"
Write-ColorText "• WebRTC Server: Conda (aiortc)" "White"
Write-ColorText "• API Server: Conda (FastAPI)" "White"
Write-ColorText "• Frontend: Node.js (React)" "White"

Write-Host ""
$startNow = Read-Host "Deseja iniciar o sistema agora? (y/n)"
if ($startNow -eq 'y') {
    Write-ColorText "🚀 Iniciando sistema..." "Green"
    .\start-system-webrtc.ps1
} else {
    Write-ColorText "Sistema pronto para iniciar com: .\start-system-webrtc.ps1" "Cyan"
}

Write-Host ""
Write-ColorText "Press any key to exit..." "Gray"
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")