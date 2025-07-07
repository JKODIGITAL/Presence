// Sistema inteligente de gerenciamento isolado de streams
// Cada câmera tem seu próprio ciclo de vida independente

const startWebRTCStreamIsolated = async (cameraId: string): Promise<void> => {
  const state = getCameraState(cameraId);
  
  // Verificar se já está conectando/conectado - evitar múltiplas conexões
  if (state.status === 'connecting' || state.status === 'connected') {
    console.log(`⚠️ [${cameraId}] Já está ${state.status}, ignorando nova tentativa`);
    return;
  }
  
  console.log(`🔌 [${cameraId}] Iniciando conexão WebRTC isolada`);
  updateCameraState(cameraId, { status: 'connecting' });
  
  try {
    // Limpar estado anterior se existir
    if (state.connection || state.websocket) {
      console.log(`🧹 [${cameraId}] Limpando conexões anteriores`);
      cleanupCameraState(cameraId);
    }
    
    // Test server first
    const serverAvailable = await testWebRTCServer();
    if (!serverAvailable) {
      throw new Error('WebRTC Server não está respondendo');
    }
    
    // Create WebSocket connection
    const webrtcUrl = (import.meta.env.VITE_VMS_WEBRTC_URL || 'http://127.0.0.1:17236').trim();
    const wsUrl = webrtcUrl.replace('http', 'ws');
    const fullWsUrl = `${wsUrl}/ws/${cameraId}`;
    
    console.log(`🌐 [${cameraId}] WebSocket URL: ${fullWsUrl}`);
    const ws = new WebSocket(fullWsUrl);
    
    // Create WebRTC peer connection
    const peerConnection = new RTCPeerConnection({
      iceServers: [],  // No STUN needed for LAN
      iceCandidatePoolSize: 0,
      bundlePolicy: 'balanced',
      rtcpMuxPolicy: 'require'
    });
    
    // Update state with connections
    updateCameraState(cameraId, {
      websocket: ws,
      connection: peerConnection
    });
    
    // Handle incoming stream
    peerConnection.ontrack = (event) => {
      console.log(`📽️ [${cameraId}] Stream recebido`, event);
      const [remoteStream] = event.streams;
      
      if (remoteStream && remoteStream instanceof MediaStream && remoteStream.getTracks().length > 0) {
        console.log(`✅ [${cameraId}] Stream válido recebido`, {
          streamId: remoteStream.id,
          tracks: remoteStream.getTracks().length,
          videoTracks: remoteStream.getVideoTracks().length,
          audioTracks: remoteStream.getAudioTracks().length
        });
        
        // Update state with stream
        updateCameraState(cameraId, {
          stream: remoteStream,
          status: 'connected',
          isHealthy: true,
          errorCount: 0
        });
        
        // Start health monitoring for this camera
        startHealthMonitoring(cameraId);
        
        console.log(`✅ [${cameraId}] Stream configurado com sucesso`);
      } else {
        console.error(`❌ [${cameraId}] Stream inválido recebido:`, remoteStream);
        handleCameraError(cameraId, 'Stream inválido recebido');
      }
    };
    
    // Handle ICE candidates
    peerConnection.onicecandidate = (event) => {
      if (event.candidate && ws.readyState === WebSocket.OPEN) {
        console.log(`🧊 [${cameraId}] Enviando ICE candidate`);
        ws.send(JSON.stringify({
          type: 'ice-candidate',
          candidate: event.candidate
        }));
      }
    };
    
    // Handle connection state changes
    peerConnection.onconnectionstatechange = () => {
      const connectionState = peerConnection.connectionState;
      console.log(`🔗 [${cameraId}] Connection state: ${connectionState}`);
      
      if (connectionState === 'connected') {
        updateCameraState(cameraId, { 
          status: 'connected', 
          isHealthy: true,
          errorCount: 0,
          retryCount: 0
        });
      } else if (connectionState === 'failed' || connectionState === 'disconnected') {
        handleCameraError(cameraId, `Conexão ${connectionState}`);
      }
    };
    
    // Handle WebSocket messages
    ws.onmessage = async (event) => {
      try {
        const message = JSON.parse(event.data);
        console.log(`📨 [${cameraId}] Mensagem WebSocket:`, message.type);
        
        if (message.type === 'offer') {
          console.log(`📥 [${cameraId}] Offer recebido`);
          await peerConnection.setRemoteDescription(new RTCSessionDescription(message));
          
          const answer = await peerConnection.createAnswer();
          await peerConnection.setLocalDescription(answer);
          
          ws.send(JSON.stringify({
            type: 'answer',
            sdp: answer.sdp
          }));
          console.log(`📤 [${cameraId}] Answer enviado`);
          
        } else if (message.type === 'ice-candidate') {
          if (message.candidate) {
            await peerConnection.addIceCandidate(new RTCIceCandidate(message.candidate));
            console.log(`🧊 [${cameraId}] ICE candidate adicionado`);
          }
        }
      } catch (e) {
        console.error(`❌ [${cameraId}] Erro ao processar mensagem WebSocket:`, e);
        handleCameraError(cameraId, `Erro WebSocket: ${e.message}`);
      }
    };
    
    // WebSocket connection opened
    ws.onopen = async () => {
      console.log(`🔗 [${cameraId}] WebSocket conectado`);
      ws.send(JSON.stringify({
        type: 'request-offer',
        camera_id: cameraId
      }));
      console.log(`📤 [${cameraId}] Solicitação de offer enviada`);
    };
    
    // Handle WebSocket errors
    ws.onerror = (error) => {
      console.error(`❌ [${cameraId}] Erro WebSocket:`, error);
      handleCameraError(cameraId, 'Erro WebSocket');
    };
    
    // Handle WebSocket close
    ws.onclose = (event) => {
      console.log(`🔌 [${cameraId}] WebSocket fechado:`, event.code, event.reason);
      if (event.code !== 1000) { // Not a normal closure
        handleCameraError(cameraId, `WebSocket fechado inesperadamente: ${event.reason}`);
      }
    };
    
    console.log(`✅ [${cameraId}] WebRTC configurado com sucesso`);
    
  } catch (error) {
    console.error(`❌ [${cameraId}] Erro WebRTC:`, error);
    handleCameraError(cameraId, `Erro WebRTC: ${error.message}`);
  }
};

