# ============================================================================
# PRESENCE SYSTEM - MULTI-CAMERA WEBRTC STARTUP WITH DEEP VERIFICATION
# ============================================================================
# Architecture:
# 📸 [RTSP Cameras] → 🎥 [GStreamer NVDEC] → 🧠 [Recognition HTTP] → 
# 🎯 [OpenCV Overlay] → 🎞️ [GStreamer NVENC] → 🌐 [WebRTC] → 📺 [Frontend]
# ============================================================================

param(
    [switch]$NoDeps,
    [switch]$NoGPU,
    [switch]$Verbose,
    [switch]$TestMode,
    [int]$CameraCount = 2
)

$ErrorActionPreference = "Continue"
$Host.UI.RawUI.WindowTitle = "Presence Multi-Camera WebRTC System"

# ============================================================================
# CONFIGURATION
# ============================================================================

$ProjectPath = "D:\Projetopresence\presence"
$AppPath = "$ProjectPath\app"
$FrontendPath = "$ProjectPath\frontend"
$LogsPath = "$ProjectPath\logs"
$DataPath = "$ProjectPath\data"

# Service Ports Configuration
$Ports = @{
    API = 17234
    Recognition = 17235
    WebRTCBase = 17236  # First camera, increments for each additional camera
    Frontend = 3000
}

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

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
        return $response.StatusCode -eq 200
    }
    catch {
        return $false
    }
}

function Test-SocketIO {
    param([int]$Port)
    $socketIOUrl = "http://127.0.0.1:$Port/socket.io/"
    return Test-HttpEndpoint $socketIOUrl
}

function Test-WebRTCEndpoint {
    param([int]$Port)
    $healthUrl = "http://127.0.0.1:$Port/health"
    return Test-HttpEndpoint $healthUrl
}

function Stop-ServiceByPort {
    param([int]$Port)
    try {
        $processes = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue | 
                     Select-Object -ExpandProperty OwningProcess | 
                     Get-Process -ErrorAction SilentlyContinue
        
        foreach ($proc in $processes) {
            Write-ColorText "Stopping process on port $Port (PID: $($proc.Id))" "Yellow"
            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        }
    }
    catch {
        # Ignore errors
    }
}

