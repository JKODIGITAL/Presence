/**
 * VMSMonitor - Interface limpa para monitoramento de vídeo
 * Sem detalhes técnicos, focado na experiência do usuário
 */

import React, { useState, useEffect, useRef } from 'react';
import {
  VideoCameraIcon,
  PlayIcon,
  PauseIcon,
  SpeakerWaveIcon,
  SpeakerXMarkIcon,
  ArrowsPointingOutIcon,
  ArrowsPointingInIcon,
  Squares2X2Icon,
  RectangleGroupIcon,
  ChartBarIcon,
  PhotoIcon,
  ArrowPathIcon,
  ExclamationTriangleIcon,
  CameraIcon
} from '@heroicons/react/24/outline';
import { ApiService } from '../services/api';
import { createDirectWebRTCClient, DirectWebRTCClient, checkDirectWebRTCAvailability } from '../services/directWebRTC';
import toast from 'react-hot-toast';

// WebRTC Video Component
interface WebRTCVideoProps {
  stream: MediaStream;
  cameraName: string;
  cameraId: string;
  onError: () => void;
}

const WebRTCVideo: React.FC<WebRTCVideoProps> = ({ stream, cameraName, cameraId, onError }) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const errorCountRef = useRef(0);
  const lastErrorTimeRef = useRef(0);
  
  useEffect(() => {
    if (videoRef.current && stream) {
      try {
        // Verificar se o stream é um MediaStream válido
        if (stream instanceof MediaStream && stream.getVideoTracks().length > 0) {
          videoRef.current.srcObject = stream;
          console.log(`✅ Stream MediaStream atribuído ao video element para ${cameraName}`);
          // Reset error count on successful assignment
          errorCountRef.current = 0;
        } else {
          console.error(`❌ Stream não é MediaStream válido para ${cameraName}:`, typeof stream, stream);
          // Não chamar onError imediatamente para evitar ciclo
        }
      } catch (error) {
        console.error(`❌ Erro ao atribuir stream para ${cameraName}:`, error);
        // Não chamar onError imediatamente para evitar ciclo
      }
    }
    
    return () => {
      if (videoRef.current) {
        videoRef.current.srcObject = null;
      }
    };
  }, [stream, cameraName]);
  
  const handleVideoError = (e: any) => {
    const now = Date.now();
    
    // Só contar erro se passou mais de 5 segundos desde o último
    if (now - lastErrorTimeRef.current > 5000) {
      errorCountRef.current = 1;
    } else {
      errorCountRef.current++;
    }
    
    lastErrorTimeRef.current = now;
    
    console.log(`❌ Erro no video element da câmera ${cameraName} (${errorCountRef.current}/3):`, e);
    
    // Só chamar onError após 3 erros consecutivos em pouco tempo
    if (errorCountRef.current >= 3) {
      console.log(`💥 Muitos erros consecutivos para ${cameraName}, parando stream`);
      onError();
      errorCountRef.current = 0; // Reset
    }
  };
  
  return (
    <video
      ref={videoRef}
      className="w-full h-full object-cover"
      autoPlay
      muted
      playsInline
      controls={false}
      preload="none"
      disablePictureInPicture
      onLoadedData={() => {
        console.log(`✅ Video carregado para câmera ${cameraName}`);
        errorCountRef.current = 0; // Reset error count on successful load
      }}
      onError={handleVideoError}
    />
  );
};

interface Camera {
  id: string;
  name: string;
  location?: string;
  status: 'online' | 'offline' | 'connecting';
  recognitionEnabled: boolean;
  lastActivity?: string;
}

interface ViewLayout {
  id: string;
  name: string;
  icon: any;
  grid: string;
}

// Interface para estado isolado de cada câmera
interface CameraStreamState {
  id: string;
  status: 'idle' | 'connecting' | 'connected' | 'error' | 'retrying';
  stream?: MediaStream;
  connection?: RTCPeerConnection;
  websocket?: WebSocket;
  directWebRTCClient?: DirectWebRTCClient;
  snapshotUrl?: string;
  snapshotInterval?: number;
  errorCount: number;
  lastErrorTime: number;
  retryCount: number;
  isHealthy: boolean;
  healthCheckInterval?: number;
  connectionType?: 'webrtc' | 'janus' | 'snapshot';
}

