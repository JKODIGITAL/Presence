/**
 * Multi-Camera WebRTC Client
 * Gerencia múltiplas conexões WebRTC, uma para cada câmera
 */

export interface CameraWebRTCConfig {
  cameraId: string;
  websocketUrl: string;
  onStream?: (stream: MediaStream) => void;
  onError?: (error: string) => void;
  onConnected?: () => void;
  onDisconnected?: () => void;
  iceServers?: RTCIceServer[];
}

export class CameraWebRTCConnection {
  private config: CameraWebRTCConfig;
  private peerConnection: RTCPeerConnection | null = null;
  private websocket: WebSocket | null = null;
  private isConnecting: boolean = false;
  private isConnected: boolean = false;
  private reconnectAttempts: number = 0;
  private maxReconnectAttempts: number = 3;
  private reconnectTimer: NodeJS.Timeout | null = null;

  constructor(config: CameraWebRTCConfig) {
    this.config = config;
  }

  async connect(): Promise<void> {
    if (this.isConnecting || this.isConnected) {
      console.log(`🔄 Câmera ${this.config.cameraId} já está conectando/conectada`);
      return;
    }

    this.isConnecting = true;
    console.log(`🚀 Conectando WebRTC para câmera: ${this.config.cameraId}`);

    try {
      await this.createPeerConnection();
      await this.connectWebSocket();
      await this.requestOffer();
    } catch (error) {
      console.error(`❌ Erro ao conectar câmera ${this.config.cameraId}:`, error);
      this.isConnecting = false;
      this.config.onError?.(`Erro na conexão: ${error}`);
      this.scheduleReconnect();
    }
  }

  private async createPeerConnection(): Promise<void> {
    console.log(`🔗 Criando RTCPeerConnection para ${this.config.cameraId}...`);

    const iceServers = this.config.iceServers || [
      { urls: 'stun:stun.l.google.com:19302' }
    ];

    this.peerConnection = new RTCPeerConnection({
      iceServers,
      iceCandidatePoolSize: 10
    });

    // Event handlers
    this.peerConnection.onicecandidate = (event) => {
      if (event.candidate && this.websocket?.readyState === WebSocket.OPEN) {
        console.log(`🧊 Enviando ICE candidate para ${this.config.cameraId}`);
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
      console.log(`🎥 Stream recebido para câmera ${this.config.cameraId}!`);
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
      console.log(`🔗 Estado da conexão WebRTC ${this.config.cameraId}: ${state}`);

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
          this.scheduleReconnect();
          break;
        
        case 'closed':
          this.isConnected = false;
          this.isConnecting = false;
          break;
      }
    };

    console.log(`✅ RTCPeerConnection criado para ${this.config.cameraId}`);
  }

  private async connectWebSocket(): Promise<void> {
    return new Promise((resolve, reject) => {
      console.log(`🔌 Conectando WebSocket para ${this.config.cameraId}: ${this.config.websocketUrl}`);

      this.websocket = new WebSocket(this.config.websocketUrl);

      this.websocket.onopen = () => {
        console.log(`✅ WebSocket conectado para ${this.config.cameraId}`);
        resolve();
      };

      this.websocket.onmessage = async (event) => {
        try {
          const message = JSON.parse(event.data);
          await this.handleSignalingMessage(message);
        } catch (error) {
          console.error(`❌ Erro ao processar mensagem para ${this.config.cameraId}:`, error);
        }
      };

      this.websocket.onerror = (error) => {
        console.error(`❌ Erro no WebSocket ${this.config.cameraId}:`, error);
        reject(error);
      };

      this.websocket.onclose = (event) => {
        console.log(`🔌 WebSocket fechado para ${this.config.cameraId}: ${event.code} ${event.reason}`);
        this.isConnected = false;
        
        if (!event.wasClean && this.reconnectAttempts < this.maxReconnectAttempts) {
          this.scheduleReconnect();
        }
      };

      // Timeout para conexão
      setTimeout(() => {
        if (this.websocket?.readyState !== WebSocket.OPEN) {
          reject(new Error(`Timeout na conexão WebSocket para ${this.config.cameraId}`));
        }
      }, 5000);
    });
  }