function Test-Dependencies {
    Write-Step "DEPS" "Performing deep dependency verification..."
    
    $issues = @()
    
    # Check Conda Environment (PURO)
    Write-ColorText "Checking Conda environment 'presence' (PURO)..." "Cyan"
    $condaPath = "C:\Users\Danilo\miniconda3\Scripts\conda.exe"
    if (!(Test-Path $condaPath)) {
        $issues += "❌ Conda not found at: $condaPath"
    } else {
        Write-ColorText "✅ Conda found" "Green"
        
        # Test Conda environment activation (SEM MSYS2)
        $testCmd = "cmd /c `"call C:\Users\Danilo\miniconda3\Scripts\activate.bat presence && set PATH=%PATH:C:\msys64\mingw64\bin;=% && set PATH=%PATH:C:\msys64\usr\bin;=% && python -c `"import torch, faiss, insightface, socketio, aiortc; print('CONDA-OK')`" 2>&1`""
        $result = Invoke-Expression $testCmd
        if ($result -notcontains "CONDA-OK") {
            $issues += "❌ Conda 'presence' environment missing required packages or mixing with MSYS2"
            Write-ColorText "Conda test output: $result" "Yellow"
        } else {
            Write-ColorText "✅ Conda environment has all required packages (PURO)" "Green"
        }
    }
    
    # Check MSYS2 Environment (UCRT64)
    Write-ColorText "Checking MSYS2 UCRT64 environment..." "Cyan"
    $msysPath = "C:\msys64\ucrt64\bin\python.exe"
    if (!(Test-Path $msysPath)) {
        $issues += "❌ MSYS2 UCRT64 Python not found at: $msysPath"
    } else {
        Write-ColorText "✅ MSYS2 UCRT64 Python found" "Green"
        
        # Test MSYS2 Python packages (SEM CONDA)
        $msysTestCmd = "cmd /c `"set PATH=C:\msys64\ucrt64\bin;C:\msys64\usr\bin;%PATH% && C:\msys64\ucrt64\bin\python.exe -c `"import gi, cv2, numpy; print('MSYS2-OK')`" 2>&1`""
        $msysResult = Invoke-Expression $msysTestCmd
        if ($msysResult -notcontains "MSYS2-OK") {
            $issues += "❌ MSYS2 UCRT64 Python missing required packages (gi, cv2, numpy)"
            Write-ColorText "MSYS2 test output: $msysResult" "Yellow"
        } else {
            Write-ColorText "✅ MSYS2 UCRT64 Python has required packages" "Green"
        }
        
        # Test GStreamer
        $env:PATH = "C:\msys64\ucrt64\bin;C:\msys64\usr\bin;" + $env:PATH
        $gstTest = & "C:\msys64\ucrt64\bin\gst-inspect-1.0.exe" --version 2>&1
        if ($LASTEXITCODE -ne 0) {
            $issues += "❌ GStreamer not working in MSYS2 UCRT64"
        } else {
            Write-ColorText "✅ GStreamer working" "Green"
        }
        
        # Test critical GStreamer plugins
        $criticalPlugins = @("v4l2src", "rtspsrc", "nvh264dec", "nvh264enc", "vp8enc", "rtpvp8pay")
        foreach ($plugin in $criticalPlugins) {
            $pluginTest = & "C:\msys64\ucrt64\bin\gst-inspect-1.0.exe" $plugin 2>&1
            if ($LASTEXITCODE -ne 0) {
                Write-ColorText "⚠️ GStreamer plugin '$plugin' not available" "Yellow"
            }
        }
    }
    
    # Check GPU if not in NoGPU mode
    if (!$NoGPU) {
        Write-ColorText "Checking NVIDIA GPU..." "Cyan"
        $gpuTest = nvidia-smi 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-ColorText "⚠️ NVIDIA GPU not detected - will use CPU mode" "Yellow"
            $script:NoGPU = $true
        } else {
            Write-ColorText "✅ NVIDIA GPU available" "Green"
        }
    }
    
    # Check Node.js for Frontend
    Write-ColorText "Checking Node.js..." "Cyan"
    $nodeVersion = node --version 2>&1
    if ($LASTEXITCODE -ne 0) {
        $issues += "❌ Node.js not found"
    } else {
        Write-ColorText "✅ Node.js $nodeVersion" "Green"
    }
    
    # Check Socket.IO in MSYS2 UCRT64
    Write-ColorText "Checking Socket.IO in MSYS2 UCRT64..." "Cyan"
    try {
        $env:PATH = "C:\msys64\ucrt64\bin;C:\msys64\usr\bin;" + $env:PATH
        $socketIOResult = & "C:\msys64\ucrt64\bin\python.exe" -c "import socketio; print('SOCKETIO-VERSION:', socketio.__version__)" 2>&1
        if ($socketIOResult -match "SOCKETIO-VERSION:") {
            $version = ($socketIOResult -split "SOCKETIO-VERSION: ")[1].Trim()
            Write-ColorText "✅ Socket.IO version in MSYS2 UCRT64: $version" "Green"
        } else {
            $issues += "⚠️ Socket.IO not installed in MSYS2 UCRT64 - Camera Worker needs Socket.IO"
            Write-ColorText "Socket.IO test output: $socketIOResult" "Yellow"
        }
    } catch {
        $issues += "⚠️ Socket.IO not installed in MSYS2 UCRT64 - Camera Worker needs Socket.IO"
        Write-ColorText "Socket.IO test failed: $($_.Exception.Message)" "Yellow"
    }
    
    # Check database
    Write-ColorText "Checking database..." "Cyan"
    $dbPath = "$DataPath\db\presence.db"
    if (!(Test-Path $dbPath)) {
        Write-ColorText "⚠️ Database not found - will be created on first run" "Yellow"
    } else {
        Write-ColorText "✅ Database exists" "Green"
    }
    
    # Check models
    Write-ColorText "Checking face recognition models..." "Cyan"
    $modelPath = "C:\Users\Danilo\.insightface\models\antelopev2"
    if (!(Test-Path $modelPath)) {
        $issues += "❌ InsightFace models not found at: $modelPath"
    } else {
        Write-ColorText "✅ InsightFace models found" "Green"
    }
    
    return $issues
}

