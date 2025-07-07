# Script de instalação do GStreamer para Windows
# Este script baixa e instala o GStreamer e suas dependências no Windows

# Verificar se está sendo executado como administrador
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "Este script precisa ser executado como administrador." -ForegroundColor Red
    Write-Host "Por favor, reinicie o PowerShell como administrador e execute novamente." -ForegroundColor Red
    exit 1
}

# Configurações
$gstreamerVersion = "1.22.9"
$msvcVersion = "msvc-x86_64"
$downloadUrl = "https://gstreamer.freedesktop.org/data/pkg/windows/$gstreamerVersion/gstreamer-1.0-$msvcVersion-$gstreamerVersion.msi"
$installerPath = "$env:TEMP\gstreamer-$gstreamerVersion.msi"
$installPath = "C:\gstreamer\1.0"

# Função para mostrar progresso
function Show-Progress {
    param (
        [string]$Activity,
        [string]$Status,
        [int]$PercentComplete
    )
    
    Write-Progress -Activity $Activity -Status $Status -PercentComplete $PercentComplete
}

# Banner
Write-Host "=========================================================" -ForegroundColor Cyan
Write-Host "       INSTALADOR DO GSTREAMER PARA WINDOWS              " -ForegroundColor Cyan
Write-Host "=========================================================" -ForegroundColor Cyan
Write-Host "Versão: $gstreamerVersion"
Write-Host "Arquitetura: $msvcVersion"
Write-Host "Caminho de instalação: $installPath"
Write-Host "=========================================================" -ForegroundColor Cyan

# Verificar se o GStreamer já está instalado
if (Test-Path "$installPath\bin\gst-launch-1.0.exe") {
    $currentVersion = & "$installPath\bin\gst-launch-1.0.exe" --version 2>$null
    if ($currentVersion) {
        Write-Host "GStreamer já está instalado:" -ForegroundColor Green
        Write-Host $currentVersion
        
        $reinstall = Read-Host "Deseja reinstalar? (s/N)"
        if ($reinstall.ToLower() -ne "s") {
            Write-Host "Instalação cancelada pelo usuário." -ForegroundColor Yellow
            exit 0
        }
    }
}

# Baixar o instalador
Write-Host "Baixando GStreamer $gstreamerVersion..." -ForegroundColor Yellow
try {
    Show-Progress -Activity "Baixando GStreamer" -Status "Conectando..." -PercentComplete 0
    
    # Usar .NET WebClient para download com progresso
    $webClient = New-Object System.Net.WebClient
    $webClient.DownloadFile($downloadUrl, $installerPath)
    
    Show-Progress -Activity "Baixando GStreamer" -Status "Concluído" -PercentComplete 100
    Write-Host "Download concluído: $installerPath" -ForegroundColor Green
} 
catch {
    Write-Host "Erro ao baixar o GStreamer: $_" -ForegroundColor Red
    exit 1
}

# Verificar se o arquivo foi baixado
if (-not (Test-Path $installerPath)) {
    Write-Host "Falha ao baixar o instalador do GStreamer." -ForegroundColor Red
    exit 1
}

# Instalar o GStreamer
Write-Host "Instalando GStreamer..." -ForegroundColor Yellow
try {
    Show-Progress -Activity "Instalando GStreamer" -Status "Executando instalador..." -PercentComplete 0
    
    # Executar o instalador MSI silenciosamente com todas as opções
    $arguments = "/i `"$installerPath`" /qn ADDLOCAL=ALL INSTALLDIR=`"$installPath`""
    Start-Process -FilePath "msiexec.exe" -ArgumentList $arguments -Wait
    
    Show-Progress -Activity "Instalando GStreamer" -Status "Concluído" -PercentComplete 100
    
    # Verificar se a instalação foi bem-sucedida
    if (Test-Path "$installPath\bin\gst-launch-1.0.exe") {
        Write-Host "GStreamer instalado com sucesso!" -ForegroundColor Green
    } else {
        Write-Host "Falha na instalação do GStreamer." -ForegroundColor Red
        exit 1
    }
} 
catch {
    Write-Host "Erro ao instalar o GStreamer: $_" -ForegroundColor Red
    exit 1
}

