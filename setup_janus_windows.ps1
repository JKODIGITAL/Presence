# Setup Janus Gateway for Windows (Native Installation)
# Downloads and configures Janus Gateway to run natively on Windows

param(
    [string]$InstallPath = "D:\Projetopresence\presence\janus-gateway"
)

Write-Host "========================================" -ForegroundColor Green
Write-Host "  JANUS GATEWAY WINDOWS SETUP" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""

Write-Host "Installing Janus Gateway to: $InstallPath" -ForegroundColor Yellow
Write-Host ""

# Create installation directory
if (-not (Test-Path $InstallPath)) {
    New-Item -ItemType Directory -Path $InstallPath -Force | Out-Null
    Write-Host "Created installation directory" -ForegroundColor Green
}

# Download Janus binaries for Windows
$janusUrl = "https://github.com/rsnapshot/janus-gateway-windows/releases/download/v0.11.8/janus-gateway-windows-0.11.8.zip"
$janusZip = "$env:TEMP\janus-gateway-windows.zip"

Write-Host "Downloading Janus Gateway Windows binaries..." -ForegroundColor Cyan
Write-Host "URL: $janusUrl" -ForegroundColor White

try {
    Invoke-WebRequest -Uri $janusUrl -OutFile $janusZip -ErrorAction Stop
    Write-Host "Download completed" -ForegroundColor Green
} catch {
    Write-Host "Primary download failed, trying alternative source..." -ForegroundColor Yellow
    
    # Alternative: Use a simpler approach - create configuration for manual installation
    Write-Host "Creating Janus configuration for manual installation..." -ForegroundColor Cyan
    
    # Create directory structure
    $dirs = @("bin", "etc\janus", "lib\janus\plugins", "lib\janus\transports", "share\janus")
    foreach ($dir in $dirs) {
        $fullPath = Join-Path $InstallPath $dir
        if (-not (Test-Path $fullPath)) {
            New-Item -ItemType Directory -Path $fullPath -Force | Out-Null
        }
    }
    
    # Create main Janus configuration
    $janusConfig = @"
[general]
configs_folder = $InstallPath/etc/janus
plugins_folder = $InstallPath/lib/janus/plugins
transports_folder = $InstallPath/lib/janus/transports
admin_secret = supersecret
server_name = Janus WebRTC Server
session_timeout = 60
reclaimSession_timeout = 10
debug_level = 4
debug_timestamps = yes
log_to_stdout = yes

[webserver]
base_path = /janus
threads = unlimited
http = yes
port = 8088
https = no
secure_port = 8089

[admin]
admin_base_path = /admin
admin_threads = unlimited
admin_http = yes
admin_port = 7088
admin_https = no
admin_secure_port = 7889

[certificates]
# cert_pem = $InstallPath/share/janus/certs/mycert.pem
# cert_key = $InstallPath/share/janus/certs/mycert.key

[media]
rtp_port_range = 40000-40100
"@

    $janusConfig | Out-File -FilePath "$InstallPath\etc\janus\janus.jcfg" -Encoding utf8
    
    # Create streaming plugin configuration
    $streamingConfig = @"
[general]
admin_key = supersecret

[stream-1]
type = rtp
id = 1
description = Camera Stream 1
video = true
videoport = 5004
videopt = 96
videortpmap = H264/90000
videofmtp = profile-level-id=42e01f;packetization-mode=1

[stream-2]
type = rtp
id = 2
description = Camera Stream 2
video = true
videoport = 5006
videopt = 96
videortpmap = H264/90000
videofmtp = profile-level-id=42e01f;packetization-mode=1

[stream-3]
type = rtp
id = 3
description = Camera Stream 3
video = true
videoport = 5008
videopt = 96
videortpmap = H264/90000
videofmtp = profile-level-id=42e01f;packetization-mode=1
"@

    $streamingConfig | Out-File -FilePath "$InstallPath\etc\janus\janus.plugin.streaming.jcfg" -Encoding utf8
    
    # Create WebSocket transport configuration
    $wsConfig = @"
[general]
ws = yes
ws_port = 8188
wss = no
wss_port = 8989
"@
    
    $wsConfig | Out-File -FilePath "$InstallPath\etc\janus\janus.transport.websockets.jcfg" -Encoding utf8
    
    # Create HTTP transport configuration
    $httpConfig = @"
[general]
base_path = /janus
threads = unlimited
http = yes
port = 8088
https = no
secure_port = 8089
"@
    
    $httpConfig | Out-File -FilePath "$InstallPath\etc\janus\janus.transport.http.jcfg" -Encoding utf8
    
    Write-Host "Configuration files created successfully!" -ForegroundColor Green
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Yellow
    Write-Host "  MANUAL INSTALLATION REQUIRED" -ForegroundColor Yellow
    Write-Host "========================================" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Janus Gateway configuration has been created, but you need to:" -ForegroundColor White
    Write-Host ""
    Write-Host "1. Download Janus Gateway Windows binaries manually from:" -ForegroundColor Cyan
    Write-Host "   https://github.com/meetecho/janus-gateway/releases" -ForegroundColor White
    Write-Host "   OR" -ForegroundColor White
    Write-Host "   https://github.com/rsnapshot/janus-gateway-windows/releases" -ForegroundColor White
    Write-Host ""
    Write-Host "2. Extract the binaries to:" -ForegroundColor Cyan
    Write-Host "   $InstallPath\bin\" -ForegroundColor White
    Write-Host ""
    Write-Host "3. Make sure janus.exe is in:" -ForegroundColor Cyan
    Write-Host "   $InstallPath\bin\janus.exe" -ForegroundColor White
    Write-Host ""
    Write-Host "4. Run the system with:" -ForegroundColor Cyan
    Write-Host "   .\start-system.ps1" -ForegroundColor White
    Write-Host ""
    Write-Host "Alternatively, you can use WSL2 with Linux Janus:" -ForegroundColor Yellow
    Write-Host "   wsl sudo apt install janus" -ForegroundColor White
    Write-Host ""
    
    return $false
}

