# Install Socket.IO in MSYS2 environment
# This script installs Socket.IO specifically for the Camera Worker

function Write-ColorText {
    param([string]$Text, [string]$Color = "White")
    Write-Host $Text -ForegroundColor $Color
}

Write-Host ""
Write-ColorText "=== INSTALACAO SOCKET.IO PARA MSYS2 ===" "Cyan"
Write-Host ""

# Verificar se MSYS2 está instalado
$msysPath = "C:\msys64\mingw64\bin\python.exe"
if (!(Test-Path $msysPath)) {
    Write-ColorText "MSYS2 Python nao encontrado" "Red"
    exit 1
}

Write-ColorText "MSYS2 Python encontrado" "Green"

# Instalar Socket.IO
Write-ColorText "Instalando python-socketio..." "Cyan"
$installCmd = 'C:\msys64\usr\bin\bash.exe -lc "cd /mingw64; python -m pip install python-socketio[client] aiohttp"'

try {
    Invoke-Expression $installCmd
    if ($LASTEXITCODE -eq 0) {
        Write-ColorText "Socket.IO instalado com sucesso" "Green"
    } else {
        Write-ColorText "Possivel erro na instalacao" "Yellow"
    }
} catch {
    Write-ColorText "Erro ao instalar Socket.IO" "Red"
}

# Testar instalação
Write-ColorText "Testando instalacao..." "Cyan"
$testCmd = 'C:\msys64\usr\bin\bash.exe -lc "cd /mingw64; python -c ""import socketio; print(socketio.__version__)"""'

try {
    $result = Invoke-Expression $testCmd
    if ($result -match "\d+\.\d+") {
        Write-ColorText "Socket.IO funcionando corretamente" "Green"
        Write-ColorText "Versao: $result" "White"
    } else {
        Write-ColorText "Socket.IO nao esta funcionando" "Red"
    }
} catch {
    Write-ColorText "Erro ao testar Socket.IO" "Red"
}

Write-Host ""
Write-ColorText "Agora execute: .\start-system-webrtc.ps1" "Cyan"
Write-Host ""
Write-ColorText "Pressione qualquer tecla para sair..." "Gray"
$null = $Host.UI.RawUI.ReadKey('NoEcho,IncludeKeyDown')