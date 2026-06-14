@echo off
setlocal enabledelayedexpansion

echo ==========================================================
echo ⚡ Celery Dev Dashboard - Quick Launch Tool
echo ==========================================================
echo.

:: 1. Check if Docker CLI is installed
where docker >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Docker is not installed or not in your PATH.
    echo Please install Docker Desktop from https://www.docker.com/products/docker-desktop
    echo.
    pause
    exit /b 1
)

:: 2. Check if Docker daemon is running
docker info >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Docker is installed but the Docker daemon is not running.
    echo Please make sure Docker Desktop is open and running, then try again.
    echo.
    pause
    exit /b 1
)

echo [INFO] Docker daemon is running. Starting application stack...
echo.

:: 3. Run docker compose up --build
docker compose up --build -d
if %errorlevel% neq 0 (
    echo [ERROR] Failed to start Docker containers.
    echo.
    pause
    exit /b 1
)

echo.
echo ==========================================================
echo 🎉 Dev Dashboard Started Successfully!
echo ==========================================================
echo.
echo 🌐 Frontend UI:           http://localhost:5173
echo 📖 API Documentation:    http://localhost:8000/docs
echo 🔑 Default API Key:      dev-dashboard-super-key
echo.
echo 📝 Commands:
echo   - To view logs:        docker compose logs -f
echo   - To stop services:    docker compose down
echo.
echo ==========================================================
echo Opening browser...
start http://localhost:5173
echo.

pause