const handleCameraError = (cameraId: string, errorMessage: string) => {
  const state = getCameraState(cameraId);
  const now = Date.now();
  
  // Increment error count if errors are close together
  let newErrorCount = 1;
  if (now - state.lastErrorTime < 30000) { // Within 30 seconds
    newErrorCount = state.errorCount + 1;
  }
  
  console.log(`💥 [${cameraId}] Erro (${newErrorCount}/5): ${errorMessage}`);
  
  updateCameraState(cameraId, {
    status: 'error',
    errorCount: newErrorCount,
    lastErrorTime: now,
    isHealthy: false
  });
  
  // If too many errors, back off and try again later
  if (newErrorCount >= 5) {
    console.log(`🚫 [${cameraId}] Muitos erros, pausando por 2 minutos`);
    updateCameraState(cameraId, { status: 'error' });
    
    // Try again after 2 minutes
    setTimeout(() => {
      console.log(`🔄 [${cameraId}] Tentando reconectar após pausa`);
      updateCameraState(cameraId, { errorCount: 0, retryCount: state.retryCount + 1 });
      startWebRTCStreamIsolated(cameraId);
    }, 120000); // 2 minutes
  } else {
    // Quick retry for minor errors
    setTimeout(() => {
      console.log(`🔄 [${cameraId}] Tentativa rápida de reconexão`);
      startWebRTCStreamIsolated(cameraId);
    }, 5000); // 5 seconds
  }
};

const startHealthMonitoring = (cameraId: string) => {
  const state = getCameraState(cameraId);
  
  // Clear existing health check
  if (state.healthCheckInterval) {
    clearInterval(state.healthCheckInterval);
  }
  
  const healthInterval = setInterval(() => {
    const currentState = getCameraState(cameraId);
    
    if (!currentState.stream || !currentState.connection) {
      console.log(`💊 [${cameraId}] Health check falhou - sem stream/conexão`);
      clearInterval(healthInterval);
      return;
    }
    
    // Check if stream tracks are still active
    const videoTracks = currentState.stream.getVideoTracks();
    const hasActiveTracks = videoTracks.some(track => track.readyState === 'live');
    
    if (!hasActiveTracks) {
      console.log(`💊 [${cameraId}] Health check falhou - tracks inativos`);
      handleCameraError(cameraId, 'Stream tracks inativos');
      clearInterval(healthInterval);
      return;
    }
    
    // Check connection state
    const connectionState = currentState.connection.connectionState;
    if (connectionState === 'failed' || connectionState === 'disconnected') {
      console.log(`💊 [${cameraId}] Health check falhou - conexão ${connectionState}`);
      handleCameraError(cameraId, `Conexão ${connectionState}`);
      clearInterval(healthInterval);
      return;
    }
    
    console.log(`💊 [${cameraId}] Health check OK`);
    updateCameraState(cameraId, { isHealthy: true });
    
  }, 10000); // Check every 10 seconds
  
  updateCameraState(cameraId, { healthCheckInterval: healthInterval });
};

export { startWebRTCStreamIsolated, handleCameraError, startHealthMonitoring };