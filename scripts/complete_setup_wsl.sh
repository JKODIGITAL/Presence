#!/bin/bash
# Script para completar a instalação WSL após resolver problemas de conectividade
# Execute quando tiver melhor conectividade de rede

echo "========================================"
echo "   COMPLETANDO SETUP WSL → Windows"
echo "========================================"
echo ""

# Configurar PATH do conda
export PATH="$HOME/miniconda3/bin:$PATH"
source $HOME/miniconda3/etc/profile.d/conda.sh 2>/dev/null || true

# Verificar se ambiente existe
if ! conda env list | grep -q "presence"; then
    echo "❌ Ambiente 'presence' não encontrado. Execute primeiro o setup básico."
    exit 1
fi

echo "✓ Ambiente 'presence' encontrado"
echo ""

# Voltar ao diretório do projeto
cd /mnt/d/Projetopresence/presence

echo "[1/5] Tentando instalar PyTorch com CUDA..."
conda run -n presence pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

if [ $? -eq 0 ]; then
    echo "✓ PyTorch instalado com sucesso"
else
    echo "⚠️ Falha na instalação do PyTorch. Tente manualmente:"
    echo "conda activate presence"
    echo "pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118"
fi

echo ""
echo "[2/5] Tentando instalar FAISS-GPU..."
conda run -n presence conda install pytorch::faiss-gpu -y

if [ $? -eq 0 ]; then
    echo "✓ FAISS-GPU instalado com sucesso"
else
    echo "⚠️ Falha na instalação do FAISS-GPU. Tente manualmente:"
    echo "conda activate presence"
    echo "conda install pytorch::faiss-gpu -y"
fi

echo ""
echo "[3/5] Instalando outras dependências..."
conda run -n presence pip install insightface opencv-python numpy

echo ""
echo "[4/5] Instalando requirements.txt (se existir)..."
if [ -f "requirements.txt" ]; then
    conda run -n presence pip install -r requirements.txt
    echo "✓ requirements.txt instalado"
else
    echo "⚠️ requirements.txt não encontrado, pulando..."
fi

echo ""
echo "[5/5] Configurando base de dados..."
if [ ! -d "app/alembic" ]; then
    echo "Inicializando Alembic..."
    cd app
    conda run -n presence alembic init alembic
    conda run -n presence alembic revision --autogenerate -m "Initial migration"
    conda run -n presence alembic upgrade head
    cd ..
    echo "✓ Alembic configurado"
else
    echo "✓ Alembic já configurado"
fi

echo ""
echo "========================================"
echo "   TESTANDO INSTALAÇÃO"
echo "========================================"
echo ""

conda run -n presence python -c "
print('Testando importações...')
import sys
print(f'Python: {sys.version}')

try:
    import torch
    print(f'✓ PyTorch: {torch.__version__} (CUDA: {torch.cuda.is_available()})')
except Exception as e:
    print(f'❌ PyTorch: {e}')

try:
    import faiss
    print(f'✓ FAISS: {faiss.__version__}')
except Exception as e:
    print(f'❌ FAISS: {e}')

try:
    import cv2
    print(f'✓ OpenCV: {cv2.__version__}')
except Exception as e:
    print(f'❌ OpenCV: {e}')

try:
    import insightface
    print('✓ InsightFace: imported successfully')
except Exception as e:
    print(f'❌ InsightFace: {e}')

try:
    import aiortc
    print('✓ aiortc: imported successfully')
except Exception as e:
    print(f'❌ aiortc: {e}')

try:
    import fastapi
    print('✓ FastAPI: imported successfully')
except Exception as e:
    print(f'❌ FastAPI: {e}')
"

echo ""
echo "========================================"
echo "   SETUP COMPLETO!"
echo "========================================"
echo ""
echo "Próximos passos:"
echo "1. No Windows, execute: scripts\\start_windows_venv.bat"
echo "2. Aguarde os serviços carregarem"
echo "3. Acesse: http://127.0.0.1:3000"
echo ""
echo "Para parar: scripts\\stop_windows_venv.bat"
echo ""