# Script PowerShell para copiar ambiente conda do WSL para Windows
# Execute como Administrator

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   COPIANDO AMBIENTE WSL → WINDOWS" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Verificar se conda está disponível
if (-not (Get-Command "conda" -ErrorAction SilentlyContinue)) {
    Write-Host "❌ conda não encontrado no Windows." -ForegroundColor Red
    Write-Host ""
    Write-Host "Soluções:" -ForegroundColor Yellow
    Write-Host "1. Instalar Miniconda: https://docs.conda.io/en/latest/miniconda.html" -ForegroundColor Blue
    Write-Host "2. Executar: scripts\install_complete_windows.bat" -ForegroundColor Blue
    Write-Host "3. Ou usar ambiente WSL diretamente (próxima opção)" -ForegroundColor Blue
    Write-Host ""
    
    $useWSL = Read-Host "Deseja usar o ambiente WSL diretamente? (y/N)"
    if ($useWSL -eq "y" -or $useWSL -eq "Y") {
        Write-Host ""
        Write-Host "🔧 Configurando para usar ambiente WSL..." -ForegroundColor Yellow
        
        # Verificar se WSL está disponível
        try {
            $wslInfo = wsl --list --verbose
            Write-Host "✓ WSL disponível" -ForegroundColor Green
            
            # Criar script bat que usa WSL
            $wslScript = @"
@echo off
REM Script para usar ambiente conda do WSL

echo.
echo ========================================
echo   USANDO AMBIENTE WSL
echo ========================================
echo.

echo [1/5] Verificando ambiente WSL...
wsl bash -c "export PATH=`"`$HOME/miniconda3/bin:`$PATH`" && source `$HOME/miniconda3/etc/profile.d/conda.sh && conda env list | grep presence"
if %ERRORLEVEL% NEQ 0 (
    echo ❌ Ambiente 'presence' não encontrado no WSL
    echo Execute primeiro: ./scripts/complete_setup_wsl.sh
    pause
    exit /b 1
)

echo ✓ Ambiente WSL 'presence' encontrado

echo.
echo [2/5] Criando diretórios no Windows...
if not exist "data" mkdir data
if not exist "data\models" mkdir data\models
if not exist "data\images" mkdir data\images  
if not exist "data\embeddings" mkdir data\embeddings
if not exist "logs" mkdir logs

echo.
echo [3/5] Configurando frontend...
cd frontend
if not exist "node_modules" (
    echo Instalando dependências npm...
    npm install
)
cd ..

echo.
echo [4/5] Iniciando serviços via WSL...

echo   → Iniciando API via WSL...
start "Presence API (WSL)" cmd /k "wsl bash -c 'cd /mnt/d/Projetopresence/presence/app && export PATH=`$HOME/miniconda3/bin:`$PATH && source `$HOME/miniconda3/etc/profile.d/conda.sh && conda activate presence && uvicorn api.main:app --reload --host 0.0.0.0 --port 9000'"

timeout /t 3 /nobreak >nul

echo   → Iniciando Recognition Worker via WSL...
start "Recognition Worker (WSL)" cmd /k "wsl bash -c 'cd /mnt/d/Projetopresence/presence/app && export PATH=`$HOME/miniconda3/bin:`$PATH && source `$HOME/miniconda3/etc/profile.d/conda.sh && conda activate presence && python recognition_worker/main.py'"

timeout /t 2 /nobreak >nul

echo   → Iniciando Camera Worker via WSL...
start "Camera Worker (WSL)" cmd /k "wsl bash -c 'cd /mnt/d/Projetopresence/presence/app && export PATH=`$HOME/miniconda3/bin:`$PATH && source `$HOME/miniconda3/etc/profile.d/conda.sh && conda activate presence && USE_PERFORMANCE_WORKER=true python camera_worker/main.py'"

timeout /t 2 /nobreak >nul

echo   → Iniciando VMS WebRTC via WSL...
start "VMS WebRTC (WSL)" cmd /k "wsl bash -c 'cd /mnt/d/Projetopresence/presence/app && export PATH=`$HOME/miniconda3/bin:`$PATH && source `$HOME/miniconda3/etc/profile.d/conda.sh && conda activate presence && python -m webrtc_worker.main_vms'"

timeout /t 2 /nobreak >nul

echo   → Iniciando Frontend (Windows)...
start "Frontend" cmd /k "cd /d %cd%\frontend && npm run dev"

echo.
echo [5/5] Sistema iniciado!
echo.
echo ========================================
echo   SERVIÇOS RODANDO (WSL + Windows):
echo ========================================
echo   API:              http://127.0.0.1:9000 (WSL)
echo   Recognition:      http://127.0.0.1:9001 (WSL)
echo   VMS WebRTC:       http://127.0.0.1:8766 (WSL)
echo   Frontend:         http://127.0.0.1:3000 (Windows)
echo.
echo   Portas UDP:       40000-40100 (WebRTC)
echo ========================================
echo.
echo Aguarde alguns segundos para todos os serviços carregarem...
echo Pressione qualquer tecla para abrir o frontend no navegador.
pause >nul

start http://127.0.0.1:3000

echo.
echo Sistema híbrido WSL+Windows iniciado com sucesso!
echo Para parar: feche todas as janelas de terminal.
echo.
pause
"@
            
            # Salvar script
            $wslScript | Out-File -FilePath "scripts\start_wsl_hybrid.bat" -Encoding ASCII
            
            Write-Host "✓ Script híbrido criado: scripts\start_wsl_hybrid.bat" -ForegroundColor Green
            Write-Host ""
            Write-Host "Para usar:" -ForegroundColor Yellow
            Write-Host "  scripts\start_wsl_hybrid.bat" -ForegroundColor Blue
            Write-Host ""
            
        } catch {
            Write-Host "❌ WSL não está disponível" -ForegroundColor Red
            Write-Host "Instale o WSL primeiro ou use instalação nativa do Windows" -ForegroundColor Yellow
        }
    }
    
    exit 1
}

