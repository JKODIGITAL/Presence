@echo off
REM Script para parar todos os serviços do Presence no Windows

echo.
echo ========================================
echo   PARANDO SERVIÇOS PRESENCE
echo ========================================
echo.

echo Matando processos Python (API, Workers, WebRTC)...
taskkill /f /im python.exe >nul 2>nul
taskkill /f /im pythonw.exe >nul 2>nul

echo Matando processos Node.js (Frontend)...
taskkill /f /im node.exe >nul 2>nul

echo Matando servidores uvicorn...
taskkill /f /im uvicorn.exe >nul 2>nul

echo Fechando terminais cmd dos serviços...
taskkill /fi "WINDOWTITLE eq Presence*" /f >nul 2>nul
taskkill /fi "WINDOWTITLE eq Recognition*" /f >nul 2>nul
taskkill /fi "WINDOWTITLE eq Camera*" /f >nul 2>nul
taskkill /fi "WINDOWTITLE eq VMS*" /f >nul 2>nul
taskkill /fi "WINDOWTITLE eq Frontend*" /f >nul 2>nul

echo.
echo ✓ Todos os serviços foram parados.
echo.
pause