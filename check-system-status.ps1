#!/usr/bin/env pwsh
# ============================================================================
# CHECK SYSTEM STATUS - Verificação de saúde de todos os serviços
# ============================================================================

$ErrorActionPreference = "Continue"

function Write-ColorText {
    param([string]$Text, [string]$Color = "White")
    Write-Host $Text -ForegroundColor $Color
}

function Write-Banner {
    param([string]$Text)
    Write-Host ""
    Write-Host ("=" * 70) -ForegroundColor Cyan
    Write-Host "  $Text" -ForegroundColor Cyan
    Write-Host ("=" * 70) -ForegroundColor Cyan
    Write-Host ""
}

function Test-Port {
    param([int]$Port, [int]$TimeoutMs = 1000)
    try {
        $tcpClient = New-Object System.Net.Sockets.TcpClient
        $connect = $tcpClient.BeginConnect("127.0.0.1", $Port, $null, $null)
        $wait = $connect.AsyncWaitHandle.WaitOne($TimeoutMs, $false)
        if ($wait) {
            $tcpClient.EndConnect($connect)
            $tcpClient.Close()
            return $true
        }
        $tcpClient.Close()
        return $false
    }
    catch {
        return $false
    }
}

function Test-HttpEndpoint {
    param([string]$Url, [int]$TimeoutSec = 3)
    try {
        $response = Invoke-WebRequest -Uri $Url -TimeoutSec $TimeoutSec -ErrorAction Stop
        return @{
            Success = $true
            Status = $response.StatusCode
            Content = $response.Content
        }
    }
    catch {
        return @{
            Success = $false
            Status = $null
            Error = $_.Exception.Message
        }
    }
}

function Check-ServiceStatus {
    Write-Banner "VERIFICAÇÃO DE STATUS DOS SERVIÇOS"
    
    $services = @(
        @{
            Name = "API Server"
            Port = 17234
            HealthUrl = "http://127.0.0.1:17234/health"
            Type = "FastAPI"
        },
        @{
            Name = "Recognition Worker"
            Port = 17235
            HealthUrl = "http://127.0.0.1:17235/socket.io/"
            Type = "Socket.IO"
        },
        @{
            Name = "WebRTC Server"
            Port = 17236
            HealthUrl = "http://127.0.0.1:17236/health"
            Type = "aiortc"
        },
        @{
            Name = "Frontend"
            Port = 3000
            HealthUrl = "http://127.0.0.1:3000"
            Type = "Vite/React"
        }
    )
    
    $runningServices = 0
    $totalServices = $services.Count
    
    foreach ($service in $services) {
        Write-ColorText "🔍 Verificando: $($service.Name) [$($service.Type)]" "Cyan"
        
        # Testar porta
        $portOpen = Test-Port $service.Port
        
        if ($portOpen) {
            Write-ColorText "  ✅ Porta $($service.Port): ABERTA" "Green"
            
            # Testar endpoint HTTP se disponível
            if ($service.HealthUrl) {
                $httpTest = Test-HttpEndpoint $service.HealthUrl
                
                if ($httpTest.Success) {
                    Write-ColorText "  ✅ HTTP Health: OK (Status: $($httpTest.Status))" "Green"
                    $runningServices++
                    
                    # Informações específicas por serviço
                    switch ($service.Type) {
                        "FastAPI" {
                            try {
                                $content = $httpTest.Content | ConvertFrom-Json
                                Write-ColorText "  📊 Status: $($content.status), Timestamp: $($content.timestamp)" "White"
                            } catch {
                                Write-ColorText "  📊 Response recebida mas não parseável" "Yellow"
                            }
                        }
                        "Socket.IO" {
                            Write-ColorText "  📡 Socket.IO endpoint acessível" "White"
                        }
                        "aiortc" {
                            Write-ColorText "  🎥 WebRTC server respondendo" "White"
                        }
                        "Vite/React" {
                            Write-ColorText "  🌐 Frontend server ativo" "White"
                        }
                    }
                } else {
                    Write-ColorText "  ❌ HTTP Health: FALHOU - $($httpTest.Error)" "Red"
                }
            } else {
                Write-ColorText "  ⚠️ Porta aberta mas sem endpoint HTTP configurado" "Yellow"
                $runningServices++
            }
        } else {
            Write-ColorText "  ❌ Porta $($service.Port): FECHADA" "Red"
        }
        
        Write-Host ""
    }
    
    return @{
        Running = $runningServices
        Total = $totalServices
        Services = $services
    }
}