  private async requestOffer(): Promise<void> {
    console.log(`🤝 Solicitando offer para ${this.config.cameraId}...`);
    this.sendMessage({ type: 'request-offer' });
  }

  private async handleSignalingMessage(message: any): Promise<void> {
    console.log(`📨 Mensagem de sinalização para ${this.config.cameraId}: ${message.type}`);

    switch (message.type) {
      case 'offer':
        await this.handleOffer(message.sdp);
        break;
      
      case 'ice-candidate':
        await this.handleIceCandidate(message.candidate);
        break;
      
      default:
        console.log(`⚠️ Tipo de mensagem desconhecido para ${this.config.cameraId}: ${message.type}`);
    }
  }

  private async handleOffer(sdp: string): Promise<void> {
    if (!this.peerConnection) {
      console.error(`❌ PeerConnection não existe para ${this.config.cameraId}`);
      return;
    }

    try {
      console.log(`📥 Processando offer para ${this.config.cameraId}...`);
      
      await this.peerConnection.setRemoteDescription({
        type: 'offer',
        sdp: sdp
      });

      const answer = await this.peerConnection.createAnswer();
      await this.peerConnection.setLocalDescription(answer);

      console.log(`📤 Enviando answer para ${this.config.cameraId}...`);
      this.sendMessage({
        type: 'answer',
        sdp: answer.sdp
      });

    } catch (error) {
      console.error(`❌ Erro ao processar offer para ${this.config.cameraId}:`, error);
      this.config.onError?.(`Erro no offer: ${error}`);
    }
  }

  private async handleIceCandidate(candidate: any): Promise<void> {
    if (!this.peerConnection) {
      console.error(`❌ PeerConnection não existe para ${this.config.cameraId}`);
      return;
    }

    try {
      console.log(`🧊 Adicionando ICE candidate para ${this.config.cameraId}...`);
      
      await this.peerConnection.addIceCandidate({
        candidate: candidate.candidate,
        sdpMLineIndex: candidate.sdpMLineIndex,
        sdpMid: candidate.sdpMid
      });

    } catch (error) {
      console.error(`❌ Erro ao adicionar ICE candidate para ${this.config.cameraId}:`, error);
    }
  }

  private sendMessage(message: any): void {
    if (this.websocket?.readyState === WebSocket.OPEN) {
      this.websocket.send(JSON.stringify(message));
    } else {
      console.error(`❌ WebSocket não conectado para ${this.config.cameraId}`);
    }
  }

  private scheduleReconnect(): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error(`❌ Máximo de tentativas de reconexão excedido para ${this.config.cameraId}`);
      this.config.onError?.('Falha na conexão após múltiplas tentativas');
      return;
    }

    this.reconnectAttempts++;
    const delay = 2000 * Math.pow(2, this.reconnectAttempts - 1); // Exponential backoff
    
    console.log(`🔄 Reagendando reconexão ${this.reconnectAttempts}/${this.maxReconnectAttempts} para ${this.config.cameraId} em ${delay}ms`);
    
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
    }

    this.reconnectTimer = setTimeout(() => {
      this.disconnect();
      this.connect().catch(error => {
        console.error(`❌ Erro na reconexão para ${this.config.cameraId}:`, error);
      });
    }, delay);
  }

  disconnect(): void {
    console.log(`🔌 Desconectando WebRTC para ${this.config.cameraId}...`);
    
    this.isConnected = false;
    this.isConnecting = false;

    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }

    if (this.peerConnection) {
      this.peerConnection.close();
      this.peerConnection = null;
    }

    if (this.websocket) {
      this.websocket.close();
      this.websocket = null;
    }

    console.log(`✅ WebRTC desconectado para ${this.config.cameraId}`);
  }

  getStatus() {
    return {
      cameraId: this.config.cameraId,
      connecting: this.isConnecting,
      connected: this.isConnected,
      peerConnectionState: this.peerConnection?.connectionState,
      websocketState: this.websocket?.readyState,
      reconnectAttempts: this.reconnectAttempts
    };
  }

  async getStats(): Promise<RTCStatsReport | null> {
    if (this.peerConnection) {
      return await this.peerConnection.getStats();
    }
    return null;
  }
}

export class MultiCameraWebRTCManager {
  private connections: Map<string, CameraWebRTCConnection> = new Map();
  private baseWebSocketUrl: string;
  private onStreamCallbacks: Map<string, (stream: MediaStream) => void> = new Map();

