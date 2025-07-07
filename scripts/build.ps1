# Script para construir as imagens Docker do projeto Presence (Windows)

# Função para exibir mensagens
function Log {
    param([string]$message)
    Write-Host "[$([DateTime]::Now.ToString('HH:mm:ss'))] $message" -ForegroundColor Blue
}

# Função para exibir mensagens de sucesso
function Success {
    param([string]$message)
    Write-Host "[$([DateTime]::Now.ToString('HH:mm:ss'))] ✅ $message" -ForegroundColor Green
}

# Função para exibir avisos
function Warn {
    param([string]$message)
    Write-Host "[$([DateTime]::Now.ToString('HH:mm:ss'))] ⚠️ $message" -ForegroundColor Yellow
}

# Função para exibir erros
function Error {
    param([string]$message)
    Write-Host "[$([DateTime]::Now.ToString('HH:mm:ss'))] ❌ $message" -ForegroundColor Red
}

# Verificar se o Docker está instalado
try {
    docker --version | Out-Null
} catch {
    Error "Docker não está instalado. Por favor, instale o Docker primeiro."
    exit 1
}

# Verificar se o Docker Compose está instalado
$dockerCompose = "docker-compose"
try {
    & $dockerCompose --version | Out-Null
} catch {
    Warn "Docker Compose não encontrado, tentando usar 'docker compose'..."
    $dockerCompose = "docker compose"
    try {
        & docker compose version | Out-Null
    } catch {
        Error "Docker Compose não está instalado. Por favor, instale o Docker Compose primeiro."
        exit 1
    }
}

# Criar diretórios necessários para scripts
if (-not (Test-Path "docker/scripts")) {
    New-Item -Path "docker/scripts" -ItemType Directory -Force | Out-Null
}

# Função para construir as imagens base
function Build-BaseImages {
    Log "Construindo imagem base comum..."
    docker build -t presence-common-base:latest -f docker/Dockerfile.common-base .
    Success "Imagem base comum construída com sucesso!"

    Log "Construindo imagem base da API..."
    docker build -t presence-api-base:latest -f docker/Dockerfile.api-base .
    Success "Imagem base da API construída com sucesso!"

    Log "Construindo imagem base do Camera Worker..."
    docker build -t presence-worker-base:latest -f docker/Dockerfile.worker-base .
    Success "Imagem base do Camera Worker construída com sucesso!"

    Log "Construindo imagem base do Frontend..."
    docker build -t presence-frontend-base:latest -f docker/Dockerfile.frontend-base ./frontend
    Success "Imagem base do Frontend construída com sucesso!"
}

# Função para construir as imagens de aplicação
function Build-AppImages {
    Log "Construindo imagens de aplicação com docker-compose..."
    & $dockerCompose build
    Success "Imagens de aplicação construídas com sucesso!"
}

# Menu principal
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "🐳 Construção de Imagens Docker do Projeto Presence" -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Escolha uma opção:"
Write-Host "1) Construir apenas imagens base"
Write-Host "2) Construir apenas imagens de aplicação"
Write-Host "3) Construir todas as imagens (base + aplicação)"
Write-Host "4) Iniciar serviços com Hot Reload"
Write-Host "5) Parar todos os serviços"
Write-Host "q) Sair"
Write-Host ""

$option = Read-Host "Opção"

switch ($option) {
    "1" {
        Build-BaseImages
    }
    "2" {
        Build-AppImages
    }
    "3" {
        Build-BaseImages
        Build-AppImages
    }
    "4" {
        Log "Iniciando serviços com Hot Reload..."
        & $dockerCompose up -d
        Success "Serviços iniciados com sucesso!"
        Write-Host ""
        Write-Host "📋 Serviços disponíveis:" -ForegroundColor Cyan
        Write-Host "- API: http://localhost:9000"
        Write-Host "- Frontend: http://localhost"
    }
    "5" {
        Log "Parando todos os serviços..."
        & $dockerCompose down
        Success "Serviços parados com sucesso!"
    }
    "q" {
        Log "Saindo..."
        exit 0
    }
    default {
        Error "Opção inválida!"
        exit 1
    }
}

Write-Host ""
Success "Operação concluída com sucesso!" 