function Check-ProcessStatus {
    Write-Banner "VERIFICAÇÃO DE PROCESSOS"
    
    $processNames = @("python", "node", "npm")
    
    foreach ($processName in $processNames) {
        $processes = Get-Process -Name $processName -ErrorAction SilentlyContinue
        
        if ($processes) {
            Write-ColorText "🔍 Processos $processName ativos:" "Cyan"
            foreach ($proc in $processes) {
                $cpuUsage = try { [math]::Round($proc.CPU, 2) } catch { "N/A" }
                $memoryMB = try { [math]::Round($proc.WorkingSet64 / 1MB, 1) } catch { "N/A" }
                Write-ColorText "  📊 PID: $($proc.Id), CPU: ${cpuUsage}s, RAM: ${memoryMB}MB" "White"
            }
        } else {
            Write-ColorText "❌ Nenhum processo $processName encontrado" "Red"
        }
        Write-Host ""
    }
}

function Check-Dependencies {
    Write-Banner "VERIFICAÇÃO DE DEPENDÊNCIAS"
    
    # Verificar Python no MSYS2
    Write-ColorText "🐍 Verificando Python MSYS2..." "Cyan"
    $msysPython = "C:\msys64\mingw64\bin\python.exe"
    if (Test-Path $msysPython) {
        try {
            $version = & $msysPython --version 2>&1
            Write-ColorText "  ✅ MSYS2 Python: $version" "Green"
        } catch {
            Write-ColorText "  ❌ MSYS2 Python não funciona" "Red"
        }
    } else {
        Write-ColorText "  ❌ MSYS2 Python não encontrado" "Red"
    }
    
    # Verificar Python no Conda
    Write-ColorText "🐍 Verificando Python Conda..." "Cyan"
    try {
        $condaResult = cmd /c "call C:\Users\Danilo\miniconda3\Scripts\activate.bat presence && python --version" 2>&1
        if ($condaResult -match "Python") {
            Write-ColorText "  ✅ Conda Python: $condaResult" "Green"
        } else {
            Write-ColorText "  ❌ Conda environment 'presence' com problemas" "Red"
        }
    } catch {
        Write-ColorText "  ❌ Conda não acessível" "Red"
    }
    
    # Verificar Node.js
    Write-ColorText "🟢 Verificando Node.js..." "Cyan"
    try {
        $nodeVersion = node --version 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-ColorText "  ✅ Node.js: $nodeVersion" "Green"
        } else {
            Write-ColorText "  ❌ Node.js não funciona" "Red"
        }
    } catch {
        Write-ColorText "  ❌ Node.js não encontrado" "Red"
    }
    
    Write-Host ""
}

function Show-LogSummary {
    Write-Banner "RESUMO DOS LOGS"
    
    $logFiles = @(
        "logs/recognition-worker.bat",
        "logs/api.bat", 
        "logs/camera-worker.bat",
        "logs/webrtc-server.bat",
        "logs/frontend.bat"
    )
    
    foreach ($logFile in $logFiles) {
        if (Test-Path $logFile) {
            $fileName = Split-Path $logFile -Leaf
            Write-ColorText "📄 $fileName: Existe" "Green"
        } else {
            $fileName = Split-Path $logFile -Leaf
            Write-ColorText "📄 $fileName: Não encontrado" "Yellow"
        }
    }
    
    Write-Host ""
}

function Main {
    Clear-Host
    Write-Banner "PRESENCE SYSTEM - STATUS CHECK"
    Write-ColorText "Timestamp: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" "Cyan"
    
    # Verificar status dos serviços
    $serviceStatus = Check-ServiceStatus
    
    # Verificar processos
    Check-ProcessStatus
    
    # Verificar dependências
    Check-Dependencies
    
    # Mostrar resumo dos logs
    Show-LogSummary
    
    # Resumo final
    Write-Banner "RESUMO GERAL"
    
    $running = $serviceStatus.Running
    $total = $serviceStatus.Total
    $percentage = if ($total -gt 0) { [math]::Round(($running / $total) * 100, 1) } else { 0 }
    
    Write-ColorText "📊 Serviços em execução: $running / $total ($percentage%)" "Cyan"
    
    if ($running -eq $total) {
        Write-ColorText "🎉 Sistema completamente operacional!" "Green"
    } elseif ($running -gt 0) {
        Write-ColorText "⚠️ Sistema parcialmente operacional" "Yellow"
        Write-ColorText "Verifique os logs dos serviços que falharam" "Yellow"
    } else {
        Write-ColorText "❌ Sistema não está funcionando" "Red"
        Write-ColorText "Execute: .\start-system-webrtc.ps1" "Yellow"
    }
    
    Write-Host ""
    Write-ColorText "Para iniciar/reiniciar o sistema: .\start-system-webrtc.ps1" "Cyan"
    Write-ColorText "Para instalar dependências MSYS2: .\install_msys2_camera_deps.ps1" "Cyan"
    Write-ColorText "Para verificar ambientes: .\verify-environments.ps1" "Cyan"
    
    Write-Host ""
    Write-ColorText "Press any key to exit..." "Gray"
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
}

# Entry point
Main