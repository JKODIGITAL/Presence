#!/usr/bin/env pwsh
# ============================================================================
# PRESENCE SYSTEM - ENVIRONMENT SEPARATION VERIFICATION
# ============================================================================
# Verifica se os ambientes Conda e MSYS2 estão separados corretamente
# ============================================================================

$ErrorActionPreference = "Continue"
$Host.UI.RawUI.WindowTitle = "Presence Environment Verification"

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

function Test-CondaEnvironment {
    Write-Banner "TESTING CONDA ENVIRONMENT (PURE)"
    
    Write-ColorText "Testing Conda 'presence' environment..." "Cyan"
    
    # Test 1: Conda activation and Python path
    $condaTestCmd = @"
cmd /c "call C:\Users\Danilo\miniconda3\Scripts\activate.bat presence && 
set PATH=%PATH:C:\msys64\mingw64\bin;=% && 
set PATH=%PATH:C:\msys64\usr\bin;=% && 
python -c \"import sys; print('CONDA-PYTHON:', sys.executable)\" &&
python -c \"import os; print('CONDA-PATH:', os.environ.get('PATH', '').split(';')[0])\" &&
python -c \"import torch, faiss, insightface, socketio, aiortc, fastapi, uvicorn; print('CONDA-DEPS: OK')\"" 2>&1
"@
    
    $result = Invoke-Expression $condaTestCmd
    
    if ($result -match "CONDA-PYTHON:.*miniconda3.*presence") {
        Write-ColorText "✅ Conda Python path is correct" "Green"
        $pythonPath = ($result | Where-Object { $_ -match "CONDA-PYTHON:" } | Select-Object -First 1) -replace "CONDA-PYTHON: ", ""
        Write-ColorText "   Path: $pythonPath" "White"
    } else {
        Write-ColorText "❌ Conda Python path is incorrect" "Red"
    }
    
    if ($result -match "CONDA-DEPS: OK") {
        Write-ColorText "✅ Conda dependencies are available" "Green"
    } else {
        Write-ColorText "❌ Conda dependencies missing" "Red"
        Write-ColorText "   Error: $result" "Yellow"
    }
    
    # Test 2: Verify MSYS2 is NOT in PATH
    $pathTestCmd = @"
cmd /c "call C:\Users\Danilo\miniconda3\Scripts\activate.bat presence && 
set PATH=%PATH:C:\msys64\mingw64\bin;=% && 
set PATH=%PATH:C:\msys64\usr\bin;=% && 
echo %PATH%" 2>&1
"@
    
    $pathResult = Invoke-Expression $pathTestCmd
    if ($pathResult -match "msys64") {
        Write-ColorText "⚠️ MSYS2 still in PATH after removal" "Yellow"
    } else {
        Write-ColorText "✅ MSYS2 successfully removed from PATH" "Green"
    }
}

function Test-MSYS2Environment {
    Write-Banner "TESTING MSYS2 ENVIRONMENT (PURE)"
    
    Write-ColorText "Testing MSYS2 Python environment..." "Cyan"
    
    # Test 1: MSYS2 Python path and packages
    $msysTestCmd = @"
cmd /c "set PATH=C:\msys64\mingw64\bin;C:\msys64\usr\bin;%PATH% && 
C:\msys64\mingw64\bin\python.exe -c \"import sys; print('MSYS2-PYTHON:', sys.executable)\" &&
C:\msys64\mingw64\bin\python.exe -c \"import gi, cv2, numpy, socketio; print('MSYS2-DEPS: OK')\"" 2>&1
"@
    
    $result = Invoke-Expression $msysTestCmd
    
    if ($result -match "MSYS2-PYTHON:.*msys64.*python.exe") {
        Write-ColorText "✅ MSYS2 Python path is correct" "Green"
        $pythonPath = ($result | Where-Object { $_ -match "MSYS2-PYTHON:" } | Select-Object -First 1) -replace "MSYS2-PYTHON: ", ""
        Write-ColorText "   Path: $pythonPath" "White"
    } else {
        Write-ColorText "❌ MSYS2 Python path is incorrect" "Red"
    }
    
    if ($result -match "MSYS2-DEPS: OK") {
        Write-ColorText "✅ MSYS2 dependencies are available" "Green"
    } else {
        Write-ColorText "❌ MSYS2 dependencies missing" "Red"
        Write-ColorText "   Error: $result" "Yellow"
    }
    
    # Test 2: GStreamer
    Write-ColorText "Testing GStreamer..." "Cyan"
    $gstTest = & "C:\msys64\mingw64\bin\gst-inspect-1.0.exe" --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-ColorText "✅ GStreamer working" "Green"
    } else {
        Write-ColorText "❌ GStreamer not working" "Red"
    }
}

