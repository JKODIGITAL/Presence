/**
 * CameraManagerClean - Interface limpa para gerenciamento de câmeras
 * Sem detalhes técnicos de IA ou tecnologias
 */

import React, { useState, useEffect } from 'react';
import {
  CameraIcon,
  PlusIcon,
  PencilIcon,
  TrashIcon,
  SignalIcon,
  SignalSlashIcon,
  MapPinIcon,
  ClockIcon,
  CheckCircleIcon,
  XCircleIcon,
  ExclamationTriangleIcon,
  PlayIcon,
  StopIcon
} from '@heroicons/react/24/outline';
import { ApiService } from '../services/api';
import toast from 'react-hot-toast';

interface Camera {
  id: string;
  name: string;
  type: 'ip' | 'usb' | 'video';
  location?: string;
  description?: string;
  status: 'online' | 'offline' | 'error';
  lastSeen?: string;
  recognitionEnabled: boolean;
  recording: boolean;
  recordingPath?: string;
}

const CameraManagerClean: React.FC = () => {
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [editingCamera, setEditingCamera] = useState<Camera | null>(null);
  const [formData, setFormData] = useState({
    name: '',
    type: 'ip' as 'ip' | 'usb' | 'video',
    url: '',
    location: '',
    description: '',
    username: '',
    password: '',
    recordingPath: '',
    enableRecording: false,
    videoFile: null as File | null,
    moveToDataFolder: false
  });

  useEffect(() => {
    fetchCameras();
  }, []);

  const fetchCameras = async () => {
    try {
      console.log('🔄 Carregando câmeras do banco de dados...');
      const response = await ApiService.getCameras();
      console.log('📡 Resposta da API:', response);
      
      const cameraList = response.cameras || [];
      console.log('📋 Lista de câmeras encontradas:', cameraList.length);
      
      const mappedCameras = cameraList.map((cam: any) => {
        console.log('🎥 Mapeando câmera:', cam.name, '- Status:', cam.status);
        return {
          id: cam.id,
          name: cam.name,
          type: cam.type || 'ip',
          location: cam.location,
          description: cam.description,
          status: cam.status === 'active' ? 'online' : cam.status || 'offline',
          lastSeen: cam.last_frame_at || cam.updated_at,
          recognitionEnabled: true, // Default true pois não existe no banco
          recording: false, // Default false pois não existe no banco
          recordingPath: ''
        };
      });
      
      console.log('✅ Câmeras mapeadas:', mappedCameras);
      setCameras(mappedCameras);
    } catch (error) {
      console.error('❌ Erro ao carregar câmeras:', error);
      toast.error('Erro ao carregar câmeras do banco de dados');
    } finally {
      setIsLoading(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    try {
      if (editingCamera) {
        // Preparar dados para atualização
        const updateData: any = {
          name: formData.name,
          location: formData.location,
          description: formData.description
        };
        
        // Só incluir URL se foi fornecida
        if (formData.url.trim()) {
          updateData.url = formData.url;
        }
        
        if (formData.username.trim()) {
          updateData.username = formData.username;
        }
        
        if (formData.password.trim()) {
          updateData.password = formData.password;
        }
        
        await ApiService.updateCamera(editingCamera.id, updateData);
        toast.success('Câmera atualizada com sucesso!');
      } else {
        // Verificar se é vídeo
        if (formData.type === 'video' && formData.videoFile) {
          if (formData.moveToDataFolder) {
            // Fazer upload do arquivo para data/videos
            const uploadFormData = new FormData();
            uploadFormData.append('file', formData.videoFile);
            uploadFormData.append('name', formData.name);
            uploadFormData.append('location', formData.location);
            uploadFormData.append('description', formData.description);
            uploadFormData.append('fps_limit', '30');
            
            await ApiService.uploadVideoCamera(uploadFormData);
            toast.success('Vídeo movido para data/videos e câmera criada!');
          } else {
            // Usar arquivo no local original
            // Nota: Em browsers web, não temos acesso ao caminho completo do arquivo por segurança
            // Vamos fazer upload mesmo assim, mas indicar que é para uso local
            const uploadFormData = new FormData();
            uploadFormData.append('file', formData.videoFile);
            uploadFormData.append('name', formData.name);
            uploadFormData.append('location', formData.location);
            uploadFormData.append('description', formData.description + ' (Mantido no local original)');
            uploadFormData.append('fps_limit', '30');
            
            await ApiService.uploadVideoCamera(uploadFormData);
            toast.success('Vídeo processado! (Arquivo copiado para facilitar acesso)');
          }
        } else {
          // Criar nova câmera com todos os dados
          await ApiService.createCameraSimple({
            name: formData.name,
            url: formData.url,
            type: formData.type,
            location: formData.location,
            description: formData.description,
            username: formData.username,
            password: formData.password
          });
          toast.success('Câmera adicionada com sucesso!');
        }
      }
      
      setShowAddModal(false);
      setEditingCamera(null);
      resetForm();
      fetchCameras();
    } catch (error) {
      console.error('Erro ao salvar câmera:', error);
      toast.error('Erro ao salvar câmera');
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm('Tem certeza que deseja remover esta câmera?')) return;
    
    try {
      await ApiService.deleteCamera(id);
      toast.success('Câmera removida com sucesso!');
      fetchCameras();
    } catch (error) {
      toast.error('Erro ao remover câmera');
    }
  };

  const toggleRecognition = async (camera: Camera) => {
    try {
      await ApiService.updateCamera(camera.id, {
        is_enabled: !camera.recognitionEnabled
      });
      
      setCameras(prev => prev.map(cam => 
        cam.id === camera.id 
          ? { ...cam, recognitionEnabled: !cam.recognitionEnabled }
          : cam
      ));
      
      toast.success(
        `Reconhecimento ${!camera.recognitionEnabled ? 'ativado' : 'desativado'} para ${camera.name}`
      );
    } catch (error) {
      console.error('Erro ao alterar configuração:', error);
      toast.error('Erro ao alterar configuração');
    }
  };

  const toggleRecording = async (camera: Camera) => {
    try {
      if (!camera.recording && !camera.recordingPath) {
        // Se não tem pasta configurada, pedir para o usuário
        const path = prompt('Digite o caminho da pasta onde salvar as gravações:', 'C:\\Recordings\\' + camera.name);
        if (!path) return;
        
        // Atualizar câmera com pasta de gravação
        await ApiService.updateCamera(camera.id, {
          recordingPath: path,
          recording: true
        });
        
        setCameras(prev => prev.map(cam => 
          cam.id === camera.id 
            ? { ...cam, recording: true, recordingPath: path }
            : cam
        ));
        
        toast.success(`Gravação contínua iniciada para ${camera.name}`);
      } else {
        // Toggle da gravação
        await ApiService.updateCamera(camera.id, {
          recording: !camera.recording
        });
        
        setCameras(prev => prev.map(cam => 
          cam.id === camera.id 
            ? { ...cam, recording: !cam.recording }
            : cam
        ));
        
        toast.success(
          `Gravação contínua ${!camera.recording ? 'iniciada' : 'parada'} para ${camera.name}`
        );
      }
    } catch (error) {
      console.error('Erro ao alterar gravação:', error);
      toast.error('Erro ao alterar configuração de gravação');
    }
  };

  const resetForm = () => {
    setFormData({
      name: '',
      type: 'ip',
      url: '',
      location: '',
      description: '',
      username: '',
      password: '',
      recordingPath: '',
      enableRecording: false,
      videoFile: null,
      moveToDataFolder: false
    });
  };

  const openEditModal = (camera: Camera) => {
    setEditingCamera(camera);
    setFormData({
      name: camera.name,
      type: camera.type,
      url: '', // Não mostrar URL por segurança
      location: camera.location || '',
      description: camera.description || '',
      username: '',
      password: '',
      recordingPath: '',
      enableRecording: camera.recording || false,
      videoFile: null,
      moveToDataFolder: false
    });
    setShowAddModal(true);
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'online':
        return <SignalIcon className="w-5 h-5 text-success" />;
      case 'offline':
        return <SignalSlashIcon className="w-5 h-5 text-gray-400" />;
      case 'error':
        return <ExclamationTriangleIcon className="w-5 h-5 text-error" />;
      default:
        return <SignalSlashIcon className="w-5 h-5 text-gray-400" />;
    }
  };

  const getStatusText = (status: string) => {
    switch (status) {
      case 'online':
        return 'Conectada';
      case 'offline':
        return 'Desconectada';
      case 'error':
        return 'Erro';
      default:
        return 'Desconhecida';
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-4 border-primary border-t-transparent"></div>
      </div>
    );
  }

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold mb-1">Câmeras</h1>
          <p className="text-secondary">
            {cameras.filter(c => c.status === 'online').length} de {cameras.length} câmeras ativas
          </p>
        </div>
        
        <button
          onClick={() => setShowAddModal(true)}
          className="btn btn-primary"
        >
          <PlusIcon className="w-5 h-5 mr-2" />
          Adicionar Câmera
        </button>
      </div>

      {/* Cameras Grid */}
      {cameras.length === 0 ? (
        <div className="text-center py-12">
          <CameraIcon className="w-16 h-16 text-gray-400 mx-auto mb-4" />
          <h3 className="text-lg font-medium mb-2">Nenhuma câmera configurada</h3>
          <p className="text-secondary mb-4">Adicione câmeras para começar o monitoramento</p>
          <button
            onClick={() => setShowAddModal(true)}
            className="btn btn-primary"
          >
            <PlusIcon className="w-5 h-5 mr-2" />
            Adicionar Primeira Câmera
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {cameras.map((camera) => (
            <div key={camera.id} className="card hover:shadow-lg transition-shadow">
              {/* Camera Header */}
              <div className="flex items-start justify-between mb-4">
                <div className="flex items-center gap-3">
                  <div className="p-3 bg-surface rounded-lg">
                    <CameraIcon className="w-6 h-6 text-primary" />
                  </div>
                  <div>
                    <h3 className="font-semibold">{camera.name}</h3>
                    <div className="flex items-center gap-2 mt-1">
                      {getStatusIcon(camera.status)}
                      <span className={`text-sm ${
                        camera.status === 'online' ? 'text-success' : 
                        camera.status === 'error' ? 'text-error' : 
                        'text-secondary'
                      }`}>
                        {getStatusText(camera.status)}
                      </span>
                    </div>
                  </div>
                </div>
                
                <span className={`badge ${
                  camera.type === 'ip' ? 'badge-primary' : 
                  camera.type === 'video' ? 'badge-warning' : 
                  'badge-secondary'
                }`}>
                  {camera.type === 'ip' ? 'IP' : camera.type === 'video' ? 'MP4' : 'USB'}
                </span>
              </div>

              {/* Camera Info */}
              <div className="space-y-2 mb-4">
                {camera.location && (
                  <div className="flex items-center gap-2 text-sm text-secondary">
                    <MapPinIcon className="w-4 h-4" />
                    <span>{camera.location}</span>
                  </div>
                )}
                
                {camera.lastSeen && (
                  <div className="flex items-center gap-2 text-sm text-secondary">
                    <ClockIcon className="w-4 h-4" />
                    <span>Última atividade: {new Date(camera.lastSeen).toLocaleString()}</span>
                  </div>
                )}
              </div>

              {/* Features */}
              <div className="flex items-center gap-4 mb-4">
                <button
                  onClick={() => toggleRecognition(camera)}
                  className={`flex items-center gap-2 text-sm font-medium transition-colors ${
                    camera.recognitionEnabled ? 'text-primary' : 'text-secondary'
                  }`}
                >
                  {camera.recognitionEnabled ? (
                    <CheckCircleIcon className="w-4 h-4" />
                  ) : (
                    <XCircleIcon className="w-4 h-4" />
                  )}
                  Reconhecimento
                </button>
                
                <button
                  onClick={() => toggleRecording(camera)}
                  className={`flex items-center gap-2 text-sm font-medium transition-colors ${
                    camera.recording ? 'text-error' : 'text-secondary'
                  }`}
                >
                  {camera.recording ? (
                    <StopIcon className="w-4 h-4" />
                  ) : (
                    <PlayIcon className="w-4 h-4" />
                  )}
                  {camera.recording ? 'Gravando' : 'Gravar'}
                </button>
              </div>

              {/* Actions */}
              <div className="flex items-center gap-2 pt-4 border-t border-color">
                <button
                  onClick={() => openEditModal(camera)}
                  className="btn btn-secondary flex-1"
                >
                  <PencilIcon className="w-4 h-4 mr-1" />
                  Editar
                </button>
                
                <button
                  onClick={() => handleDelete(camera.id)}
                  className="btn btn-ghost text-error hover:bg-error/10"
                >
                  <TrashIcon className="w-4 h-4" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Add/Edit Modal */}
      {showAddModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="modal-bg rounded-xl shadow-xl max-w-md w-full p-6">
            <h2 className="text-xl font-bold mb-6">
              {editingCamera ? 'Editar Câmera' : 'Adicionar Câmera'}
            </h2>
            
            <form onSubmit={handleSubmit} className="space-y-4 max-h-[70vh] overflow-y-auto">
              {/* Informações Básicas */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium mb-2">
                    Nome da Câmera *
                  </label>
                  <input
                    type="text"
                    value={formData.name}
                    onChange={(e) => setFormData({...formData, name: e.target.value})}
                    className="input"
                    placeholder="Ex: Entrada Principal"
                    required
                  />
                </div>
                
                <div>
                  <label className="block text-sm font-medium mb-2">
                    Tipo *
                  </label>
                  <select
                    value={formData.type}
                    onChange={(e) => setFormData({...formData, type: e.target.value as 'ip' | 'usb' | 'video'})}
                    className="input"
                  >
                    <option value="ip">Câmera IP</option>
                    <option value="usb">Câmera USB</option>
                    <option value="video">Vídeo Local (MP4)</option>
                  </select>
                </div>
              </div>
              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium mb-2">
                    Localização
                  </label>
                  <input
                    type="text"
                    value={formData.location}
                    onChange={(e) => setFormData({...formData, location: e.target.value})}
                    className="input"
                    placeholder="Ex: Recepção, Estacionamento"
                  />
                </div>
                
                <div>
                  <label className="block text-sm font-medium mb-2">
                    Descrição
                  </label>
                  <input
                    type="text"
                    value={formData.description}
                    onChange={(e) => setFormData({...formData, description: e.target.value})}
                    className="input"
                    placeholder="Descrição adicional"
                  />
                </div>
              </div>
              
              {/* Configurações de Rede (IP) */}
              {formData.type === 'ip' && (
                <>
                  <div className="border-t pt-4">
                    <h4 className="font-medium mb-3">Configurações de Rede</h4>
                  </div>
                  
                  <div>
                    <label className="block text-sm font-medium mb-2">
                      {editingCamera ? 'Novo Endereço RTSP (opcional)' : 'Endereço RTSP *'}
                    </label>
                    <input
                      type="text"
                      value={formData.url}
                      onChange={(e) => setFormData({...formData, url: e.target.value})}
                      className="input"
                      placeholder="rtsp://usuario:senha@192.168.1.100:554/stream"
                      required={!editingCamera}
                    />
                    <p className="text-xs text-secondary mt-1">
                      {editingCamera ? 'Deixe vazio para manter o endereço atual' : 'Formato RTSP completo com credenciais'}
                    </p>
                  </div>
                  
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium mb-2">
                        Usuário
                      </label>
                      <input
                        type="text"
                        value={formData.username}
                        onChange={(e) => setFormData({...formData, username: e.target.value})}
                        className="input"
                        placeholder="admin"
                      />
                    </div>
                    
                    <div>
                      <label className="block text-sm font-medium mb-2">
                        Senha
                      </label>
                      <input
                        type="password"
                        value={formData.password}
                        onChange={(e) => setFormData({...formData, password: e.target.value})}
                        className="input"
                        placeholder="••••••••"
                      />
                    </div>
                  </div>
                </>
              )}
              
              {/* Configurações de Vídeo */}
              {formData.type === 'video' && !editingCamera && (
                <>
                  <div className="border-t pt-4">
                    <h4 className="font-medium mb-3">Configuração de Vídeo</h4>
                  </div>
                  
                  <div>
                    <label className="block text-sm font-medium mb-2">
                      Arquivo de Vídeo *
                    </label>
                    <input
                      type="file"
                      accept="video/mp4,video/avi,video/mov"
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (file) {
                          setFormData({...formData, videoFile: file});
                        }
                      }}
                      className="input"
                      required
                    />
                    <p className="text-xs text-secondary mt-1">
                      Formatos suportados: MP4, AVI, MOV (máx. 500MB)
                    </p>
                    {formData.videoFile && (
                      <p className="text-sm text-success mt-2">
                        ✓ Arquivo selecionado: {formData.videoFile.name}
                      </p>
                    )}
                  </div>
                  
                  <div className="mt-4">
                    <label className="flex items-center gap-3">
                      <input
                        type="checkbox"
                        checked={formData.moveToDataFolder}
                        onChange={(e) => setFormData({...formData, moveToDataFolder: e.target.checked})}
                        className="w-4 h-4 text-primary"
                      />
                      <span className="text-sm font-medium">Mover arquivo para pasta data\videos</span>
                    </label>
                    <p className="text-xs text-secondary mt-1 ml-7">
                      {formData.moveToDataFolder 
                        ? 'O arquivo será copiado para a pasta do projeto (data/videos) para facilitar o acesso'
                        : 'O arquivo será copiado para a pasta do projeto mesmo assim (browsers não permitem acesso direto a arquivos locais)'
                      }
                    </p>
                  </div>
                </>
              )}
              
              {/* Configurações de Gravação */}
              <div className="border-t pt-4">
                <h4 className="font-medium mb-3">Gravação (VMS)</h4>
                
                <div className="space-y-4">
                  <label className="flex items-center gap-3">
                    <input
                      type="checkbox"
                      checked={formData.enableRecording}
                      onChange={(e) => setFormData({...formData, enableRecording: e.target.checked})}
                      className="w-4 h-4 text-primary"
                    />
                    <span className="text-sm font-medium">Habilitar gravação contínua</span>
                  </label>
                  
                  {formData.enableRecording && (
                    <div>
                      <label className="block text-sm font-medium mb-2">
                        Pasta de Gravação *
                      </label>
                      <div className="flex gap-2">
                        <input
                          type="text"
                          value={formData.recordingPath}
                          onChange={(e) => setFormData({...formData, recordingPath: e.target.value})}
                          className="input flex-1"
                          placeholder="C:\\Recordings\\Camera1 ou /recordings/camera1"
                          required={formData.enableRecording}
                        />
                        <button
                          type="button"
                          className="btn btn-secondary px-3"
                          onClick={() => {
                            // Simula seleção de pasta
                            const path = prompt('Digite o caminho da pasta de gravação:');
                            if (path) setFormData({...formData, recordingPath: path});
                          }}
                        >
                          📁
                        </button>
                      </div>
                      <p className="text-xs text-secondary mt-1">
                        Pasta onde os vídeos serão salvos. Certifique-se que há espaço suficiente.
                      </p>
                    </div>
                  )}
                </div>
              </div>
              
              <div className="flex gap-3 pt-4">
                <button
                  type="button"
                  onClick={() => {
                    setShowAddModal(false);
                    setEditingCamera(null);
                    resetForm();
                  }}
                  className="btn btn-secondary flex-1"
                >
                  Cancelar
                </button>
                
                <button
                  type="submit"
                  className="btn btn-primary flex-1"
                >
                  {editingCamera ? 'Salvar' : 'Adicionar'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default CameraManagerClean;