if (Test-Path $janusZip) {
    Write-Host "Extracting Janus Gateway..." -ForegroundColor Cyan
    
    try {
        Expand-Archive -Path $janusZip -DestinationPath $InstallPath -Force
        Remove-Item $janusZip -Force
        
        Write-Host "Extraction completed" -ForegroundColor Green
        
        # Look for janus executable
        $janusExe = Get-ChildItem -Path $InstallPath -Recurse -Name "janus.exe" | Select-Object -First 1
        
        if ($janusExe) {
            $janusPath = Join-Path $InstallPath $janusExe
            Write-Host "Found Janus executable: $janusPath" -ForegroundColor Green
            
            # Test if it runs
            Write-Host "Testing Janus installation..." -ForegroundColor Cyan
            
            $testResult = Start-Process -FilePath $janusPath -ArgumentList "--help" -Wait -PassThru -WindowStyle Hidden
            
            if ($testResult.ExitCode -eq 0) {
                Write-Host "Janus installation successful!" -ForegroundColor Green
                return $true
            } else {
                Write-Host "Janus installation may have issues" -ForegroundColor Yellow
            }
        } else {
            Write-Host "Janus executable not found in extracted files" -ForegroundColor Yellow
        }
        
    } catch {
        Write-Host "Extraction failed: $_" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Red
Write-Host "  INSTALLATION INCOMPLETE" -ForegroundColor Red
Write-Host "========================================" -ForegroundColor Red
Write-Host ""
Write-Host "Janus Gateway could not be automatically installed." -ForegroundColor Yellow
Write-Host ""
Write-Host "RECOMMENDED SOLUTION:" -ForegroundColor Cyan
Write-Host ""
Write-Host "Use WSL2 (Windows Subsystem for Linux) for Janus:" -ForegroundColor White
Write-Host ""
Write-Host "1. Install WSL2:" -ForegroundColor Yellow
Write-Host "   wsl --install" -ForegroundColor White
Write-Host ""
Write-Host "2. Install Janus in WSL2:" -ForegroundColor Yellow
Write-Host "   wsl sudo apt update" -ForegroundColor White
Write-Host "   wsl sudo apt install janus" -ForegroundColor White
Write-Host ""
Write-Host "3. Start Janus in WSL2:" -ForegroundColor Yellow
Write-Host "   wsl janus --config=/etc/janus/janus.jcfg" -ForegroundColor White
Write-Host ""
Write-Host "4. Then run your system:" -ForegroundColor Yellow
Write-Host "   .\start-system.ps1" -ForegroundColor White
Write-Host ""

Read-Host "Press Enter to continue"