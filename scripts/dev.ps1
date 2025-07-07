# Script de desenvolvimento para Presence (PowerShell)
# Uso: .\scripts\dev.ps1 [comando]

param(
    [Parameter(Position=0)]
    [string]$Command = "help"
)

# Função para imprimir mensagens coloridas
function Write-Status {
    param([string]$Message)
    Write-Host "[INFO] $Message" -ForegroundColor Blue
}

function Write-Success {
    param([string]$Message)
    Write-Host "[SUCCESS] $Message" -ForegroundColor Green
}

function Write-Warning {
    param([string]$Message)
    Write-Host "[WARNING] $Message" -ForegroundColor Yellow
}

function Write-Error {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

# Função para mostrar ajuda
function Show-Help {
    Write-Host "Script de desenvolvimento para Presence" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Uso: .\scripts\dev.ps1 [comando]"
    Write-Host ""
    Write-Host "Comandos disponíveis:"
    Write-Host "  start     - Inicia todos os serviços em modo desenvolvimento"
    Write-Host "  stop      - Para todos os serviços"
    Write-Host "  restart   - Reinicia todos os serviços"
    Write-Host "  rebuild   - Reconstrói as imagens Docker"
    Write-Host "  logs      - Mostra logs de todos os serviços"
    Write-Host "  api-logs  - Mostra logs apenas da API"
    Write-Host "  worker-logs - Mostra logs apenas do worker"
    Write-Host "  frontend-logs - Mostra logs apenas do frontend"
    Write-Host "  shell     - Abre shell no container da API"
    Write-Host "  frontend-shell - Abre shell no container do frontend"
    Write-Host "  clean     - Remove containers e volumes não utilizados"
    Write-Host "  help      - Mostra esta ajuda"
    Write-Host ""
    Write-Host "Exemplos:"
    Write-Host "  .\scripts\dev.ps1 start"
    Write-Host "  .\scripts\dev.ps1 logs"
    Write-Host "  .\scripts\dev.ps1 shell"
}

# Função para verificar se Docker está rodando
function Test-Docker {
    try {
        docker info | Out-Null
        return $true
    }
    catch {
        return $false
    }
}

# Função para iniciar serviços
function Start-Services {
    Write-Status "Iniciando serviços em modo desenvolvimento..."
    docker-compose -f docker-compose.dev.yml up -d
    Write-Success "Serviços iniciados!"
    Write-Status "API: http://localhost:9000"
    Write-Status "Frontend: http://localhost:3000"
    Write-Status "Use '.\scripts\dev.ps1 logs' para ver os logs"
}

# Função para parar serviços
function Stop-Services {
    Write-Status "Parando serviços..."
    docker-compose -f docker-compose.dev.yml down
    Write-Success "Serviços parados!"
}

# Função para reiniciar serviços
function Restart-Services {
    Write-Status "Reiniciando serviços..."
    docker-compose -f docker-compose.dev.yml restart
    Write-Success "Serviços reiniciados!"
}

# Função para reconstruir imagens
function Rebuild-Services {
    Write-Status "Reconstruindo imagens Docker..."
    docker-compose -f docker-compose.dev.yml build --no-cache
    Write-Success "Imagens reconstruídas!"
    Write-Status "Use '.\scripts\dev.ps1 start' para iniciar os serviços"
}

# Função para mostrar logs
function Show-Logs {
    Write-Status "Mostrando logs de todos os serviços..."
    docker-compose -f docker-compose.dev.yml logs -f
}

# Função para mostrar logs da API
function Show-ApiLogs {
    Write-Status "Mostrando logs da API..."
    docker-compose -f docker-compose.dev.yml logs -f presence-api
}

# Função para mostrar logs do worker
function Show-WorkerLogs {
    Write-Status "Mostrando logs do worker..."
    docker-compose -f docker-compose.dev.yml logs -f presence-camera-worker
}

# Função para mostrar logs do frontend
function Show-FrontendLogs {
    Write-Status "Mostrando logs do frontend..."
    docker-compose -f docker-compose.dev.yml logs -f presence-frontend
}

# Função para abrir shell na API
function Open-ApiShell {
    Write-Status "Abrindo shell no container da API..."
    docker-compose -f docker-compose.dev.yml exec presence-api bash
}

# Função para abrir shell no frontend
function Open-FrontendShell {
    Write-Status "Abrindo shell no container do frontend..."
    docker-compose -f docker-compose.dev.yml exec presence-frontend bash
}

# Função para limpar containers não utilizados
function Clean-Docker {
    Write-Status "Limpando containers e volumes não utilizados..."
    docker system prune -f
    docker volume prune -f
    Write-Success "Limpeza concluída!"
}

# Verificar se Docker está rodando
if (-not (Test-Docker)) {
    Write-Error "Docker não está rodando. Inicie o Docker primeiro."
    exit 1
}

# Processar comando
switch ($Command.ToLower()) {
    "start" {
        Start-Services
    }
    "stop" {
        Stop-Services
    }
    "restart" {
        Restart-Services
    }
    "rebuild" {
        Rebuild-Services
    }
    "logs" {
        Show-Logs
    }
    "api-logs" {
        Show-ApiLogs
    }
    "worker-logs" {
        Show-WorkerLogs
    }
    "frontend-logs" {
        Show-FrontendLogs
    }
    "shell" {
        Open-ApiShell
    }
    "frontend-shell" {
        Open-FrontendShell
    }
    "clean" {
        Clean-Docker
    }
    "help" {
        Show-Help
    }
    default {
        Write-Error "Comando desconhecido: $Command"
        Write-Host ""
        Show-Help
        exit 1
    }
} 