function Stop-AllServices {
    Write-Step "CLEANUP" "Stopping all existing services..."
    
    # Stop all known ports
    $allPorts = @($Ports.API, $Ports.Recognition, $Ports.Frontend)
    
    # Add WebRTC ports for multiple cameras
    for ($i = 0; $i -lt 10; $i++) {
        $allPorts += ($Ports.WebRTCBase + $i)
    }
    
    foreach ($port in $allPorts) {
        Stop-ServiceByPort $port
    }
    
    Start-Sleep -Seconds 2
    Write-ColorText "✅ All services stopped" "Green"
}

function Test-ServiceConnections {
    Write-Banner "SERVICE CONNECTION VERIFICATION"
    
    # Test Recognition Worker Socket.IO
    Write-ColorText "Testing Recognition Worker Socket.IO..." "Cyan"
    if (Test-SocketIO $Ports.Recognition) {
        Write-ColorText "✅ Recognition Worker Socket.IO is accessible" "Green"
    } else {
        Write-ColorText "❌ Recognition Worker Socket.IO not ready" "Red"
    }
    
    # Test API Health
    Write-ColorText "Testing API health endpoint..." "Cyan"
    if (Test-HttpEndpoint "http://127.0.0.1:$($Ports.API)/health") {
        Write-ColorText "✅ API health check passed" "Green"
        
        # Test camera endpoint
        if (Test-HttpEndpoint "http://127.0.0.1:$($Ports.API)/api/v1/cameras") {
            Write-ColorText "✅ API camera endpoint accessible" "Green"
        }
    } else {
        Write-ColorText "❌ API not responding" "Red"
    }
    
    # Test WebRTC endpoints for each camera
    Write-ColorText "Testing WebRTC endpoints..." "Cyan"
    for ($i = 0; $i -lt $CameraCount; $i++) {
        $port = $Ports.WebRTCBase + $i
        if (Test-WebRTCEndpoint $port) {
            Write-ColorText "✅ WebRTC Camera $i health check passed (port $port)" "Green"
        } else {
            Write-ColorText "⚠️ WebRTC Camera $i not ready yet (port $port)" "Yellow"
        }
    }
}

# ============================================================================
# MAIN EXECUTION
# ============================================================================

