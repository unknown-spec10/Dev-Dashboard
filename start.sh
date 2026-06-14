#!/bin/bash
set -e

echo "=========================================================="
echo "⚡ Celery Dev Dashboard - Quick Launch Tool"
echo "=========================================================="
echo

# 1. Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "[ERROR] Docker is not installed or not in your PATH."
    echo "Please install Docker Desktop from https://www.docker.com/products/docker-desktop"
    echo
    exit 1
fi

# 2. Check if Docker daemon is running
if ! docker info &> /dev/null; then
    echo "[ERROR] Docker is installed but the Docker daemon is not running."
    echo "Please make sure Docker Desktop is open and running, then try again."
    echo
    exit 1
fi

echo "[INFO] Docker daemon is running. Starting application stack..."
echo

# 3. Run docker compose up --build
docker compose up --build -d

echo
echo "=========================================================="
echo "🎉 Dev Dashboard Started Successfully!"
echo "=========================================================="
echo
echo "🌐 Frontend UI:           http://localhost:5173"
echo "📖 API Documentation:    http://localhost:8000/docs"
echo "🔑 Default API Key:      dev-dashboard-super-key"
echo
echo "📝 Commands:"
echo "  - To view logs:        docker compose logs -f"
echo "  - To stop services:    docker compose down"
echo
echo "=========================================================="
echo "Opening browser..."

# Open browser depending on OS
if [[ "$OSTYPE" == "darwin"* ]]; then
    open http://localhost:5173
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    if command -v xdg-open &> /dev/null; then
        xdg-open http://localhost:5173
    else
        echo "Please open http://localhost:5173 in your browser."
    fi
else
    echo "Please open http://localhost:5173 in your browser."
fi
echo
