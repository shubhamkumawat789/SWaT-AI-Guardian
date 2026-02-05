@echo off
echo ========================================================
echo   SWaT AI Guardian - Live Demo Launcher
echo ========================================================
echo.
echo [1/3] Checking Docker Status...
docker info >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Error: Docker is NOT running!
    echo     Please start Docker Desktop and run this script again.
    pause
    exit /b
)

echo [2/3] Starting System (Kafka, Spark, Dashboard)...
docker compose up -d
if %errorlevel% neq 0 (
    echo [!] Failed to start containers.
    pause
    exit /b
)

echo.
echo [3/3] Generating Public URL for Recruiter...
echo     (This may ask you to install 'localtunnel' temporarily - say Yes)
echo.
echo ========================================================
echo   Use the URL below to share with the Recruiter
echo   Keep this window OPEN while they are viewing.
echo ========================================================
echo.
cmd /c "npx localtunnel --port 8501"
pause