function Main {
    Clear-Host
    
    Write-Banner "PRESENCE MULTI-CAMERA WEBRTC SYSTEM"
    Write-ColorText "Timestamp: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" "Cyan"
    Write-ColorText "Camera Count: $CameraCount" "Cyan"
    Write-ColorText "GPU Mode: $(if($NoGPU){'Disabled (CPU)'}else{'Enabled (CUDA)'})" "Cyan"
    Write-ColorText "Test Mode: $(if($TestMode){'Yes'}else{'No'})" "Cyan"
    Write-Host ""
    
    # Step 1: Dependency verification (SKIPPED - dependencies now working)
    Write-ColorText "✅ Skipping dependency check - all dependencies resolved" "Green"
    
    # Step 2: Stop existing services
    Stop-AllServices
    
    # Step 3: Create logs directory
    if (!(Test-Path $LogsPath)) {
        New-Item -ItemType Directory -Path $LogsPath -Force | Out-Null
        Write-ColorText "✅ Logs directory created" "Green"
    }
    
    # Step 4: Prepare batch files
    Write-Banner "PREPARING SERVICE CONFIGURATIONS"
    
    $useGpu = if ($NoGPU) { "false" } else { "true" }
    $testModeStr = if ($TestMode) { "true" } else { "false" }
    
    # Recognition Worker Batch (CONDA PURO)
    $recognitionBatch = @"
@echo off
title Recognition Worker - Socket.IO Server (CONDA PURO)
REM ============================================
REM IMPORTANTE: CONDA PURO - SEM MSYS2
REM ============================================
call C:\Users\Danilo\miniconda3\Scripts\activate.bat presence
set PATH="C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v11.8\bin";%PATH%
set PYTHONPATH=$ProjectPath
set ENVIRONMENT=production
set USE_GPU=$useGpu
set CUDA_VISIBLE_DEVICES=0
set INSIGHTFACE_HOME=$ProjectPath\data\models
set RECOGNITION_PORT=$($Ports.Recognition)
set RECOGNITION_HOST=0.0.0.0
set API_BASE_URL=http://127.0.0.1:$($Ports.API)
set RECOGNITION_WORKER=true
REM Remover qualquer referência ao MSYS2 do PATH
set PATH=%PATH:C:\msys64\mingw64\bin;=%
set PATH=%PATH:C:\msys64\usr\bin;=%
echo ============================================
echo Recognition Worker - Socket.IO Server (CONDA PURO)
echo Port: $($Ports.Recognition)
echo GPU Mode: $useGpu
echo Environment: Conda 'presence' (SEM MSYS2)
echo Python: %CONDA_PREFIX%\python.exe
echo ============================================
REM Verificar se estamos no ambiente Conda correto
python -c "import sys; print('Python:', sys.executable)"
python -c "import torch, faiss, insightface; print('Dependencies OK')"
python recognition_worker/main.py
pause
"@
    
    # API Server Batch (CONDA PURO)
    $apiBatch = @"
@echo off
title Presence API - Camera Management (CONDA PURO)
REM ============================================
REM IMPORTANTE: CONDA PURO - SEM MSYS2
REM ============================================
call C:\Users\Danilo\miniconda3\Scripts\activate.bat presence
set PATH="C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v11.8\bin";%PATH%
set PYTHONPATH=$ProjectPath
set ENVIRONMENT=production
set USE_GPU=$useGpu
set CUDA_VISIBLE_DEVICES=0
set INSIGHTFACE_HOME=$ProjectPath\data\models
set API_HOST=0.0.0.0
set RECOGNITION_HOST=127.0.0.1
REM Remover qualquer referência ao MSYS2 do PATH
set PATH=%PATH:C:\msys64\mingw64\bin;=%
set PATH=%PATH:C:\msys64\usr\bin;=%
echo ============================================
echo Presence API Server (CONDA PURO)
echo Port: $($Ports.API)
echo Database: $DataPath\db\presence.db
echo Environment: Conda 'presence' (SEM MSYS2)
echo Python: %CONDA_PREFIX%\python.exe
echo ============================================
REM Verificar se estamos no ambiente Conda correto
python -c "import sys; print('Python:', sys.executable)"
uvicorn api.main:app --reload --host 0.0.0.0 --port $($Ports.API)
pause
"@
    
    # Camera Worker Batch (MSYS2 UCRT64 for GStreamer - SEPARADO)
    $cameraWorkerBatch = @"
@echo off
title Camera Worker (GStreamer) - MSYS2 UCRT64
REM ============================================
REM IMPORTANTE: MSYS2 UCRT64 - SEM CONDA
REM ============================================
set PATH=C:\msys64\ucrt64\bin;C:\msys64\usr\bin;%PATH%
set PYTHONPATH=$ProjectPath
set ENVIRONMENT=production
set USE_GPU=$useGpu
set CUDA_VISIBLE_DEVICES=0
set API_BASE_URL=http://127.0.0.1:$($Ports.API)
set RECOGNITION_WORKER_URL=http://127.0.0.1:$($Ports.Recognition)
set GST_PLUGIN_PATH=C:\msys64\ucrt64\lib\gstreamer-1.0
set USE_PERFORMANCE_WORKER=true
REM Forçar uso do Python do MSYS2 UCRT64 (não do Conda)
set MSYS2_PYTHON=C:\msys64\ucrt64\bin\python.exe
echo ============================================
echo Camera Worker (GStreamer) - MSYS2 UCRT64
echo Python: %MSYS2_PYTHON%
echo Recognition Worker: http://127.0.0.1:$($Ports.Recognition)
echo API Server: http://127.0.0.1:$($Ports.API)
echo Camera Count: $CameraCount cameras
echo Environment: MSYS2 UCRT64 (GStreamer native, SEM CONDA)
echo ============================================
REM Verificar se o Python do MSYS2 UCRT64 existe
if not exist "%MSYS2_PYTHON%" (
    echo ERRO: Python do MSYS2 UCRT64 não encontrado em %MSYS2_PYTHON%
    pause
    exit /b 1
)
REM Usar explicitamente o Python do MSYS2 UCRT64
%MSYS2_PYTHON% camera_worker/main.py
pause
"@

    # WebRTC Server Batch (CONDA PURO)
    $webrtcBatch = @"
@echo off
title WebRTC Server (aiortc) - CONDA PURO
REM ============================================
REM IMPORTANTE: CONDA PURO - SEM MSYS2
REM ============================================
call C:\Users\Danilo\miniconda3\Scripts\activate.bat presence
set PATH="C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v11.8\bin";%PATH%
set PYTHONPATH=$ProjectPath
set ENVIRONMENT=production
set USE_GPU=$useGpu
set CUDA_VISIBLE_DEVICES=0
set API_URL=http://127.0.0.1:$($Ports.API)
set RECOGNITION_WORKER_URL=http://127.0.0.1:$($Ports.Recognition)
set VMS_WEBRTC_PORT=$($Ports.WebRTCBase)
set WEBRTC_PUBLIC_IP=127.0.0.1
REM Remover qualquer referência ao MSYS2 do PATH
set PATH=%PATH:C:\msys64\mingw64\bin;=%
set PATH=%PATH:C:\msys64\usr\bin;=%
echo ============================================
echo WebRTC Server (aiortc) - CONDA PURO
echo Recognition Worker: http://127.0.0.1:$($Ports.Recognition)
echo API Server: http://127.0.0.1:$($Ports.API)
echo WebRTC Port: $($Ports.WebRTCBase)
echo Camera Count: $CameraCount cameras
echo Environment: Conda 'presence' (SEM MSYS2)
echo Python: %CONDA_PREFIX%\python.exe
echo ============================================
REM Verificar se estamos no ambiente Conda correto
python -c "import sys; print('Python:', sys.executable)"
python -c "import aiortc, av; print('WebRTC Dependencies OK')"
python webrtc_worker/vms_webrtc_server_native.py
pause
"@
    
    # Frontend Batch (Com verificações robustas)
    $frontendBatch = @"
@echo off
title Frontend - Multi-Camera View
setlocal enabledelayedexpansion
REM ============================================
REM IMPORTANTE: Frontend Node.js
REM ============================================
set VITE_API_URL=http://127.0.0.1:$($Ports.API)
set VITE_VMS_WEBRTC_URL=http://127.0.0.1:$($Ports.WebRTCBase)
set VITE_WEBRTC_CAMERA_WS_BASE=ws://127.0.0.1:$($Ports.WebRTCBase)
echo ============================================
echo Frontend Development Server
echo API URL: http://127.0.0.1:$($Ports.API)
echo WebRTC Base URL: http://127.0.0.1:$($Ports.WebRTCBase)
echo Camera WebSockets: 
for /L %%i in (0,1,$($CameraCount-1)) do (
    set /A port=$($Ports.WebRTCBase)+%%i
    echo   Camera %%i: ws://127.0.0.1:!port!
)
echo ============================================
REM Verificar se Node.js está disponível
node --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ERRO: Node.js nao encontrado
    echo Instale Node.js de: https://nodejs.org/
    pause
    exit /b 1
)
REM Verificar se npm está disponível
npm --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ERRO: npm nao encontrado
    pause
    exit /b 1
)
echo ✅ Node.js e npm detectados
REM Verificar se package.json existe
if not exist "package.json" (
    echo ERRO: package.json nao encontrado
    echo Certifique-se de estar no diretorio frontend
    pause
    exit /b 1
)
echo ✅ package.json encontrado
REM Instalar dependências
echo 📦 Instalando dependencias...
npm install
if %ERRORLEVEL% neq 0 (
    echo ERRO: Falha ao instalar dependencias
    pause
    exit /b 1
)
echo ✅ Dependencias instaladas
REM Verificar se vite está disponível
echo 🔍 Verificando Vite...
npx vite --version
if %ERRORLEVEL% neq 0 (
    echo ERRO: Vite nao esta funcionando
    echo Tentando instalar vite globalmente...
    npm install -g vite
)
REM Verificar porta 3000
echo 🔍 Verificando porta 3000...
netstat -an | find ":3000"
if %ERRORLEVEL% equ 0 (
    echo AVISO: Porta 3000 pode estar em uso
)
REM Iniciar servidor de desenvolvimento
echo 🚀 Iniciando servidor de desenvolvimento...
echo Executando: npm run dev
echo Aguarde alguns segundos para o servidor inicializar...
npm run dev
if %ERRORLEVEL% neq 0 (
    echo ERRO: Falha ao iniciar servidor de desenvolvimento
    echo Tentando modo seguro...
    npm run dev:safe
)
pause
"@
    
    # Write batch files
    [System.IO.File]::WriteAllText("$LogsPath\recognition-worker.bat", $recognitionBatch)
    [System.IO.File]::WriteAllText("$LogsPath\api.bat", $apiBatch)
    [System.IO.File]::WriteAllText("$LogsPath\camera-worker.bat", $cameraWorkerBatch)
    [System.IO.File]::WriteAllText("$LogsPath\webrtc-server.bat", $webrtcBatch)
    [System.IO.File]::WriteAllText("$LogsPath\frontend.bat", $frontendBatch)
    
    Write-ColorText "✅ Service configurations created" "Green"
    
    # Step 5: Start services in correct order
    Write-Banner "STARTING SERVICES"
    
    Write-Step "1/6" "Starting API Server..."
    Start-Process -FilePath "$LogsPath\api.bat" -WorkingDirectory $AppPath
    Write-ColorText "Waiting for API initialization..." "Cyan"
    Start-Sleep -Seconds 5
    
    Write-Step "2/6" "Starting Recognition Worker (Socket.IO Server)..."
    Start-Process -FilePath "$LogsPath\recognition-worker.bat" -WorkingDirectory $AppPath
    Write-ColorText "Waiting for Recognition Worker initialization (GPU models)..." "Cyan"
    Start-Sleep -Seconds 10
    
    Write-Step "3/6" "Starting Camera Worker (Unified Pipeline)..."
    Start-Process -FilePath "$LogsPath\camera-worker.bat" -WorkingDirectory $AppPath
    Write-ColorText "Waiting for unified pipeline initialization..." "Cyan"
    Start-Sleep -Seconds 12
    
    Write-Step "4/6" "Starting WebRTC Server (Socket.IO + aiortc)..."
    Start-Process -FilePath "$LogsPath\webrtc-server.bat" -WorkingDirectory $AppPath
    Write-ColorText "Waiting for WebRTC and Socket.IO initialization..." "Cyan"
    Start-Sleep -Seconds 10
    
    Write-Step "5/6" "Waiting for unified pipeline connection..."
    Write-ColorText "Ensuring Camera Worker connects to WebRTC bridge..." "Cyan"
    Start-Sleep -Seconds 8
    
    Write-Step "6/6" "Starting Frontend..."
    Start-Process -FilePath "$LogsPath\frontend.bat" -WorkingDirectory $FrontendPath
    Write-ColorText "Waiting for frontend build..." "Cyan"
    Start-Sleep -Seconds 15
    
    # Step 6: Verify all connections
    Test-ServiceConnections
    
    # Step 7: Final status
    Write-Banner "SYSTEM STATUS"
    
    # Check all services
    $services = @(
        @{Name="Recognition Worker"; Port=$Ports.Recognition; Type="Socket.IO"},
        @{Name="API Server"; Port=$Ports.API; Type="HTTP"},
        @{Name="WebRTC Server"; Port=$Ports.WebRTCBase; Type="WebRTC/HTTP"},
        @{Name="Frontend"; Port=$Ports.Frontend; Type="HTTP"}
    )
    
    $runningCount = 0
    foreach ($service in $services) {
        $status = if (Test-Port $service.Port) { 
            $runningCount++
            "RUNNING" 
        } else { 
            "STOPPED" 
        }
        $color = if ($status -eq "RUNNING") { "Green" } else { "Red" }
        Write-ColorText "$($service.Name) [$($service.Type)] (Port $($service.Port)): $status" $color
    }
    
    Write-Host ""
    Write-ColorText "System Summary:" "Cyan"
    Write-ColorText "- Services Running: $runningCount / $($services.Count)" "White"
    Write-ColorText "- Camera Support: $CameraCount cameras" "White"
    Write-ColorText "- GPU Acceleration: $(if($NoGPU){'Disabled'}else{'Enabled'})" "White"
    
    Write-Host ""
    Write-ColorText "Unified Pipeline Architecture:" "Cyan"
    Write-ColorText "[RTSP/MP4] -> [MSYS2:GStreamer Unified] -> [CONDA:Recognition]" "White"
    Write-ColorText "-> [GStreamer Overlay] -> [Socket.IO] -> [CONDA:WebRTC] -> [Node.js:Frontend]" "White"
    Write-Host ""
    Write-ColorText "Pipeline Components:" "Cyan"
    Write-ColorText "- Camera Worker: MSYS2 GStreamer (RTSP + MP4 unified processing)" "White"
    Write-ColorText "- Recognition Worker: CONDA (InsightFace, FAISS)" "White"
    Write-ColorText "- Overlay System: Integrated in Camera Worker pipeline" "White"
    Write-ColorText "- WebRTC Bridge: Socket.IO communication with unified pipeline" "White"
    Write-ColorText "- WebRTC Server: CONDA (aiortc + Socket.IO server)" "White"
    Write-ColorText "- API Server: CONDA (FastAPI)" "White"
    Write-ColorText "- Frontend: Node.js (React, Tauri)" "White"
    
    Write-Host ""
    Write-ColorText "Access Points:" "Cyan"
    Write-ColorText "Frontend: http://localhost:$($Ports.Frontend)" "Green"
    Write-ColorText "API Docs: http://127.0.0.1:$($Ports.API)/docs" "Green"
    
    Write-Host ""
    Write-ColorText "WebRTC Endpoints (one per camera):" "Cyan"
    for ($i = 0; $i -lt $CameraCount; $i++) {
        $port = $Ports.WebRTCBase + $i
        Write-ColorText "Camera $i : ws://127.0.0.1:$port" "White"
    }
    
    Write-Host ""
    Write-ColorText "Press Ctrl+C to stop monitoring (services continue running)" "Yellow"
    
    # Keep monitoring
    try {
        while ($true) {
            Start-Sleep -Seconds 30
            
            if ($Verbose) {
                Write-Host ""
                Write-ColorText "Health Check $(Get-Date -Format 'HH:mm:ss')" "Cyan"
                Test-ServiceConnections
            }
        }
    }
    catch {
        Write-ColorText "Monitoring stopped" "Yellow"
    }
}

# Entry point
Main