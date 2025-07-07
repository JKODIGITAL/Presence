# Check if WebRTC server is running
Write-Host "Checking WebRTC server status..." -ForegroundColor Cyan

# Check for Python processes related to WebRTC
$webrtcProcesses = Get-Process | Where-Object {
    $_.ProcessName -eq "python" -and 
    $_.MainWindowTitle -like "*WebRTC*"
}

if ($webrtcProcesses) {
    Write-Host "WebRTC processes found:" -ForegroundColor Green
    $webrtcProcesses | Format-Table Id, ProcessName, MainWindowTitle
} else {
    Write-Host "No WebRTC server processes found" -ForegroundColor Red
}

# Check port 17236
Write-Host "Checking port 17236..." -ForegroundColor Cyan
try {
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:17236/health" -TimeoutSec 3
    Write-Host "Port 17236 is responding: $($response.StatusCode)" -ForegroundColor Green
} catch {
    Write-Host "Port 17236 is not responding: $($_.Exception.Message)" -ForegroundColor Red
}

# Start WebRTC server if not running
if (-not $webrtcProcesses) {
    Write-Host "Starting WebRTC server..." -ForegroundColor Yellow
    Start-Process -FilePath "logs\webrtc-server.bat" -WorkingDirectory "app"
    Write-Host "WebRTC server started" -ForegroundColor Green
}

Write-Host "Check complete" -ForegroundColor Cyan