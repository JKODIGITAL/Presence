#!/usr/bin/env pwsh
# ============================================================================
# INSTALL MSYS2 CAMERA WORKER DEPENDENCIES
# ============================================================================
# Instala todas as dependências necessárias para o Camera Worker no MSYS2
# ============================================================================

$ErrorActionPreference = "Continue"
$Host.UI.RawUI.WindowTitle = "MSYS2 Camera Worker Dependencies Installation"

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

function Test-MSYS2Installation {
    Write-Banner "VERIFICANDO INSTALAÇÃO MSYS2"
    
    $msysPath = "C:\msys64"
    $pythonPath = "C:\msys64\mingw64\bin\python.exe"
    $pacmanPath = "C:\msys64\usr\bin\pacman.exe"
    
    if (!(Test-Path $msysPath)) {
        Write-ColorText "❌ MSYS2 não encontrado em $msysPath" "Red"
        Write-ColorText "Baixe e instale o MSYS2 de: https://www.msys2.org/" "Yellow"
        return $false
    }
    
    if (!(Test-Path $pythonPath)) {
        Write-ColorText "❌ Python do MSYS2 não encontrado em $pythonPath" "Red"
        return $false
    }
    
    if (!(Test-Path $pacmanPath)) {
        Write-ColorText "❌ Pacman não encontrado em $pacmanPath" "Red"
        return $false
    }
    
    Write-ColorText "✅ MSYS2 encontrado e configurado" "Green"
    return $true
}