  constructor() {
    // Usar variável de ambiente ou fallback
    this.baseWebSocketUrl = import.meta.env.VITE_WEBRTC_CAMERA_WS_BASE || 'ws://127.0.0.1:8765';
    console.log(`🔧 WebSocket base configurado: ${this.baseWebSocketUrl}`);
  }

  /**
   * Adicionar câmera para gerenciamento WebRTC
   */
  addCamera(cameraId: string, onStream: (stream: MediaStream) => void): void {
    if (this.connections.has(cameraId)) {
      console.log(`⚠️ Câmera ${cameraId} já está sendo gerenciada`);
      return;
    }

    // Calcular porta WebSocket específica da câmera
    const cameraIndex = parseInt(cameraId.split('_').pop() || '0', 10);
    const websocketPort = this.baseWebSocketPort + cameraIndex;
    const websocketUrl = `ws://127.0.0.1:${websocketPort}/${cameraId}`;

    console.log(`📹 Adicionando câmera ${cameraId} na porta ${websocketPort}`);

    const config: CameraWebRTCConfig = {
      cameraId,
      websocketUrl,
      onStream: onStream,
      onError: (error) => {
        console.error(`❌ Erro na câmera ${cameraId}: ${error}`);
      },
      onConnected: () => {
        console.log(`✅ Câmera ${cameraId} conectada`);
      },
      onDisconnected: () => {
        console.log(`🔌 Câmera ${cameraId} desconectada`);
      },
      iceServers: [
        { urls: 'stun:stun.l.google.com:19302' }
      ]
    };

    const connection = new CameraWebRTCConnection(config);
    this.connections.set(cameraId, connection);
    this.onStreamCallbacks.set(cameraId, onStream);
  }

  /**
   * Conectar câmera específica
   */
  async connectCamera(cameraId: string): Promise<void> {
    const connection = this.connections.get(cameraId);
    if (connection) {
      await connection.connect();
    } else {
      console.error(`❌ Câmera ${cameraId} não encontrada no gerenciador`);
    }
  }

  /**
   * Desconectar câmera específica
   */
  disconnectCamera(cameraId: string): void {
    const connection = this.connections.get(cameraId);
    if (connection) {
      connection.disconnect();
    }
  }

  /**
   * Remover câmera do gerenciamento
   */
  removeCamera(cameraId: string): void {
    const connection = this.connections.get(cameraId);
    if (connection) {
      connection.disconnect();
      this.connections.delete(cameraId);
      this.onStreamCallbacks.delete(cameraId);
      console.log(`🗑️ Câmera ${cameraId} removida do gerenciador`);
    }
  }

  /**
   * Conectar todas as câmeras
   */
  async connectAllCameras(): Promise<void> {
    console.log(`🚀 Conectando ${this.connections.size} câmeras...`);
    
    const promises = Array.from(this.connections.keys()).map(cameraId => 
      this.connectCamera(cameraId)
    );

    await Promise.allSettled(promises);
  }

  /**
   * Desconectar todas as câmeras
   */
  disconnectAllCameras(): void {
    console.log(`🛑 Desconectando ${this.connections.size} câmeras...`);
    
    for (const cameraId of this.connections.keys()) {
      this.disconnectCamera(cameraId);
    }
  }

  /**
   * Limpar todas as conexões
   */
  cleanup(): void {
    this.disconnectAllCameras();
    this.connections.clear();
    this.onStreamCallbacks.clear();
    console.log(`🧹 Limpeza do MultiCameraWebRTCManager concluída`);
  }

  /**
   * Obter status de todas as câmeras
   */
  getStatus(): Record<string, any> {
    const status: Record<string, any> = {};
    
    for (const [cameraId, connection] of this.connections) {
      status[cameraId] = connection.getStatus();
    }

    return {
      totalCameras: this.connections.size,
      cameras: status
    };
  }

  /**
   * Obter estatísticas WebRTC de uma câmera
   */
  async getCameraStats(cameraId: string): Promise<RTCStatsReport | null> {
    const connection = this.connections.get(cameraId);
    if (connection) {
      return await connection.getStats();
    }
    return null;
  }
}