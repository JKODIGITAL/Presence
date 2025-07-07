#!/bin/bash
# Setup CUDA environment for Recognition Engine

# Ativar ambiente conda
source /home/pikachu/miniconda3/etc/profile.d/conda.sh
conda activate presence

# Configurar LD_LIBRARY_PATH com todas as bibliotecas CUDA necessárias
CONDA_PREFIX=/home/pikachu/miniconda3/envs/presence

export LD_LIBRARY_PATH="\
~/cuda/lib64:\
$CONDA_PREFIX/lib/python3.10/site-packages/nvidia/cublas/lib:\
$CONDA_PREFIX/lib/python3.10/site-packages/nvidia/curand/lib:\
$CONDA_PREFIX/lib/python3.10/site-packages/nvidia/cufft/lib:\
$CONDA_PREFIX/lib/python3.10/site-packages/nvidia/cusolver/lib:\
$CONDA_PREFIX/lib/python3.10/site-packages/nvidia/cusparse/lib:\
$CONDA_PREFIX/lib:\
$LD_LIBRARY_PATH"

echo "CUDA environment configured:"
echo "LD_LIBRARY_PATH=$LD_LIBRARY_PATH"

# Testar se ONNX Runtime funciona
python -c "import onnxruntime as ort; print('ONNX Providers:', ort.get_available_providers())"

# Executar teste se fornecido
if [ "$1" ]; then
    python "$1"
fi