function Test-EnvironmentSeparation {
    Write-Banner "TESTING ENVIRONMENT SEPARATION"
    
    Write-ColorText "Verifying environments don't interfere..." "Cyan"
    
    # Test that Conda can't import gi (GStreamer Python bindings)
    $condaGITest = @"
cmd /c "call C:\Users\Danilo\miniconda3\Scripts\activate.bat presence && 
set PATH=%PATH:C:\msys64\mingw64\bin;=% && 
set PATH=%PATH:C:\msys64\usr\bin;=% && 
python -c \"import gi; print('GI-IMPORTED')\"" 2>&1
"@
    
    $result = Invoke-Expression $condaGITest
    if ($result -match "GI-IMPORTED") {
        Write-ColorText "⚠️ Conda can import gi (potential mixing)" "Yellow"
    } else {
        Write-ColorText "✅ Conda cannot import gi (good separation)" "Green"
    }
    
    # Test that MSYS2 can't import torch
    $msysTorchTest = @"
cmd /c "set PATH=C:\msys64\mingw64\bin;C:\msys64\usr\bin;%PATH% && 
C:\msys64\mingw64\bin\python.exe -c \"import torch; print('TORCH-IMPORTED')\"" 2>&1
"@
    
    $result = Invoke-Expression $msysTorchTest
    if ($result -match "TORCH-IMPORTED") {
        Write-ColorText "⚠️ MSYS2 can import torch (potential mixing)" "Yellow"
    } else {
        Write-ColorText "✅ MSYS2 cannot import torch (good separation)" "Green"
    }
}

function Test-PipConfiguration {
    Write-Banner "TESTING PIP CONFIGURATION"
    
    Write-ColorText "Testing pip in Conda environment..." "Cyan"
    
    # Test pip in Conda
    $condaPipTest = @"
cmd /c "call C:\Users\Danilo\miniconda3\Scripts\activate.bat presence && 
set PATH=%PATH:C:\msys64\mingw64\bin;=% && 
set PATH=%PATH:C:\msys64\usr\bin;=% && 
pip --version" 2>&1
"@
    
    $result = Invoke-Expression $condaPipTest
    if ($result -match "externally managed") {
        Write-ColorText "❌ Conda pip shows 'externally managed' (mixing detected)" "Red"
    } elseif ($result -match "pip.*python.*miniconda3.*presence") {
        Write-ColorText "✅ Conda pip working correctly" "Green"
    } else {
        Write-ColorText "⚠️ Conda pip response unclear: $result" "Yellow"
    }
    
    Write-ColorText "Testing pip in MSYS2 environment..." "Cyan"
    
    # Test pip in MSYS2
    $msysPipTest = @"
cmd /c "set PATH=C:\msys64\mingw64\bin;C:\msys64\usr\bin;%PATH% && 
C:\msys64\mingw64\bin\python.exe -m pip --version" 2>&1
"@
    
    $result = Invoke-Expression $msysPipTest
    if ($result -match "pip.*python.*msys64") {
        Write-ColorText "✅ MSYS2 pip working correctly" "Green"
    } else {
        Write-ColorText "⚠️ MSYS2 pip response unclear: $result" "Yellow"
    }
}

function Main {
    Clear-Host
    Write-Banner "PRESENCE ENVIRONMENT SEPARATION VERIFICATION"
    Write-ColorText "Timestamp: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" "Cyan"
    
    Test-CondaEnvironment
    Test-MSYS2Environment  
    Test-EnvironmentSeparation
    Test-PipConfiguration
    
    Write-Banner "VERIFICATION COMPLETE"
    Write-ColorText "✅ If all tests pass, environments are properly separated" "Green"
    Write-ColorText "⚠️ If any tests show warnings, review the mixing issues" "Yellow"
    Write-ColorText "❌ If tests fail, dependencies need to be installed" "Red"
    
    Write-Host ""
    Write-ColorText "Press any key to exit..." "Cyan"
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
}

# Entry point
Main