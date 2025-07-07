/**
 * Cliente WebRTC Direto - Conexão direta com GStreamer webrtcbin
 * Substitui a integração com Janus Gateway
 */

export interface DirectWebRTCConfig {
  signalingUrl: string;
  cameraId: string;
  onStream?: (stream: MediaStream) => void;
  onError?: (error: string) => void;
  onConnected?: () => void;
  onDisconnected?: () => void;
  iceServers?: RTCIceServer[];
}

export class DirectWebRTCClient {
  private config: DirectWebRTCConfig;
  private peerConnection: RTCPeerConnection | null = null;
  private websocket: WebSocket | null = null;
  private isConnecting: boolean = false;
  private isConnected: boolean = false;
  private reconnectAttempts: number = 0;
  private maxReconnectAttempts: number = 5;
  private reconnectDelay: number = 1000;

  constructor(config: DirectWebRTCConfig) {
    this.config = config;
  }

  /**
   * Conecta ao pipeline WebRTC
   */
  async connect(): Promise<void> {
    if (this.isConnecting || this.isConnected) {
      console.log('🔄 WebRTC já está conectando/conectado');
      return;
    }

    this.isConnecting = true;
    console.log(`🚀 Conectando WebRTC direto para câmera: ${this.config.cameraId}`);

    try {
      // Criar peer connection
      this.createPeerConnection();
      
      // Conectar WebSocket de sinalização
      await this.connectWebSocket();
      
      // Solicitar offer do servidor
      this.requestOffer();
      
    } catch (error) {
      console.error('❌ Erro ao conectar WebRTC:', error);
      this.isConnecting = false;
      this.config.onError?.(`Erro na conexão: ${error}`);
      throw error;
    }
  }

  private createPeerConnection() {
    console.log('🔗 Criando RTCPeerConnection para LAN local...');

    // Para LAN local, não precisamos de STUN servers
    // Isso força o uso de candidatos host locais
    const iceServers = this.config.iceServers || [];

    this.peerConnection = new RTCPeerConnection({
      iceServers, // Array vazio para forçar LAN local
      iceCandidatePoolSize: 0, // Reduzido para LAN
      iceTransportPolicy: 'all', // Permitir todos os tipos de transporte
      bundlePolicy: 'max-bundle'
    });

    // Eventos da peer connection
    this.peerConnection.onicecandidate = (event) => {
      if (event.candidate) {
        console.log('🧊 ICE candidate gerado');
        this.sendMessage({
          type: 'ice-candidate',
          candidate: {
            candidate: event.candidate.candidate,
            sdpMLineIndex: event.candidate.sdpMLineIndex,
            sdpMid: event.candidate.sdpMid
          }
        });
      }
    };

    this.peerConnection.ontrack = (event) => {
      console.log('🎥 Stream recebido!');
      if (event.streams && event.streams[0]) {
        this.isConnecting = false;
        this.isConnected = true;
        this.reconnectAttempts = 0;
        this.config.onConnected?.();
        this.config.onStream?.(event.streams[0]);
      }
    };

    this.peerConnection.onconnectionstatechange = () => {
      const state = this.peerConnection?.connectionState;
      console.log(`🔗 Estado da conexão WebRTC: ${state}`);

      switch (state) {
        case 'connected':
          this.isConnected = true;
          this.isConnecting = false;
          this.reconnectAttempts = 0;
          break;
        
        case 'disconnected':
        case 'failed':
          this.isConnected = false;
          this.config.onDisconnected?.();
          this.handleConnectionFailure();
          break;
        
        case 'closed':
          this.isConnected = false;
          this.isConnecting = false;
          break;
      }
    };

    this.peerConnection.onicegatheringstatechange = () => {
      console.log(`🧊 ICE gathering state: ${this.peerConnection?.iceGatheringState}`);
    };

    console.log('✅ RTCPeerConnection criado');
  }

  private async connectWebSocket(): Promise<void> {
    return new Promise((resolve, reject) => {
      // Garantir que usa WebSocket protocol e localhost para LAN
      const wsUrl = `${this.config.signalingUrl}/ws/${this.config.cameraId}`.replace('http', 'ws');
      console.log(`🔌 Conectando WebSocket LAN: ${wsUrl}`);

      this.websocket = new WebSocket(wsUrl);

      this.websocket.onopen = () => {
        console.log('✅ WebSocket conectado');
        resolve();
      };

      this.websocket.onmessage = async (event) => {
        try {
          const message = JSON.parse(event.data);
          await this.handleSignalingMessage(message);
        } catch (error) {
          console.error('❌ Erro ao processar mensagem:', error);
        }
      };

      this.websocket.onerror = (error) => {
        console.error('❌ Erro no WebSocket:', error);
        reject(error);
      };

      this.websocket.onclose = (event) => {
        console.log(`🔌 WebSocket fechado: ${event.code} ${event.reason}`);
        this.isConnected = false;
        
        if (!event.wasClean && this.reconnectAttempts < this.maxReconnectAttempts) {
          this.scheduleReconnect();
        }
      };

      // Timeout para conexão
      setTimeout(() => {
        if (this.websocket?.readyState !== WebSocket.OPEN) {
          reject(new Error('Timeout na conexão WebSocket'));
        }
      }, 5000);
    });
  }

  private requestOffer() {
    console.log('🤝 Solicitando offer do servidor...');
    this.sendMessage({ 
      type: 'request-offer',
      cameraId: this.config.cameraId 
    });
  }