Write-Host "✓ conda encontrado no Windows" -ForegroundColor Green

# Verificar se ambiente WSL existe
Write-Host ""
Write-Host "Verificando ambiente no WSL..." -ForegroundColor Yellow

try {
    $wslCheck = wsl bash -c "export PATH=`$HOME/miniconda3/bin:`$PATH && source `$HOME/miniconda3/etc/profile.d/conda.sh 2>/dev/null && conda env list | grep presence"
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ Ambiente 'presence' encontrado no WSL" -ForegroundColor Green
        
        Write-Host ""
        Write-Host "Exportando ambiente do WSL..." -ForegroundColor Yellow
        
        # Exportar lista de pacotes do WSL
        $packages = wsl bash -c "export PATH=`$HOME/miniconda3/bin:`$PATH && source `$HOME/miniconda3/etc/profile.d/conda.sh 2>/dev/null && conda activate presence && pip freeze"
        
        # Salvar em arquivo temporário
        $packages | Out-File -FilePath "wsl_requirements.txt" -Encoding UTF8
        
        Write-Host "✓ Lista de pacotes exportada" -ForegroundColor Green
        
        # Criar ambiente Windows
        Write-Host ""
        Write-Host "Criando ambiente no Windows..." -ForegroundColor Yellow
        
        & conda create -n presence python=3.10 -y
        
        Write-Host "Instalando pacotes..." -ForegroundColor Yellow
        & conda run -n presence pip install -r wsl_requirements.txt
        
        # Instalar dependências específicas do Windows
        Write-Host "Instalando PyTorch para Windows..." -ForegroundColor Yellow
        & conda run -n presence pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
        
        Write-Host "Instalando FAISS-GPU..." -ForegroundColor Yellow
        & conda run -n presence conda install pytorch::faiss-gpu -y
        
        # Limpar arquivo temporário
        Remove-Item "wsl_requirements.txt" -ErrorAction SilentlyContinue
        
        Write-Host ""
        Write-Host "✓ Ambiente copiado com sucesso!" -ForegroundColor Green
        
    } else {
        Write-Host "❌ Ambiente 'presence' não encontrado no WSL" -ForegroundColor Red
        Write-Host "Execute primeiro no WSL: ./scripts/complete_setup_wsl.sh" -ForegroundColor Yellow
        exit 1
    }
    
} catch {
    Write-Host "❌ Erro ao acessar WSL" -ForegroundColor Red
    Write-Host "WSL pode não estar configurado corretamente" -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   CÓPIA CONCLUÍDA!" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "Testando ambiente Windows..." -ForegroundColor Yellow
& conda run -n presence python -c "
try:
    import torch, fastapi, aiortc
    print('✅ Componentes principais funcionando')
except Exception as e:
    print(f'❌ Erro: {e}')
"

Write-Host ""
Write-Host "Para iniciar o sistema:" -ForegroundColor Yellow
Write-Host "  scripts\start_windows_venv.bat" -ForegroundColor Blue
Write-Host ""

$start = Read-Host "Deseja iniciar o sistema agora? (y/N)"
if ($start -eq "y" -or $start -eq "Y") {
    Write-Host "Iniciando sistema..." -ForegroundColor Green
    Start-Process -FilePath "scripts\start_windows_venv.bat" -WorkingDirectory $PWD
}