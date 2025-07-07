/**
 * VMSMonitor Multi-Camera - Interface para monitoramento com múltiplas câmeras WebRTC
 * Cada câmera tem sua própria RTCPeerConnection e WebSocket
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
  CameraIcon,
  SignalIcon,
  ClockIcon
} from '@heroicons/react/24/outline';
import { ApiService } from '../services/api';
import { MultiCameraWebRTCManager } from '../services/multiCameraWebRTC';
import toast from 'react-hot-toast';

// Componente de vídeo individual
interface CameraVideoProps {
  cameraId: string;
  cameraName: string;
  stream?: MediaStream;
  status: 'idle' | 'connecting' | 'connected' | 'error';
  onStartStream: () => void;
  onStopStream: () => void;
  onReconnect: () => void;
}

const CameraVideo: React.FC<CameraVideoProps> = ({ 
  cameraId, 
  cameraName, 
  stream, 
  status, 
  onStartStream, 
  onStopStream, 
  onReconnect 
}) => {
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    if (videoRef.current && stream) {
      videoRef.current.srcObject = stream;
      console.log(`✅ Stream atribuído ao vídeo da câmera ${cameraName}`);
    } else if (videoRef.current && !stream) {
      videoRef.current.srcObject = null;
    }
  }, [stream, cameraName]);

  const renderVideoContent = () => {
    if (status === 'connected' && stream) {
      return (
        <video
          ref={videoRef}
          className="w-full h-full object-cover"
          autoPlay
          muted
          playsInline
          controls={false}
          onLoadedData={() => {
            console.log(`✅ Vídeo carregado para câmera ${cameraName}`);
          }}
          onError={(e) => {
            console.error(`❌ Erro no vídeo da câmera ${cameraName}:`, e);
          }}
        />
      );
    }

    if (status === 'connecting') {
      return (
        <div className="w-full h-full flex items-center justify-center bg-gray-900">
          <div className="text-center">
            <div className="animate-spin rounded-full h-8 w-8 border-4 border-blue-500 border-t-transparent mx-auto mb-2"></div>
            <p className="text-blue-400 text-sm">Conectando...</p>
            <p className="text-blue-300 text-xs">{cameraName}</p>
          </div>
        </div>
      );
    }

    if (status === 'error') {
      return (
        <div className="w-full h-full flex items-center justify-center bg-gray-900">
          <div className="text-center">
            <ExclamationTriangleIcon className="w-12 h-12 text-red-500 mx-auto mb-2" />
            <p className="text-red-400 text-sm">Erro na conexão</p>
            <p className="text-red-300 text-xs">{cameraName}</p>
            <button
              onClick={onReconnect}
              className="mt-2 px-3 py-1 bg-red-500 text-white text-xs rounded hover:bg-red-600"
            >
              Reconectar
            </button>
          </div>
        </div>
      );
    }

    // Status idle - botão para iniciar
    return (
      <div className="w-full h-full flex items-center justify-center bg-gray-900">
        <div className="text-center">
          <CameraIcon className="w-16 h-16 text-gray-500 mx-auto mb-4" />
          <p className="text-gray-400 text-sm mb-2">{cameraName}</p>
          <button
            onClick={onStartStream}
            className="flex items-center gap-2 mx-auto px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 transition-colors"
          >
            <PlayIcon className="w-4 h-4" />
            Iniciar WebRTC
          </button>
          <p className="text-gray-600 text-xs mt-2">Conexão direta via webrtcbin</p>
        </div>
      </div>
    );
  };

  return (
    <div className="relative bg-black rounded-lg overflow-hidden">
      {/* Status Badge */}
      <div className="absolute top-3 left-3 z-10">
        <span className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium ${
          status === 'connected' ? 'bg-green-100 text-green-800' : 
          status === 'connecting' ? 'bg-yellow-100 text-yellow-800' : 
          status === 'error' ? 'bg-red-100 text-red-800' :
          'bg-gray-100 text-gray-800'
        }`}>
          <span className={`w-2 h-2 rounded-full mr-1 ${
            status === 'connected' ? 'bg-green-500' : 
            status === 'connecting' ? 'bg-yellow-500' : 
            status === 'error' ? 'bg-red-500' :
            'bg-gray-500'
          }`}></span>
          {status === 'connected' ? 'Ao Vivo' : 
           status === 'connecting' ? 'Conectando' : 
           status === 'error' ? 'Erro' : 'Inativa'}
        </span>
      </div>

      {/* Camera Name */}
      <div className="absolute top-3 right-3 z-10">
        <span className="bg-black/70 text-white px-2 py-1 rounded text-sm font-medium">
          {cameraName}
        </span>
      </div>

      {/* Video Content */}
      <div className="aspect-video">
        {renderVideoContent()}
      </div>

      {/* Controls */}
      {status === 'connected' && (
        <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/80 to-transparent p-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <button
                onClick={onStopStream}
                className="p-2 bg-red-500/20 text-red-400 rounded-md hover:bg-red-500/30 transition-colors"
                title="Parar stream"
              >
                <PauseIcon className="w-4 h-4" />
              </button>
              
              <button
                className="p-2 bg-white/10 text-white/70 rounded-md hover:bg-white/20 transition-colors"
                title="Capturar imagem"
              >
                <PhotoIcon className="w-4 h-4" />
              </button>
            </div>
            
            <div className="flex items-center gap-1 text-white/70 text-xs">
              <SignalIcon className="w-3 h-3" />
              <span>WebRTC</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

interface Camera {
  id: string;
  name: string;
  location?: string;
  status: 'online' | 'offline';
  lastActivity?: string;
  enabled: boolean;
}

interface CameraStreamState {
  status: 'idle' | 'connecting' | 'connected' | 'error';
  stream?: MediaStream;
  lastError?: string;
}

interface ViewLayout {
  id: string;
  name: string;
  icon: any;
  grid: string;
}

const VMSMonitorMultiCamera: React.FC = () => {
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [viewLayout, setViewLayout] = useState<string>('grid-2x2');
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [isMuted, setIsMuted] = useState(true);
  const [showStats, setShowStats] = useState(false);
  const [apiConnected, setApiConnected] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  
  // Estados das câmeras
  const [cameraStreams, setCameraStreams] = useState<Map<string, CameraStreamState>>(new Map());
  
  // Gerenciador WebRTC
  const webrtcManager = useRef<MultiCameraWebRTCManager>(new MultiCameraWebRTCManager());

  const layouts: ViewLayout[] = [
    { id: 'single', name: 'Única', icon: RectangleGroupIcon, grid: 'grid-cols-1' },
    { id: 'grid-2x2', name: '2x2', icon: Squares2X2Icon, grid: 'grid-cols-2' },
    { id: 'grid-3x3', name: '3x3', icon: Squares2X2Icon, grid: 'grid-cols-3' },
  ];

  useEffect(() => {
    fetchCameras();
    
    // Cleanup ao desmontar
    return () => {
      webrtcManager.current.cleanup();
    };
  }, []);

  const fetchCameras = async () => {
    try {
      console.log('🔄 Carregando câmeras da API...');
      
      // Test API connectivity
      const healthCheck = await fetch(`${ApiService.getBaseUrl()}/health`, {
        signal: AbortSignal.timeout(5000)
      });
      
      if (!healthCheck.ok) {
        throw new Error(`API retornou status ${healthCheck.status}`);
      }
      
      setApiConnected(true);
      
      const response = await ApiService.getCameras();
      const cameraList = response.cameras || [];
      
      const mappedCameras = cameraList.map((cam: any) => ({
        id: cam.id,
        name: cam.name || `Câmera ${cam.id}`,
        location: cam.location,
        status: cam.status === 'active' ? 'online' : 'offline',
        lastActivity: cam.last_frame_at || cam.updated_at,
        enabled: cam.enabled !== false
      }));
      
      setCameras(mappedCameras);
      
      // Preparar estados das câmeras
      const newCameraStreams = new Map();
      mappedCameras.forEach((camera: Camera) => {
        if (camera.enabled) {
          newCameraStreams.set(camera.id, { status: 'idle' });
          
          // Adicionar ao gerenciador WebRTC
          webrtcManager.current.addCamera(camera.id, (stream) => {
            console.log(`📺 Stream recebido para câmera ${camera.id}`);
            setCameraStreams(prev => {
              const newMap = new Map(prev);
              newMap.set(camera.id, {
                status: 'connected',
                stream: stream
              });
              return newMap;
            });
          });
        }
      });
      
      setCameraStreams(newCameraStreams);
      
      console.log(`✅ ${mappedCameras.length} câmeras carregadas`);
      
    } catch (error) {
      console.error('❌ Erro ao buscar câmeras:', error);
      setApiConnected(false);
      toast.error(`Erro ao carregar câmeras: ${error}`);
    }
  };

  const startCameraStream = async (cameraId: string) => {
    console.log(`🚀 Iniciando stream para câmera ${cameraId}`);
    
    setCameraStreams(prev => {
      const newMap = new Map(prev);
      newMap.set(cameraId, { status: 'connecting' });
      return newMap;
    });

    try {
      await webrtcManager.current.connectCamera(cameraId);
    } catch (error) {
      console.error(`❌ Erro ao conectar câmera ${cameraId}:`, error);
      setCameraStreams(prev => {
        const newMap = new Map(prev);
        newMap.set(cameraId, { 
          status: 'error', 
          lastError: error.toString() 
        });
        return newMap;
      });
      toast.error(`Erro ao conectar câmera ${cameraId}`);
    }
  };

  const stopCameraStream = (cameraId: string) => {
    console.log(`⏹️ Parando stream para câmera ${cameraId}`);
    
    webrtcManager.current.disconnectCamera(cameraId);
    
    setCameraStreams(prev => {
      const newMap = new Map(prev);
      newMap.set(cameraId, { status: 'idle' });
      return newMap;
    });
    
    toast.success(`Stream da câmera ${cameraId} parada`);
  };

  const reconnectCamera = async (cameraId: string) => {
    console.log(`🔄 Reconectando câmera ${cameraId}`);
    stopCameraStream(cameraId);
    
    // Aguardar um pouco antes de reconectar
    setTimeout(() => {
      startCameraStream(cameraId);
    }, 1000);
  };

  const startAllStreams = async () => {
    console.log('🚀 Iniciando todas as streams...');
    
    const enabledCameras = cameras.filter(cam => cam.enabled);
    
    for (const camera of enabledCameras) {
      setCameraStreams(prev => {
        const newMap = new Map(prev);
        newMap.set(camera.id, { status: 'connecting' });
        return newMap;
      });
    }

    try {
      await webrtcManager.current.connectAllCameras();
      toast.success(`${enabledCameras.length} câmeras conectadas`);
    } catch (error) {
      console.error('❌ Erro ao conectar todas as câmeras:', error);
      toast.error('Erro ao conectar algumas câmeras');
    }
  };

  const stopAllStreams = () => {
    console.log('🛑 Parando todas as streams...');
    
    webrtcManager.current.disconnectAllCameras();
    
    setCameraStreams(prev => {
      const newMap = new Map();
      for (const [cameraId] of prev) {
        newMap.set(cameraId, { status: 'idle' });
      }
      return newMap;
    });
    
    toast.success('Todas as streams paradas');
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

  const getLayoutGrid = () => {
    const layout = layouts.find(l => l.id === viewLayout);
    return layout?.grid || 'grid-cols-2';
  };

  const enabledCameras = cameras.filter(cam => cam.enabled);
  const connectedCount = Array.from(cameraStreams.values()).filter(state => state.status === 'connected').length;

  return (
    <div ref={containerRef} className="h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold mb-1">Central de Monitoramento Multi-Câmera</h1>
          <p className="text-secondary">
            {connectedCount} de {enabledCameras.length} câmeras conectadas via WebRTC
          </p>
        </div>

        {/* Controls */}
        <div className="flex items-center gap-2">
          {/* API Status */}
          <div className="flex items-center gap-2 px-3 py-1 rounded-md bg-surface">
            <div className={`w-2 h-2 rounded-full ${apiConnected ? 'bg-green-500' : 'bg-red-500'}`}></div>
            <span className="text-xs text-secondary">
              {apiConnected ? 'API Online' : 'API Offline'}
            </span>
          </div>

          {/* Start/Stop All */}
          <button
            onClick={startAllStreams}
            className="px-3 py-2 bg-green-500 text-white rounded-md text-sm font-medium hover:bg-green-600 transition-colors"
            title="Iniciar todas as câmeras"
          >
            <PlayIcon className="w-4 h-4 mr-1 inline" />
            Todas
          </button>

          <button
            onClick={stopAllStreams}
            className="px-3 py-2 bg-red-500 text-white rounded-md text-sm font-medium hover:bg-red-600 transition-colors"
            title="Parar todas as câmeras"
          >
            <PauseIcon className="w-4 h-4 mr-1 inline" />
            Parar
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
        {enabledCameras.length === 0 ? (
          <div className="h-full flex items-center justify-center">
            <div className="text-center">
              <VideoCameraIcon className="w-16 h-16 text-gray-400 mx-auto mb-4" />
              <h3 className="text-lg font-medium mb-2">Nenhuma câmera habilitada</h3>
              <p className="text-secondary mb-4">Configure câmeras na seção de gerenciamento</p>
              <button className="btn btn-primary" onClick={fetchCameras}>
                Recarregar Câmeras
              </button>
            </div>
          </div>
        ) : (
          <div className={`grid ${getLayoutGrid()} gap-4 h-full`}>
            {enabledCameras.map((camera) => {
              const streamState = cameraStreams.get(camera.id) || { status: 'idle' };
              
              return (
                <CameraVideo
                  key={camera.id}
                  cameraId={camera.id}
                  cameraName={camera.name}
                  stream={streamState.stream}
                  status={streamState.status}
                  onStartStream={() => startCameraStream(camera.id)}
                  onStopStream={() => stopCameraStream(camera.id)}
                  onReconnect={() => reconnectCamera(camera.id)}
                />
              );
            })}
          </div>
        )}
      </div>

      {/* Stats Overlay */}
      {showStats && (
        <div className="absolute bottom-6 left-6 bg-surface-elevated rounded-lg shadow-lg p-4 max-w-xs">
          <h4 className="font-semibold mb-3">Estatísticas WebRTC</h4>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-secondary">Câmeras:</span>
              <span className="font-medium">{enabledCameras.length}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-secondary">Conectadas:</span>
              <span className="font-medium text-success">{connectedCount}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-secondary">Modo:</span>
              <span className="font-medium">WebRTC Direto</span>
            </div>
            <div className="flex justify-between">
              <span className="text-secondary">Protocolo:</span>
              <span className="font-medium">webrtcbin</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default VMSMonitorMultiCamera;