  private async handleSignalingMessage(message: any) {
    console.log(`📨 Mensagem de sinalização: ${message.type}`);

    switch (message.type) {
      case 'welcome':
        console.log(`🎉 Conectado à câmera ${message.camera_id}, status: ${message.status}`);
        break;
        
      case 'offer':
        await this.handleOffer(message.sdp);
        break;
      
      case 'ice-candidate':
        await this.handleIceCandidate(message.candidate);
        break;
      
      default:
        console.log(`⚠️ Tipo de mensagem desconhecido: ${message.type}`);
    }
  }

  private async handleOffer(sdp: string) {
    if (!this.peerConnection) {
      console.error('❌ PeerConnection não existe');
      return;
    }

    try {
      console.log('📥 Processando offer do servidor...');
      
      // Set remote description
      await this.peerConnection.setRemoteDescription({
        type: 'offer',
        sdp: sdp
      });

      // Criar answer
      const answer = await this.peerConnection.createAnswer();
      await this.peerConnection.setLocalDescription(answer);

      // Enviar answer
      console.log('📤 Enviando answer...');
      this.sendMessage({
        type: 'answer',
        sdp: answer.sdp
      });

    } catch (error) {
      console.error('❌ Erro ao processar offer:', error);
      this.config.onError?.(`Erro no offer: ${error}`);
    }
  }

  private async handleIceCandidate(candidate: any) {
    if (!this.peerConnection) {
      console.error('❌ PeerConnection não existe');
      return;
    }

    try {
      console.log('🧊 Adicionando ICE candidate...');
      
      await this.peerConnection.addIceCandidate({
        candidate: candidate.candidate,
        sdpMLineIndex: candidate.sdpMLineIndex,
        sdpMid: candidate.sdpMid
      });

    } catch (error) {
      console.error('❌ Erro ao adicionar ICE candidate:', error);
    }
  }

  private sendMessage(message: any) {
    if (this.websocket?.readyState === WebSocket.OPEN) {
      this.websocket.send(JSON.stringify(message));
    } else {
      console.error('❌ WebSocket não conectado, não é possível enviar mensagem');
    }
  }

  private handleConnectionFailure() {
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.scheduleReconnect();
    } else {
      console.error('❌ Máximo de tentativas de reconexão excedido');
      this.config.onError?.('Falha na conexão WebRTC após múltiplas tentativas');
    }
  }

  private scheduleReconnect() {
    this.reconnectAttempts++;
    const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1); // Exponential backoff
    
    console.log(`🔄 Tentativa de reconexão ${this.reconnectAttempts}/${this.maxReconnectAttempts} em ${delay}ms`);
    
    setTimeout(() => {
      this.disconnect();
      this.connect().catch(error => {
        console.error('❌ Erro na reconexão:', error);
      });
    }, delay);
  }

  /**
   * Desconecta completamente
   */
  disconnect() {
    console.log('🔌 Desconectando WebRTC...');
    
    this.isConnected = false;
    this.isConnecting = false;

    if (this.peerConnection) {
      this.peerConnection.close();
      this.peerConnection = null;
    }

    if (this.websocket) {
      this.websocket.close();
      this.websocket = null;
    }

    console.log('✅ WebRTC desconectado');
  }

  /**
   * Status da conexão
   */
  getStatus() {
    return {
      connecting: this.isConnecting,
      connected: this.isConnected,
      peerConnectionState: this.peerConnection?.connectionState,
      websocketState: this.websocket?.readyState,
      cameraId: this.config.cameraId,
      reconnectAttempts: this.reconnectAttempts
    };
  }

  /**
   * Obter estatísticas WebRTC
   */
  async getStats(): Promise<RTCStatsReport | null> {
    if (this.peerConnection) {
      return await this.peerConnection.getStats();
    }
    return null;
  }
}

/**
 * Factory para criar cliente WebRTC direto
 */
export async function createDirectWebRTCClient(
  cameraId: string, 
  signalingUrl: string = import.meta.env.VITE_VMS_WEBRTC_URL || 'http://127.0.0.1:17236'
): Promise<DirectWebRTCClient> {
  
  console.log(`🔧 Criando cliente WebRTC direto para câmera: ${cameraId}`);
  console.log(`🔧 URL de sinalização: ${signalingUrl}`);
  
  const config: DirectWebRTCConfig = {
    signalingUrl,
    cameraId,
    iceServers: [] // Array vazio para LAN local
  };

  return new DirectWebRTCClient(config);
}

/**
 * Verificar se WebRTC direto está disponível
 */
export async function checkDirectWebRTCAvailability(
  signalingUrl: string = import.meta.env.VITE_VMS_WEBRTC_URL || 'http://127.0.0.1:17236'
): Promise<boolean> {
  try {
    const response = await fetch(`${signalingUrl}/health`);
    if (response.ok) {
      const health = await response.json();
      return health.status === 'healthy';
    }
    return false;
  } catch (error) {
    console.log('⚠️ Servidor WebRTC direto não disponível:', error);
    return false;
  }
}

/**
 * Obter lista de câmeras disponíveis
 */
export async function getAvailableCameras(
  signalingUrl: string = import.meta.env.VITE_VMS_WEBRTC_URL || 'http://127.0.0.1:17236'
): Promise<string[]> {
  try {
    const response = await fetch(`${signalingUrl}/sessions`);
    if (response.ok) {
      const data = await response.json();
      const cameraIds = [...new Set(data.sessions.map((s: any) => s.camera_id))];
      return cameraIds;
    }
    return [];
  } catch (error) {
    console.error('❌ Erro ao buscar câmeras:', error);
    return [];
  }
}