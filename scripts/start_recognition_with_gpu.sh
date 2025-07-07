#!/bin/bash
# Start Recognition Engine with full GPU support

# Set up CUDA environment
export CUDA_HOME=/home/pikachu/cuda
export CUDNN_HOME=/home/pikachu/cuda
export LD_LIBRARY_PATH="/home/pikachu/cuda/lib64:/home/pikachu/miniconda3/envs/presence/lib/python3.10/site-packages/nvidia/cublas/lib:/home/pikachu/miniconda3/envs/presence/lib/python3.10/site-packages/nvidia/curand/lib:/home/pikachu/miniconda3/envs/presence/lib:$LD_LIBRARY_PATH"

# GPU configuration
export USE_GPU=true
export RECOGNITION_WORKER=true
export CUDA_VISIBLE_DEVICES=0

# Activate conda environment
source /home/pikachu/miniconda3/etc/profile.d/conda.sh
conda activate presence

echo "🚀 CUDA/GPU Environment:"
echo "  CUDA_HOME: $CUDA_HOME"
echo "  USE_GPU: $USE_GPU"
echo "  CUDA_VISIBLE_DEVICES: $CUDA_VISIBLE_DEVICES"
echo "  LD_LIBRARY_PATH configured with CUDA libraries"

# Test CUDA libraries
echo -n "🧪 Testing libcudnn.so.8: "
if [ -f "/home/pikachu/cuda/lib64/libcudnn.so.8" ]; then
    echo "✅ Found"
else
    echo "❌ Not found"
fi

echo -n "🧪 Testing ONNX Runtime CUDA: "
python -c "import onnxruntime as ort; providers = ort.get_available_providers(); print('✅ OK' if 'CUDAExecutionProvider' in providers else '❌ FAIL')"

# Run the provided script or Recognition Engine test
if [ "$1" ]; then
    echo "🏃 Running: $1"
    python "$1"
else
    echo "🏃 Testing Recognition Engine with GPU..."
    python scripts/test_gpu_final.py
fi