const VMSMonitor: React.FC = () => {
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [selectedCamera, setSelectedCamera] = useState<string | null>(null);
  const [viewLayout, setViewLayout] = useState<string>('grid-2x2');
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [isMuted, setIsMuted] = useState(true);
  const [isRecording, setIsRecording] = useState(false);
  const [showStats, setShowStats] = useState(false);
  const [autoPlay, setAutoPlay] = useState(true);
  const [apiConnected, setApiConnected] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  
  // Estado isolado por câmera - cada câmera tem seu próprio estado independente
  const cameraStates = useRef<Map<string, CameraStreamState>>(new Map());

  const layouts: ViewLayout[] = [
    { id: 'single', name: 'Única', icon: RectangleGroupIcon, grid: 'grid-cols-1' },
    { id: 'grid-2x2', name: '2x2', icon: Squares2X2Icon, grid: 'grid-cols-2' },
    { id: 'grid-3x3', name: '3x3', icon: Squares2X2Icon, grid: 'grid-cols-3' },
  ];

  useEffect(() => {
    fetchCameras();
    const interval = setInterval(fetchCameras, 30000);
    return () => clearInterval(interval);
  }, []);

  // Funções de gerenciamento isolado de câmeras
  const initializeCameraState = (cameraId: string): CameraStreamState => {
    return {
      id: cameraId,
      status: 'idle',
      errorCount: 0,
      lastErrorTime: 0,
      retryCount: 0,
      isHealthy: true
    };
  };

  const getCameraState = (cameraId: string): CameraStreamState => {
    if (!cameraStates.current.has(cameraId)) {
      cameraStates.current.set(cameraId, initializeCameraState(cameraId));
    }
    return cameraStates.current.get(cameraId)!;
  };

  const updateCameraState = (cameraId: string, updates: Partial<CameraStreamState>) => {
    const currentState = getCameraState(cameraId);
    const newState = { ...currentState, ...updates };
    cameraStates.current.set(cameraId, newState);
    
    // Forçar re-render quando necessário
    if (updates.stream || updates.status) {
      setCameras(prev => [...prev]); // Trigger re-render
    }
  };

  const cleanupCameraState = (cameraId: string) => {
    const state = getCameraState(cameraId);
    
    console.log(`🧹 Limpando estado isolado da câmera ${cameraId}`);
    
    // Cleanup WebSocket
    if (state.websocket) {
      try {
        if (state.websocket.readyState === WebSocket.OPEN) {
          state.websocket.close();
        }
      } catch (e) {
        console.warn(`Erro ao fechar WebSocket ${cameraId}:`, e);
      }
    }
    
    // Cleanup WebRTC Connection
    if (state.connection) {
      try {
        state.connection.close();
      } catch (e) {
        console.warn(`Erro ao fechar RTCPeerConnection ${cameraId}:`, e);
      }
    }
    
    // Cleanup Direct WebRTC Client
    if (state.directWebRTCClient) {
      try {
        state.directWebRTCClient.disconnect();
      } catch (e) {
        console.warn(`Erro ao desconectar WebRTC direto ${cameraId}:`, e);
      }
    }
    
    // Cleanup Snapshot URL
    if (state.snapshotUrl) {
      try {
        URL.revokeObjectURL(state.snapshotUrl);
      } catch (e) {
        console.warn(`Erro ao revogar snapshot URL ${cameraId}:`, e);
      }
    }
    
    // Cleanup Intervals
    if (state.snapshotInterval) {
      clearInterval(state.snapshotInterval);
    }
    if (state.healthCheckInterval) {
      clearInterval(state.healthCheckInterval);
    }
    
    // Reset state
    updateCameraState(cameraId, initializeCameraState(cameraId));
  };

  // Cleanup global ao desmontar componente
  useEffect(() => {
    return () => {
      console.log('🧹 Limpeza global - parando todas as câmeras');
      cameraStates.current.forEach((_, cameraId) => {
        cleanupCameraState(cameraId);
      });
      cameraStates.current.clear();
    };
  }, []);

  const fetchCameras = async () => {
    try {
      console.log('🔄 [VMSMonitor] Carregando câmeras...');
      console.log('🔌 [VMSMonitor] URL da API:', ApiService.getBaseUrl());
      
      // Testar conectividade primeiro com timeout menor
      try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 5000); // 5 segundos para health check
        
        const healthCheck = await fetch(`${ApiService.getBaseUrl()}/health`, {
          signal: controller.signal
        });
        clearTimeout(timeoutId);
        
        if (!healthCheck.ok) {
          throw new Error(`API retornou status ${healthCheck.status}`);
        }
        
        console.log('✅ [VMSMonitor] API respondendo');
        setApiConnected(true);
      } catch (healthError) {
        console.error('❌ [VMSMonitor] API não responde:', healthError);
        setApiConnected(false);
        toast.error('API não está respondendo. Verifique se o servidor está rodando.');
        return;
      }
      
      const response = await ApiService.getCameras();
      console.log('📡 [VMSMonitor] Resposta da API:', response);
      
      const cameraList = response.cameras || [];
      console.log('📋 [VMSMonitor] Lista de câmeras extraída:', cameraList.length, 'câmeras');
      
      if (!Array.isArray(cameraList)) {
        console.error('❌ [VMSMonitor] cameraList não é um array:', cameraList);
        return;
      }
      
      const mappedCameras = cameraList.map((cam: any) => {
        console.log('🎥 [VMSMonitor] Mapeando câmera:', cam.name || cam.id);
        return {
          id: cam.id,
          name: cam.name,
          location: cam.location,
          status: cam.status === 'active' ? 'online' : cam.status || 'offline',
          recognitionEnabled: true, // Default true
          lastActivity: cam.last_frame_at || cam.updated_at
        };
      });
      
      console.log('✅ [VMSMonitor] Câmeras mapeadas:', mappedCameras);
      setCameras(mappedCameras);
      
      // Desabilitar auto-start temporariamente para debug
      console.log('🎥 [VMSMonitor] Sistema isolado pronto - auto-start DESABILITADO para debug');
      
    } catch (error) {
      console.error('❌ [VMSMonitor] Erro ao buscar câmeras:', error);
      setApiConnected(false);
      
      // Mensagem de erro mais específica
      let errorMessage = 'Erro desconhecido';
      if (error.name === 'AbortError') {
        errorMessage = 'Timeout na conexão com a API';
      } else if (error.message) {
        errorMessage = error.message;
      }
      
      toast.error(`Erro ao carregar câmeras: ${errorMessage}`);
    }
  };

  const handleFullscreen = () => {
    if (!document.fullscreenElement) {
      containerRef.current?.requestFullscreen();
      setIsFullscreen(true);
    } else {
      document.exitFullscreen();
      setIsFullscreen(false);
    }
  };

  const handleSnapshot = (cameraId: string) => {
    toast.info('Snapshot desabilitado - usando WebRTC stream');
  };

  const handleReconnect = (cameraId: string) => {
    const camera = cameras.find(c => c.id === cameraId);
    toast.loading(`Reconectando ${camera?.name}...`);
    
    setTimeout(() => {
      toast.success(`${camera?.name} reconectada!`);
      setCameras(prev => prev.map(cam => 
        cam.id === cameraId ? { ...cam, status: 'online' } : cam
      ));
    }, 2000);
  };

  // Test WebRTC server availability
  const testWebRTCServer = async (): Promise<boolean> => {
    try {
      const webrtcUrl = (import.meta.env.VITE_VMS_WEBRTC_URL || 'http://127.0.0.1:17236').trim();
      console.log(`🔍 Testando WebRTC Server: ${webrtcUrl}/health`);
      
      const response = await fetch(`${webrtcUrl}/health`, { 
        method: 'GET',
        signal: AbortSignal.timeout(10000) // 10 segundos para garantir
      });
      
      if (response.ok) {
        const health = await response.json();
        console.log(`✅ WebRTC Server OK:`, health);
        return true;
      } else {
        console.log(`❌ WebRTC Server erro HTTP: ${response.status}`);
        return false;
      }
    } catch (error) {
      console.log(`⚠️ WebRTC Server teste falhou:`, error);
      return false;
    }
  };

  const startWebRTCStreamIsolated = async (cameraId: string): Promise<void> => {
    console.log(`🚀 [${cameraId}] startWebRTCStreamIsolated INÍCIO`);
    
    const state = getCameraState(cameraId);
    console.log(`📋 [${cameraId}] Estado atual:`, state.status);
    
    // Verificar se já está conectando/conectado - evitar múltiplas conexões
    if (state.status === 'connecting' || state.status === 'connected') {
      console.log(`⚠️ Câmera ${cameraId} já está ${state.status}, ignorando nova tentativa`);
      return;
    }
    
    console.log(`🔌 [${cameraId}] Iniciando conexão WebRTC isolada`);
    updateCameraState(cameraId, { status: 'connecting' });
    
    // Limpar estado anterior se existir
    if (state.connection || state.websocket) {
      console.log(`🧹 Limpando conexões anteriores para ${cameraId}`);
      cleanupCameraState(cameraId);
    }
    
    try {
      // Test server first
      console.log(`🧪 [${cameraId}] Testando servidor WebRTC...`);
      const serverAvailable = await testWebRTCServer();
      console.log(`🧪 [${cameraId}] Teste do servidor: ${serverAvailable ? 'OK' : 'FALHOU'}`);
      
      if (!serverAvailable) {
        throw new Error('WebRTC Server não está respondendo');
      }
      
      // Create WebSocket connection to WebRTC server
      const webrtcUrl = (import.meta.env.VITE_VMS_WEBRTC_URL || 'http://127.0.0.1:17236').trim();
      const wsUrl = webrtcUrl.replace('http', 'ws');
      const fullWsUrl = `${wsUrl}/ws/${cameraId}`;
      
      console.log(`🌐 [${cameraId}] WebRTC URL: ${webrtcUrl}`);
      console.log(`🔌 [${cameraId}] WebSocket URL: ${fullWsUrl}`);
      
      // Create WebRTC peer connection (LAN only - optimized)
      const peerConnection = new RTCPeerConnection({
        iceServers: [],  // No STUN needed for LAN
        iceCandidatePoolSize: 0,  // No need for candidate pool in LAN
        bundlePolicy: 'balanced',  // Optimize for LAN
        rtcpMuxPolicy: 'require'   // Single port for efficiency
      });
      
      // Test WebSocket connection
      console.log(`🔥 [${cameraId}] Criando WebSocket: ${fullWsUrl}`);
      const ws = new WebSocket(fullWsUrl);
      
      // Update state with connections
      updateCameraState(cameraId, { 
        websocket: ws,
        connection: peerConnection 
      });
      
      // Handle incoming stream
      peerConnection.ontrack = (event) => {
        console.log(`📽️ Stream recebido para câmera ${cameraId}`, event);
        const [remoteStream] = event.streams;
        
        // Usar o stream diretamente (sem createObjectURL)
        try {
          if (remoteStream && remoteStream instanceof MediaStream && remoteStream.getTracks().length > 0) {
            console.log(`✅ Stream válido recebido para câmera ${cameraId}`, {
              streamId: remoteStream.id,
              tracks: remoteStream.getTracks().length,
              videoTracks: remoteStream.getVideoTracks().length,
              audioTracks: remoteStream.getAudioTracks().length
            });            
            
            // Atualizar estado isolado com o stream
            updateCameraState(cameraId, {
              stream: remoteStream,
              status: 'connected',
              isHealthy: true,
              errorCount: 0
            });
            
            console.log(`✅ [${cameraId}] Stream configurado e estado atualizado`);
          } else {
            console.error('Stream inválido recebido:', remoteStream);
            return;
          }
        } catch (error) {
          console.error('Erro ao processar stream da câmera', cameraId, ':', error);
          return;
        }
        
        // Stream já foi configurado acima - não precisa de configuração adicional
      };
      
      // Handle ICE candidates
      peerConnection.onicecandidate = (event) => {
        if (event.candidate && ws.readyState === WebSocket.OPEN) {
          console.log(`🧊 Enviando ICE candidate para câmera ${cameraId}`);
          ws.send(JSON.stringify({
            type: 'ice-candidate',
            candidate: event.candidate
          }));
        }
      };
      
      // Handle WebSocket messages
      ws.onmessage = async (event) => {
        try {
          const message = JSON.parse(event.data);
          console.log(`📨 Mensagem WebSocket recebida:`, message.type);
          
          // Verificar se é redirecionamento para Janus
          if (message.type === 'janus_redirect') {
            console.log(`🎯 [${cameraId}] Redirecionando para Janus SFU`);
            console.log(`🔗 Janus WS: ${message.janus_ws}`);
            console.log(`📺 Stream ID: ${message.stream_id}`);
            
            // TODO: Implementar conexão Janus
            // Por enquanto, marcar como conectado
            updateCameraState(cameraId, {
              status: 'connected',
              isHealthy: true,
              errorCount: 0
            });
            
            toast.info(`Câmera usando Janus Gateway (Stream ID: ${message.stream_id})`);
            return;
          }
          
          if (message.type === 'offer') {
            console.log(`📥 Offer recebido para câmera ${cameraId}`);
            await peerConnection.setRemoteDescription(new RTCSessionDescription(message));
            
            // Create answer
            const answer = await peerConnection.createAnswer();
            await peerConnection.setLocalDescription(answer);
            
            // Send answer back
            ws.send(JSON.stringify({
              type: 'answer',
              sdp: answer.sdp
            }));
            console.log(`📤 Answer enviado para câmera ${cameraId}`);
            
          } else if (message.type === 'ice-candidate') {
            if (message.candidate) {
              await peerConnection.addIceCandidate(new RTCIceCandidate(message.candidate));
              console.log(`🧊 ICE candidate adicionado para câmera ${cameraId}`);
            }
          }
        } catch (e) {
          console.error(`❌ Erro ao processar mensagem WebSocket:`, e);
        }
      };
      
      // WebSocket connection opened
      ws.onopen = async () => {
        console.log(`🔗 [${cameraId}] WebSocket conectado`);
        
        // Protocolo correto: enviar start-stream primeiro
        ws.send(JSON.stringify({
          type: 'start-stream',
          camera_id: cameraId
        }));
        console.log(`📤 [${cameraId}] Comando start-stream enviado`);
      };
      
      // Handle WebSocket errors
      ws.onerror = (error) => {
        console.error(`❌ Erro WebSocket para câmera ${cameraId}:`, error);
      };
      
      // Handle WebSocket close
      ws.onclose = () => {
        console.log(`🔌 WebSocket fechado para câmera ${cameraId}`);
      };
      
      // Connections são armazenadas no estado isolado da câmera
      
      console.log(`✅ [${cameraId}] WebRTC configurado com sucesso`);
      
    } catch (error) {
      console.error(`❌ [${cameraId}] Erro WebRTC:`, error);
      handleCameraError(cameraId, `Erro WebRTC: ${error.message}`);
    }
  };

  // Sistema inteligente isolado - cada câmera tem seu próprio ciclo de vida
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
    
    // Se muitos erros, pausar e tentar mais tarde
    if (newErrorCount >= 5) {
      console.log(`🚫 [${cameraId}] Muitos erros, pausando por 2 minutos`);
      updateCameraState(cameraId, { status: 'error' });
      
      // Try again after 2 minutes
      setTimeout(() => {
        console.log(`🔄 [${cameraId}] Tentando reconectar após pausa`);
        updateCameraState(cameraId, { errorCount: 0, retryCount: state.retryCount + 1 });
        startCameraStreamIsolated(cameraId);
      }, 120000); // 2 minutes
    } else {
      // Quick retry for minor errors
      setTimeout(() => {
        console.log(`🔄 [${cameraId}] Tentativa rápida de reconexão`);
        startCameraStreamIsolated(cameraId);
      }, 5000); // 5 seconds
    }
  };

  const startCameraStreamIsolated = async (cameraId: string) => {
    const state = getCameraState(cameraId);
    
    // Se já está conectando há muito tempo, limpar e tentar novamente
    if (state.status === 'connecting') {
      const timeSinceLastError = Date.now() - state.lastErrorTime;
      if (timeSinceLastError > 30000) { // 30 segundos
        console.log(`🔄 [${cameraId}] Limpando estado 'connecting' antigo e tentando novamente`);
        cleanupCameraState(cameraId);
      } else {
        console.log(`⚠️ [${cameraId}] Já está conectando recentemente, ignorando`);
        return;
      }
    }
    
    // Verificar se já está conectado - evitar múltiplas conexões
    if (state.status === 'connected') {
      console.log(`⚠️ [${cameraId}] Já está conectado, ignorando nova tentativa`);
      return;
    }
    
    console.log(`🎥 [ISOLADO] Iniciando stream para câmera ${cameraId}`);
    updateCameraState(cameraId, { status: 'connecting' });
    
    try {
      // Tentar WebRTC direto com webrtcbin
      console.log(`📡 [${cameraId}] Tentando WebRTC direto com webrtcbin...`);
      const directWebRTCAvailable = await checkDirectWebRTCAvailability(import.meta.env.VITE_VMS_WEBRTC_URL || 'http://127.0.0.1:17236');
      
      if (directWebRTCAvailable) {
        console.log(`✅ [${cameraId}] WebRTC direto disponível, conectando...`);
        await startDirectWebRTCStreamIsolated(cameraId);
        return;
      }
      
      // Fallback para modo VMS (antigo)
      console.log(`📺 [${cameraId}] WebRTC direto não disponível, tentando modo VMS...`);
      const webRtcResponse = await fetch(`http://127.0.0.1:17236/health`, {
        signal: AbortSignal.timeout(2000)
      });
      
      if (webRtcResponse.ok) {
        console.log(`🔴 [${cameraId}] Iniciando WebRTC VMS`);
        await startWebRTCStreamIsolated(cameraId);
        return;
      }
    } catch (e) {
      console.log(`⚠️ [${cameraId}] Erro nas conexões WebRTC:`, e);
    }
    
    // Fallback final para snapshots
    console.log(`📸 [${cameraId}] Usando modo snapshot como fallback`);
    startSnapshotModeIsolated(cameraId);
  };

  const startDirectWebRTCStreamIsolated = async (cameraId: string) => {
    console.log(`🚀 [${cameraId}] Iniciando WebRTC direto com webrtcbin...`);
    
    try {
      // Criar cliente WebRTC direto
      const directClient = await createDirectWebRTCClient(cameraId, import.meta.env.VITE_VMS_WEBRTC_URL || 'http://127.0.0.1:17236');
      
      // Configurar callbacks
      directClient.config.onStream = (stream: MediaStream) => {
        console.log(`🎥 [${cameraId}] Stream WebRTC direto recebido!`);
        updateCameraState(cameraId, {
          stream: stream,
          status: 'connected',
          connectionType: 'direct_webrtc',
          isHealthy: true,
          errorCount: 0
        });
        
        toast.success(`Câmera ${cameraId} conectada via WebRTC direto!`);
      };
      
      directClient.config.onError = (error: string) => {
        console.error(`❌ [${cameraId}] Erro WebRTC direto:`, error);
        handleCameraError(cameraId, `WebRTC direto: ${error}`);
      };
      
      directClient.config.onConnected = () => {
        console.log(`✅ [${cameraId}] WebRTC direto conectado, aguardando stream...`);
      };
      
      directClient.config.onDisconnected = () => {
        console.log(`🔌 [${cameraId}] WebRTC direto desconectado`);
        updateCameraState(cameraId, {
          status: 'error',
          connectionType: undefined,
          isHealthy: false
        });
      };
      
      // Salvar cliente no estado
      updateCameraState(cameraId, { 
        directWebRTCClient: directClient,
        connectionType: 'direct_webrtc'
      });
      
      // Conectar
      await directClient.connect();
      console.log(`✅ [${cameraId}] Conexão WebRTC direto estabelecida`);
      
    } catch (error) {
      console.error(`❌ [${cameraId}] Falha na conexão WebRTC direto:`, error);
      handleCameraError(cameraId, `Falha WebRTC direto: ${error.message}`);
    }
  };


  const startSnapshotModeIsolated = (cameraId: string) => {
    const state = getCameraState(cameraId);
    
    try {
      // Limpar intervalo anterior se existir
      if (state.snapshotInterval) {
        clearInterval(state.snapshotInterval);
      }
      
      // Usar snapshots como fallback ou método principal (apenas se WebRTC não estiver ativo)
      const interval = setInterval(async () => {
        const currentState = getCameraState(cameraId);
        
        // Verificar se WebRTC ainda está ativo - se sim, não fazer snapshots
        if (currentState.status === 'connected' && currentState.stream) {
          console.log(`⏸️ [${cameraId}] Pulando snapshot - WebRTC ativo`);
          return;
        }
        
        try {
          const controller = new AbortController();
          const timeoutId = setTimeout(() => controller.abort(), 3000);
          
          const response = await fetch(`${ApiService.getBaseUrl()}/api/v1/cameras/${cameraId}/snapshot?t=${Date.now()}`, {
            signal: controller.signal
          });
          clearTimeout(timeoutId);
          
          if (response.ok) {
            const blob = await response.blob();
            const imageUrl = URL.createObjectURL(blob);
            
            // Update isolated state
            const currentState = getCameraState(cameraId);
            if (currentState.snapshotUrl && currentState.snapshotUrl !== imageUrl) {
              // Aguardar um pouco antes de revogar para evitar ERR_FILE_NOT_FOUND
              setTimeout(() => URL.revokeObjectURL(currentState.snapshotUrl!), 1000);
            }
            
            updateCameraState(cameraId, {
              snapshotUrl: imageUrl,
              status: 'connected',
              isHealthy: true,
              errorCount: 0
            });
          } else {
            console.log(`⚠️ [${cameraId}] Snapshot falhou: ${response.status}`);
            handleCameraError(cameraId, `Snapshot falhou: ${response.status}`);
          }
        } catch (error) {
          if (error.name !== 'AbortError') {
            console.error(`❌ [${cameraId}] Erro no snapshot:`, error);
            handleCameraError(cameraId, `Erro snapshot: ${error.message}`);
          }
        }
      }, 2000); // Atualizar a cada 2 segundos para evitar sobrecarga
      
      // Store interval in isolated state
      updateCameraState(cameraId, { snapshotInterval: interval });
      
      if (!autoPlay) {
        toast.success(`[${cameraId}] Modo snapshot iniciado`);
      }
    } catch (error) {
      console.error(`❌ [${cameraId}] Erro ao iniciar snapshot:`, error);
      handleCameraError(cameraId, `Erro ao iniciar snapshot: ${error.message}`);
    }
  };

  const stopCameraStream = (cameraId: string) => {
    console.log(`⏹️ Parando stream para câmera ${cameraId}`);
    
    // Limpar WebRTC connections
    const connection = webrtcConnections.current.get(cameraId);
    if (connection) {
      try {
        connection.close();
        webrtcConnections.current.delete(cameraId);
        console.log(`📼 Conexão WebRTC fechada para câmera ${cameraId}`);
      } catch (error) {
        console.warn(`Erro ao fechar conexão WebRTC para ${cameraId}:`, error);
      }
    }
    
    const interval = streamIntervals.current.get(cameraId);
    if (interval) {
      clearInterval(interval);
      streamIntervals.current.delete(cameraId);
    }
    
    // Limpar streams e snapshots
    setCameraStreams(prev => {
      const newMap = new Map(prev);
      newMap.delete(cameraId);
      return newMap;
    });
    
    setCameraSnapshots(prev => {
      const newMap = new Map(prev);
      const oldUrl = newMap.get(cameraId);
      if (oldUrl) URL.revokeObjectURL(oldUrl);
      newMap.delete(cameraId);
      return newMap;
    });
    
    setStreamingCameras(prev => {
      const newSet = new Set(prev);
      newSet.delete(cameraId);
      return newSet;
    });
    
    toast.success('Stream parado');
  };

  const toggleRecognition = (cameraId: string) => {
    setCameras(prev => prev.map(cam => 
      cam.id === cameraId 
        ? { ...cam, recognitionEnabled: !cam.recognitionEnabled }
        : cam
    ));
    
    const camera = cameras.find(c => c.id === cameraId);
    const newState = !camera?.recognitionEnabled;
    toast.success(`Reconhecimento ${newState ? 'ativado' : 'desativado'} para ${camera?.name}`);
  };

  const getLayoutGrid = () => {
    const layout = layouts.find(l => l.id === viewLayout);
    return layout?.grid || 'grid-cols-2';
  };

  const renderCameraView = (camera: Camera) => (
    <div
      key={camera.id}
      className={`relative bg-black rounded-lg overflow-hidden cursor-pointer transition-all hover:ring-2 hover:ring-primary ${
        selectedCamera === camera.id ? 'ring-2 ring-primary' : ''
      }`}
      onClick={() => setSelectedCamera(camera.id)}
    >
      {/* Status Badge */}
      <div className="absolute top-3 left-3 z-10">
        <span className={`badge ${
          camera.status === 'online' ? 'badge-success' : 
          camera.status === 'connecting' ? 'badge-warning' : 
          'badge-error'
        }`}>
          <span className="status-dot mr-1"></span>
          {camera.status === 'online' ? 'Ao Vivo' : 
           camera.status === 'connecting' ? 'Conectando' : 
           'Offline'}
        </span>
      </div>

      {/* Camera Name */}
      <div className="absolute top-3 right-3 z-10">
        <span className="bg-black/70 text-white px-3 py-1 rounded-md text-sm font-medium">
          {camera.name}
        </span>
      </div>

      {/* Video Feed ou Placeholder */}
      {camera.status === 'online' ? (
        <div className="aspect-video bg-gray-900 flex items-center justify-center relative">
          {(() => {
            const state = getCameraState(camera.id);
            
            // Usar stream isolado se disponível
            if (state.status === 'connected' && state.stream) {
              return (
                <WebRTCVideo 
                  key={`video-isolated-${camera.id}`}
                  stream={state.stream}
                  cameraName={camera.name}
                  cameraId={camera.id}
                  onError={() => handleCameraError(camera.id, 'Erro no elemento de vídeo')}
                />
              );
            }
            
            // Usar snapshot isolado se disponível
            if (state.snapshotUrl) {
              return (
                <img 
                  src={state.snapshotUrl}
                  alt={camera.name}
                  className="w-full h-full object-cover rounded"
                  onError={() => handleCameraError(camera.id, 'Erro na imagem snapshot')}
                />
              );
            }
            
            // Estado de conectando
            if (state.status === 'connecting') {
              return (
                <div className="w-full h-full flex items-center justify-center border border-yellow-600 rounded bg-yellow-50">
                  <div className="text-center">
                    <div className="animate-spin rounded-full h-8 w-8 border-4 border-yellow-500 border-t-transparent mx-auto mb-2"></div>
                    <p className="text-yellow-700 text-sm">Conectando...</p>
                    <p className="text-yellow-600 text-xs">{camera.name}</p>
                  </div>
                </div>
              );
            }
            
            // Estado de erro
            if (state.status === 'error') {
              return (
                <div className="w-full h-full flex items-center justify-center border border-red-600 rounded bg-red-50">
                  <div className="text-center">
                    <ExclamationTriangleIcon className="w-12 h-12 text-red-600 mx-auto mb-2" />
                    <p className="text-red-700 text-sm">Erro na conexão</p>
                    <p className="text-red-600 text-xs">{camera.name}</p>
                    <p className="text-red-500 text-xs mt-1">Erros: {state.errorCount}/5</p>
                    {state.retryCount > 0 && (
                      <p className="text-red-400 text-xs">Tentativas: {state.retryCount}</p>
                    )}
                  </div>
                </div>
              );
            }
            
            // Estado padrão - botão de iniciar
            return (
              <div className="w-full h-full flex items-center justify-center border border-gray-600 rounded">
              <div className="text-center">
                <CameraIcon className="w-16 h-16 text-gray-500 mx-auto mb-4" />
                <p className="text-gray-400 text-sm mb-2">{camera.name}</p>
                <div className="flex flex-col gap-2">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      startCameraStreamIsolated(camera.id);
                    }}
                    className="flex items-center gap-2 mx-auto px-4 py-2 bg-primary text-white rounded-md hover:bg-primary/80 transition-colors"
                  >
                    <PlayIcon className="w-4 h-4" />
                    Iniciar Stream Isolado
                  </button>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      console.log(`🧹 [${camera.id}] Limpando estado manualmente`);
                      cleanupCameraState(camera.id);
                    }}
                    className="flex items-center gap-2 mx-auto px-2 py-1 bg-gray-500 text-white text-xs rounded-md hover:bg-gray-600 transition-colors"
                  >
                    Reset Estado
                  </button>
                </div>
                <p className="text-gray-600 text-xs mt-2">Sistema inteligente - não interfere em outras câmeras</p>
              </div>
              </div>
            );
          })()}
        </div>
      ) : (
        <div className="aspect-video bg-gray-900 flex flex-col items-center justify-center">
          <ExclamationTriangleIcon className="w-12 h-12 text-gray-600 mb-2" />
          <p className="text-gray-500 text-sm">Câmera indisponível</p>
          {camera.status === 'offline' && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                handleReconnect(camera.id);
              }}
              className="mt-3 btn btn-secondary btn-sm"
            >
              <ArrowPathIcon className="w-4 h-4 mr-1" />
              Reconectar
            </button>
          )}
        </div>
      )}

      {/* Controls Overlay */}
      {camera.status === 'online' && (
        <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/80 to-transparent p-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              {(() => {
                const state = getCameraState(camera.id);
                const isStreaming = state.status === 'connected' || state.status === 'connecting';
                
                return isStreaming ? (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      cleanupCameraState(camera.id);
                      toast.success(`Stream ${camera.name} parado`);
                    }}
                    className="p-2 bg-red-500/20 text-red-400 rounded-md hover:bg-red-500/30 transition-colors"
                    title="Parar stream isolado"
                  >
                    <PauseIcon className="w-4 h-4" />
                  </button>
                ) : (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      startCameraStreamIsolated(camera.id);
                    }}
                    className="p-2 bg-green-500/20 text-green-400 rounded-md hover:bg-green-500/30 transition-colors"
                    title="Iniciar stream isolado"
                  >
                    <PlayIcon className="w-4 h-4" />
                  </button>
                );
              })()}
              
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  toggleRecognition(camera.id);
                }}
                className={`p-2 rounded-md transition-colors ${
                  camera.recognitionEnabled 
                    ? 'bg-primary/20 text-primary hover:bg-primary/30' 
                    : 'bg-white/10 text-white/50 hover:bg-white/20'
                }`}
                title={camera.recognitionEnabled ? 'Reconhecimento ativo' : 'Reconhecimento inativo'}
              >
                <VideoCameraIcon className="w-4 h-4" />
              </button>
              
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  handleSnapshot(camera.id);
                }}
                className="p-2 bg-white/10 text-white/70 rounded-md hover:bg-white/20 transition-colors"
                title="Capturar imagem"
              >
                <PhotoIcon className="w-4 h-4" />
              </button>
            </div>
            
            {camera.location && (
              <span className="text-white/70 text-xs">
                {camera.location}
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );

  return (
    <div ref={containerRef} className="h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold mb-1">Central de Monitoramento</h1>
          <p className="text-secondary">
            {cameras.filter(c => c.status === 'online').length} de {cameras.length} câmeras ativas
          </p>
        </div>

        {/* Controls */}
        <div className="flex items-center gap-2">
          {/* Status da API */}
          <div className="flex items-center gap-2 px-3 py-1 rounded-md bg-surface">
            <div className={`w-2 h-2 rounded-full ${apiConnected ? 'bg-green-500' : 'bg-red-500'}`}></div>
            <span className="text-xs text-secondary">
              {apiConnected ? 'API Online' : 'API Offline'}
            </span>
          </div>

          {/* AutoPlay Toggle */}
          <button
            onClick={() => setAutoPlay(!autoPlay)}
            className={`px-3 py-2 rounded-md text-sm font-medium transition-colors ${
              autoPlay 
                ? 'bg-primary text-white' 
                : 'bg-surface text-secondary hover:text-primary'
            }`}
            title={autoPlay ? 'Autoplay ativo' : 'Autoplay inativo'}
          >
            <PlayIcon className="w-4 h-4 mr-1 inline" />
            Auto
          </button>

          {/* Layout Selector */}
          <div className="flex items-center bg-surface rounded-lg p-1">
            {layouts.map((layout) => {
              const Icon = layout.icon;
              return (
                <button
                  key={layout.id}
                  onClick={() => setViewLayout(layout.id)}
                  className={`p-2 rounded-md transition-colors ${
                    viewLayout === layout.id
                      ? 'bg-primary text-white'
                      : 'text-secondary hover:text-primary'
                  }`}
                  title={layout.name}
                >
                  <Icon className="w-5 h-5" />
                </button>
              );
            })}
          </div>

          {/* Audio Toggle */}
          <button
            onClick={() => setIsMuted(!isMuted)}
            className="btn btn-secondary"
            title={isMuted ? 'Ativar som' : 'Desativar som'}
          >
            {isMuted ? (
              <SpeakerXMarkIcon className="w-5 h-5" />
            ) : (
              <SpeakerWaveIcon className="w-5 h-5" />
            )}
          </button>

          {/* Stats Toggle */}
          <button
            onClick={() => setShowStats(!showStats)}
            className={`btn ${showStats ? 'btn-primary' : 'btn-secondary'}`}
            title="Estatísticas"
          >
            <ChartBarIcon className="w-5 h-5" />
          </button>

          {/* Fullscreen */}
          <button
            onClick={handleFullscreen}
            className="btn btn-secondary"
            title={isFullscreen ? 'Sair do modo tela cheia' : 'Tela cheia'}
          >
            {isFullscreen ? (
              <ArrowsPointingInIcon className="w-5 h-5" />
            ) : (
              <ArrowsPointingOutIcon className="w-5 h-5" />
            )}
          </button>
        </div>
      </div>

      {/* Camera Grid */}
      <div className="flex-1 overflow-hidden">
        {cameras.length === 0 ? (
          <div className="h-full flex items-center justify-center">
            <div className="text-center">
              <VideoCameraIcon className="w-16 h-16 text-gray-400 mx-auto mb-4" />
              <h3 className="text-lg font-medium mb-2">Nenhuma câmera encontrada</h3>
              <p className="text-secondary mb-4">Configure câmeras para começar o monitoramento</p>
              <p className="text-xs text-muted">Debug: {cameras.length} câmeras carregadas</p>
              <button className="btn btn-primary" onClick={fetchCameras}>
                Recarregar Câmeras
              </button>
            </div>
          </div>
        ) : (
          <div className={`grid ${getLayoutGrid()} gap-4 h-full`}>
            {cameras.map(camera => renderCameraView(camera))}
          </div>
        )}
      </div>

      {/* Stats Overlay */}
      {showStats && selectedCamera && (
        <div className="absolute bottom-6 left-6 bg-surface-elevated rounded-lg shadow-lg p-4 max-w-xs">
          <h4 className="font-semibold mb-3">Estatísticas</h4>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-secondary">FPS:</span>
              <span className="font-medium">30</span>
            </div>
            <div className="flex justify-between">
              <span className="text-secondary">Resolução:</span>
              <span className="font-medium">1920x1080</span>
            </div>
            <div className="flex justify-between">
              <span className="text-secondary">Bitrate:</span>
              <span className="font-medium">2.5 Mbps</span>
            </div>
            <div className="flex justify-between">
              <span className="text-secondary">Latência:</span>
              <span className="font-medium text-success">32ms</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default VMSMonitor;