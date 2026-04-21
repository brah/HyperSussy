@echo off
rem Dev orchestrator for HyperSussy — starts backend, frontend, or both.
rem
rem Usage:
rem   dev.bat             :: both (backend on :8000, frontend on :5173)
rem   dev.bat backend     :: backend only (uv run hypersussy --api)
rem   dev.bat frontend    :: frontend only (npm run dev in .\frontend)
rem
rem Each server launches in its own console window so logs stay readable
rem and Ctrl+C in either window shuts down just that server. The parent
rem script exits after spawning the child windows.

setlocal
cd /d "%~dp0"

set "TARGET=%~1"
if "%TARGET%"=="" set "TARGET=all"

if /i "%TARGET%"=="backend"  goto backend
if /i "%TARGET%"=="frontend" goto frontend
if /i "%TARGET%"=="all"      goto all
echo Usage: %~nx0 [backend^|frontend]
exit /b 2

:backend
echo ^>^> Starting backend (uv run hypersussy --api)...
start "hypersussy-backend" cmd /k "uv run hypersussy --api"
goto end

:frontend
echo ^>^> Starting frontend (npm run dev)...
start "hypersussy-frontend" cmd /k "cd frontend && npm run dev"
goto end

:all
echo ^>^> Starting backend (uv run hypersussy --api)...
start "hypersussy-backend" cmd /k "uv run hypersussy --api"
echo ^>^> Starting frontend (npm run dev)...
start "hypersussy-frontend" cmd /k "cd frontend && npm run dev"
goto end

:end
endlocal
