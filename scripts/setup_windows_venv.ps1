# Script PowerShell para setup completo do ambiente Windows venv
# Execute como Administrator se necessário

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   PRESENCE SYSTEM - Windows Setup" -ForegroundColor Cyan  
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Função para verificar se comando existe
function Test-Command($cmdname) {
    return [bool](Get-Command -Name $cmdname -ErrorAction SilentlyContinue)
}

# 1. Verificar dependências básicas
Write-Host "[1/6] Verificando dependências..." -ForegroundColor Yellow

# Verificar conda
if (-not (Test-Command "conda")) {
    Write-Host "❌ conda não encontrado. Instale Miniconda/Anaconda primeiro." -ForegroundColor Red
    Write-Host "Download: https://docs.conda.io/en/latest/miniconda.html" -ForegroundColor Blue
    exit 1
}
Write-Host "✓ conda encontrado" -ForegroundColor Green

# Verificar Node.js
if (-not (Test-Command "node")) {
    Write-Host "❌ Node.js não encontrado. Instale Node.js primeiro." -ForegroundColor Red
    Write-Host "Download: https://nodejs.org/" -ForegroundColor Blue
    exit 1
}
Write-Host "✓ Node.js encontrado" -ForegroundColor Green

# Verificar npm
if (-not (Test-Command "npm")) {
    Write-Host "❌ npm não encontrado. Instale Node.js/npm primeiro." -ForegroundColor Red
    exit 1
}
Write-Host "✓ npm encontrado" -ForegroundColor Green

# Verificar NVIDIA GPU (opcional)
try {
    $gpu = Get-WmiObject -Class Win32_VideoController | Where-Object {$_.Name -like "*NVIDIA*"}
    if ($gpu) {
        Write-Host "✓ NVIDIA GPU detectada: $($gpu.Name)" -ForegroundColor Green
    } else {
        Write-Host "⚠️ NVIDIA GPU não detectada. GPU features serão limitadas." -ForegroundColor Yellow
    }
} catch {
    Write-Host "⚠️ Não foi possível detectar GPU." -ForegroundColor Yellow
}

Write-Host ""

# 2. Criar ambiente conda
Write-Host "[2/6] Configurando ambiente conda..." -ForegroundColor Yellow

# Verificar se ambiente já existe
$envExists = & conda env list | Select-String "presence"
if ($envExists) {
    Write-Host "✓ Ambiente 'presence' já existe" -ForegroundColor Green
    $response = Read-Host "Deseja recriar o ambiente? (y/N)"
    if ($response -eq "y" -or $response -eq "Y") {
        Write-Host "Removendo ambiente existente..." -ForegroundColor Yellow
        & conda env remove -n presence -y
        Write-Host "Criando novo ambiente..." -ForegroundColor Yellow
        & conda create -n presence python=3.10 -y
    }
} else {
    Write-Host "Criando ambiente conda 'presence'..." -ForegroundColor Yellow
    & conda create -n presence python=3.10 -y
}

Write-Host ""

# 3. Instalar dependências Python
Write-Host "[3/6] Instalando dependências Python..." -ForegroundColor Yellow

Write-Host "Instalando PyTorch com CUDA..." -ForegroundColor Blue
& conda run -n presence conda install pytorch torchvision torchaudio pytorch-cuda=11.8 -c pytorch -c nvidia -y

Write-Host "Instalando FAISS-GPU..." -ForegroundColor Blue  
& conda run -n presence conda install pytorch::faiss-gpu -y

Write-Host "Instalando dependências do requirements.txt..." -ForegroundColor Blue
& conda run -n presence pip install -r requirements.txt

Write-Host "Instalando dependências WebRTC adicionais..." -ForegroundColor Blue
& conda run -n presence pip install aiortc aiofiles uvloop

Write-Host ""

# 4. Configurar banco de dados
Write-Host "[4/6] Configurando banco de dados..." -ForegroundColor Yellow

if (-not (Test-Path "app\alembic")) {
    Write-Host "Inicializando Alembic..." -ForegroundColor Blue
    Set-Location "app"
    & conda run -n presence alembic init alembic
    & conda run -n presence alembic revision --autogenerate -m "Initial migration"  
    & conda run -n presence alembic upgrade head
    Set-Location ".."
} else {
    Write-Host "✓ Alembic já configurado" -ForegroundColor Green
}

Write-Host ""

# 5. Configurar frontend
Write-Host "[5/6] Configurando frontend..." -ForegroundColor Yellow

Set-Location "frontend"
if (-not (Test-Path "node_modules")) {
    Write-Host "Instalando dependências npm..." -ForegroundColor Blue
    npm install
} else {
    Write-Host "✓ Dependências npm já instaladas" -ForegroundColor Green
}
Set-Location ".."

Write-Host ""

# 6. Criar diretórios necessários
Write-Host "[6/6] Criando estrutura de diretórios..." -ForegroundColor Yellow

$dirs = @("data", "data\models", "data\images", "data\embeddings", "logs")
foreach ($dir in $dirs) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        Write-Host "✓ Criado: $dir" -ForegroundColor Green
    } else {
        Write-Host "✓ Existe: $dir" -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   SETUP CONCLUÍDO!" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "Para iniciar o sistema, execute:" -ForegroundColor Yellow
Write-Host "  scripts\start_windows_venv.bat" -ForegroundColor Blue
Write-Host ""

Write-Host "Para parar o sistema, execute:" -ForegroundColor Yellow  
Write-Host "  scripts\stop_windows_venv.bat" -ForegroundColor Blue
Write-Host ""

Write-Host "Portas utilizadas:" -ForegroundColor Yellow
Write-Host "  API:        9000" -ForegroundColor Blue
Write-Host "  Recognition: 9001" -ForegroundColor Blue
Write-Host "  WebRTC:     8766" -ForegroundColor Blue  
Write-Host "  Frontend:   3000" -ForegroundColor Blue
Write-Host "  UDP WebRTC: 40000-40100" -ForegroundColor Blue
Write-Host ""

$response = Read-Host "Deseja iniciar o sistema agora? (y/N)"
if ($response -eq "y" -or $response -eq "Y") {
    Write-Host "Iniciando sistema..." -ForegroundColor Green
    Start-Process -FilePath "scripts\start_windows_venv.bat" -WorkingDirectory $PWD
}