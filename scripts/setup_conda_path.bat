@echo off
REM Script para detectar e configurar conda no Windows
echo.
echo ========================================
echo   DETECTANDO CONDA NO SISTEMA
echo ========================================
echo.

REM Verificar se conda já está no PATH
where conda >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    echo ✓ conda já está disponível no PATH
    conda --version
    goto :conda_found
)

echo Procurando instalação do conda...

REM Verificar locais comuns do Miniconda/Anaconda
set CONDA_PATHS[0]=%USERPROFILE%\miniconda3\Scripts\conda.exe
set CONDA_PATHS[1]=%USERPROFILE%\anaconda3\Scripts\conda.exe
set CONDA_PATHS[2]=C:\ProgramData\miniconda3\Scripts\conda.exe
set CONDA_PATHS[3]=C:\ProgramData\anaconda3\Scripts\conda.exe
set CONDA_PATHS[4]=C:\miniconda3\Scripts\conda.exe
set CONDA_PATHS[5]=C:\anaconda3\Scripts\conda.exe
set CONDA_PATHS[6]=%LOCALAPPDATA%\Continuum\miniconda3\Scripts\conda.exe
set CONDA_PATHS[7]=%LOCALAPPDATA%\Continuum\anaconda3\Scripts\conda.exe

for /L %%i in (0,1,7) do (
    call set "conda_path=%%CONDA_PATHS[%%i]%%"
    call :check_conda_path
)

echo.
echo ❌ Conda não encontrado nos locais padrão.
echo.
echo Para instalar o Miniconda:
echo 1. Acesse: https://docs.conda.io/en/latest/miniconda.html
echo 2. Baixe a versão para Windows
echo 3. Execute o instalador
echo 4. Marque "Add to PATH" durante a instalação
echo 5. Reinicie o Command Prompt
echo.
pause
exit /b 1

:check_conda_path
if exist "%conda_path%" (
    echo ✓ Encontrado: %conda_path%
    
    REM Adicionar ao PATH da sessão atual
    for %%F in ("%conda_path%") do set "conda_dir=%%~dpF"
    set "PATH=%conda_dir%;%PATH%"
    
    REM Testar se funciona
    "%conda_path%" --version >nul 2>nul
    if %ERRORLEVEL% EQU 0 (
        echo ✓ conda funcionando: 
        "%conda_path%" --version
        goto :conda_found
    ) else (
        echo ⚠️ conda encontrado mas não funciona
    )
)
goto :eof

:conda_found
echo.
echo ✓ conda configurado com sucesso!
echo.

REM Verificar se ambiente presence existe
conda env list | findstr "presence" >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    echo ✓ Ambiente 'presence' encontrado
) else (
    echo ❌ Ambiente 'presence' não encontrado
    echo.
    echo Para criar o ambiente, execute:
    echo conda create -n presence python=3.10 -y
    echo.
    echo Ou execute o setup completo:
    echo scripts\setup_windows_venv.ps1
    echo.
    pause
    exit /b 1
)

echo.
echo Ambiente pronto para uso!
echo Para ativar: conda activate presence
echo.
exit /b 0