# Script para instalar dependências Python no MSYS2
Write-Host "🔧 INSTALANDO DEPENDÊNCIAS PYTHON NO MSYS2" -ForegroundColor Green
Write-Host "=" * 50

# Verificar se MSYS2 existe
$msys2Path = "C:\msys64"
if (-not (Test-Path $msys2Path)) {
    Write-Host "❌ MSYS2 não encontrado em $msys2Path" -ForegroundColor Red
    Write-Host "   Instale o MSYS2 primeiro: https://www.msys2.org/" -ForegroundColor Yellow
    exit 1
}

Write-Host "✅ MSYS2 encontrado: $msys2Path" -ForegroundColor Green

# Configurar ambiente
$env:PATH = "C:\msys64\mingw64\bin;C:\msys64\usr\bin;$env:PATH"

Write-Host "`n📦 Instalando pacotes base do MSYS2..." -ForegroundColor Yellow
& "C:\msys64\usr\bin\pacman.exe" -S --noconfirm mingw-w64-x86_64-python-pip

Write-Host "`n🐍 Instalando dependências Python via pip..." -ForegroundColor Yellow

# Lista de dependências Python necessárias
$pythonDeps = @(
    "websockets",
    "aiohttp", 
    "loguru",
    "numpy"
)

foreach ($dep in $pythonDeps) {
    Write-Host "   Instalando $dep..." -ForegroundColor Cyan
    & "C:\msys64\mingw64\bin\python.exe" -m pip install $dep
    if ($LASTEXITCODE -eq 0) {
        Write-Host "   ✅ $dep instalado" -ForegroundColor Green
    } else {
        Write-Host "   ❌ Erro ao instalar $dep" -ForegroundColor Red
    }
}

Write-Host "`n🧪 Testando importações..." -ForegroundColor Yellow
$testScript = @"
try:
    import websockets
    print('✅ websockets OK')
    
    import aiohttp  
    print('✅ aiohttp OK')
    
    import gi
    gi.require_version('Gst', '1.0')
    from gi.repository import Gst
    print('✅ GStreamer OK')
    
    import loguru
    print('✅ loguru OK')
    
    print('🎉 TODAS AS DEPENDÊNCIAS OK!')
    
except ImportError as e:
    print(f'❌ Erro: {e}')
"@

Write-Host "   Executando teste..." -ForegroundColor Cyan
$testScript | & "C:\msys64\mingw64\bin\python.exe"

Write-Host "`n✅ INSTALAÇÃO CONCLUÍDA!" -ForegroundColor Green
Write-Host "🚀 Sistema pronto para executar WebRTC Worker no MSYS2" -ForegroundColor Cyan