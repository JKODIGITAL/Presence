@echo off
REM Script para iniciar todos os serviços do Presence em venv no Windows
REM Execute este script na raiz do projeto

echo.
echo ========================================
echo   PRESENCE SYSTEM - Windows venv Startup
echo ========================================
echo.

REM Configurar conda automaticamente
call "%~dp0setup_conda_path.bat"
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Falha ao configurar conda. Verifique a instalação.
    pause
    exit /b 1
)

REM Ativar ambiente conda
echo [1/5] Ativando ambiente conda 'presence'...
call conda activate presence
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Ambiente 'presence' não encontrado. Execute primeiro:
    echo conda create -n presence python=3.10
    pause
    exit /b 1
)

REM Verificar estrutura do projeto
if not exist "app" (
    echo ERROR: Diretório 'app' não encontrado. Execute na raiz do projeto.
    pause
    exit /b 1
)

if not exist "frontend" (
    echo ERROR: Diretório 'frontend' não encontrado. Execute na raiz do projeto.
    pause
    exit /b 1
)

echo.
echo [2/5] Configurando variáveis de ambiente...

REM Configurar variáveis de ambiente para todos os serviços
set PYTHONPATH=%cd%
set INSIGHTFACE_HOME=%cd%\data\models
set ENVIRONMENT=development
set USE_GPU=true
set CUDA_VISIBLE_DEVICES=0
set API_BASE_URL=http://localhost:17234
set RECOGNITION_WORKER_URL=http://localhost:9001

REM Configurações WebRTC específicas
set AIORTC_UDP_PORT_RANGE=40000-40100
set AIORTC_FORCE_HOST_IP=127.0.0.1
set WEBRTC_PUBLIC_IP=127.0.0.1
set AIORTC_STRICT_PORT_RANGE=true
set WEBRTC_FORCE_UDP_RANGE=true

REM Configurações Frontend
set VITE_API_URL=http://127.0.0.1:17234
set VITE_VMS_WEBRTC_URL=http://127.0.0.1:8766

echo   ✓ Variáveis configuradas
echo.

echo [3/5] Criando diretórios necessários...
if not exist "data" mkdir data
if not exist "data\models" mkdir data\models
if not exist "data\images" mkdir data\images
if not exist "data\embeddings" mkdir data\embeddings
if not exist "logs" mkdir logs
echo   ✓ Diretórios criados

echo.
echo [4/5] Iniciando serviços em terminais separados...

REM Terminal 1: API
echo   → Iniciando API (porta 17234)...
start "Presence API" cmd /k "cd /d %cd%\app && conda activate presence && uvicorn api.main:app --reload --host 0.0.0.0 --port 17234"

REM Aguardar um pouco entre os starts
timeout /t 3 /nobreak >nul

REM Terminal 2: Recognition Worker
echo   → Iniciando Recognition Worker (porta 9001)...
start "Recognition Worker" cmd /k "cd /d %cd%\app && conda activate presence && python recognition_worker/main.py"

timeout /t 2 /nobreak >nul

REM Terminal 3: Camera Worker
echo   → Iniciando Camera Worker...
start "Camera Worker" cmd /k "cd /d %cd%\app && conda activate presence && set USE_PERFORMANCE_WORKER=true && python camera_worker/main.py"

timeout /t 2 /nobreak >nul

REM Terminal 4: VMS WebRTC Server
echo   → Iniciando VMS WebRTC Server (porta 8766)...
start "VMS WebRTC" cmd /k "cd /d %cd%\app && conda activate presence && python -m webrtc_worker.main_vms"

timeout /t 2 /nobreak >nul

REM Terminal 5: Frontend
echo   → Iniciando Frontend (porta 3000)...
start "Frontend" cmd /k "cd /d %cd%\frontend && npm run dev"

echo.
echo [5/5] Todos os serviços foram iniciados!
echo.
echo ========================================
echo   SERVIÇOS RODANDO:
echo ========================================
echo   API:              http://127.0.0.1:17234
echo   Recognition:      http://127.0.0.1:9001  
echo   VMS WebRTC:       http://127.0.0.1:8766
echo   Frontend:         http://127.0.0.1:3000
echo.
echo   Portas UDP:       40000-40100 (WebRTC)
echo ========================================
echo.
echo Aguarde alguns segundos para todos os serviços carregarem...
echo Pressione qualquer tecla para abrir o frontend no navegador.
pause >nul

REM Abrir frontend no navegador
start http://127.0.0.1:3000

echo.
echo Sistema iniciado com sucesso!
echo Para parar todos os serviços, feche todas as janelas de terminal.
echo.
pause