# Force restart frontend with cache clear
Write-Host "🔄 Reiniciando frontend com cache limpo..." -ForegroundColor Cyan

# Kill existing processes
$processes = Get-Process | Where-Object {$_.ProcessName -eq "node" -and $_.MainWindowTitle -like "*vite*"}
if ($processes) {
    Write-Host "🛑 Parando processos Vite..." -ForegroundColor Yellow
    $processes | Stop-Process -Force
    Start-Sleep -Seconds 2
}

# Clear all cache
Write-Host "🧹 Limpando cache..." -ForegroundColor Yellow
Set-Location "frontend"
if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }
if (Test-Path "node_modules\.vite") { Remove-Item -Recurse -Force "node_modules\.vite" }
if (Test-Path ".vite") { Remove-Item -Recurse -Force ".vite" }

# Add cache busting to environment
$timestamp = Get-Date -Format "yyyyMMddHHmmss"
$env:VITE_CACHE_BUST = $timestamp

Write-Host "⚙️ Configurando variáveis de ambiente..." -ForegroundColor Cyan
$env:VITE_API_URL = "http://127.0.0.1:17234"
$env:VITE_VMS_WEBRTC_URL = "http://127.0.0.1:17236"
$env:VITE_WEBRTC_CAMERA_WS_BASE = "ws://127.0.0.1:17236"

Write-Host "🚀 Iniciando servidor de desenvolvimento..." -ForegroundColor Green
Write-Host "Porta WebRTC configurada: 17236" -ForegroundColor White
Write-Host "Cache bust: $timestamp" -ForegroundColor White

# Start dev server
npm run dev