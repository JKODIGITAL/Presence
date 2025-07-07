@echo off
REM Script completo de instalação para Windows
REM Execute como Administrator para melhores resultados

echo.
echo ========================================
echo   INSTALAÇÃO COMPLETA - PRESENCE SYSTEM
echo ========================================
echo.

REM Verificar se estamos no diretório correto
if not exist "app" (
    echo ERROR: Execute este script na raiz do projeto Presence
    echo Exemplo: D:\Projetopresence\presence\scripts\install_complete_windows.bat
    pause
    exit /b 1
)

echo [1/6] Verificando pré-requisitos...

REM Verificar conda
call scripts\setup_conda_path.bat
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ❌ Conda não encontrado. Instalando Miniconda...
    echo.
    
    REM Download Miniconda
    echo Baixando Miniconda...
    powershell -Command "Invoke-WebRequest -Uri 'https://repo.anaconda.com/miniconda/Miniconda3-latest-Windows-x86_64.exe' -OutFile 'Miniconda3-latest-Windows-x86_64.exe'"
    
    if not exist "Miniconda3-latest-Windows-x86_64.exe" (
        echo ❌ Falha no download do Miniconda
        echo Por favor, baixe manualmente de: https://docs.conda.io/en/latest/miniconda.html
        pause
        exit /b 1
    )
    
    echo Instalando Miniconda...
    echo ⚠️ IMPORTANTE: Marque "Add to PATH" durante a instalação!
    start /wait Miniconda3-latest-Windows-x86_64.exe /InstallationType=JustMe /RegisterPython=1 /S /D=%USERPROFILE%\miniconda3
    
    REM Remover installer
    del Miniconda3-latest-Windows-x86_64.exe
    
    echo.
    echo ✓ Miniconda instalado! Reinicie este terminal e execute novamente.
    echo.
    pause
    exit /b 0
)

REM Verificar Node.js
where node >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ❌ Node.js não encontrado. 
    echo Por favor, instale Node.js LTS de: https://nodejs.org/
    echo Após a instalação, reinicie o terminal e execute novamente.
    echo.
    pause
    exit /b 1
)

echo ✓ Node.js encontrado:
node --version
echo.

echo [2/6] Criando ambiente conda...

REM Verificar se ambiente presence existe
conda env list | findstr "presence" >nul 2>nul
if %ERRORLEVEL% EQL 0 (
    echo ✓ Ambiente 'presence' já existe
    
    set /p recreate="Deseja recriar o ambiente? (y/N): "
    if /i "%recreate%"=="y" (
        echo Removendo ambiente existente...
        conda env remove -n presence -y
        echo Criando novo ambiente...
        conda create -n presence python=3.10 -y
    )
) else (
    echo Criando ambiente conda 'presence'...
    conda create -n presence python=3.10 -y
)

echo.
echo [3/6] Instalando dependências Python...

echo Instalando PyTorch com CUDA...
conda run -n presence pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

echo Instalando FAISS-GPU...
conda run -n presence conda install pytorch::faiss-gpu -y

echo Instalando dependências do projeto...
conda run -n presence pip install -r requirements.txt

echo Instalando dependências WebRTC...
conda run -n presence pip install aiortc aiofiles uvloop

echo.
echo [4/6] Configurando frontend...

cd frontend
if not exist "node_modules" (
    echo Instalando dependências npm...
    npm install
) else (
    echo ✓ Dependências npm já instaladas
)
cd ..

echo.
echo [5/6] Criando estrutura de diretórios...

if not exist "data" mkdir data
if not exist "data\models" mkdir data\models  
if not exist "data\images" mkdir data\images
if not exist "data\embeddings" mkdir data\embeddings
if not exist "logs" mkdir logs

echo ✓ Estrutura criada

echo.
echo [6/6] Configurando banco de dados...

cd app
conda run -n presence alembic init alembic 2>nul || echo ✓ Alembic já inicializado
cd ..

echo.
echo ========================================
echo   INSTALAÇÃO CONCLUÍDA!
echo ========================================
echo.

echo Testando instalação...
conda run -n presence python -c "
try:
    import torch, cv2, fastapi, aiortc
    print('✅ Componentes principais: OK')
    print(f'✅ PyTorch: {torch.__version__} (CUDA: {torch.cuda.is_available()})')
except Exception as e:
    print(f'❌ Erro: {e}')
"

echo.
echo Para iniciar o sistema:
echo   scripts\start_windows_venv.bat
echo.
echo Para acessar:
echo   http://127.0.0.1:3000
echo.

set /p start_now="Deseja iniciar o sistema agora? (y/N): "
if /i "%start_now%"=="y" (
    echo Iniciando sistema...
    call scripts\start_windows_venv.bat
)

echo.
echo ✓ Instalação completa finalizada!
pause