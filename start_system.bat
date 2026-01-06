@echo off
title SWaT AI Guardian v2.0 (Hybrid Windows+WSL)
setlocal enabledelayedexpansion

echo ===========================================
echo   SWaT AI GUARDIAN V2.0 - HYBRID STARTUP
echo ===========================================
echo   [Windows] : Kafka, API, Inference, UI
echo ===========================================
echo.


cd /d "C:\Users\Shubham\Documents\Secure Water Treatment System"

REM 0. Cleanup existing processes (Fresh Restart)
echo [0/7] Cleaning up existing processes...
taskkill /F /IM python.exe >nul 2>&1
taskkill /F /IM streamlit.exe >nul 2>&1
echo     Cleanup complete.
timeout /t 2 >nul

REM 1. Infrastructure
echo [1/7] Starting Kafka Infrastructure (Docker)...
docker compose up -d
echo Waiting for Kafka to stabilize (20)...
timeout /t 20
ping -n 6 127.0.0.1 > nul

REM 2. Topics
echo [2/7] Initializing Kafka Topics (Windows)...
call .venv\Scripts\activate
python src/data_ingestion/topics_setup.py
timeout /t 3

REM 3. API
echo [3/7] Starting FastAPI Backend (Windows)...
start "SWaT API" cmd /k "call .venv\Scripts\activate && python src/api/fastapi_server.py"
timeout /t 2

REM 4. Ensemble Inference
echo [4/7] Starting Ensemble Inference (Windows)...
start "SWaT AI Engine" cmd /k "call .venv\Scripts\activate && python src/inference/streaming_inference.py"
timeout /t 5

REM 5. Dashboard
echo [5/7] Starting Streamlit Dashboard (Windows)...
start "SWaT Dashboard" cmd /k "call .venv\Scripts\activate && streamlit run src/dashboard/app_kafka_live.py"
timeout /t 3

REM 6. Producer
echo [6/7] Starting Kafka Producer (Windows)...
start "SWaT Producer" cmd /k "call .venv\Scripts\activate && python src/data_ingestion/kafka_producer.py"

REM 7. Spark (WSL Ubuntu)
echo [7/7] Starting Spark Engine (WSL)...
start "SWaT Spark Engine" wsl bash -c "export PYSPARK_PYTHON=python3; cd '$(wslpath 'C:\Users\Shubham\Documents\Secure Water Treatment System')'; echo 'Fixing Dependencies for Python 3.12...'; pip uninstall -y kafka-python --break-system-packages > /dev/null 2>&1; pip install kafka-python-ng pandas numpy tensorflow scikit-learn pyspark --break-system-packages > /dev/null 2>&1; echo 'Starting Spark Consumer...'; python3 src/inference/spark_consumer.py; echo 'Process exited.'; read -p 'Press Enter to close...'"

echo.
echo ===========================================
echo   SYSTEM READY - MONITORING ACTIVE
echo ===========================================
echo Windows VEnv:  Active (.venv_swat)
echo API Backend:   http://localhost:8000
echo Dashboard:     http://localhost:8501
echo Kafka UI:      http://localhost:8081
echo ===========================================
pause
