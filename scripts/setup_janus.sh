#!/bin/bash
# Script para instalar e configurar Janus WebRTC Gateway

echo "==================================="
echo "  Instalação do Janus Gateway"
echo "==================================="

# Detectar sistema operacional
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    # Linux
    if command -v apt-get &> /dev/null; then
        # Debian/Ubuntu
        echo "📦 Instalando Janus no Ubuntu/Debian..."
        
        # Dependências
        sudo apt-get update
        sudo apt-get install -y \
            libmicrohttpd-dev libjansson-dev \
            libssl-dev libsrtp2-dev libsofia-sip-ua-dev \
            libglib2.0-dev libopus-dev libogg-dev \
            libcurl4-openssl-dev liblua5.3-dev \
            libconfig-dev pkg-config gengetopt \
            libtool automake build-essential \
            git cmake
        
        # libnice (para ICE)
        if ! pkg-config --exists nice; then
            echo "📦 Instalando libnice..."
            cd /tmp
            git clone https://gitlab.freedesktop.org/libnice/libnice
            cd libnice
            meson builddir
            ninja -C builddir
            sudo ninja -C builddir install
        fi
        
        # Janus
        if ! command -v janus &> /dev/null; then
            echo "📦 Compilando Janus..."
            cd /tmp
            git clone https://github.com/meetecho/janus-gateway.git
            cd janus-gateway
            sh autogen.sh
            ./configure --prefix=/usr/local
            make
            sudo make install
            sudo make configs
        fi
        
    elif command -v yum &> /dev/null; then
        # RHEL/CentOS/Fedora
        echo "📦 Instalando Janus no RHEL/Fedora..."
        sudo yum install -y janus janus-streaming
    fi
    
elif [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" ]]; then
    # Windows (MSYS2)
    echo "📦 Instalando Janus no Windows via MSYS2..."
    echo "⚠️  Janus não tem suporte nativo no Windows."
    echo "🐳 Recomendado: Use Docker!"
    
    # Docker option
    if command -v docker &> /dev/null; then
        echo "🐳 Docker detectado! Criando container Janus..."
        
        # Criar diretório de config
        mkdir -p ./janus/config
        
        # Criar docker-compose para Janus
        cat > docker-compose.janus.yml << 'EOF'
version: '3.8'

services:
  janus:
    image: canyan/janus-gateway:latest
    container_name: presence-janus
    restart: unless-stopped
    ports:
      - "8088:8088"   # HTTP API
      - "8188:8188"   # WebSocket
      - "7088:7088"   # Admin HTTP
      - "7188:7188"   # Admin WebSocket
      - "5000-5100:5000-5100/udp"  # RTP ports
    environment:
      - JANUS_STREAMING_ENABLED=true
      - JANUS_VIDEOROOM_ENABLED=true
    volumes:
      - ./janus/config:/etc/janus
    networks:
      - presence-network

networks:
  presence-network:
    external: true
EOF
        
        # Iniciar Janus
        docker-compose -f docker-compose.janus.yml up -d
        
        echo "✅ Janus rodando no Docker!"
        echo "   HTTP API: http://localhost:8088/janus"
        echo "   WebSocket: ws://localhost:8188"
    else
        echo "❌ Docker não encontrado. Instale Docker para Windows."
    fi
fi

# Configuração do Janus Streaming Plugin
echo ""
echo "📝 Configurando Janus Streaming Plugin..."

# Criar configuração para streaming
if [[ -d "/usr/local/etc/janus" ]]; then
    JANUS_CONFIG_DIR="/usr/local/etc/janus"
elif [[ -d "/etc/janus" ]]; then
    JANUS_CONFIG_DIR="/etc/janus"
else
    JANUS_CONFIG_DIR="./janus/config"
fi

cat > $JANUS_CONFIG_DIR/janus.plugin.streaming.jcfg << 'EOF'
# Streaming plugin configuration
general: {
    # Admin API key
    #admin_key = "supersecret"
}

# Mountpoints (streams) serão criados dinamicamente via API
EOF

echo ""
echo "==================================="
echo "  Configuração Concluída!"
echo "==================================="
echo ""
echo "Para iniciar o Janus:"
echo "  Linux: sudo janus -F $JANUS_CONFIG_DIR"
echo "  Docker: docker-compose -f docker-compose.janus.yml up"
echo ""
echo "Endpoints:"
echo "  HTTP API: http://localhost:8088/janus"
echo "  WebSocket: ws://localhost:8188"
echo "  Admin: http://localhost:7088/admin"
echo ""
echo "Próximos passos:"
echo "  1. Inicie o Janus"
echo "  2. Execute: python app/webrtc_worker/janus_webrtc_server.py"
echo ""