# Configurar variáveis de ambiente
Write-Host "Configurando variáveis de ambiente..." -ForegroundColor Yellow

# Adicionar ao PATH
$envPath = [Environment]::GetEnvironmentVariable("PATH", "Machine")
$gstBinPath = "$installPath\bin"
if (-not $envPath.Contains($gstBinPath)) {
    [Environment]::SetEnvironmentVariable("PATH", "$envPath;$gstBinPath", "Machine")
    Write-Host "GStreamer adicionado ao PATH do sistema." -ForegroundColor Green
} else {
    Write-Host "GStreamer já está no PATH do sistema." -ForegroundColor Green
}

# Definir GSTREAMER_ROOT_X86_64
[Environment]::SetEnvironmentVariable("GSTREAMER_ROOT_X86_64", $installPath, "Machine")
Write-Host "Variável GSTREAMER_ROOT_X86_64 configurada." -ForegroundColor Green

# Instalar dependências Python
Write-Host "Instalando dependências Python..." -ForegroundColor Yellow
try {
    # Verificar se o pip está disponível
    $pipVersion = & python -m pip --version 2>$null
    if (-not $pipVersion) {
        Write-Host "Python pip não encontrado. Por favor, instale o Python e o pip." -ForegroundColor Red
        exit 1
    }
    
    # Instalar PyGObject e outras dependências
    & python -m pip install pygobject-stubs opencv-python numpy
    
    Write-Host "Dependências Python instaladas com sucesso!" -ForegroundColor Green
} 
catch {
    Write-Host "Erro ao instalar dependências Python: $_" -ForegroundColor Red
}

# Testar a instalação
Write-Host "Testando instalação do GStreamer..." -ForegroundColor Yellow
try {
    $gstVersion = & "$installPath\bin\gst-launch-1.0.exe" --version
    Write-Host "GStreamer instalado e funcionando:" -ForegroundColor Green
    Write-Host $gstVersion
    
    # Testar plugins
    Write-Host "Verificando plugins instalados..." -ForegroundColor Yellow
    $plugins = & "$installPath\bin\gst-inspect-1.0.exe" | Select-String "^(" -Context 0,1
    $pluginCount = ($plugins | Measure-Object).Count
    Write-Host "Total de $pluginCount plugins encontrados." -ForegroundColor Green
    
    # Verificar plugins críticos
    $criticalPlugins = @("rtspsrc", "v4l2src", "videoconvert", "appsink")
    foreach ($plugin in $criticalPlugins) {
        $result = & "$installPath\bin\gst-inspect-1.0.exe" $plugin 2>$null
        if ($result) {
            Write-Host "✓ Plugin $plugin: Disponível" -ForegroundColor Green
        } else {
            Write-Host "✗ Plugin $plugin: Não encontrado" -ForegroundColor Red
        }
    }
} 
catch {
    Write-Host "Erro ao testar o GStreamer: $_" -ForegroundColor Red
}

# Limpar arquivos temporários
Write-Host "Limpando arquivos temporários..." -ForegroundColor Yellow
Remove-Item $installerPath -Force -ErrorAction SilentlyContinue

# Conclusão
Write-Host "=========================================================" -ForegroundColor Cyan
Write-Host "       INSTALAÇÃO DO GSTREAMER CONCLUÍDA                 " -ForegroundColor Cyan
Write-Host "=========================================================" -ForegroundColor Cyan
Write-Host "GStreamer $gstreamerVersion instalado em: $installPath"
Write-Host "Caminho do executável: $installPath\bin\gst-launch-1.0.exe"
Write-Host "Variáveis de ambiente configuradas."
Write-Host ""
Write-Host "Para testar, abra um NOVO terminal e execute:"
Write-Host "gst-launch-1.0 --version" -ForegroundColor Yellow
Write-Host ""
Write-Host "Para testar um pipeline simples:"
Write-Host "gst-launch-1.0 videotestsrc ! videoconvert ! autovideosink" -ForegroundColor Yellow
Write-Host "=========================================================" -ForegroundColor Cyan 