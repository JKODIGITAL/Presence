/**
 * Janus WebRTC Client - Conexão real com Janus Gateway
 */

import Janus from 'janus-gateway';

export interface JanusConfig {
  server: string;
  streamId: number;
  onStream?: (stream: MediaStream) => void;
  onError?: (error: string) => void;
  onConnected?: () => void;
  onDisconnected?: () => void;
}

export class JanusWebRTCClient {
  private janus: any = null;
  private pluginHandle: any = null;
  private config: JanusConfig;
  private opaqueId: string;
  private isConnecting: boolean = false;
  private isConnected: boolean = false;

  constructor(config: JanusConfig) {
    this.config = config;
    this.opaqueId = 'streamviewer-' + Janus.randomString(12);
  }

  /**
   * Conecta ao Janus e inicia visualização da stream
   */
  async connect(): Promise<void> {
    if (this.isConnecting || this.isConnected) {
      console.log('🔄 Janus já está conectando/conectado');
      return;
    }

    this.isConnecting = true;

    return new Promise((resolve, reject) => {
      // Verificar se Janus está disponível
      if (!Janus.isWebrtcSupported()) {
        const error = 'WebRTC não suportado neste navegador';
        console.error('❌', error);
        this.config.onError?.(error);
        reject(new Error(error));
        return;
      }

      // Inicializar Janus
      Janus.init({
        debug: 'all',
        callback: () => {
          console.log('✅ Janus.js inicializado');
          this.createJanusSession(resolve, reject);
        }
      });
    });
  }

  private createJanusSession(resolve: Function, reject: Function) {
    console.log(`🔌 Conectando ao Janus: ${this.config.server}`);
    
    this.janus = new Janus({
      server: this.config.server,
      success: () => {
        console.log('✅ Sessão Janus criada');
        this.attachToStreamingPlugin(resolve, reject);
      },
      error: (error: any) => {
        console.error('❌ Erro ao criar sessão Janus:', error);
        this.isConnecting = false;
        this.config.onError?.(`Erro na sessão: ${error}`);
        reject(new Error(error));
      },
      destroyed: () => {
        console.log('🔌 Sessão Janus destruída');
        this.isConnected = false;
        this.config.onDisconnected?.();
      }
    });
  }

  private attachToStreamingPlugin(resolve: Function, reject: Function) {
    console.log('🔗 Anexando ao plugin streaming...');
    
    this.janus.attach({
      plugin: 'janus.plugin.streaming',
      opaqueId: this.opaqueId,
      success: (pluginHandle: any) => {
        console.log('✅ Plugin streaming anexado');
        this.pluginHandle = pluginHandle;
        this.watchStream(resolve, reject);
      },
      error: (error: any) => {
        console.error('❌ Erro ao anexar plugin:', error);
        this.isConnecting = false;
        this.config.onError?.(`Erro no plugin: ${error}`);
        reject(new Error(error));
      },
      onmessage: (msg: any, jsep: any) => {
        console.log('📨 Mensagem do Janus:', msg);
        this.handleJanusMessage(msg, jsep);
      },
      onremotestream: (stream: MediaStream) => {
        console.log('🎥 Stream recebido do Janus!');
        this.isConnecting = false;
        this.isConnected = true;
        this.config.onConnected?.();
        this.config.onStream?.(stream);
      },
      oncleanup: () => {
        console.log('🧹 Cleanup do plugin');
        this.isConnected = false;
      },
      onerror: (error: any) => {
        console.error('❌ Erro no plugin:', error);
        this.isConnecting = false;
        this.config.onError?.(`Erro no plugin: ${error}`);
      }
    });
  }

  private watchStream(resolve: Function, reject: Function) {
    console.log(`📺 Solicitando stream ${this.config.streamId}...`);
    
    const body = { 
      request: 'watch', 
      id: this.config.streamId 
    };
    
    this.pluginHandle.send({
      message: body,
      success: () => {
        console.log(`✅ Solicitação watch enviada para stream ${this.config.streamId}`);
        resolve();
      },
      error: (error: any) => {
        console.error('❌ Erro ao enviar watch:', error);
        this.isConnecting = false;
        this.config.onError?.(`Erro ao assistir stream: ${error}`);
        reject(new Error(error));
      }
    });
  }

  private handleJanusMessage(msg: any, jsep: any) {
    const result = msg.result;
    
    if (result?.status) {
      console.log(`📊 Status da stream: ${result.status}`);
      
      if (result.status === 'starting') {
        console.log('▶️ Stream iniciando...');
      } else if (result.status === 'started') {
        console.log('✅ Stream iniciada!');
      } else if (result.status === 'stopped') {
        console.log('⏹️ Stream parada');
        this.isConnected = false;
      }
    }

    if (jsep) {
      console.log('📝 Processando offer do Janus...');
      this.handleRemoteOffer(jsep);
    }
  }

  private handleRemoteOffer(jsep: any) {
    this.pluginHandle.createAnswer({
      jsep: jsep,
      media: { 
        audioSend: false, 
        videoSend: false,
        data: false 
      },
      success: (jsep: any) => {
        console.log('📤 Answer criado e enviado');
        const body = { request: 'start' };
        this.pluginHandle.send({
          message: body,
          jsep: jsep
        });
      },
      error: (error: any) => {
        console.error('❌ Erro ao criar answer:', error);
        this.config.onError?.(`Erro no answer: ${error}`);
      }
    });
  }

  /**
   * Para a stream
   */
  stop() {
    if (this.pluginHandle) {
      console.log('⏹️ Parando stream...');
      this.pluginHandle.send({ 
        message: { request: 'stop' },
        success: () => {
          console.log('✅ Stream parada');
        }
      });
    }
  }

  /**
   * Desconecta completamente
   */
  disconnect() {
    console.log('🔌 Desconectando do Janus...');
    
    if (this.pluginHandle) {
      this.pluginHandle.detach();
      this.pluginHandle = null;
    }
    
    if (this.janus) {
      this.janus.destroy();
      this.janus = null;
    }
    
    this.isConnected = false;
    this.isConnecting = false;
  }

  /**
   * Status da conexão
   */
  getStatus() {
    return {
      connecting: this.isConnecting,
      connected: this.isConnected,
      streamId: this.config.streamId
    };
  }
}

/**
 * Factory para criar cliente Janus
 */
export async function createJanusClient(cameraId: string, serverUrl: string = 'http://127.0.0.1:17236'): Promise<JanusWebRTCClient | null> {
  try {
    // Verificar se servidor suporta Janus
    const response = await fetch(`${serverUrl}/health`);
    const health = await response.json();
    
    if (health.mode !== 'janus_sfu') {
      console.log('⚠️ Servidor não usa Janus SFU');
      return null;
    }

    // Buscar info da stream
    const streamResponse = await fetch(`${serverUrl}/streams`);
    if (!streamResponse.ok) {
      throw new Error('Não foi possível buscar streams');
    }

    const streamData = await streamResponse.json();
    const streams = streamData.streams || [];
    
    // Encontrar stream da câmera
    const cameraStream = streams.find((s: any) => s.camera_id === cameraId);
    if (!cameraStream) {
      throw new Error(`Stream não encontrada para câmera ${cameraId}`);
    }

    console.log(`🎯 Stream encontrada: ${cameraStream.id} para câmera ${cameraId}`);

    // Criar cliente Janus
    const config: JanusConfig = {
      server: 'ws://localhost:8188',
      streamId: cameraStream.id
    };

    return new JanusWebRTCClient(config);

  } catch (error) {
    console.error('❌ Erro ao criar cliente Janus:', error);
    return null;
  }
}