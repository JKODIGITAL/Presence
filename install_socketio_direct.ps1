# Direct Socket.IO installation script for MSYS2

Write-Host "Installing Socket.IO directly in MSYS2..." -ForegroundColor Cyan

# Set environment for MSYS2
$env:MSYSTEM = "MINGW64"
$env:PATH = "C:\msys64\mingw64\bin;C:\msys64\usr\bin;" + $env:PATH

# Install using MSYS2 Python directly
Write-Host "Using MSYS2 Python to install socketio..." -ForegroundColor Yellow

try {
    # First try pip install
    & "C:\msys64\mingw64\bin\python.exe" -m pip install python-socketio aiohttp --user
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Socket.IO installed successfully!" -ForegroundColor Green
    } else {
        Write-Host "Trying alternative installation..." -ForegroundColor Yellow
        & "C:\msys64\mingw64\bin\python.exe" -m pip install python-socketio --user
    }
    
    # Test installation
    Write-Host "Testing Socket.IO installation..." -ForegroundColor Cyan
    $testResult = & "C:\msys64\mingw64\bin\python.exe" -c "import socketio; print('SUCCESS:', socketio.__version__)"
    
    if ($testResult -match "SUCCESS:") {
        Write-Host "Socket.IO is working: $testResult" -ForegroundColor Green
    } else {
        Write-Host "Socket.IO test failed" -ForegroundColor Red
    }
    
} catch {
    Write-Host "Error installing Socket.IO: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host "Installation complete. Press any key to continue..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey('NoEcho,IncludeKeyDown')