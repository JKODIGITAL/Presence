# Test Frontend Setup
param([switch]$Fix)

Write-Host "Testing Frontend Setup..." -ForegroundColor Cyan

# Check Node.js
Write-Host "Checking Node.js..." -ForegroundColor Yellow
try {
    $nodeVersion = node --version
    Write-Host "✅ Node.js: $nodeVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ Node.js not found!" -ForegroundColor Red
    exit 1
}

# Check npm
Write-Host "Checking npm..." -ForegroundColor Yellow
try {
    $npmVersion = npm --version
    Write-Host "✅ npm: $npmVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ npm not found!" -ForegroundColor Red
    exit 1
}

# Check frontend directory
$FrontendPath = "D:\Projetopresence\presence\frontend"
if (Test-Path $FrontendPath) {
    Write-Host "✅ Frontend directory exists" -ForegroundColor Green
    Set-Location $FrontendPath
} else {
    Write-Host "❌ Frontend directory not found!" -ForegroundColor Red
    exit 1
}

# Check package.json
if (Test-Path "package.json") {
    Write-Host "✅ package.json exists" -ForegroundColor Green
} else {
    Write-Host "❌ package.json not found!" -ForegroundColor Red
    exit 1
}

# Install dependencies if requested
if ($Fix) {
    Write-Host "Installing dependencies..." -ForegroundColor Yellow
    npm install
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Dependencies installed" -ForegroundColor Green
    } else {
        Write-Host "❌ Failed to install dependencies" -ForegroundColor Red
        exit 1
    }
}

# Check if dev script exists
$packageContent = Get-Content "package.json" | ConvertFrom-Json
if ($packageContent.scripts.dev) {
    Write-Host "✅ dev script found: $($packageContent.scripts.dev)" -ForegroundColor Green
} else {
    Write-Host "❌ dev script not found in package.json!" -ForegroundColor Red
}

Write-Host ""
Write-Host "Frontend test complete!" -ForegroundColor Green
Write-Host "To fix issues, run: .\test-frontend.ps1 -Fix" -ForegroundColor Cyan