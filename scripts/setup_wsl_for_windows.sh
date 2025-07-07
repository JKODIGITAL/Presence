#!/bin/bash
# Script para setup no WSL que será usado no Windows
# Execute no WSL, depois use o ambiente no Windows

echo "========================================"
echo "   PRESENCE SETUP - WSL → Windows"
echo "========================================"
echo ""

# Verificar se estamos no WSL
if [[ ! $(uname -r) =~ microsoft ]]; then
    echo "❌ Este script deve ser executado no WSL"
    exit 1
fi

echo "✓ Executando no WSL"
echo ""

# 1. Verificar conda
echo "[1/7] Verificando conda..."
if ! command -v conda &> /dev/null; then
    echo "❌ conda não encontrado. Instalando Miniconda..."
    
    # Download e instalar Miniconda
    cd /tmp
    wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
    bash Miniconda3-latest-Linux-x86_64.sh -b -p $HOME/miniconda3
    
    # Adicionar ao PATH e inicializar conda
    export PATH="$HOME/miniconda3/bin:$PATH"
    $HOME/miniconda3/bin/conda init bash
    
    # Recarregar configuração
    source ~/.bashrc || source $HOME/miniconda3/etc/profile.d/conda.sh
    
    echo "✓ Miniconda instalado"
else
    echo "✓ conda encontrado"
fi

# Voltar ao diretório do projeto
cd /mnt/d/Projetopresence/presence

echo ""

# 2. Criar ambiente conda
echo "[2/7] Criando ambiente conda 'presence'..."

# Assegurar que conda está no PATH
export PATH="$HOME/miniconda3/bin:$PATH"
source $HOME/miniconda3/etc/profile.d/conda.sh 2>/dev/null || true

# Verificar se ambiente já existe
if conda env list | grep -q "presence"; then
    echo "✓ Ambiente 'presence' já existe"
    read -p "Deseja recriar? (y/N): " -r
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Removendo ambiente existente..."
        conda env remove -n presence -y
        echo "Criando novo ambiente..."
        conda create -n presence python=3.10 -y
    fi
else
    echo "Criando ambiente conda 'presence'..."
    conda create -n presence python=3.10 -y
fi

echo ""

# 3. Instalar PyTorch com CUDA
echo "[3/7] Instalando PyTorch com CUDA..."
conda run -n presence conda install pytorch torchvision torchaudio pytorch-cuda=11.8 -c pytorch -c nvidia -y

echo ""

# 4. Instalar FAISS-GPU
echo "[4/7] Instalando FAISS-GPU..."
conda run -n presence conda install pytorch::faiss-gpu -y

echo ""

# 5. Instalar dependências do requirements.txt
echo "[5/7] Instalando dependências do requirements.txt..."
if [ -f "requirements.txt" ]; then
    conda run -n presence pip install -r requirements.txt
else
    echo "⚠️ requirements.txt não encontrado, instalando dependências básicas..."
    conda run -n presence pip install fastapi uvicorn sqlalchemy alembic insightface opencv-python numpy
fi

echo ""

# 6. Instalar dependências WebRTC
echo "[6/7] Instalando dependências WebRTC..."
conda run -n presence pip install aiortc aiofiles uvloop

echo ""

# 7. Configurar banco de dados
echo "[7/7] Configurando banco de dados..."

# Criar diretórios necessários
mkdir -p data/{models,images,embeddings} logs

# Configurar Alembic se necessário
if [ ! -d "app/alembic" ]; then
    echo "Inicializando Alembic..."
    cd app
    conda run -n presence alembic init alembic
    conda run -n presence alembic revision --autogenerate -m "Initial migration"
    conda run -n presence alembic upgrade head
    cd ..
else
    echo "✓ Alembic já configurado"
fi

echo ""
echo "========================================"
echo "   SETUP WSL CONCLUÍDO!"
echo "========================================"
echo ""

# Obter informações do ambiente
CONDA_ENV_PATH=$(conda run -n presence python -c "import sys; print(sys.executable)" | head -1)
CONDA_BASE_PATH=$(dirname $(dirname $CONDA_ENV_PATH))

echo "Informações do ambiente criado:"
echo "  Conda base: $CONDA_BASE_PATH"
echo "  Environment: presence"
echo "  Python: $CONDA_ENV_PATH"
echo ""

echo "Para usar no Windows:"
echo "1. Abra o Anaconda Prompt no Windows"
echo "2. Ative o ambiente: conda activate presence"
echo "3. Execute os serviços conforme CLAUDE.md"
echo ""

echo "Testando importações básicas..."
conda run -n presence python -c "
import torch
print(f'✓ PyTorch: {torch.__version__} (CUDA: {torch.cuda.is_available()})')

try:
    import faiss
    print(f'✓ FAISS: {faiss.__version__}')
except:
    print('❌ FAISS import failed')

try:
    import cv2
    print(f'✓ OpenCV: {cv2.__version__}')
except:
    print('❌ OpenCV import failed')

try:
    import insightface
    print('✓ InsightFace imported')
except:
    print('❌ InsightFace import failed')

try:
    import aiortc
    print('✓ aiortc imported')
except:
    print('❌ aiortc import failed')
"

echo ""
echo "Setup concluído! Ambiente pronto para uso no Windows."