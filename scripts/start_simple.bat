@echo off
REM Start simples usando caminho direto do conda

REM Ir para o diretório raiz do projeto
cd /d "%~dp0.."

echo.
echo ========================================
echo   INICIANDO PRESENCE SYSTEM
echo ========================================
echo.
echo Diretorio atual: %cd%

REM Definir caminho do conda
set CONDA_PATH=C:\Users\Danilo\miniconda3\Scripts\conda.exe

REM Verificar se estamos no diretório correto
if not exist "app" (
    echo ERROR: Diretorio 'app' nao encontrado
    echo Execute este script da pasta scripts: scripts\start_simple.bat
    echo Ou da raiz do projeto: start_simple.bat
    pause
    exit /b 1
)

REM Verificar conda
if not exist "%CONDA_PATH%" (
    echo ERROR: Conda nao encontrado em %CONDA_PATH%
    echo Execute primeiro: setup_simple.bat
    pause
    exit /b 1
)

REM Verificar ambiente presence
"%CONDA_PATH%" env list | findstr "presence" >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Ambiente 'presence' nao encontrado
    echo Execute primeiro: setup_simple.bat
    pause
    exit /b 1
)

echo + Ambiente presence encontrado

REM Configurar variáveis
set PYTHONPATH=%cd%
set ENVIRONMENT=development
set API_BASE_URL=http://localhost:9000
set VITE_API_URL=http://127.0.0.1:9000
set VITE_VMS_WEBRTC_URL=http://127.0.0.1:8766

echo.
echo Iniciando servicos em terminais separados...

echo   -> API (porta 9000)
start "Presence API" cmd /k "cd /d %cd%\app && "%CONDA_PATH%" run -n presence uvicorn api.main:app --reload --host 0.0.0.0 --port 9000"

timeout /t 3 /nobreak >nul

echo   -> Recognition Worker (porta 9001)  
start "Recognition Worker" cmd /k "cd /d %cd%\app && "%CONDA_PATH%" run -n presence python recognition_worker/main.py"

timeout /t 2 /nobreak >nul

echo   -> Camera Worker
start "Camera Worker" cmd /k "cd /d %cd%\app && "%CONDA_PATH%" run -n presence python camera_worker/main.py"

timeout /t 2 /nobreak >nul

echo   -> VMS WebRTC (porta 8766)
start "VMS WebRTC" cmd /k "cd /d %cd%\app && "%CONDA_PATH%" run -n presence python -m webrtc_worker.main_vms"

timeout /t 2 /nobreak >nul

echo   -> Frontend (porta 3000)
start "Frontend" cmd /k "cd /d %cd%\frontend && npm run dev"

echo.
echo ========================================
echo   SERVICOS INICIADOS!
echo ========================================
echo.
echo   API:         http://127.0.0.1:9000
echo   Frontend:    http://127.0.0.1:3000
echo   VMS WebRTC:  http://127.0.0.1:8766
echo.

echo Aguarde 30-60 segundos para todos carregarem...
echo.

set /p open_browser="Abrir navegador agora? (y/N): "
if /i "%open_browser%"=="y" (
    start http://127.0.0.1:3000
)

echo.
echo Sistema iniciado! Para parar, feche todas as janelas de terminal.
echo.
pause