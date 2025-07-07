# Script PowerShell para configurar PATHs CUDA permanentemente
# Execute como Administrador

Write-Host "Configurando PATHs CUDA permanentemente..." -ForegroundColor Green

# Definir caminhos CUDA
$cudaPath = "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v11.8"
$cudaBin = "$cudaPath\bin"
$cudaLibnvvp = "$cudaPath\libnvvp"

Write-Host "Verificando se CUDA existe..." -ForegroundColor Yellow
if (Test-Path $cudaBin) {
    Write-Host "✅ CUDA Toolkit encontrado em: $cudaBin" -ForegroundColor Green
} else {
    Write-Host "❌ CUDA Toolkit NAO encontrado em: $cudaBin" -ForegroundColor Red
    exit 1
}

# Verificar cuDNN
$cudnnDll = "$cudaBin\cudnn64_8.dll"
if (Test-Path $cudnnDll) {
    Write-Host "✅ cuDNN DLL encontrada: $cudnnDll" -ForegroundColor Green
} else {
    Write-Host "❌ cuDNN DLL NAO encontrada: $cudnnDll" -ForegroundColor Red
    Write-Host "💡 Baixe cuDNN e copie os arquivos para as pastas CUDA" -ForegroundColor Yellow
}

Write-Host "Configurando variáveis de ambiente..." -ForegroundColor Yellow

# Configurar variáveis de ambiente do sistema
try {
    [Environment]::SetEnvironmentVariable("CUDA_PATH", $cudaPath, [EnvironmentVariableTarget]::Machine)
    [Environment]::SetEnvironmentVariable("CUDA_PATH_V11_8", $cudaPath, [EnvironmentVariableTarget]::Machine)
    Write-Host "✅ Variáveis CUDA_PATH configuradas" -ForegroundColor Green
} catch {
    Write-Host "❌ Erro ao configurar variáveis de ambiente: $_" -ForegroundColor Red
}

# Obter PATH atual do sistema
$systemPath = [Environment]::GetEnvironmentVariable("PATH", [EnvironmentVariableTarget]::Machine)

# Verificar se os caminhos CUDA já estão no PATH
$pathsToAdd = @($cudaBin, $cudaLibnvvp)
$pathsAdded = @()

foreach ($pathToAdd in $pathsToAdd) {
    if ($systemPath -notlike "*$pathToAdd*") {
        $systemPath += ";$pathToAdd"
        $pathsAdded += $pathToAdd
        Write-Host "➕ Adicionado ao PATH: $pathToAdd" -ForegroundColor Green
    } else {
        Write-Host "⚠️ Já existe no PATH: $pathToAdd" -ForegroundColor Yellow
    }
}

# Atualizar PATH do sistema se necessário
if ($pathsAdded.Count -gt 0) {
    try {
        [Environment]::SetEnvironmentVariable("PATH", $systemPath, [EnvironmentVariableTarget]::Machine)
        Write-Host "✅ PATH do sistema atualizado" -ForegroundColor Green
    } catch {
        Write-Host "❌ Erro ao atualizar PATH: $_" -ForegroundColor Red
    }
} else {
    Write-Host "ℹ️ PATH já estava configurado corretamente" -ForegroundColor Cyan
}

Write-Host "`n🔄 IMPORTANTE: Reinicie o terminal/PowerShell para aplicar as mudanças" -ForegroundColor Magenta
Write-Host "Ou execute: `$env:PATH = [Environment]::GetEnvironmentVariable('PATH', [EnvironmentVariableTarget]::Machine)" -ForegroundColor Cyan

# Testar nvcc
Write-Host "`nTestando nvcc..." -ForegroundColor Yellow
try {
    $nvccVersion = & nvcc --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ nvcc funciona:" -ForegroundColor Green
        Write-Host $nvccVersion
    } else {
        Write-Host "❌ nvcc não funciona" -ForegroundColor Red
    }
} catch {
    Write-Host "❌ nvcc não encontrado: $_" -ForegroundColor Red
}

Write-Host "`n🎉 Configuração concluída!" -ForegroundColor Green
Write-Host "Agora teste o Recognition Worker novamente." -ForegroundColor Cyan