#!/bin/bash

echo "[1] Testing Camera Worker initialization..."

cd /mnt/d/Projetopresence/presence/app

# Set environment variables
export PYTHONPATH=/mnt/d/Projetopresence/presence
export ENVIRONMENT=development
export USE_GPU=true
export USE_PERFORMANCE_WORKER=true
export INSIGHTFACE_HOME=/mnt/d/Projetopresence/presence/data/models
export API_BASE_URL=http://127.0.0.1:17234
export RECOGNITION_WORKER_URL=http://127.0.0.1:17235
export FORCE_GSTREAMER_NATIVE=true
export CUDA_VISIBLE_DEVICES=0

echo "[2] Starting Camera Worker test..."
python3 camera_worker/main.py &

# Wait for a few seconds then kill
sleep 10
echo "[3] Stopping test..."
pkill -f "camera_worker/main.py"

echo "[4] Test completed"