function Install-SystemPackages {
    Write-Banner "INSTALANDO PACOTES DO SISTEMA (PACMAN)"
    
    $packages = @(
        "mingw-w64-x86_64-python",
        "mingw-w64-x86_64-python-pip",
        "mingw-w64-x86_64-gstreamer",
        "mingw-w64-x86_64-gst-plugins-base",
        "mingw-w64-x86_64-gst-plugins-good", 
        "mingw-w64-x86_64-gst-plugins-bad",
        "mingw-w64-x86_64-gst-plugins-ugly",
        "mingw-w64-x86_64-gst-libav",
        "mingw-w64-x86_64-python-gobject",
        "mingw-w64-x86_64-gtk3",
        "mingw-w64-x86_64-python-cairo",
        "mingw-w64-x86_64-opencv",
        "mingw-w64-x86_64-python-numpy"
    )
    
    Write-ColorText "Instalando pacotes essenciais..." "Cyan"
    
    foreach ($package in $packages) {
        Write-ColorText "📦 Instalando: $package" "White"
        $cmd = "C:\msys64\usr\bin\bash.exe -lc `"pacman -S --noconfirm $package`""
        try {
            Invoke-Expression $cmd | Out-Null
            if ($LASTEXITCODE -eq 0) {
                Write-ColorText "✅ $package instalado" "Green"
            } else {
                Write-ColorText "⚠️ Erro ao instalar $package (pode já estar instalado)" "Yellow"
            }
        } catch {
            Write-ColorText "⚠️ Erro ao instalar $package" "Yellow"
        }
    }
}

function Install-PythonPackages {
    Write-Banner "INSTALANDO PACOTES PYTHON (PIP)"
    
    $pythonPackages = @(
        "aiohttp",
        "loguru", 
        "opencv-python",
        "numpy",
        "python-socketio[client]",
        "requests",
        "pillow",
        "asyncio",
        "pathlib"
    )
    
    Write-ColorText "Atualizando pip..." "Cyan"
    $updatePipCmd = "C:\msys64\usr\bin\bash.exe -lc `"cd /mingw64 && python -m pip install --upgrade pip`""
    try {
        Invoke-Expression $updatePipCmd | Out-Null
        Write-ColorText "✅ pip atualizado" "Green"
    } catch {
        Write-ColorText "⚠️ Erro ao atualizar pip (continuando...)" "Yellow"
    }
    
    foreach ($package in $pythonPackages) {
        Write-ColorText "🐍 Instalando: $package" "White"
        $cmd = "C:\msys64\usr\bin\bash.exe -lc `"cd /mingw64 && python -m pip install $package`""
        try {
            Invoke-Expression $cmd | Out-Null
            if ($LASTEXITCODE -eq 0) {
                Write-ColorText "✅ $package instalado" "Green"
            } else {
                Write-ColorText "⚠️ Erro ao instalar $package" "Yellow"
            }
        } catch {
            Write-ColorText "⚠️ Erro ao instalar $package" "Yellow"
        }
    }
}

function Test-Installation {
    Write-Banner "TESTANDO INSTALAÇÃO"
    
    $tests = @(
        @{
            Name = "Python Import Test"
            Command = "C:\msys64\usr\bin\bash.exe -lc `"cd /mingw64 && python -c 'import sys; print(`"Python OK:`", sys.executable)'`""
        },
        @{
            Name = "GStreamer Test"
            Command = "C:\msys64\mingw64\bin\gst-inspect-1.0.exe --version"
        },
        @{
            Name = "Python GI Test"
            Command = "C:\msys64\usr\bin\bash.exe -lc `"cd /mingw64 && python -c 'import gi; print(`"GI OK`")'`""
        },
        @{
            Name = "OpenCV Test"
            Command = "C:\msys64\usr\bin\bash.exe -lc `"cd /mingw64 && python -c 'import cv2; print(`"OpenCV OK:`", cv2.__version__)'`""
        },
        @{
            Name = "Socket.IO Test"
            Command = "C:\msys64\usr\bin\bash.exe -lc `"cd /mingw64 && python -c 'import socketio; print(`"SocketIO OK:`", socketio.__version__)'`""
        },
        @{
            Name = "NumPy Test"
            Command = "C:\msys64\usr\bin\bash.exe -lc `"cd /mingw64 && python -c 'import numpy; print(`"NumPy OK:`", numpy.__version__)'`""
        },
        @{
            Name = "Loguru Test"
            Command = "C:\msys64\usr\bin\bash.exe -lc `"cd /mingw64 && python -c 'import loguru; print(`"Loguru OK`")'`""
        }
    )
    
    $passedTests = 0
    $totalTests = $tests.Count
    
    foreach ($test in $tests) {
        Write-ColorText "🧪 Testando: $($test.Name)" "Cyan"
        try {
            $result = Invoke-Expression $test.Command 2>&1
            if ($LASTEXITCODE -eq 0) {
                Write-ColorText "✅ $($test.Name): PASSOU" "Green"
                if ($result) {
                    Write-ColorText "   → $result" "White"
                }
                $passedTests++
            } else {
                Write-ColorText "❌ $($test.Name): FALHOU" "Red"
                if ($result) {
                    Write-ColorText "   → $result" "Yellow"
                }
            }
        } catch {
            Write-ColorText "❌ $($test.Name): ERRO" "Red"
            Write-ColorText "   → $($_.Exception.Message)" "Yellow"
        }
    }
    
    Write-Host ""
    Write-ColorText "📊 Resultado dos testes: $passedTests / $totalTests passaram" "Cyan"
    
    if ($passedTests -eq $totalTests) {
        Write-ColorText "🎉 Todas as dependências estão funcionando!" "Green"
        return $true
    } else {
        Write-ColorText "⚠️ Algumas dependências podem ter problemas" "Yellow"
        return $false
    }
}

function Show-Summary {
    Write-Banner "RESUMO DA INSTALAÇÃO"
    
    Write-ColorText "📋 O que foi instalado:" "Cyan"
    Write-ColorText "• GStreamer e plugins (v4l2src, rtspsrc, etc.)" "White"
    Write-ColorText "• Python GObject bindings (gi)" "White"  
    Write-ColorText "• OpenCV para processamento de imagem" "White"
    Write-ColorText "• Socket.IO para comunicação com Recognition Worker" "White"
    Write-ColorText "• NumPy para arrays numéricos" "White"
    Write-ColorText "• Loguru para logging" "White"
    Write-ColorText "• Aiohttp para comunicação HTTP assíncrona" "White"
    
    Write-Host ""
    Write-ColorText "🚀 Próximos passos:" "Cyan"
    Write-ColorText "1. Execute o sistema: .\start-system-webrtc.ps1" "White"
    Write-ColorText "2. O Camera Worker agora deve funcionar no MSYS2" "White"
    Write-ColorText "3. Verifique os logs para confirmar funcionamento" "White"
    
    Write-Host ""
    Write-ColorText "🔧 Ambientes configurados:" "Cyan"
    Write-ColorText "• Camera Worker: MSYS2 (GStreamer nativo)" "White"
    Write-ColorText "• Recognition Worker: Conda (InsightFace + FAISS)" "White"
    Write-ColorText "• WebRTC Server: Conda (aiortc)" "White"
    Write-ColorText "• API Server: Conda (FastAPI)" "White"
}

function Main {
    Clear-Host
    Write-Banner "MSYS2 CAMERA WORKER DEPENDENCIES INSTALLER"
    Write-ColorText "Timestamp: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" "Cyan"
    
    # Verificar MSYS2
    if (!(Test-MSYS2Installation)) {
        Write-ColorText "❌ MSYS2 não está configurado corretamente" "Red"
        Write-Host ""
        Write-ColorText "Press any key to exit..." "Cyan"
        $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
        return
    }
    
    # Instalar pacotes do sistema
    Install-SystemPackages
    
    # Instalar pacotes Python
    Install-PythonPackages
    
    # Testar instalação
    $allGood = Test-Installation
    
    # Mostrar resumo
    Show-Summary
    
    if ($allGood) {
        Write-ColorText "🎉 Instalação concluída com sucesso!" "Green"
    } else {
        Write-ColorText "⚠️ Instalação concluída com alguns avisos" "Yellow"
        Write-ColorText "O sistema pode funcionar mesmo assim" "Yellow"
    }
    
    Write-Host ""
    Write-ColorText "Press any key to exit..." "Cyan"
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
}

# Entry point
Main