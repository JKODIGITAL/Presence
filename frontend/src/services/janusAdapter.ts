/**
 * Janus WebRTC Adapter
 * Adapta o frontend existente para usar Janus Gateway
 */

import { Janus } from './janus.js'; // Biblioteca Janus.js

export interface JanusStreamInfo {
  id: number;
  camera_id: string;
  name: string;
  description: string;
}

export class JanusAdapter {
  private janus: any = null;
  private pluginHandle: any = null;
  private opaqueId: string;
  private server: string;
  private streamId: number;
  private onStreamCallback: ((stream: MediaStream) => void) | null = null;
  private onErrorCallback: ((error: string) => void) | null = null;

  constructor(server: string = 'ws://localhost:8188') {
    this.server = server;
    this.opaqueId = 'streamingtest-' + Janus.randomString(12);
  }

  /**
   * Conecta ao Janus e inicia stream
   */
  async connect(streamId: number): Promise<void> {
    this.streamId = streamId;

    return new Promise((resolve, reject) => {
      // Inicializar Janus
      Janus.init({
        debug: 'all',
        callback: () => {
          // Criar sessão
          this.janus = new Janus({
            server: this.server,
            success: () => {
              // Attach ao plugin streaming
              this.attachToStreamingPlugin(resolve, reject);
            },
            error: (error: any) => {
              console.error('❌ Erro ao criar sessão Janus:', error);
              reject(error);
            },
            destroyed: () => {
              console.log('🔌 Sessão Janus destruída');
            }
          });
        }
      });
    });
  }

  /**
   * Attach ao plugin streaming do Janus
   */
  private attachToStreamingPlugin(resolve: Function, reject: Function) {
    this.janus.attach({
      plugin: 'janus.plugin.streaming',
      opaqueId: this.opaqueId,
      success: (pluginHandle: any) => {
        console.log('✅ Plugin Streaming attached');
        this.pluginHandle = pluginHandle;
        
        // Iniciar visualização da stream
        this.watchStream();
        resolve();
      },
      error: (error: any) => {
        console.error('❌ Erro ao attach plugin:', error);
        reject(error);
      },
      onmessage: (msg: any, jsep: any) => {
        console.log('📨 Mensagem do Janus:', msg);
        
        if (msg.result && msg.result.status) {
          console.log('📊 Status:', msg.result.status);
        }
        
        if (jsep) {
          console.log('📝 SDP recebido:', jsep);
          this.handleRemoteJsep(jsep);
        }
      },
      onremotestream: (stream: MediaStream) => {
        console.log('🎥 Stream remoto recebido!');
        if (this.onStreamCallback) {
          this.onStreamCallback(stream);
        }
      },
      onerror: (error: any) => {
        console.error('❌ Erro no plugin:', error);
        if (this.onErrorCallback) {
          this.onErrorCallback(error);
        }
      }
    });
  }

  /**
   * Inicia visualização da stream
   */
  private watchStream() {
    const body = { 
      request: 'watch', 
      id: this.streamId 
    };
    
    this.pluginHandle.send({
      message: body,
      success: () => {
        console.log(`✅ Solicitação watch enviada para stream ${this.streamId}`);
      },
      error: (error: any) => {
        console.error('❌ Erro ao enviar watch:', error);
      }
    });
  }

  /**
   * Processa SDP remoto do Janus
   */
  private handleRemoteJsep(jsep: any) {
    this.pluginHandle.createAnswer({
      jsep: jsep,
      media: { 
        audioSend: false, 
        videoSend: false,
        data: false 
      },
      success: (jsep: any) => {
        console.log('📤 Answer criado:', jsep);
        const body = { request: 'start' };
        this.pluginHandle.send({
          message: body,
          jsep: jsep
        });
      },
      error: (error: any) => {
        console.error('❌ Erro ao criar answer:', error);
      }
    });
  }

  /**
   * Define callback para quando stream estiver disponível
   */
  onStream(callback: (stream: MediaStream) => void) {
    this.onStreamCallback = callback;
  }

  /**
   * Define callback para erros
   */
  onError(callback: (error: string) => void) {
    this.onErrorCallback = callback;
  }

  /**
   * Desconecta do Janus
   */
  disconnect() {
    if (this.pluginHandle) {
      this.pluginHandle.send({ message: { request: 'stop' } });
      this.pluginHandle.detach();
    }
    
    if (this.janus) {
      this.janus.destroy();
    }
  }

  /**
   * Método helper para converter sistema antigo para Janus
   */
  static async convertWebSocketMessage(message: any): Promise<any> {
    // Se receber redirect para Janus
    if (message.type === 'janus_redirect') {
      return {
        useJanus: true,
        server: message.janus_ws,
        streamId: message.stream_id
      };
    }
    
    // Outros tipos de mensagem permanecem iguais
    return message;
  }
}

/**
 * Factory para criar adapter correto baseado na resposta do servidor
 */
export class WebRTCAdapterFactory {
  static async createAdapter(
    cameraId: string, 
    serverUrl: string = 'http://127.0.0.1:17236'
  ): Promise<JanusAdapter | null> {
    
    try {
      // Verificar se servidor usa Janus
      const response = await fetch(`${serverUrl}/health`);
      const health = await response.json();
      
      if (health.mode === 'janus_sfu') {
        console.log('🎯 Servidor usando Janus SFU');
        
        // Obter info da stream
        const streamResponse = await fetch(`${serverUrl}/streams/${cameraId}/start`, {
          method: 'POST'
        });
        
        if (streamResponse.ok) {
          const streamInfo = await streamResponse.json();
          
          // Criar adapter Janus
          const adapter = new JanusAdapter(streamInfo.janus_info.ws_url);
          await adapter.connect(streamInfo.stream_id);
          
          return adapter;
        }
      }
    } catch (error) {
      console.error('❌ Erro ao criar adapter:', error);
    }
    
    return null;
  }
}