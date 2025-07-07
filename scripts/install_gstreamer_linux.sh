#!/bin/bash
# Script de instalação do GStreamer para Linux
# Este script instala o GStreamer e suas dependências em sistemas baseados em Debian/Ubuntu

# Cores para saída
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Função para imprimir mensagens coloridas
print_message() {
    local color=$1
    local message=$2
    echo -e "${color}${message}${NC}"
}

# Verificar se está sendo executado como root
if [ "$EUID" -ne 0 ]; then
    print_message "$RED" "Este script precisa ser executado como root (sudo)."
    print_message "$RED" "Por favor, execute: sudo $0"
    exit 1
fi

# Banner
print_message "$CYAN" "========================================================="
print_message "$CYAN" "       INSTALADOR DO GSTREAMER PARA LINUX                "
print_message "$CYAN" "========================================================="
echo ""

# Detectar distribuição
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$NAME
    VERSION=$VERSION_ID
    print_message "$BLUE" "Sistema operacional detectado: $OS $VERSION"
else
    print_message "$YELLOW" "Não foi possível detectar a distribuição Linux."
    print_message "$YELLOW" "Assumindo sistema baseado em Debian/Ubuntu."
    OS="Unknown"
fi

# Atualizar repositórios
print_message "$YELLOW" "Atualizando repositórios..."
apt-get update

# Instalar dependências básicas
print_message "$YELLOW" "Instalando dependências básicas..."
apt-get install -y \
    build-essential \
    pkg-config \
    curl \
    wget \
    git \
    python3-dev \
    python3-pip \
    python3-setuptools \
    python3-wheel

# Instalar GStreamer e dependências
print_message "$YELLOW" "Instalando GStreamer e dependências..."
apt-get install -y \
    gstreamer1.0-tools \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly \
    gstreamer1.0-libav \
    gstreamer1.0-alsa \
    gstreamer1.0-gl \
    gstreamer1.0-gtk3 \
    gstreamer1.0-qt5 \
    gstreamer1.0-pulseaudio \
    libgstreamer1.0-0 \
    libgstreamer1.0-dev \
    libgstreamer-plugins-base1.0-0 \
    libgstreamer-plugins-base1.0-dev \
    libglib2.0-0 \
    libglib2.0-dev

# Instalar bindings Python para GStreamer
print_message "$YELLOW" "Instalando bindings Python para GStreamer..."
apt-get install -y \
    python3-gi \
    python3-gi-cairo \
    python3-gst-1.0 \
    gir1.2-gstreamer-1.0 \
    gir1.2-gst-plugins-base-1.0 \
    gir1.2-gtk-3.0 \
    libgirepository1.0-dev \
    libcairo2-dev \
    gobject-introspection

# Instalar dependências Python adicionais
print_message "$YELLOW" "Instalando dependências Python adicionais..."
pip3 install --upgrade pip
pip3 install opencv-python numpy pygobject

# Verificar instalação
print_message "$YELLOW" "Verificando instalação do GStreamer..."

# Verificar versão do GStreamer
GST_VERSION=$(gst-launch-1.0 --version 2>/dev/null)
if [ $? -eq 0 ]; then
    print_message "$GREEN" "✓ GStreamer instalado com sucesso!"
    echo "$GST_VERSION"
else
    print_message "$RED" "✗ Falha ao verificar instalação do GStreamer."
    exit 1
fi

# Verificar plugins críticos
print_message "$YELLOW" "Verificando plugins críticos..."
CRITICAL_PLUGINS=("rtspsrc" "v4l2src" "videoconvert" "appsink")
MISSING_PLUGINS=()

for plugin in "${CRITICAL_PLUGINS[@]}"; do
    if gst-inspect-1.0 $plugin &>/dev/null; then
        print_message "$GREEN" "✓ Plugin $plugin: Disponível"
    else
        print_message "$RED" "✗ Plugin $plugin: Não encontrado"
        MISSING_PLUGINS+=("$plugin")
    fi
done

# Verificar integração Python
print_message "$YELLOW" "Verificando integração Python com GStreamer..."
PYTHON_TEST=$(python3 -c "
import gi
try:
    gi.require_version('Gst', '1.0')
    from gi.repository import Gst
    Gst.init(None)
    print('GStreamer inicializado com sucesso: ' + Gst.version_string())
    exit(0)
except Exception as e:
    print('Erro: ' + str(e))
    exit(1)
" 2>&1)

if [ $? -eq 0 ]; then
    print_message "$GREEN" "✓ Integração Python com GStreamer funcionando!"
    echo "$PYTHON_TEST"
else
    print_message "$RED" "✗ Falha na integração Python com GStreamer:"
    echo "$PYTHON_TEST"
fi

# Verificar webcams conectadas
print_message "$YELLOW" "Verificando dispositivos de webcam..."
if [ -x "$(command -v v4l2-ctl)" ]; then
    v4l2-ctl --list-devices
else
    print_message "$YELLOW" "Comando v4l2-ctl não encontrado. Instalando v4l-utils..."
    apt-get install -y v4l-utils
    v4l2-ctl --list-devices
fi

# Conclusão
print_message "$CYAN" "========================================================="
print_message "$CYAN" "       INSTALAÇÃO DO GSTREAMER CONCLUÍDA                 "
print_message "$CYAN" "========================================================="

if [ ${#MISSING_PLUGINS[@]} -eq 0 ]; then
    print_message "$GREEN" "Todos os plugins críticos estão instalados!"
else
    print_message "$YELLOW" "Alguns plugins críticos estão faltando: ${MISSING_PLUGINS[*]}"
    print_message "$YELLOW" "Isso pode limitar algumas funcionalidades."
fi

echo ""
print_message "$BLUE" "Para testar o GStreamer, execute:"
echo "gst-launch-1.0 videotestsrc ! videoconvert ! autovideosink"
echo ""
print_message "$BLUE" "Para testar uma webcam:"
echo "gst-launch-1.0 v4l2src device=/dev/video0 ! videoconvert ! autovideosink"
echo ""
print_message "$BLUE" "Para testar uma câmera RTSP:"
echo "gst-launch-1.0 rtspsrc location=rtsp://URL:PORT/STREAM ! rtph264depay ! h264parse ! avdec_h264 ! videoconvert ! autovideosink"
echo ""
print_message "$CYAN" "=========================================================" 