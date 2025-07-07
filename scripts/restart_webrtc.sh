#!/bin/bash

echo "🔄 Reiniciando VMS WebRTC com configuração de rede corrigida..."

# Parar container se estiver rodando
echo "⏹️ Parando container VMS WebRTC..."
docker-compose down presence-vms-webrtc

# Rebuild da imagem
echo "🏗️ Rebuilding imagem WebRTC..."
docker-compose build presence-vms-webrtc

# Verificar se o sistema é Linux (para host network)
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    echo "🐧 Sistema Linux detectado - usando host network mode"
    export WEBRTC_HOST_NETWORK=true
else
    echo "🪟 Sistema não-Linux detectado - usando bridge network com UDP ports"
    export WEBRTC_HOST_NETWORK=false
fi

# Iniciar container
echo "🚀 Iniciando VMS WebRTC..."
docker-compose up -d presence-vms-webrtc

# Aguardar inicialização
echo "⏳ Aguardando inicialização..."
sleep 5

# Verificar status
echo "📊 Status do container:"
docker-compose ps presence-vms-webrtc

# Mostrar logs
echo "📋 Logs recentes:"
docker-compose logs --tail=20 presence-vms-webrtc

echo ""
echo "✅ VMS WebRTC reiniciado!"
echo "🌐 Acesse: http://172.21.15.83:8765/demo"
echo "🔧 Para debug: docker-compose logs -f presence-vms-webrtc"